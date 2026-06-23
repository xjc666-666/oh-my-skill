"""
Download STM32 Standard Peripheral Library and CMSIS from ST's GitHub
to create project templates for the stm32-keil skill.

Sources:
  - ARM CMSIS Core:   https://github.com/ARM-software/CMSIS_5
  - ST CMSIS Device:  https://github.com/STMicroelectronics/cmsis_device_f4 (F4)
                      https://github.com/STMicroelectronics/cmsis_device_f1 (F1)
  - ST SPL:           https://github.com/STMicroelectronics/stm32f4xx_stdperiph_driver (F4)
                      https://github.com/STMicroelectronics/stm32f10x_stdperiph_driver (F1)
"""
import os
import sys
import shutil
import zipfile
import tempfile
import urllib.request
import urllib.error
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, List, Set

# Polyfill ET.indent for Python < 3.9
if not hasattr(ET, 'indent'):
    def _indent(elem, level=0):
        i = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            for idx, child in enumerate(elem):
                _indent(child, level + 1)
                if idx == len(elem) - 1:
                    if not child.tail or not child.tail.strip():
                        child.tail = i
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    ET.indent = _indent

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import ensure_dir, load_chip_db
from skeleton_manager import extract_skeleton

# ─── download configuration ───────────────────────────────────────────

# For each family, define what to download from ST's GitHub
FAMILY_DOWNLOADS = {
    "F407": {
        "cmsis_device": {
            "urls": [
                "https://github.com/STMicroelectronics/cmsis_device_f4/archive/refs/tags/v2.6.8.zip",
                "https://github.com/STMicroelectronics/cmsis_device_f4/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["cmsis_device_f4-2.6.8", "cmsis_device_f4-master"],
            "description": "STM32F4 CMSIS Device",
            "files": {
                # source_in_zip → dest_in_skeleton
                "Include/": "STM32/CMSIS/Device/ST/STM32F4xx/Include/",
                "Source/Templates/arm/startup_stm32f40_41xxx.s": "STM32/CMSIS/Device/ST/STM32F4xx/Source/Templates/arm/startup_stm32f40_41xxx.s",
                "Source/Templates/arm/startup_stm32f401xx.s": "STM32/CMSIS/Device/ST/STM32F4xx/Source/Templates/arm/startup_stm32f401xx.s",
                "Source/Templates/arm/startup_stm32f427_437xx.s": "STM32/CMSIS/Device/ST/STM32F4xx/Source/Templates/arm/startup_stm32f427_437xx.s",
                "Source/Templates/arm/startup_stm32f429_439xx.s": "STM32/CMSIS/Device/ST/STM32F4xx/Source/Templates/arm/startup_stm32f429_439xx.s",
                "Source/Templates/arm/startup_stm32f446xx.s": "STM32/CMSIS/Device/ST/STM32F4xx/Source/Templates/arm/startup_stm32f446xx.s",
                "Source/Templates/system_stm32f4xx.c": "STM32/CMSIS/Device/ST/STM32F4xx/Source/Templates/system_stm32f4xx.c",
            },
        },
        "spl": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32f4xx_stdperiph_driver/archive/refs/tags/v1.9.0.zip",
                "https://github.com/STMicroelectronics/stm32f4xx_stdperiph_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32f4xx_stdperiph_driver-1.9.0", "stm32f4xx_stdperiph_driver-master"],
            "description": "STM32F4 Standard Peripheral Library",
            "files": {
                "inc/": "STM32/STM32F4xx_StdPeriph_Driver/inc/",
                "src/": "STM32/STM32F4xx_StdPeriph_Driver/src/",
            },
        },
        "hal": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32f4xx_hal_driver/archive/refs/tags/v1.8.3.zip",
                "https://github.com/STMicroelectronics/stm32f4xx_hal_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32f4xx_hal_driver-1.8.3", "stm32f4xx_hal_driver-master"],
            "description": "STM32F4 HAL Driver",
            "files": {
                "Inc/": "STM32/STM32F4xx_HAL_Driver/Inc/",
                "Src/": "STM32/STM32F4xx_HAL_Driver/Src/",
            },
        },
        "cmsis_device_dir": "STM32F4xx",
        "spl_dir_name": "STM32F4xx_StdPeriph_Driver",
        "hal_dir_name": "STM32F4xx_HAL_Driver",
        "cmsis_core_needed": ["core_cm4.h", "core_cmFunc.h", "core_cmInstr.h", "core_cmSimd.h"],
    },
    "F103": {
        "cmsis_device": {
            "urls": [
                "https://github.com/STMicroelectronics/cmsis_device_f1/archive/refs/tags/v4.3.3.zip",
                "https://github.com/STMicroelectronics/cmsis_device_f1/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["cmsis_device_f1-4.3.3", "cmsis_device_f1-master"],
            "description": "STM32F1 CMSIS Device",
            "files": {
                "Include/": "STM32/CMSIS/Device/ST/STM32F10x/Include/",
                "Source/Templates/arm/startup_stm32f10x_md.s": "STM32/CMSIS/Device/ST/STM32F10x/Source/Templates/arm/startup_stm32f10x_md.s",
                "Source/Templates/arm/startup_stm32f10x_hd.s": "STM32/CMSIS/Device/ST/STM32F10x/Source/Templates/arm/startup_stm32f10x_hd.s",
                "Source/Templates/arm/startup_stm32f10x_ld.s": "STM32/CMSIS/Device/ST/STM32F10x/Source/Templates/arm/startup_stm32f10x_ld.s",
                "Source/Templates/arm/startup_stm32f10x_xl.s": "STM32/CMSIS/Device/ST/STM32F10x/Source/Templates/arm/startup_stm32f10x_xl.s",
                "Source/Templates/arm/startup_stm32f10x_cl.s": "STM32/CMSIS/Device/ST/STM32F10x/Source/Templates/arm/startup_stm32f10x_cl.s",
                "Source/Templates/system_stm32f10x.c": "STM32/CMSIS/Device/ST/STM32F10x/Source/Templates/system_stm32f10x.c",
            },
        },
        "spl": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32f10x_stdperiph_driver/archive/refs/tags/v3.6.0.zip",
                "https://github.com/STMicroelectronics/stm32f10x_stdperiph_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32f10x_stdperiph_driver-3.6.0", "stm32f10x_stdperiph_driver-master"],
            "description": "STM32F10x Standard Peripheral Library",
            "files": {
                "inc/": "STM32/STM32F10x_StdPeriph_Driver/inc/",
                "src/": "STM32/STM32F10x_StdPeriph_Driver/src/",
            },
        },
        "hal": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32f1xx_hal_driver/archive/refs/tags/v1.1.9.zip",
                "https://github.com/STMicroelectronics/stm32f1xx_hal_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32f1xx_hal_driver-1.1.9", "stm32f1xx_hal_driver-master"],
            "description": "STM32F1 HAL Driver",
            "files": {
                "Inc/": "STM32/STM32F1xx_HAL_Driver/Inc/",
                "Src/": "STM32/STM32F1xx_HAL_Driver/Src/",
            },
        },
        "cmsis_device_dir": "STM32F10x",
        "spl_dir_name": "STM32F10x_StdPeriph_Driver",
        "hal_dir_name": "STM32F1xx_HAL_Driver",
        "cmsis_core_needed": ["core_cm3.h", "core_cmFunc.h", "core_cmInstr.h"],
    },
    "G4": {
        "cmsis_device": {
            "urls": [
                "https://github.com/STMicroelectronics/cmsis_device_g4/archive/refs/tags/v1.3.0.zip",
                "https://github.com/STMicroelectronics/cmsis_device_g4/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["cmsis_device_g4-1.3.0", "cmsis_device_g4-master"],
            "description": "STM32G4 CMSIS Device",
            "files": {
                "Include/": "STM32/CMSIS/Device/ST/STM32G4xx/Include/",
                "Source/Templates/arm/startup_stm32g431xx.s": "STM32/CMSIS/Device/ST/STM32G4xx/Source/Templates/arm/startup_stm32g431xx.s",
                "Source/Templates/arm/startup_stm32g474xx.s": "STM32/CMSIS/Device/ST/STM32G4xx/Source/Templates/arm/startup_stm32g474xx.s",
                "Source/Templates/arm/startup_stm32g4a1xx.s": "STM32/CMSIS/Device/ST/STM32G4xx/Source/Templates/arm/startup_stm32g4a1xx.s",
                "Source/Templates/system_stm32g4xx.c": "STM32/CMSIS/Device/ST/STM32G4xx/Source/Templates/system_stm32g4xx.c",
            },
        },
        "hal": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32g4xx_hal_driver/archive/refs/tags/v1.6.0.zip",
                "https://github.com/STMicroelectronics/stm32g4xx_hal_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32g4xx_hal_driver-1.6.0", "stm32g4xx_hal_driver-master"],
            "description": "STM32G4 HAL Driver",
            "files": {
                "Inc/": "STM32/STM32G4xx_HAL_Driver/Inc/",
                "Src/": "STM32/STM32G4xx_HAL_Driver/Src/",
            },
        },
        "hal_dir_name": "STM32G4xx_HAL_Driver",
        "cmsis_device_dir": "STM32G4xx",
        "cmsis_core_needed": ["core_cm4.h", "core_cmFunc.h", "core_cmInstr.h", "core_cmSimd.h"],
        "hal_only": True,
    },
    "L4": {
        "cmsis_device": {
            "urls": [
                "https://github.com/STMicroelectronics/cmsis_device_l4/archive/refs/tags/v2.6.5.zip",
                "https://github.com/STMicroelectronics/cmsis_device_l4/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["cmsis_device_l4-2.6.5", "cmsis_device_l4-master"],
            "description": "STM32L4 CMSIS Device",
            "files": {
                "Include/": "STM32/CMSIS/Device/ST/STM32L4xx/Include/",
                "Source/Templates/arm/startup_stm32l476xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l476xx.s",
                "Source/Templates/arm/startup_stm32l431xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l431xx.s",
                "Source/Templates/arm/startup_stm32l432xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l432xx.s",
                "Source/Templates/arm/startup_stm32l433xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l433xx.s",
                "Source/Templates/arm/startup_stm32l452xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l452xx.s",
                "Source/Templates/arm/startup_stm32l496xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l496xx.s",
                "Source/Templates/arm/startup_stm32l4r5xx.s": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/arm/startup_stm32l4r5xx.s",
                "Source/Templates/system_stm32l4xx.c": "STM32/CMSIS/Device/ST/STM32L4xx/Source/Templates/system_stm32l4xx.c",
            },
        },
        "hal": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32l4xx_hal_driver/archive/refs/tags/v1.14.0.zip",
                "https://github.com/STMicroelectronics/stm32l4xx_hal_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32l4xx_hal_driver-1.14.0", "stm32l4xx_hal_driver-master"],
            "description": "STM32L4 HAL Driver",
            "files": {
                "Inc/": "STM32/STM32L4xx_HAL_Driver/Inc/",
                "Src/": "STM32/STM32L4xx_HAL_Driver/Src/",
            },
        },
        "hal_dir_name": "STM32L4xx_HAL_Driver",
        "cmsis_device_dir": "STM32L4xx",
        "cmsis_core_needed": ["core_cm4.h", "core_cmFunc.h", "core_cmInstr.h", "core_cmSimd.h"],
        "hal_only": True,
    },
    "H7": {
        "cmsis_device": {
            "urls": [
                "https://github.com/STMicroelectronics/cmsis_device_h7/archive/refs/tags/v1.11.3.zip",
                "https://github.com/STMicroelectronics/cmsis_device_h7/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["cmsis_device_h7-1.11.3", "cmsis_device_h7-master"],
            "description": "STM32H7 CMSIS Device",
            "files": {
                "Include/": "STM32/CMSIS/Device/ST/STM32H7xx/Include/",
                "Source/Templates/arm/startup_stm32h743xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h743xx.s",
                "Source/Templates/arm/startup_stm32h745xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h745xx.s",
                "Source/Templates/arm/startup_stm32h747xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h747xx.s",
                "Source/Templates/arm/startup_stm32h750xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h750xx.s",
                "Source/Templates/arm/startup_stm32h753xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h753xx.s",
                "Source/Templates/arm/startup_stm32h755xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h755xx.s",
                "Source/Templates/arm/startup_stm32h757xx.s": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/arm/startup_stm32h757xx.s",
                "Source/Templates/system_stm32h7xx.c": "STM32/CMSIS/Device/ST/STM32H7xx/Source/Templates/system_stm32h7xx.c",
            },
        },
        "hal": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32h7xx_hal_driver/archive/refs/tags/v1.12.0.zip",
                "https://github.com/STMicroelectronics/stm32h7xx_hal_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32h7xx_hal_driver-1.12.0", "stm32h7xx_hal_driver-master"],
            "description": "STM32H7 HAL Driver",
            "files": {
                "Inc/": "STM32/STM32H7xx_HAL_Driver/Inc/",
                "Src/": "STM32/STM32H7xx_HAL_Driver/Src/",
            },
        },
        "hal_dir_name": "STM32H7xx_HAL_Driver",
        "cmsis_device_dir": "STM32H7xx",
        "cmsis_core_needed": ["core_cm7.h", "core_cmFunc.h", "core_cmInstr.h", "core_cmSimd.h"],
        "hal_only": True,
    },
    "C0": {
        "cmsis_device": {
            "urls": [
                "https://github.com/STMicroelectronics/cmsis_device_c0/archive/refs/tags/v1.3.0.zip",
                "https://github.com/STMicroelectronics/cmsis_device_c0/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["cmsis_device_c0-1.3.0", "cmsis_device_c0-master"],
            "description": "STM32C0 CMSIS Device",
            "files": {
                "Include/": "STM32/CMSIS/Device/ST/STM32C0xx/Include/",
                "Source/Templates/arm/startup_stm32c011xx.s": "STM32/CMSIS/Device/ST/STM32C0xx/Source/Templates/arm/startup_stm32c011xx.s",
                "Source/Templates/arm/startup_stm32c031xx.s": "STM32/CMSIS/Device/ST/STM32C0xx/Source/Templates/arm/startup_stm32c031xx.s",
                "Source/Templates/system_stm32c0xx.c": "STM32/CMSIS/Device/ST/STM32C0xx/Source/Templates/system_stm32c0xx.c",
            },
        },
        "hal": {
            "urls": [
                "https://github.com/STMicroelectronics/stm32c0xx_hal_driver/archive/refs/tags/v1.3.0.zip",
                "https://github.com/STMicroelectronics/stm32c0xx_hal_driver/archive/refs/heads/master.zip",
            ],
            "strip_prefixes": ["stm32c0xx_hal_driver-1.3.0", "stm32c0xx_hal_driver-master"],
            "description": "STM32C0 HAL Driver",
            "files": {
                "Inc/": "STM32/STM32C0xx_HAL_Driver/Inc/",
                "Src/": "STM32/STM32C0xx_HAL_Driver/Src/",
            },
        },
        "hal_dir_name": "STM32C0xx_HAL_Driver",
        "cmsis_device_dir": "STM32C0xx",
        "cmsis_core_needed": ["core_cm0plus.h", "core_cmFunc.h", "core_cmInstr.h"],
        "hal_only": True,
    },
}

CMSIS_CORE_URLS = [
    "https://github.com/ARM-software/CMSIS_5/archive/refs/tags/v5.9.0.zip",
    "https://github.com/ARM-software/CMSIS_5/archive/refs/heads/develop.zip",
]
CMSIS_CORE_PREFIXES = ["CMSIS_5-5.9.0", "CMSIS_5-develop"]
CMSIS_CORE_SOURCE_DIR = "CMSIS/Core/Include"

# Files to always copy from CMSIS Core
CMSIS_CORE_FILES = [
    "cmsis_armcc.h", "cmsis_armclang.h", "cmsis_compiler.h",
    "cmsis_gcc.h", "cmsis_version.h",
    "core_cm0.h", "core_cm0plus.h", "core_cm3.h", "core_cm4.h",
    "core_cm7.h", "core_cm23.h", "core_cm33.h",
    "core_cmFunc.h", "core_cmInstr.h", "core_cmSimd.h",
    "core_sc000.h", "core_sc300.h",
    "mpu_armv7.h", "mpu_armv8.h",
    "cachel1_armv7.h", "tz_context.h",
]


# ─── main entry point ─────────────────────────────────────────────────

def fetch_template(family: str, skill_dir: Optional[str] = None,
                   library: str = "SPL") -> Dict:
    """
    Download and assemble a complete project template for a chip family.

    Args:
        family: "F103" or "F407"
        skill_dir: Path to skill directory (auto-detected if None)
        library: "SPL" or "HAL"

    Returns:
        {"success": bool, "skeleton_path": str, "error": str or None}
    """
    if skill_dir is None:
        skill_dir = str(Path(__file__).resolve().parent.parent)

    if family not in FAMILY_DOWNLOADS:
        return {"success": False, "skeleton_path": "",
                "error": f"Unknown family: {family}"}

    dl = FAMILY_DOWNLOADS[family]
    use_hal = (library.upper() == "HAL") or dl.get("hal_only", False)
    lib_key = "hal" if use_hal else "spl"
    if lib_key not in dl:
        return {"success": False, "skeleton_path": "",
                "error": f"{library} not available for family {family}"}

    family_lower = family.lower()
    skeleton_key = f"hal_{family_lower}" if use_hal else family_lower
    skeleton_dir = os.path.join(skill_dir, "skeleton", skeleton_key)

    work_dir = tempfile.mkdtemp(prefix=f"stm32_{skeleton_key}_")
    try:
        print(f"Downloading {library} template for {family}...")

        # 1. CMSIS Core
        cmsis_core_dst = os.path.join(skeleton_dir, "STM32", "CMSIS", "Include")
        cmsis_core_ok = _download_and_extract_cmsis_core(work_dir, cmsis_core_dst)
        if not cmsis_core_ok:
            if not _copy_cmsis_core_from_existing(skill_dir, cmsis_core_dst):
                return {"success": False, "skeleton_path": skeleton_dir,
                        "error": "Failed to download CMSIS Core. Check internet connection."}

        # 2. CMSIS Device (also copy missing startup files from SPL skeleton if available)
        if not _download_and_extract("cmsis_device", dl, work_dir, skeleton_dir):
            return {"success": False, "skeleton_path": skeleton_dir,
                    "error": f"Failed to download {dl['cmsis_device']['description']}."}
        _copy_missing_startup_files(skeleton_dir, family, skill_dir)

        # 3. SPL or HAL
        if not _download_and_extract(lib_key, dl, work_dir, skeleton_dir):
            return {"success": False, "skeleton_path": skeleton_dir,
                    "error": f"Failed to download {dl[lib_key]['description']}."}

        # 4. Project files
        try:
            _generate_uvprojx(skeleton_dir, family, skill_dir, library=library)
            _generate_uvoptx(skeleton_dir, family, library=library)
        except Exception as e:
            return {"success": False, "skeleton_path": skeleton_dir,
                    "error": f"Failed to generate project files: {e}"}

        # 5. Source files (only for SPL — HAL users typically generate via CubeMX)
        if not use_hal:
            _generate_drive_files(skeleton_dir, family)
            _generate_user_files(skeleton_dir, family)
        else:
            _generate_hal_user_files(skeleton_dir, family)

        # 6. Skeleton trim (SPL only — HAL keeps all files for flexibility)
        if not use_hal:
            print("Extracting minimal skeleton...")
            extract_skeleton(skeleton_dir, skeleton_dir, family)

        print(f"Template for {family}/{library} created at: {skeleton_dir}")
        return {"success": True, "skeleton_path": skeleton_dir, "error": None}

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ─── download helpers ─────────────────────────────────────────────────

# GitHub mirror proxies for regions with restricted access
_MIRROR_PROXIES = [
    "https://gh-proxy.com/",
]


def _try_mirror_urls(original_url: str) -> List[str]:
    """Build a list of URLs to try: original first, then mirror proxies."""
    urls = [original_url]
    for mirror in _MIRROR_PROXIES:
        urls.append(mirror + original_url)
    return urls


def _download_zip(url: str, dest: str, try_mirrors: bool = True) -> bool:
    """Download a ZIP file from URL to dest. Returns True on success.

    When try_mirrors is True, mirror proxies are tried as fallback
    after the original URL fails.
    """
    urls = _try_mirror_urls(url) if try_mirrors else [url]

    for i, u in enumerate(urls):
        label = "mirror" if i > 0 else "direct"
        try:
            print(f"  Downloading [{label}]: {u[:80]}...")
            req = urllib.request.Request(u, headers={
                "User-Agent": "stm32-keil-skill/1.0",
                "Accept": "application/zip, application/octet-stream",
            })
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
            if os.path.getsize(dest) > 1024:
                return True
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            print(f"  Download error [{label}]: {e}")
            continue

    return False


def _extract_zip(zip_path: str, extract_dir: str, file_map: Dict[str, str],
                 strip_prefix: str, base_in_zip: str = "") -> int:
    """
    Extract specific files/dirs from ZIP according to file_map.

    file_map: {"source_relative_path_in_zip": "dest_relative_to_extract_dir"}
    Supports trailing '/' to copy directory contents.

    If strip_prefix doesn't match, auto-detects the first top-level directory
    in the ZIP as the prefix (handles master→main renames, etc.).
    """
    copied = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Auto-detect actual prefix if the given one doesn't match
            actual_prefix = _auto_detect_prefix(zf, strip_prefix)

            for zip_info in zf.infolist():
                name = zip_info.filename
                if actual_prefix:
                    if not name.startswith(actual_prefix + "/") and name != actual_prefix + "/":
                        continue
                    rel = name[len(actual_prefix) + 1:] if name != actual_prefix + "/" else ""
                else:
                    rel = name

                if base_in_zip:
                    if not rel.startswith(base_in_zip):
                        continue
                    rel = rel[len(base_in_zip):]

                # Check against file_map
                dst_path = None
                for src_pattern, dst_rel in file_map.items():
                    if src_pattern.endswith("/"):
                        # Directory pattern: match prefix
                        if rel.startswith(src_pattern) or rel == src_pattern.rstrip("/"):
                            file_rel = rel[len(src_pattern):] if rel.startswith(src_pattern) else rel
                            dst_path = os.path.join(extract_dir, dst_rel, file_rel)
                    else:
                        # Exact file match
                        if rel == src_pattern or rel.lstrip("/") == src_pattern.lstrip("/"):
                            dst_path = os.path.join(extract_dir, dst_rel)

                    if dst_path:
                        if zip_info.is_dir():
                            ensure_dir(dst_path)
                        else:
                            ensure_dir(os.path.dirname(dst_path))
                            with zf.open(zip_info) as src, open(dst_path, "wb") as dst:
                                dst.write(src.read())
                            copied += 1
                        break
    except (zipfile.BadZipFile, OSError) as e:
        print(f"  ZIP error: {e}")
        return 0
    return copied


def _auto_detect_prefix(zf: zipfile.ZipFile, given_prefix: str) -> Optional[str]:
    """Auto-detect the real root directory inside a GitHub ZIP archive.

    GitHub ZIPs contain a single top-level dir named like:
      repo-branch  or  repo-tag
    e.g. 'cmsis_device_f4-master', 'cmsis_device_f4-2.6.8', 'cmsis_device_f4-main'

    Returns the detected prefix if the given one is not found, else
    returns given_prefix unchanged.
    """
    # Check if given prefix exists
    for info in zf.infolist():
        if info.filename.startswith(given_prefix + "/"):
            return given_prefix

    # Not found — collect top-level dir names
    top_dirs = set()
    for info in zf.infolist():
        name = info.filename
        if "/" in name:
            top_dirs.add(name.split("/")[0])

    if not top_dirs:
        return given_prefix  # no dirs? keep original

    # Return the first top-level dir (GitHub ZIPs have exactly one)
    detected = sorted(top_dirs)[0]
    print(f"  Auto-detected ZIP root: '{detected}' (given: '{given_prefix}')")
    return detected


def _download_and_extract(kind: str, dl: Dict, work_dir: str,
                          skeleton_dir: str) -> bool:
    """Download a component (cmsis_device or spl) and extract to skeleton."""
    info = dl[kind]
    zip_path = os.path.join(work_dir, f"{kind}.zip")

    # Try each URL in sequence
    downloaded = False
    for url in info["urls"]:
        if _download_zip(url, zip_path):
            downloaded = True
            break

    if not downloaded:
        print(f"  Failed to download {info['description']}")
        return False

    copied = _extract_zip(zip_path, skeleton_dir, info["files"],
                          info["strip_prefixes"][0])  # _auto_detect_prefix fixes mismatch
    print(f"  {info['description']}: {copied} files extracted")
    return copied > 0


def _download_and_extract_cmsis_core(work_dir: str, dest_dir: str) -> bool:
    """Download CMSIS Core from ARM GitHub and extract Include files."""
    zip_path = os.path.join(work_dir, "cmsis_core.zip")

    downloaded = False
    zip_path_local = zip_path
    for i, url in enumerate(CMSIS_CORE_URLS):
        if _download_zip(url, zip_path_local):
            downloaded = True
            break

    if not downloaded:
        return False

    # Build file_map for specific CMSIS core files
    file_map = {}
    for fname in CMSIS_CORE_FILES:
        src = os.path.join(CMSIS_CORE_SOURCE_DIR, fname).replace("\\", "/")
        file_map[src] = fname

    ensure_dir(dest_dir)

    # Extract with auto-detect prefix
    copied = 0
    try:
        with zipfile.ZipFile(zip_path_local, "r") as zf:
            auto_prefix = _auto_detect_prefix(zf, CMSIS_CORE_PREFIXES[0])

            for zip_info in zf.infolist():
                name = zip_info.filename
                if auto_prefix and name.startswith(auto_prefix + "/"):
                    rel = name[len(auto_prefix) + 1:]
                else:
                    rel = name

                if not rel.startswith(CMSIS_CORE_SOURCE_DIR):
                    continue

                fname = os.path.basename(rel)
                if fname in CMSIS_CORE_FILES and not zip_info.is_dir():
                    dst_path = os.path.join(dest_dir, fname)
                    ensure_dir(os.path.dirname(dst_path))
                    with zf.open(zip_info) as src, open(dst_path, "wb") as dst:
                        dst.write(src.read())
                    copied += 1
    except (zipfile.BadZipFile, OSError) as e:
        print(f"  CMSIS Core ZIP error: {e}")
        return False

    print(f"  CMSIS Core: {copied} files extracted")
    return copied >= 10


def _copy_missing_startup_files(skeleton_dir: str, family: str,
                                 skill_dir: str) -> None:
    """Copy startup .s files and system files from an existing SPL skeleton to the HAL skeleton.

    Some GitHub repos (like cmsis-device-f4 renamed from cmsis_device_f4) may
    have a different file structure that doesn't include all startup variants.
    We copy missing ones from the SPL skeleton (which has a more complete set).
    """
    cmsis_dir = FAMILY_DOWNLOADS[family]["cmsis_device_dir"]
    hal_startup = os.path.join(skeleton_dir, "STM32", "CMSIS", "Device",
                                "ST", cmsis_dir, "Source", "Templates", "arm")
    hal_templates = os.path.join(skeleton_dir, "STM32", "CMSIS", "Device",
                                "ST", cmsis_dir, "Source", "Templates")

    # Find all SPL skeleton paths for this family
    for sp_family in [family, "F103" if family == "F407" else "F407"]:
        sp_key = "f103" if sp_family == "F103" else "f407"
        sp_skel = os.path.join(skill_dir, "skeleton", sp_key)
        
        # Check multiple possible startup file locations
        startup_locations = [
            # Standard CMSIS location
            os.path.join(sp_skel, "STM32", "CMSIS", "Device", "ST",
                        FAMILY_DOWNLOADS[sp_family]["cmsis_device_dir"],
                        "Source", "Templates", "arm"),
            # Alternative location for some skeletons (like f103)
            os.path.join(sp_skel, "Start"),
        ]
        
        for sp_startup in startup_locations:
            if not os.path.isdir(sp_startup):
                continue

            # Copy any .s files missing from HAL skeleton
            for fname in os.listdir(sp_startup):
                if not fname.endswith(".s"):
                    continue
                dst = os.path.join(hal_startup, fname)
                if not os.path.isfile(dst):
                    ensure_dir(os.path.dirname(dst))
                    shutil.copy2(os.path.join(sp_startup, fname), dst)
                    print(f"  Copied startup from SPL: {fname}")
            
            # Also copy system files if missing
            for fname in ["system_stm32f10x.c", "system_stm32f4xx.c", 
                         "system_stm32f10x.h", "system_stm32f4xx.h"]:
                src = os.path.join(sp_startup, fname)
                if os.path.isfile(src):
                    dst = os.path.join(hal_templates, fname)
                    if not os.path.isfile(dst):
                        ensure_dir(hal_templates)
                        shutil.copy2(src, dst)
                        print(f"  Copied system file from SPL: {fname}")


def _copy_cmsis_core_from_existing(skill_dir: str, dest_dir: str) -> bool:
    """Try to copy CMSIS Core files from an existing skeleton."""
    skeleton_dir = os.path.join(skill_dir, "skeleton")
    for family_key in ["f407", "f103"]:
        src = os.path.join(skeleton_dir, family_key, "STM32", "CMSIS", "Include")
        if os.path.isdir(src) and os.listdir(src):
            ensure_dir(dest_dir)
            for fname in os.listdir(src):
                full = os.path.join(src, fname)
                if os.path.isfile(full):
                    shutil.copy2(full, os.path.join(dest_dir, fname))
            print(f"  CMSIS Core: copied from existing {family_key} skeleton")
            return True
    return False


# ─── uvprojx generator ────────────────────────────────────────────────

def _generate_uvprojx(skeleton_dir: str, family: str, skill_dir: str,
                      library: str = "SPL") -> None:
    """Generate a complete .uvprojx file for the skeleton."""
    db = load_chip_db()
    use_hal = (library.upper() == "HAL")
    # Find a chip from this family to use for default settings
    default_chip = None
    for name, info in db.items():
        if info["family"] == family:
            default_chip = name
            break
    if default_chip is None:
        raise ValueError(f"No chip found for family {family}")

    chip = db[default_chip]

    proj_dir = os.path.join(skeleton_dir, "Project")
    ensure_dir(proj_dir)

    # Build XML tree
    root = ET.Element("Project",
                      {"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                       "xsi:noNamespaceSchemaLocation": "project_projx.xsd"})

    ET.SubElement(root, "SchemaVersion").text = "2.1"
    ET.SubElement(root, "Header").text = "### uVision Project, (C) Keil Software"

    targets = ET.SubElement(root, "Targets")
    target = ET.SubElement(targets, "Target")

    ET.SubElement(target, "TargetName").text = "Template"
    ET.SubElement(target, "ToolsetNumber").text = "0x4"
    ET.SubElement(target, "ToolsetName").text = "ARM-ADS"
    ET.SubElement(target, "pCCUsed").text = "5060960::V5.06 update 7 (build 960)::.\\ARMComplier5"
    ET.SubElement(target, "uAC6").text = "0"

    # TargetOption
    topt = ET.SubElement(target, "TargetOption")

    # TargetCommonOption
    tco = ET.SubElement(topt, "TargetCommonOption")
    ET.SubElement(tco, "Device").text = chip["device"]
    ET.SubElement(tco, "Vendor").text = "STMicroelectronics"
    ET.SubElement(tco, "PackID").text = chip["pack_id"]
    ET.SubElement(tco, "PackURL").text = "https://www.keil.com/pack/"
    ET.SubElement(tco, "Cpu").text = chip["cpu_string"]
    ET.SubElement(tco, "FlashUtilSpec").text = ""
    ET.SubElement(tco, "StartupFile").text = ""
    ET.SubElement(tco, "FlashDriverDll").text = chip["flash_driver"]
    ET.SubElement(tco, "DeviceId").text = "0"
    ET.SubElement(tco, "RegisterFile").text = ""
    ET.SubElement(tco, "MemoryEnv").text = ""
    ET.SubElement(tco, "Cmp").text = ""
    ET.SubElement(tco, "Asm").text = ""
    ET.SubElement(tco, "Linker").text = ""
    ET.SubElement(tco, "OHString").text = ""
    ET.SubElement(tco, "InfinionOptionDll").text = ""
    ET.SubElement(tco, "SLE66CMisc").text = ""
    ET.SubElement(tco, "SLE66AMisc").text = ""
    ET.SubElement(tco, "SLE66LinkerMisc").text = ""
    ET.SubElement(tco, "SFDFile").text = f"$$Device:{chip['device']}$CMSIS\\SVD\\{chip['svd_file']}"
    ET.SubElement(tco, "bCustSvd").text = "0"
    ET.SubElement(tco, "UseEnv").text = "0"
    ET.SubElement(tco, "BinPath").text = ""
    ET.SubElement(tco, "IncludePath").text = ""
    ET.SubElement(tco, "LibPath").text = ""
    ET.SubElement(tco, "RegisterFilePath").text = ""
    ET.SubElement(tco, "DBRegisterFilePath").text = ""

    # TargetStatus
    ts = ET.SubElement(tco, "TargetStatus")
    for tag, val in [("Error", "0"), ("ExitCodeStop", "0"), ("ButtonStop", "0"),
                     ("NotGenerated", "0"), ("InvalidFlash", "0")]:
        ET.SubElement(ts, tag).text = val

    ET.SubElement(tco, "OutputDirectory").text = ".\\Objects\\"
    ET.SubElement(tco, "OutputName").text = "Template"
    ET.SubElement(tco, "CreateExecutable").text = "1"
    ET.SubElement(tco, "CreateLib").text = "0"
    ET.SubElement(tco, "CreateHexFile").text = "1"
    ET.SubElement(tco, "DebugInformation").text = "1"
    ET.SubElement(tco, "BrowseInformation").text = "1"
    ET.SubElement(tco, "ListingPath").text = ".\\Listings\\"
    ET.SubElement(tco, "HexFormatSelection").text = "1"
    ET.SubElement(tco, "Merge32K").text = "0"
    ET.SubElement(tco, "CreateBatchFile").text = "0"

    # BeforeCompile / BeforeMake / AfterMake
    for section in ["BeforeCompile", "BeforeMake", "AfterMake"]:
        bc = ET.SubElement(tco, section)
        for tag in ["RunUserProg1", "RunUserProg2"]:
            ET.SubElement(bc, tag).text = "0"
        for tag in ["UserProg1Name", "UserProg2Name"]:
            ET.SubElement(bc, tag).text = ""
        ET.SubElement(bc, "UserProg1Dos16Mode").text = "0"
        ET.SubElement(bc, "UserProg2Dos16Mode").text = "0"
        n1 = "nStopU1X" if section == "BeforeCompile" else ("nStopB1X" if section == "BeforeMake" else "nStopA1X")
        n2 = "nStopU2X" if section == "BeforeCompile" else ("nStopB2X" if section == "BeforeMake" else "nStopA2X")
        ET.SubElement(bc, n1).text = "0"
        ET.SubElement(bc, n2).text = "0"

    ET.SubElement(tco, "SelectedForBatchBuild").text = "0"
    ET.SubElement(tco, "SVCSIdString").text = ""

    # CommonProperty
    cp = ET.SubElement(topt, "CommonProperty")
    for tag, val in [
        ("UseCPPCompiler", "0"), ("RVCTCodeConst", "0"), ("RVCTZI", "0"),
        ("RVCTOtherData", "0"), ("ModuleSelection", "0"), ("IncludeInBuild", "1"),
        ("AlwaysBuild", "0"), ("GenerateAssemblyFile", "0"), ("AssembleAssemblyFile", "0"),
        ("PublicsOnly", "0"), ("StopOnExitCode", "3"),
    ]:
        ET.SubElement(cp, tag).text = val
    ET.SubElement(cp, "CustomArgument").text = ""
    ET.SubElement(cp, "IncludeLibraryModules").text = ""
    ET.SubElement(cp, "ComprImg").text = "1"

    # DllOption
    dll = ET.SubElement(topt, "DllOption")
    ET.SubElement(dll, "SimDllName").text = "SARMCM3.DLL"
    ET.SubElement(dll, "SimDllArguments").text = " -REMAP -MPU" if chip.get("has_fpu") else " -REMAP"
    ET.SubElement(dll, "SimDlgDll").text = "DCM.DLL"
    ET.SubElement(dll, "SimDlgDllArguments").text = chip["sim_dll_args"]
    ET.SubElement(dll, "TargetDllName").text = "SARMCM3.DLL"
    ET.SubElement(dll, "TargetDllArguments").text = " -MPU" if chip.get("has_fpu") else ""
    ET.SubElement(dll, "TargetDlgDll").text = "TCM.DLL"
    ET.SubElement(dll, "TargetDlgDllArguments").text = chip["sim_dll_args"]

    # DebugOption
    dbgopt = ET.SubElement(topt, "DebugOption")
    ophx = ET.SubElement(dbgopt, "OPTHX")
    for tag, val in [("HexSelection", "1"), ("HexRangeLowAddress", "0"),
                     ("HexRangeHighAddress", "0"), ("HexOffset", "0"),
                     ("Oh166RecLen", "16")]:
        ET.SubElement(ophx, tag).text = val

    # Utilities (flash settings)
    util = ET.SubElement(topt, "Utilities")
    flash1 = ET.SubElement(util, "Flash1")
    for tag, val in [("UseTargetDll", "1"), ("UseExternalTool", "0"), ("RunIndependent", "0"),
                     ("UpdateFlashBeforeDebugging", "1"), ("Capability", "1"),
                     ("DriverSelection", "4096")]:
        ET.SubElement(flash1, tag).text = val
    ET.SubElement(util, "bUseTDR").text = "1"
    ET.SubElement(util, "Flash2").text = "BIN\\UL2CM3.DLL"
    ET.SubElement(util, "Flash3").text = '"" ()'
    ET.SubElement(util, "Flash4").text = ""
    ET.SubElement(util, "pFcarmOut").text = ""
    ET.SubElement(util, "pFcarmGrp").text = ""
    ET.SubElement(util, "pFcArmRoot").text = ""
    ET.SubElement(util, "FcArmLst").text = "0"

    # TargetArmAds (compiler/assembler/linker)
    taa = ET.SubElement(topt, "TargetArmAds")

    # ArmAdsMisc
    aam = ET.SubElement(taa, "ArmAdsMisc")
    for tag, val in [
        ("GenerateListings", "0"), ("asHll", "1"), ("asAsm", "1"), ("asMacX", "1"),
        ("asSyms", "1"), ("asFals", "1"), ("asDbgD", "1"), ("asForm", "1"),
        ("ldLst", "0"), ("ldmm", "1"), ("ldXref", "1"), ("BigEnd", "0"),
        ("AdsALst", "1"), ("AdsACrf", "1"), ("AdsANop", "0"), ("AdsANot", "0"),
        ("AdsLLst", "1"), ("AdsLmap", "1"), ("AdsLcgr", "1"), ("AdsLsym", "1"),
        ("AdsLszi", "1"), ("AdsLtoi", "1"), ("AdsLsun", "1"), ("AdsLven", "1"),
        ("AdsLsxf", "1"), ("RvctClst", "0"), ("GenPPlst", "0"),
    ]:
        ET.SubElement(aam, tag).text = val

    cortex = _get_cortex_type(family, chip)
    ET.SubElement(aam, "AdsCpuType").text = f'"{cortex}"'
    ET.SubElement(aam, "RvctDeviceName").text = ""
    ET.SubElement(aam, "mOS").text = "0"
    ET.SubElement(aam, "uocRom").text = "0"
    ET.SubElement(aam, "uocRam").text = "0"
    ET.SubElement(aam, "hadIROM").text = "1"
    ET.SubElement(aam, "hadIRAM").text = "1"
    ET.SubElement(aam, "hadXRAM").text = "0"
    ET.SubElement(aam, "uocXRam").text = "0"
    ET.SubElement(aam, "RvdsVP").text = "2"
    ET.SubElement(aam, "RvdsMve").text = "0"
    ET.SubElement(aam, "RvdsCdeCp").text = "0"
    ET.SubElement(aam, "nBranchProt").text = "0"
    ET.SubElement(aam, "hadIRAM2").text = "1" if chip.get("has_iram2") else "0"
    ET.SubElement(aam, "hadIROM2").text = "0"
    ET.SubElement(aam, "StupSel").text = "8"
    ET.SubElement(aam, "useUlib").text = "1"
    ET.SubElement(aam, "EndSel").text = "0"
    ET.SubElement(aam, "uLtcg").text = "0"
    ET.SubElement(aam, "nSecure").text = "0"
    ET.SubElement(aam, "RoSelD").text = "3"
    ET.SubElement(aam, "RwSelD").text = "4"
    ET.SubElement(aam, "CodeSel").text = "0"
    ET.SubElement(aam, "OptFeed").text = "0"
    for i in range(1, 6):
        ET.SubElement(aam, f"NoZi{i}").text = "0"
    for i in range(1, 4):
        ET.SubElement(aam, f"Ro{i}Chk").text = "0"
    for i in range(1, 3):
        ET.SubElement(aam, f"Ir{i}Chk").text = "1" if i == 1 else "0"
    for i in range(1, 4):
        ET.SubElement(aam, f"Ra{i}Chk").text = "0"
    for i in range(1, 3):
        ET.SubElement(aam, f"Im{i}Chk").text = "1" if i == 1 else "0"

    # OnChipMemories
    ocm = ET.SubElement(aam, "OnChipMemories")
    ocm_items = [
        ("Ocm1", "0", "0x0", "0x0"), ("Ocm2", "0", "0x0", "0x0"),
        ("Ocm3", "0", "0x0", "0x0"), ("Ocm4", "0", "0x0", "0x0"),
        ("Ocm5", "0", "0x0", "0x0"), ("Ocm6", "0", "0x0", "0x0"),
        ("IRAM", "0", chip["ram_start"], chip["ram_size"]),
        ("IROM", "1", chip["flash_start"], chip["flash_size"]),
        ("XRAM", "0", "0x0", "0x0"),
    ]
    for name, typ, start, size in ocm_items:
        el = ET.SubElement(ocm, name)
        ET.SubElement(el, "Type").text = typ
        ET.SubElement(el, "StartAddress").text = start
        ET.SubElement(el, "Size").text = size

    # OCR_RVCT entries
    for i in range(1, 9):
        el = ET.SubElement(ocm, f"OCR_RVCT{i}")
        ET.SubElement(el, "Type").text = "1" if i <= 5 else "0"
        ET.SubElement(el, "StartAddress").text = "0x0"
        ET.SubElement(el, "Size").text = "0x0"

    # OCR_RVCT4 = IROM, OCR_RVCT9 = IRAM
    for rvct_name, start, size in [("OCR_RVCT4", chip["flash_start"], chip["flash_size"]),
                                     ("OCR_RVCT9", chip["ram_start"], chip["ram_size"])]:
        el = ocm.find(rvct_name)
        if el is not None:
            el.find("StartAddress").text = start
            el.find("Size").text = size

    # OCR_RVCT10 = IRAM2 (CCM)
    rvct10 = ocm.find("OCR_RVCT10")
    if rvct10 is None:
        rvct10 = ET.SubElement(ocm, "OCR_RVCT10")
        ET.SubElement(rvct10, "Type").text = "0"
        ET.SubElement(rvct10, "StartAddress").text = "0x0"
        ET.SubElement(rvct10, "Size").text = "0x0"
    if chip.get("has_iram2"):
        rvct10.find("StartAddress").text = "0x10000000"
        rvct10.find("Size").text = "0x10000"

    ET.SubElement(aam, "RvctStartVector").text = ""

    # Cads (C compiler settings)
    cads = ET.SubElement(taa, "Cads")
    for tag, val in [
        ("interw", "1"), ("Optim", "1"), ("oTime", "0"), ("SplitLS", "0"),
        ("OneElfS", "1"), ("Strict", "0"), ("EnumInt", "0"), ("PlainCh", "0"),
        ("Ropi", "0"), ("Rwpi", "0"), ("wLevel", "2"), ("uThumb", "0"),
        ("uSurpInc", "0"), ("uC99", "1"), ("uGnu", "0"), ("useXO", "0"),
        ("v6Lang", "3"), ("v6LangP", "3"), ("vShortEn", "1"), ("vShortWch", "1"),
        ("v6Lto", "0"), ("v6WtE", "0"), ("v6Rtti", "0"),
    ]:
        ET.SubElement(cads, tag).text = val

    vc = ET.SubElement(cads, "VariousControls")
    ET.SubElement(vc, "MiscControls").text = ""
    if use_hal:
        # HAL projects must define USE_HAL_DRIVER, and NOT USE_STDPERIPH_DRIVER
        if "hal_device_define" in chip:
            # Use the specific HAL device define (e.g., STM32F103xB, STM32F407xx)
            hal_device_define = chip["hal_device_define"]
            hal_defines = f"USE_HAL_DRIVER,{hal_device_define}"
            # Add other defines (like ARM_MATH_CM4) if present
            other_defines = [d for d in chip["defines"].split(",") 
                           if d not in ["USE_STDPERIPH_DRIVER", "USE_HAL_DRIVER"] 
                           and not d.startswith("STM32F10X_") 
                           and not d.startswith("STM32F40_41xxx")
                           and not d.startswith("STM32F411xE")
                           and not d.startswith("STM32F429_439xx")]
            if other_defines:
                hal_defines += "," + ",".join(other_defines)
        else:
            hal_defines = chip["defines"]
            if "USE_STDPERIPH_DRIVER" in hal_defines:
                hal_defines = hal_defines.replace("USE_STDPERIPH_DRIVER", "USE_HAL_DRIVER")
            if "USE_HAL_DRIVER" not in hal_defines:
                hal_defines = "USE_HAL_DRIVER," + hal_defines
        ET.SubElement(vc, "Define").text = hal_defines
    else:
        ET.SubElement(vc, "Define").text = chip["defines"]
    ET.SubElement(vc, "Undefine").text = ""

    cmsis_dir = chip["cmsis_device_dir"]
    if use_hal:
        hal_dir = FAMILY_DOWNLOADS[family]["hal_dir_name"]
        inc_path = (
            f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Include;"
            f"..\\STM32\\CMSIS\\Include;"
            f"..\\STM32\\{hal_dir}\\Inc;"
            f"..\\User;..\\Drive\\Include"
        )
    else:
        spl_dir = chip["std_periph_driver_dir"]
        inc_path = (
            f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Include;"
            f"..\\STM32\\CMSIS\\Include;"
            f"..\\STM32\\{spl_dir}\\inc;"
            f"..\\User;..\\Drive\\Include"
        )
    ET.SubElement(vc, "IncludePath").text = inc_path

    # Aads (assembler settings)
    aads = ET.SubElement(taa, "Aads")
    for tag, val in [("interw", "1"), ("Ropi", "0"), ("Rwpi", "0"), ("thumb", "0"),
                     ("SplitLS", "0"), ("SwStkChk", "0"), ("NoWarn", "0"),
                     ("uSurpInc", "0"), ("useXO", "0"), ("ClangAsOpt", "4")]:
        ET.SubElement(aads, tag).text = val
    avc = ET.SubElement(aads, "VariousControls")
    for tag in ["MiscControls", "Define", "Undefine", "IncludePath"]:
        ET.SubElement(avc, tag).text = ""

    # LDads (linker settings)
    ldad = ET.SubElement(taa, "LDads")
    for tag, val in [("umfTarg", "1"), ("Ropi", "0"), ("Rwpi", "0"), ("noStLib", "0"),
                     ("RepFail", "1"), ("useFile", "0")]:
        ET.SubElement(ldad, tag).text = val
    ET.SubElement(ldad, "TextAddressRange").text = chip["flash_start"]
    ET.SubElement(ldad, "DataAddressRange").text = chip["ram_start"]
    ET.SubElement(ldad, "pXoBase").text = ""
    ET.SubElement(ldad, "ScatterFile").text = ""
    ET.SubElement(ldad, "IncludeLibs").text = ""
    ET.SubElement(ldad, "IncludeLibsPath").text = ""
    ET.SubElement(ldad, "Misc").text = ""
    ET.SubElement(ldad, "LinkerInputFile").text = ""
    ET.SubElement(ldad, "DisabledWarnings").text = ""

    # Groups
    groups = ET.SubElement(target, "Groups")
    if use_hal:
        _add_uvprojx_group(groups, "User", [
            ("main.c", "1", "..\\User\\main.c"),
            ("stm32f4xx_hal_msp.c" if family == "F407" else "stm32f1xx_hal_msp.c", "1",
             f"..\\User\\{_hal_prefix(family)}_hal_msp.c"),
            (f"{_hal_prefix(family)}_it.c", "1", f"..\\User\\{_hal_prefix(family)}_it.c"),
        ])
        _add_uvprojx_group(groups, "STM32", _hal_stm32_group_files(family, chip))
    else:
        _add_uvprojx_group(groups, "User", [
            ("main.c", "1", "..\\User\\main.c"),
            (f"{chip['conf_header']}", "5", f"..\\User\\{chip['conf_header']}"),
            (f"{chip['it_source']}", "1", f"..\\User\\{chip['it_source']}"),
        ])
        _add_uvprojx_group(groups, "Drive", [
            ("led.c", "1", "..\\Drive\\Source\\led.c"),
            ("delay.c", "1", "..\\Drive\\Source\\delay.c"),
            ("GPIO.c", "1", "..\\Drive\\Source\\GPIO.c"),
            ("delay.h", "5", "..\\Drive\\Include\\delay.h"),
            ("GPIO.h", "5", "..\\Drive\\Include\\GPIO.h"),
            ("led.h", "5", "..\\Drive\\Include\\led.h"),
            ("USART.h", "5", "..\\Drive\\Include\\USART.h"),
            ("USART.c", "1", "..\\Drive\\Source\\USART.c"),
        ])
        spl_dir = chip["std_periph_driver_dir"]
        _add_uvprojx_group(groups, "STM32", [
            (chip["startup_file"], "2", f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\arm\\{chip['startup_file']}"),
            (chip["system_file"], "1", f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\{chip['system_file']}"),
            ("misc.c", "1", f"..\\STM32\\{spl_dir}\\src\\misc.c"),
            (f"{_spl_prefix(family)}_rcc.c", "1", f"..\\STM32\\{spl_dir}\\src\\{_spl_prefix(family)}_rcc.c"),
            (f"{_spl_prefix(family)}_gpio.c", "1", f"..\\STM32\\{spl_dir}\\src\\{_spl_prefix(family)}_gpio.c"),
            (f"{_spl_prefix(family)}_usart.c", "1", f"..\\STM32\\{spl_dir}\\src\\{_spl_prefix(family)}_usart.c"),
        ])

    # RTE (empty)
    rte = ET.SubElement(root, "RTE")
    ET.SubElement(rte, "apis")
    ET.SubElement(rte, "components")
    ET.SubElement(rte, "files")

    # LayerInfo
    li = ET.SubElement(root, "LayerInfo")
    layers = ET.SubElement(li, "Layers")
    layer = ET.SubElement(layers, "Layer")
    ET.SubElement(layer, "LayName").text = chip["device"]
    ET.SubElement(layer, "LayTarg").text = "0"
    ET.SubElement(layer, "LayPrjMark").text = "1"

    # Write
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    uvprojx_path = os.path.join(proj_dir, "Template.uvprojx")
    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
    print(f"  Generated: {uvprojx_path}")


def _add_uvprojx_group(groups: ET.Element, name: str,
                       files: List[tuple]) -> None:
    """Add a group with files to the uvprojx XML."""
    grp = ET.SubElement(groups, "Group")
    ET.SubElement(grp, "GroupName").text = name
    fe = ET.SubElement(grp, "Files")
    for fname, ftype, fpath in files:
        f = ET.SubElement(fe, "File")
        ET.SubElement(f, "FileName").text = fname
        ET.SubElement(f, "FileType").text = ftype
        ET.SubElement(f, "FilePath").text = fpath


def _spl_prefix(family: str) -> str:
    """Get the SPL file prefix for a family (e.g., 'stm32f4xx')."""
    return "stm32f4xx" if family == "F407" else "stm32f10x"


def _get_cortex_type(family: str, chip: Dict) -> str:
    """Map family/core to Keil's Cortex string."""
    core = chip.get("core", "")
    core_map = {
        "Cortex-M0+": "Cortex-M0+",
        "Cortex-M0": "Cortex-M0",
        "Cortex-M3": "Cortex-M3",
        "Cortex-M4": "Cortex-M4",
        "Cortex-M7": "Cortex-M7",
        "Cortex-M33": "Cortex-M33",
    }
    return core_map.get(core, f"Cortex-{core.split('-')[-1]}" if core else "Cortex-M4")


def _hal_prefix(family: str) -> str:
    """Get the HAL file prefix for a family (e.g., 'stm32f4xx', 'stm32g4xx').
    Note: F1 HAL drivers use 'stm32f1xx' (not 'stm32f10x' like SPL did)."""
    _HAL_PREFIX_MAP = {
        "F103": "stm32f1xx", "F407": "stm32f4xx",
        "G4": "stm32g4xx", "H7": "stm32h7xx",
        "L4": "stm32l4xx", "C0": "stm32c0xx",
    }
    return _HAL_PREFIX_MAP.get(family, f"stm32{family.lower()}xx")


def _hal_stm32_group_files(family: str, chip: Dict) -> List[tuple]:
    """Files for the STM32 group of a HAL-based project."""
    cmsis_dir = chip["cmsis_device_dir"]
    hal_dir = FAMILY_DOWNLOADS[family]["hal_dir_name"]
    hp = _hal_prefix(family)
    files = [
        (chip["startup_file"], "2",
         f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\arm\\{chip['startup_file']}"),
        (chip["system_file"], "1",
         f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\{chip['system_file']}"),
    ]
    # Include every HAL source that is present in the downloaded driver
    hal_src = os.path.join(os.path.dirname(__file__), "..", "skeleton",
                           f"hal_{family.lower()}", "STM32", hal_dir, "Src")
    if not os.path.isdir(hal_src):
        # Skeleton not yet built — include a known-good minimal set per family
        _DEFAULT_HAL_MODULES = {
            "F103": ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma"),
            "F407": ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma"),
            "G4":   ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma", "_exti"),
            "L4":   ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma", "_exti"),
            "H7":   ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma", "_exti"),
            "C0":   ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma"),
        }
        module_list = _DEFAULT_HAL_MODULES.get(family, ("", "_rcc", "_gpio", "_cortex", "_uart", "_pwr", "_flash", "_flash_ex", "_dma"))
        for mod in module_list:
            fn = f"{hp}_hal{mod}.c"
            # Skip template files
            if "_template" not in fn.lower():
                files.append((fn, "1", f"..\\STM32\\{hal_dir}\\Src\\{fn}"))
    else:
        for fname in sorted(os.listdir(hal_src)):
            if fname.endswith(".c") and "_template" not in fname.lower():
                files.append((fname, "1", f"..\\STM32\\{hal_dir}\\Src\\{fname}"))
    return files


# ─── uvoptx generator ─────────────────────────────────────────────────

def _generate_uvoptx(skeleton_dir: str, family: str,
                     library: str = "SPL") -> None:
    """Generate a minimal .uvoptx file."""
    db = load_chip_db()
    default_chip = None
    for name, info in db.items():
        if info["family"] == family:
            default_chip = name
            break
    chip = db[default_chip]
    cmsis_dir = chip["cmsis_device_dir"]
    use_hal = (library.upper() == "HAL")
    spl_dir = chip["std_periph_driver_dir"]
    f_pre = _spl_prefix(family)

    proj_dir = os.path.join(skeleton_dir, "Project")
    ensure_dir(proj_dir)

    root = ET.Element("ProjectOpt",
                      {"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
                       "xsi:noNamespaceSchemaLocation": "project_optx.xsd"})
    ET.SubElement(root, "SchemaVersion").text = "1.0"
    ET.SubElement(root, "Header").text = "### uVision Project, (C) Keil Software"

    ext = ET.SubElement(root, "Extensions")
    for tag, val in [("cExt", "*.c"), ("aExt", "*.s*; *.src; *.a*"), ("oExt", "*.obj; *.o"),
                     ("lExt", "*.lib"), ("tExt", "*.txt; *.h; *.inc; *.md"),
                     ("pExt", "*.plm"), ("CppX", "*.cpp; *.cc; *.cxx")]:
        ET.SubElement(ext, tag).text = val
    ET.SubElement(ext, "nMigrate").text = "0"

    dt = ET.SubElement(root, "DaveTm")
    ET.SubElement(dt, "dwLowDateTime").text = "0"
    ET.SubElement(dt, "dwHighDateTime").text = "0"

    tgt = ET.SubElement(root, "Target")
    ET.SubElement(tgt, "TargetName").text = "Template"
    ET.SubElement(tgt, "ToolsetNumber").text = "0x4"
    ET.SubElement(tgt, "ToolsetName").text = "ARM-ADS"

    topt = ET.SubElement(tgt, "TargetOption")
    ET.SubElement(topt, "CLKADS").text = "12000000"

    # OPTTT
    ott = ET.SubElement(topt, "OPTTT")
    for tag, val in [("gFlags", "1"), ("BeepAtEnd", "1"), ("RunSim", "0"),
                     ("RunTarget", "1"), ("RunAbUc", "0")]:
        ET.SubElement(ott, tag).text = val

    # OPTHX
    ohx = ET.SubElement(topt, "OPTHX")
    for tag, val in [("HexSelection", "1"), ("FlashByte", "65535"),
                     ("HexRangeLowAddress", "0"), ("HexRangeHighAddress", "0"),
                     ("HexOffset", "0")]:
        ET.SubElement(ohx, tag).text = val

    # OPTLEX
    olx = ET.SubElement(topt, "OPTLEX")
    for tag, val in [("PageWidth", "79"), ("PageLength", "66"), ("TabStop", "8")]:
        ET.SubElement(olx, tag).text = val
    ET.SubElement(olx, "ListingPath").text = ".\\Listings\\"

    # ListingPage
    lp = ET.SubElement(topt, "ListingPage")
    for tag, val in [("CreateCListing", "1"), ("CreateAListing", "1"), ("CreateLListing", "1"),
                     ("CreateIListing", "0"), ("AsmCond", "1"), ("AsmSymb", "1"),
                     ("AsmXref", "0"), ("CCond", "1"), ("CCode", "0"),
                     ("CListInc", "0"), ("CSymb", "0"), ("LinkerCodeListing", "0")]:
        ET.SubElement(lp, tag).text = val

    # OPTXL
    oxl = ET.SubElement(topt, "OPTXL")
    for tag, val in [("LMap", "1"), ("LComments", "1"), ("LGenerateSymbols", "1"),
                     ("LLibSym", "1"), ("LLines", "1"), ("LLocSym", "1"),
                     ("LPubSym", "1"), ("LXref", "0"), ("LExpSel", "0")]:
        ET.SubElement(oxl, tag).text = val

    # OPTFL
    ofl = ET.SubElement(topt, "OPTFL")
    for tag, val in [("tvExp", "1"), ("tvExpOptDlg", "0"), ("IsCurrentTarget", "1")]:
        ET.SubElement(ofl, tag).text = val

    ET.SubElement(topt, "CpuCode").text = "18"

    # DebugOpt
    dbo = ET.SubElement(topt, "DebugOpt")
    for tag, val in [("uSim", "0"), ("uTrg", "1"), ("sLdApp", "1"), ("sGomain", "1"),
                     ("sRbreak", "1"), ("sRwatch", "1"), ("sRmem", "1"), ("sRfunc", "1"),
                     ("sRbox", "1"), ("tLdApp", "1"), ("tGomain", "1"), ("tRbreak", "1"),
                     ("tRwatch", "1"), ("tRmem", "1"), ("tRfunc", "0"), ("tRbox", "1"),
                     ("tRtrace", "1"), ("sRSysVw", "1"), ("tRSysVw", "1"),
                     ("sRunDeb", "0"), ("sLrtime", "0"), ("bEvRecOn", "1"),
                     ("bSchkAxf", "0"), ("bTchkAxf", "0"), ("nTsel", "6")]:
        ET.SubElement(dbo, tag).text = val
    for tag in ["sDll", "sDllPa", "sDlgDll", "sDlgPa", "sIfile",
                "tDll", "tDllPa", "tDlgDll", "tDlgPa", "tIfile"]:
        ET.SubElement(dbo, tag).text = ""
    ET.SubElement(dbo, "pMon").text = "STLink\\ST-LINKIII-KEIL_SWO.dll"

    # TargetDriverDllRegistry (ST-Link entry with Reset and Run enabled)
    tddr = ET.SubElement(topt, "TargetDriverDllRegistry")
    
    # ST-Link configuration with Reset and Run (-R1 at the end)
    stlink_cfg = (
        '-O206 -SF4000 -C0 -A0 -I0 -HNlocalhost -HP7184 -P1 '
        '-N00("ARM CoreSight SW-DP") -D00(2BA01477) -L00(0) '
        '-TO131090 -TC10000000 -TT10000000 -TP21 -TDS8007 -TDT0 -TDC1F '
        '-TIEFFFFFFFF -TIP8 -FO15 '
        f'-FD20000000 -FC1000 -FN1 '
        f'-FF0{os.path.splitext(chip["flash_driver"].split(" ")[0])[0] if chip.get("flash_driver") else "STM32F4xx_1024"} '
        f'-FS0{chip["flash_start"]} -FL0{chip["flash_size"]} '
        f'-FP0($$Device:{chip["device"]}$CMSIS\\Flash\\) '
        '-WA0 -WE0 -WVCE4 -WS2710 -WM0 -WP2 -WK0 -R1'
    )
    
    for num, key, name in [
        ("0", "ST-LINKIII-KEIL_SWO", stlink_cfg),
        ("0", "UL2CM3", chip["flash_driver"]),
    ]:
        sre = ET.SubElement(tddr, "SetRegEntry")
        ET.SubElement(sre, "Number").text = num
        ET.SubElement(sre, "Key").text = key
        ET.SubElement(sre, "Name").text = name

    ET.SubElement(topt, "Breakpoint")
    tp = ET.SubElement(topt, "Tracepoint")
    ET.SubElement(tp, "THDelay").text = "0"

    # DebugFlag
    df = ET.SubElement(topt, "DebugFlag")
    for tag in ["trace", "periodic", "aLwin", "aCover", "aSer1", "aSer2",
                "aPa", "viewmode", "vrSel", "aSym", "aTbox", "AscS1", "AscS2",
                "AscS3", "aSer3", "eProf", "aLa", "aPa1", "AscS4", "aSer4",
                "StkLoc", "TrcWin", "newCpu", "uProt"]:
        ET.SubElement(df, tag).text = "0"

    for tag in ["LintExecutable", "LintConfigFile"]:
        ET.SubElement(topt, tag).text = ""
    ET.SubElement(topt, "bLintAuto").text = "0"
    ET.SubElement(topt, "bAutoGenD").text = "0"
    ET.SubElement(topt, "LntExFlags").text = "0"
    for tag in ["pMisraName", "pszMrule", "pSingCmds", "pMultCmds",
                "pMisraNamep", "pszMrulep", "pSingCmdsp", "pMultCmdsp"]:
        ET.SubElement(topt, tag).text = ""

    # DebugDescription
    dd = ET.SubElement(topt, "DebugDescription")
    for tag, val in [("Enable", "1"), ("EnableFlashSeq", "0"), ("EnableLog", "0"),
                     ("Protocol", "2"), ("DbgClock", "10000000")]:
        ET.SubElement(dd, tag).text = val

    # Group entries in uvoptx
    if use_hal:
        hal_dir = FAMILY_DOWNLOADS[family]["hal_dir_name"]
        hp = _hal_prefix(family)
        group_files_map = [
            ("User", [
                ("main.c", "..\\User\\main.c", "1"),
                (f"{hp}_hal_msp.c", f"..\\User\\{hp}_hal_msp.c", "1"),
                (f"{hp}_it.c", f"..\\User\\{hp}_it.c", "1"),
            ]),
            ("STM32", [
                (chip["startup_file"],
                 f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\arm\\{chip['startup_file']}", "2"),
                (chip["system_file"],
                 f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\{chip['system_file']}", "1"),
                (f"{hp}_hal.c",       f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal.c", "1"),
                (f"{hp}_hal_rcc.c",   f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_rcc.c", "1"),
                (f"{hp}_hal_gpio.c",  f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_gpio.c", "1"),
                (f"{hp}_hal_cortex.c",f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_cortex.c", "1"),
                (f"{hp}_hal_uart.c",  f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_uart.c", "1"),
                (f"{hp}_hal_pwr.c",   f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_pwr.c", "1"),
                (f"{hp}_hal_flash.c", f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_flash.c", "1"),
                (f"{hp}_hal_flash_ex.c", f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_flash_ex.c", "1"),
                (f"{hp}_hal_dma.c",   f"..\\STM32\\{hal_dir}\\Src\\{hp}_hal_dma.c", "1"),
            ]),
        ]
    else:
        group_files_map = [
            ("User", [
                ("main.c", "..\\User\\main.c", "1"),
                (chip["conf_header"], f"..\\User\\{chip['conf_header']}", "5"),
                (chip["it_source"], f"..\\User\\{chip['it_source']}", "1"),
            ]),
            ("Drive", [
                ("led.c", "..\\Drive\\Source\\led.c", "1"),
                ("delay.c", "..\\Drive\\Source\\delay.c", "1"),
                ("GPIO.c", "..\\Drive\\Source\\GPIO.c", "1"),
                ("delay.h", "..\\Drive\\Include\\delay.h", "5"),
                ("GPIO.h", "..\\Drive\\Include\\GPIO.h", "5"),
                ("led.h", "..\\Drive\\Include\\led.h", "5"),
                ("USART.h", "..\\Drive\\Include\\USART.h", "5"),
                ("USART.c", "..\\Drive\\Source\\USART.c", "1"),
            ]),
            ("STM32", [
                (chip["startup_file"], f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\arm\\{chip['startup_file']}", "2"),
                (chip["system_file"], f"..\\STM32\\CMSIS\\Device\\ST\\{cmsis_dir}\\Source\\Templates\\{chip['system_file']}", "1"),
                ("misc.c", f"..\\STM32\\{spl_dir}\\src\\misc.c", "1"),
                (f"{f_pre}_rcc.c", f"..\\STM32\\{spl_dir}\\src\\{f_pre}_rcc.c", "1"),
                (f"{f_pre}_gpio.c", f"..\\STM32\\{spl_dir}\\src\\{f_pre}_gpio.c", "1"),
                (f"{f_pre}_usart.c", f"..\\STM32\\{spl_dir}\\src\\{f_pre}_usart.c", "1"),
            ]),
        ]

    file_num = 0
    for gidx, (gname, files) in enumerate(group_files_map, 1):
        grp = ET.SubElement(root, "Group")
        ET.SubElement(grp, "GroupName").text = gname
        for tag, val in [("tvExp", "1" if gidx == 1 else "0"),
                         ("tvExpOptDlg", "0"), ("cbSel", "0"), ("RteFlg", "0")]:
            ET.SubElement(grp, tag).text = val
        for fname, fpath, ftype in files:
            file_num += 1
            fe = ET.SubElement(grp, "File")
            for tag, val in [("GroupNumber", str(gidx)), ("FileNumber", str(file_num)),
                             ("FileType", ftype), ("tvExp", "0"), ("tvExpOptDlg", "0"),
                             ("bDave2", "0"), ("PathWithFileName", fpath),
                             ("FilenameWithoutPath", fname), ("RteFlg", "0"), ("bShared", "0")]:
                ET.SubElement(fe, tag).text = val

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    uvoptx_path = os.path.join(proj_dir, "Template.uvoptx")
    tree.write(uvoptx_path, encoding="UTF-8", xml_declaration=True)
    print(f"  Generated: {uvoptx_path}")


# ─── source file generators ───────────────────────────────────────────

def _generate_drive_files(skeleton_dir: str, family: str) -> None:
    """Generate Drive layer source files."""
    src_dir = os.path.join(skeleton_dir, "Drive", "Source")
    inc_dir = os.path.join(skeleton_dir, "Drive", "Include")
    ensure_dir(src_dir)
    ensure_dir(inc_dir)

    header = "stm32f4xx.h" if family == "F407" else "stm32f10x.h"
    rcc_clk = "RCC_AHB1PeriphClockCmd" if family == "F407" else "RCC_APB2PeriphClockCmd"
    rcc_gpiof = "RCC_AHB1Periph_GPIOF" if family == "F407" else "RCC_APB2Periph_GPIOF"
    gpio_mode_out = "GPIO_Mode_OUT" if family == "F407" else "GPIO_Mode_Out_PP"
    gpio_otype_line = "GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;\n" if family == "F407" else ""

    # delay.h
    _write_file(os.path.join(inc_dir, "delay.h"), f"""#ifndef __DELAY_H
#define __DELAY_H

#include "{header}"

void Delay_Init(void);
void Delay_ms(uint32_t nTime);
void Delay_us(uint32_t nTime);
void Delay_s(uint32_t nTime);

#endif
""")

    # delay.c
    _write_file(os.path.join(src_dir, "delay.c"), f"""/**
*****************************************************************************
*
*  @file    delay.c
*  @brief   利用系统时钟中断实现延时函数
*
*  @author  stm32-keil skill
*  @date    2026/5/23
*  @version 1.0
*
*****************************************************************************
**/

#include "delay.h"

static __IO uint32_t TimingDelay;

void Delay_Init(void)
{{
    SysTick_Config(SystemCoreClock / 1000000);
}}

void TimingDelay_Decrement(void)
{{
    if (TimingDelay != 0)
        TimingDelay--;
}}

void Delay_us(uint32_t nTime)
{{
    TimingDelay = nTime;
    while (TimingDelay != 0);
}}

void Delay_ms(uint32_t nTime)
{{
    TimingDelay = nTime * 1000;
    while (TimingDelay != 0);
}}

void Delay_s(uint32_t nTime)
{{
    TimingDelay = nTime * 1000000;
    while (TimingDelay != 0);
}}
""")

    # GPIO.h
    _write_file(os.path.join(inc_dir, "GPIO.h"), f"""#ifndef __GPIO_H
#define __GPIO_H

#include "{header}"

#define PAout(x) Config_GPIO(GPIOA, 1 << x, GPIO_MODE_OUTPUT)
#define PBout(x) Config_GPIO(GPIOB, 1 << x, GPIO_MODE_OUTPUT)
#define PCout(x) Config_GPIO(GPIOC, 1 << x, GPIO_MODE_OUTPUT)
#define PDout(x) Config_GPIO(GPIOD, 1 << x, GPIO_MODE_OUTPUT)
#define PEout(x) Config_GPIO(GPIOE, 1 << x, GPIO_MODE_OUTPUT)
#define PFout(x) Config_GPIO(GPIOF, 1 << x, GPIO_MODE_OUTPUT)
#define PGout(x) Config_GPIO(GPIOG, 1 << x, GPIO_MODE_OUTPUT)

#define PAin(x) Config_GPIO(GPIOA, 1 << x, GPIO_MODE_INPUT)
#define PBin(x) Config_GPIO(GPIOB, 1 << x, GPIO_MODE_INPUT)
#define PCin(x) Config_GPIO(GPIOC, 1 << x, GPIO_MODE_INPUT)
#define PDin(x) Config_GPIO(GPIOD, 1 << x, GPIO_MODE_INPUT)
#define PEin(x) Config_GPIO(GPIOE, 1 << x, GPIO_MODE_INPUT)
#define PFin(x) Config_GPIO(GPIOF, 1 << x, GPIO_MODE_INPUT)
#define PGin(x) Config_GPIO(GPIOG, 1 << x, GPIO_MODE_INPUT)

typedef enum {{
    GPIO_MODE_INPUT,
    GPIO_MODE_OUTPUT
}} GPIO_Mode_TypeDef;

void Config_GPIO(GPIO_TypeDef* GPIOx, uint16_t GPIO_Pin, GPIO_Mode_TypeDef Mode);
void Set_GPIO_High(GPIO_TypeDef* GPIOx, uint16_t GPIO_Pin);
void Set_GPIO_Low(GPIO_TypeDef* GPIOx, uint16_t GPIO_Pin);

#endif
""")

    # GPIO.c
    clock_lines = _generate_gpio_clock_lines(family)
    _write_file(os.path.join(src_dir, "GPIO.c"), f"""/**
*****************************************************************************
*
*  @file    GPIO.c
*  @brief   通用GPIO配置
*
*  @author  stm32-keil skill
*  @date    2026/5/23
*  @version 1.0
*
*****************************************************************************
**/

#include "{header}"
#include "GPIO.h"

void Config_GPIO(GPIO_TypeDef* GPIOx, uint16_t GPIO_Pin, GPIO_Mode_TypeDef Mode)
{{
{clock_lines}

    GPIO_InitTypeDef GPIO_InitStructure;
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;
{gpio_otype_line}
    if (Mode == GPIO_MODE_OUTPUT)
        GPIO_InitStructure.GPIO_Mode = {gpio_mode_out};
    else
        GPIO_InitStructure.GPIO_Mode = GPIO_Mode_IN;

    GPIO_Init(GPIOx, &GPIO_InitStructure);
}}

void Set_GPIO_High(GPIO_TypeDef* GPIOx, uint16_t GPIO_Pin)
{{
    GPIO_SetBits(GPIOx, GPIO_Pin);
}}

void Set_GPIO_Low(GPIO_TypeDef* GPIOx, uint16_t GPIO_Pin)
{{
    GPIO_ResetBits(GPIOx, GPIO_Pin);
}}
""")

    # led.h
    gpio_clk, gpio_port = ("RCC_AHB1Periph_GPIOF", "GPIOF") if family == "F407" else ("RCC_APB2Periph_GPIOF", "GPIOF")
    _write_file(os.path.join(inc_dir, "led.h"), f"""#ifndef __LED_H
#define __LED_H

#include "{header}"

#define LED1_PIN             GPIO_Pin_7
#define LED1_PORT            {gpio_port}
#define LED1_CLK             {gpio_clk}

#define LED1_ON       GPIO_ResetBits(LED1_PORT, LED1_PIN)
#define LED1_OFF      GPIO_SetBits(LED1_PORT, LED1_PIN)
#define LED1_Toggle   GPIO_ToggleBits(LED1_PORT, LED1_PIN)

void LED_Init(void);

#endif
""")

    # led.c
    _write_file(os.path.join(src_dir, "led.c"), f"""/**
*****************************************************************************
*
*  @file    led.c
*  @brief   LED指示灯初始化
*
*  @author  stm32-keil skill
*  @date    2026/5/23
*  @version 1.0
*
*****************************************************************************
**/

#include "led.h"

void LED_Init(void)
{{
    GPIO_InitTypeDef GPIO_InitStructure;
    RCC_AHB1PeriphClockCmd(LED1_CLK, ENABLE);

    GPIO_InitStructure.GPIO_Mode = {gpio_mode_out};
    GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_2MHz;
{gpio_otype_line}
    GPIO_InitStructure.GPIO_Pin = LED1_PIN;
    GPIO_Init(LED1_PORT, &GPIO_InitStructure);

    GPIO_ResetBits(LED1_PORT, LED1_PIN);
}}
""")

    # USART.h
    _write_file(os.path.join(inc_dir, "USART.h"), f"""#ifndef __USART_H
#define __USART_H

#include "{header}"
#include <stdio.h>

void USART1_Init(uint32_t baud_rate);
int fputc(int ch, FILE* f);

#endif
""")

    # USART.c (uses printf retarget)
    rcc_usart1 = "RCC_APB2Periph_USART1" if family == "F407" else "RCC_APB2Periph_USART1"
    rcc_gpioa = "RCC_AHB1Periph_GPIOA" if family == "F407" else "RCC_APB2Periph_GPIOA"
    _write_file(os.path.join(src_dir, "USART.c"), f"""/**
*****************************************************************************
*
*  @file    USART.c
*  @brief   USART1初始化和printf重定向
*
*  @author  stm32-keil skill
*  @date    2026/5/23
*  @version 1.0
*
*****************************************************************************
**/

#include "USART.h"

void USART1_Init(uint32_t baud_rate)
{{
    GPIO_InitTypeDef GPIO_InitStructure;
    USART_InitTypeDef USART_InitStructure;

    RCC_AHB1PeriphClockCmd({rcc_gpioa}, ENABLE);
    RCC_APB2PeriphClockCmd({rcc_usart1}, ENABLE);

    GPIO_PinAFConfig(GPIOA, GPIO_PinSource9, GPIO_AF_USART1);
    GPIO_PinAFConfig(GPIOA, GPIO_PinSource10, GPIO_AF_USART1);

    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_9 | GPIO_Pin_10;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AF;
    GPIO_InitStructure.GPIO_OType = GPIO_OType_PP;
    GPIO_InitStructure.GPIO_PuPd = GPIO_PuPd_UP;
    GPIO_InitStructure.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    USART_InitStructure.USART_BaudRate = baud_rate;
    USART_InitStructure.USART_WordLength = USART_WordLength_8b;
    USART_InitStructure.USART_StopBits = USART_StopBits_1;
    USART_InitStructure.USART_Parity = USART_Parity_No;
    USART_InitStructure.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
    USART_InitStructure.USART_Mode = USART_Mode_Rx | USART_Mode_Tx;
    USART_Init(USART1, &USART_InitStructure);

    USART_Cmd(USART1, ENABLE);
}}

int fputc(int ch, FILE* f)
{{
    while (USART_GetFlagStatus(USART1, USART_FLAG_TXE) == RESET);
    USART_SendData(USART1, (uint8_t)ch);
    return ch;
}}
""")


def _generate_gpio_clock_lines(family: str) -> str:
    """Generate GPIO clock enable lines for each port."""
    ports = ["GPIOA", "GPIOB", "GPIOC", "GPIOD", "GPIOE", "GPIOF", "GPIOG"]
    if family == "F407":
        periph = {"GPIOA": "RCC_AHB1Periph_GPIOA", "GPIOB": "RCC_AHB1Periph_GPIOB",
                   "GPIOC": "RCC_AHB1Periph_GPIOC", "GPIOD": "RCC_AHB1Periph_GPIOD",
                   "GPIOE": "RCC_AHB1Periph_GPIOE", "GPIOF": "RCC_AHB1Periph_GPIOF",
                   "GPIOG": "RCC_AHB1Periph_GPIOG"}
        func = "RCC_AHB1PeriphClockCmd"
    else:
        periph = {"GPIOA": "RCC_APB2Periph_GPIOA", "GPIOB": "RCC_APB2Periph_GPIOB",
                   "GPIOC": "RCC_APB2Periph_GPIOC", "GPIOD": "RCC_APB2Periph_GPIOD",
                   "GPIOE": "RCC_APB2Periph_GPIOE", "GPIOF": "RCC_APB2Periph_GPIOF",
                   "GPIOG": "RCC_APB2Periph_GPIOG"}
        func = "RCC_APB2PeriphClockCmd"

    lines = []
    for i, port in enumerate(ports):
        cond = "if" if i == 0 else "else if"
        lines.append(f"    {cond}(GPIOx == {port}) {func}({periph[port]}, ENABLE);")
    return "\n".join(lines)


def _generate_hal_user_files(skeleton_dir: str, family: str) -> None:
    """Generate User files for a HAL-based project (main.c, *_it.c, *_hal_msp.c, *_hal_conf.h).

    Minimal but compileable: blinks a LED on PA5 (commonly available)
    and starts SysTick + HSI clock (no HSE assumption)."""
    user_dir = os.path.join(skeleton_dir, "User")
    ensure_dir(user_dir)
    hp = _hal_prefix(family)

    # *_hal_conf.h — minimal HAL configuration.
    # The conf header must include the CMSIS device header (stm32f4xx.h etc)
    # BEFORE the module-specific headers, so that __IO, uint32_t etc are defined.
    enabled = ["GPIO", "RCC", "CORTEX", "UART", "PWR", "FLASH", "DMA"]
    lines = ["/* Auto-generated minimal HAL configuration */",
             f"#ifndef __{hp.upper()}_HAL_CONF_H__",
             f"#define __{hp.upper()}_HAL_CONF_H__",
             "",
             "#ifdef __cplusplus",
             "extern \"C\" {",
             "#endif",
             "",
             "/* Includes (CMSIS device must come first) */",
             f"#include \"{hp}.h\"",
             "",
             "/* ########################## Assert Selection ############################ */",
             "/**",
             "  * @brief Uncomment the line below to enable full assertion in HAL drivers.",
             "  */",
             "/* #define USE_FULL_ASSERT    1U */",
             "",
             "#ifdef  USE_FULL_ASSERT",
             "  #define assert_param(expr) ((expr) ? (void)0U : assert_failed((uint8_t *)__FILE__, __LINE__))",
             "  void assert_failed(uint8_t* file, uint32_t line);",
             "#else",
             "  #define assert_param(expr) ((void)0U)",
             "#endif /* USE_FULL_ASSERT */",
             ""]
    # Module enables
    for m in enabled:
        lines.append(f"#define HAL_{m}_MODULE_ENABLED")
    lines.append("")
    # System clock values (needed by HAL RCC)
    lines.append("/* Exported constants (tick & timeout values) */")
    lines.append("#define TICK_INT_PRIORITY            0x0FU")
    lines.append("#define HSE_STARTUP_TIMEOUT          100U")
    lines.append("#define LSE_STARTUP_TIMEOUT          5000U")
    lines.append("")
    lines.append("/* Clock values */")
    lines.append("#if !defined(HSE_VALUE)")
    lines.append("#define HSE_VALUE    8000000U")
    lines.append("#endif")
    lines.append("#if !defined(HSI_VALUE)")
    lines.append("#define HSI_VALUE    16000000U")
    lines.append("#endif")
    lines.append("#if !defined(LSE_VALUE)")
    lines.append("#define LSE_VALUE    32768U")
    lines.append("#endif")
    lines.append("#if !defined(LSI_VALUE)")
    lines.append("#define LSI_VALUE    32000U")
    lines.append("#endif")
    lines.append("#if !defined(EXTERNAL_CLOCK_VALUE)")
    lines.append("#define EXTERNAL_CLOCK_VALUE 25000000U")
    lines.append("#endif")
    lines.append("")
    # Include module headers (DMA before UART — UART depends on DMA)
    # Order matters: some HAL headers depend on others being included first
    module_order = ["GPIO", "RCC", "CORTEX", "PWR", "FLASH", "DMA", "UART"]
    for m in module_order:
        m_lower = m.lower()
        if m == "CORTEX":
            lines.append(f"#include \"{hp}_hal_cortex.h\"")
        elif m == "UART":
            lines.append(f"#include \"{hp}_hal_uart.h\"")
        elif m == "DMA":
            lines.append(f"#include \"{hp}_hal_dma.h\"")
        else:
            lines.append(f"#include \"{hp}_hal_{m_lower}.h\"")
    lines.append("")
    lines.append("#ifdef __cplusplus")
    lines.append("}")
    lines.append("#endif")
    lines.append("")
    lines.append(f"#endif /* __{hp.upper()}_HAL_CONF_H__ */")
    conf = "\n".join(lines) + "\n"
    _write_file(os.path.join(user_dir, f"{hp}_hal_conf.h"), conf)

    # main.c
    led_port, led_pin, clk_macro = "GPIOA", "GPIO_PIN_5", "__HAL_RCC_GPIOA_CLK_ENABLE"
    _write_file(os.path.join(user_dir, "main.c"), f"""/**
  * @file    main.c
  * @brief   HAL minimal template (LED blink on {led_port} pin {led_pin})
  */
#include "{hp}_hal.h"

static void SystemClock_Config(void);

int main(void)
{{
    HAL_Init();
    SystemClock_Config();

    {clk_macro}();
    GPIO_InitTypeDef g = {{0}};
    g.Pin = {led_pin};
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Pull = GPIO_NOPULL;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init({led_port}, &g);

    while (1)
    {{
        HAL_GPIO_TogglePin({led_port}, {led_pin});
        HAL_Delay(500);
    }}
}}

static void SystemClock_Config(void)
{{
    /* Use HSI by default. Replace with HSE+PLL for production. */
    __HAL_RCC_PWR_CLK_ENABLE();
    RCC_OscInitTypeDef oi = {{0}};
    oi.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    oi.HSIState = RCC_HSI_ON;
    oi.PLL.PLLState = RCC_PLL_NONE;
    HAL_RCC_OscConfig(&oi);

    RCC_ClkInitTypeDef ci = {{0}};
    ci.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                   RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    ci.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
    ci.AHBCLKDivider = RCC_SYSCLK_DIV1;
    ci.APB1CLKDivider = RCC_HCLK_DIV1;
    ci.APB2CLKDivider = RCC_HCLK_DIV1;
    HAL_RCC_ClockConfig(&ci, FLASH_LATENCY_0);
}}
""")

    # *_hal_msp.c
    _write_file(os.path.join(user_dir, f"{hp}_hal_msp.c"), f"""#include "{hp}_hal.h"

void HAL_MspInit(void)
{{
    __HAL_RCC_SYSCFG_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();
}}
""")

    # *_it.c — minimal handlers + SysTick
    _write_file(os.path.join(user_dir, f"{hp}_it.c"), f"""#include "{hp}_hal.h"

void NMI_Handler(void) {{}}
void HardFault_Handler(void) {{ while (1); }}
void MemManage_Handler(void) {{ while (1); }}
void BusFault_Handler(void) {{ while (1); }}
void UsageFault_Handler(void) {{ while (1); }}
void SVC_Handler(void) {{}}
void DebugMon_Handler(void) {{}}
void PendSV_Handler(void) {{}}

void SysTick_Handler(void)
{{
    HAL_IncTick();
}}
""")


def _generate_user_files(skeleton_dir: str, family: str) -> None:
    """Generate User layer source files."""
    user_dir = os.path.join(skeleton_dir, "User")
    ensure_dir(user_dir)

    header = "stm32f4xx.h" if family == "F407" else "stm32f10x.h"
    prefix = "stm32f4xx" if family == "F407" else "stm32f10x"
    is_f4 = (family == "F407")

    # conf.h
    conf_lines = [f'#include "{header}"']
    spl_dir = "STM32F4xx_StdPeriph_Driver" if is_f4 else "STM32F10x_StdPeriph_Driver"
    modules = ["rcc", "gpio", "usart", "exti", "tim", "spi", "i2c", "adc", "dma", "syscfg"]
    for mod in modules:
        conf_lines.append(f'#include "../STM32/{spl_dir}/inc/{prefix}_{mod}.h"')
    _write_file(os.path.join(user_dir, f"{prefix}_conf.h"),
                "\n".join(conf_lines) + "\n")

    # it.h
    _write_file(os.path.join(user_dir, f"{prefix}_it.h"), f"""#ifndef __{prefix.upper()}_IT_H
#define __{prefix.upper()}_IT_H

void NMI_Handler(void);
void HardFault_Handler(void);
void MemManage_Handler(void);
void BusFault_Handler(void);
void UsageFault_Handler(void);
void SVC_Handler(void);
void DebugMon_Handler(void);
void PendSV_Handler(void);
void SysTick_Handler(void);

#endif
""")

    # it.c
    _write_file(os.path.join(user_dir, f"{prefix}_it.c"), f"""/**
*****************************************************************************
*
*  @file    {prefix}_it.c
*  @brief   中断服务函数
*
*  @author  stm32-keil skill
*  @date    2026/5/23
*  @version 1.0
*
*****************************************************************************
**/

#include "{prefix}_it.h"

void NMI_Handler(void) {{}}
void HardFault_Handler(void) {{ while (1); }}
void MemManage_Handler(void) {{ while (1); }}
void BusFault_Handler(void) {{ while (1); }}
void UsageFault_Handler(void) {{ while (1); }}
void SVC_Handler(void) {{}}
void DebugMon_Handler(void) {{}}
void PendSV_Handler(void) {{}}

extern void TimingDelay_Decrement(void);

void SysTick_Handler(void)
{{
    TimingDelay_Decrement();
}}
""")

    # main.c
    _write_file(os.path.join(user_dir, "main.c"), f"""/**
*****************************************************************************
*
*  @file    main.c
*  @brief   主程序
*
*  @author  stm32-keil skill
*  @date    2026/5/23
*  @version 1.0
*
*****************************************************************************
**/

#include "{header}"
#include <stdio.h>
#include "delay.h"
#include "GPIO.h"
#include "USART.h"
#include "led.h"

int main(void)
{{
    Delay_Init();
    USART1_Init(115200);
    LED_Init();

    printf("System initialized.\\r\\n");

    while (1)
    {{
        LED1_Toggle;
        Delay_ms(500);
    }}
}}
""")


# ─── helpers ──────────────────────────────────────────────────────────

def _write_file(path: str, content: str) -> None:
    """Write content to file, ensuring directory exists.

    Keil project files (.uvprojx/.uvoptx) use CRLF for Windows compatibility.
    Source files (.c/.h) use system default line endings so they work with
    both Keil (Windows) and GCC (Linux/macOS).
    """
    ensure_dir(os.path.dirname(path))
    if path.endswith((".uvprojx", ".uvoptx")):
        newline = "\r\n"
    else:
        newline = None  # use system default
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(content)


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download STM32 project template")
    parser.add_argument("--family", required=True,
                        choices=["F103", "F407", "F411", "F429", "G4", "L4", "H7", "C0"],
                        help="Chip family to fetch template for")
    parser.add_argument("--library", default="SPL", choices=["SPL", "HAL"],
                        help="Peripheral library variant (default: SPL)")
    parser.add_argument("--skill-dir", default=None,
                        help="Skill directory (auto-detected if omitted)")
    args = parser.parse_args()

    result = fetch_template(args.family, args.skill_dir, args.library)
    if result["success"]:
        print(f"\nTemplate ready: {result['skeleton_path']}")
    else:
        print(f"\nError: {result['error']}")
        sys.exit(1)
