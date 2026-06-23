"""
Create a new Keil project from skeleton template or CubeMX.
"""
import os
import sys
import re
import shutil
import json
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import ensure_dir, load_chip_db, get_chip_family, normalize_path
from uvprojx_modifier import modify_device, rename_project, read_current_config, enable_reset_and_run
from utils import ensure_dir, load_chip_db, normalize_path
from uvprojx_modifier import modify_device, rename_project, enable_reset_and_run
from skeleton_manager import get_skeleton_path
from template_fetcher import fetch_template


def create_project(
    chip: str,
    project_name: str,
    project_dir: str,
    library: str = "HAL",
    use_cubemx: bool = False,
    smoke_build: bool = False,
    peripherals: Optional[List[str]] = None
) -> Dict:
    """
    Create a new Keil project from skeleton or CubeMX.

    Args:
        chip: Chip model (e.g., STM32F407ZGT6)
        project_name: Project name
        project_dir: Parent directory for the project
        library: "SPL" or "HAL"
        use_cubemx: If True, try CubeMX headless generation first
        smoke_build: Run a test build immediately after creation
        peripherals: List of peripherals to enable in HAL
    """
    skill_dir = str(Path(__file__).resolve().parent.parent)

    # Validate chip
    db = load_chip_db(None)
    if chip not in db:
        return {
            "success": False,
            "error": f"Unknown chip: {chip}. Available: {', '.join(db.keys())}"
        }

    chip_info = dict(db[chip])
    chip_info["library"] = library
    family = chip_info["family"]
    use_hal = (library.upper() == "HAL")

    # Check if project directory is empty
    full_project_path = os.path.join(project_dir, project_name)
    if os.path.isdir(full_project_path) and os.listdir(full_project_path):
        return {
            "success": False,
            "error": f"Directory {full_project_path} is not empty. Please choose a different name or path."
        }

    # If user wants CubeMX or chip is HAL-only and skeleton not ready, try CubeMX
    cubemx_result = None
    if use_cubemx and use_hal:
        try:
            from cubemx_project_gen import generate_project as cubemx_generate
            cubemx_result = cubemx_generate(chip, project_name, project_dir)
        except Exception as e:
            cubemx_result = {"success": False, "error": str(e)}

    if cubemx_result and cubemx_result.get("success"):
        final_result = cubemx_result
        final_result["library"] = library
        _maybe_generate_ioc_reference(full_project_path, project_name, chip, chip_info, skill_dir)
        return final_result

    if cubemx_result:
        print(f"CubeMX generation failed: {cubemx_result.get('error', 'unknown error')}")
        print("Falling back to skeleton template...")

    # Find skeleton
    skeleton_path = get_skeleton_path(family, skill_dir, library)
    if not os.path.isdir(skeleton_path):
        print(f"No skeleton found for {family}/{library}, downloading from ST GitHub...")
        result = fetch_template(family, skill_dir, library)
        if not result["success"]:
            return {
                "success": False,
                "error": f"Failed to download template for {family} ({library}): {result['error']}"
            }
        skeleton_path = get_skeleton_path(family, skill_dir, library)

    # Copy skeleton
    ensure_dir(full_project_path)
    _copy_skeleton(skeleton_path, full_project_path)

    # Dynamically enable peripherals in hal_conf.h if requested
    if peripherals and library == "HAL":
        _enable_hal_peripherals(full_project_path, family, peripherals)

    # Fix any absolute paths in .uvprojx / .uvoptx carried over from skeleton
    _fix_absolute_paths(full_project_path)

    uvprojx_files = list(Path(full_project_path).rglob("*.uvprojx"))
    if not uvprojx_files:
        return {"success": False, "error": "No .uvprojx found in skeleton"}

    old_uvprojx = str(uvprojx_files[0])
    proj_subdir = os.path.dirname(old_uvprojx)

    # Rename .uvprojx / .uvoptx
    new_uvprojx = _rename_in_dir(proj_subdir, project_name)

    if new_uvprojx and os.path.isfile(new_uvprojx):
        modify_device(new_uvprojx, chip, None)
        rename_project(new_uvprojx, project_name)

        uvoptx_path = os.path.splitext(new_uvprojx)[0] + ".uvoptx"
        if os.path.isfile(uvoptx_path):
            _update_uvoptx_targetname(uvoptx_path, project_name)

    _generate_readme(os.path.join(full_project_path, "README.md"), project_name, chip, chip_info)

    enable_reset_and_run(full_project_path)

    if use_hal:
        _maybe_generate_ioc_reference(full_project_path, project_name, chip, chip_info, skill_dir)

    final_uvprojx = new_uvprojx if (new_uvprojx and os.path.isfile(new_uvprojx)) else old_uvprojx

    return {
        "success": True,
        "project_path": normalize_path(full_project_path),
        "uvprojx_path": normalize_path(final_uvprojx),
        "chip": chip,
        "family": family,
        "library": library,
        "cubemx_available": _check_cubemx_available(),
        "error": None,
    }

def _enable_hal_peripherals(project_dir: str, family: str, peripherals: List[str]) -> None:
    """Uncomment HAL_xxx_MODULE_ENABLED and #include in the hal_conf.h based on user requested peripherals."""
    conf_name = f"stm32{family.lower()[:2]}xx_hal_conf.h"
    search_dirs = [os.path.join(project_dir, "User"), os.path.join(project_dir, "Core", "Inc")]
    conf_path = None
    for d in search_dirs:
        p = os.path.join(d, conf_name)
        if os.path.exists(p):
            conf_path = p
            break
            
    if not conf_path:
        return
        
    with open(conf_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    for p in peripherals:
        mod_name = p.upper().strip()
        if mod_name.startswith("HAL_") and mod_name.endswith("_MODULE_ENABLED"):
            def_str = mod_name
            mod_prefix = mod_name.split("_MODULE")[0].lower()
        else:
            def_str = f"HAL_{mod_name}_MODULE_ENABLED"
            mod_prefix = f"hal_{mod_name.lower()}"
            
        mod_prefix = mod_prefix.replace("hal_", f"stm32{family.lower()[:2]}xx_hal_")
        
        # Uncomment #define if it exists but is commented
        content = re.sub(rf'//\s*(#define\s+{def_str})', r'\1', content)
        # Uncomment #include if it exists
        inc_str = f'#include "{mod_prefix}.h"'
        content = re.sub(rf'//\s*(#include\s+"{mod_prefix}\.h")', r'\1', content)
        
    with open(conf_path, 'w', encoding='utf-8') as f:
        f.write(content)



def _copy_skeleton(src: str, dst: str) -> None:
    """Copy skeleton directory to project directory."""
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)


def _fix_absolute_paths(project_dir: str) -> None:
    """Convert any absolute Windows paths in .uvprojx and .uvoptx to relative
    paths.  Skeletons sometimes carry over absolute paths from the machine
    they were created on (e.g. D:\\workspace_for_claude\\...\\User\\main.c).
    Without this fix the project opens with broken file references on any
    other machine."""
    # Search in both Project/ subdir (old layout) and root (new layout)
    search_dirs = [os.path.join(project_dir, "Project"), project_dir]
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for fname in os.listdir(search_dir):
            if not (fname.endswith(".uvprojx") or fname.endswith(".uvoptx")):
                continue
            full = os.path.join(search_dir, fname)
            _fix_paths_in_xml(full)


def _fix_paths_in_xml(xml_path: str) -> None:
    """Fix absolute paths in a single .uvprojx or .uvoptx file."""
    try:
        tree = ET.parse(xml_path)
    except Exception as e:
        warnings.warn(f"Failed to parse {xml_path}: {e}")
        return
    root = tree.getroot()
    changed = False
    for tag in ("FilePath", "PathWithFileName", "Filename"):
        for elem in root.iter(tag):
            if elem.text and _is_abs_windows_path(elem.text):
                rel = _abs_to_rel_path(elem.text)
                if rel:
                    elem.text = rel
                    changed = True
    if changed:
        tree.write(xml_path, encoding="UTF-8", xml_declaration=True)


def _is_abs_windows_path(p: str) -> bool:
    """Match patterns like C:\\... or D:/..."""
    return bool(re.match(r"^[A-Za-z]:[\\/]", p))


def _abs_to_rel_path(abs_path: str) -> Optional[str]:
    """Convert an absolute path to a relative path from the project's
    .uvprojx directory.

    Looks for known top-level project subdirectories and rewrites the path
    relative to the directory holding the .uvprojx (which can be either
    User/ or Project/). Returns None if the path cannot be converted.
    """
    p = abs_path.replace("/", "\\")
    # Vendor (正点原子): USER/CORE/FWLIB/SYSTEM/HARDWARE/STM32F10x_FWLib/OBJ
    # Generated layout: User/Drive/STM32/Project
    top_dirs = [
        "USER", "User",
        "CORE", "Core",
        "FWLIB", "STM32F10x_FWLib",
        "SYSTEM", "System",
        "HARDWARE", "Hardware",
        "OBJ", "Obj",
        "Drive", "STM32", "Project",
    ]
    for top_dir in top_dirs:
        marker = f"\\{top_dir}\\"
        idx = p.lower().find(marker.lower())
        if idx >= 0:
            rest = p[idx + len(marker):]
            return f"..\\{top_dir}\\{rest}"
    return None


def _rename_in_dir(proj_subdir: str, new_name: str) -> str:
    """Rename any .uvprojx/.uvoptx in `proj_subdir` to {new_name}.uvprojx/.uvoptx.
    Returns the path of the renamed .uvprojx (empty string on failure)."""
    new_uvprojx = ""
    if not os.path.isdir(proj_subdir):
        return ""
    for fname in os.listdir(proj_subdir):
        full = os.path.join(proj_subdir, fname)
        if not os.path.isfile(full):
            continue
        if fname.endswith(".uvprojx"):
            dest = os.path.join(proj_subdir, f"{new_name}.uvprojx")
            if full != dest:
                os.replace(full, dest)
            new_uvprojx = dest
        elif fname.endswith(".uvoptx"):
            dest = os.path.join(proj_subdir, f"{new_name}.uvoptx")
            if full != dest:
                os.replace(full, dest)
        elif fname.endswith(".uvguix") or ".uvguix." in fname:
            # Keil-generated per-user GUI state; safe to delete to avoid
            # confusion from old usernames.
            try:
                os.remove(full)
            except OSError:
                pass
    return new_uvprojx


def _update_uvoptx_targetname(uvoptx_path: str, name: str) -> None:
    """Update TargetName in .uvoptx to match project name, ensuring
    debugger settings (ST-Link) are properly associated with the target."""
    try:
        tree = ET.parse(uvoptx_path)
        root = tree.getroot()
        target = root.find(".//Target")
        if target is not None:
            tn = target.find("TargetName")
            if tn is not None:
                tn.text = name
                tree.write(uvoptx_path, encoding="UTF-8", xml_declaration=True)
    except Exception as e:
        warnings.warn(f"Failed to update {uvoptx_path}: {e}")


def _generate_readme(readme_path: str, name: str, chip: str, chip_info: Dict) -> None:
    flash_kb = int(chip_info["flash_size"], 16) // 1024
    ram_kb = int(chip_info["ram_size"], 16) // 1024
    family = chip_info["family"]
    core = chip_info["core"]
    fpu = "有" if chip_info.get("has_fpu", False) else "无"
    library = chip_info.get("library", "SPL")
    proj_dir = os.path.dirname(readme_path)

    # Detect structure: old (Project/ subdir) vs new (uvprojx at root)
    has_project_subdir = os.path.isdir(os.path.join(proj_dir, "Project"))
    uvprojx_rel = f"Project/{name}.uvprojx" if has_project_subdir else f"{name}.uvprojx"

    if has_project_subdir:
        tree_block = f"""{name}/
├── Project/     # Keil 工程文件 ({name}.uvprojx)
├── User/        # 用户代码 (main.c, 中断, 配置头)
├── Drive/       # 用户外设驱动层 (.c/.h)
└── STM32/       # CMSIS + {library} 库"""
    else:
        tree_block = f"""{name}/
├── {name}.uvprojx   # Keil 工程文件
├── Hardware/    # 外设驱动 (.c/.h)
├── Library/     # {library} 库
├── Start/       # 启动文件 + CMSIS
├── System/      # 系统层 (Delay, USART)
└── User/        # 用户代码 (main.c, 中断, 配置头)"""

    content = f"""# {name}

## 芯片信息
- **型号**: {chip}
- **系列**: {family}
- **内核**: {core}
- **Flash**: {flash_kb}KB
- **RAM**: {ram_kb}KB
- **FPU**: {fpu}
- **库**: {library}

## 引脚分配
> 由 stm32-keil skill 在确认引脚后填入。

| 外设 | 引脚 | 端口 | 说明 |
|------|------|------|------|
| _待填_ | | | |

## 工程结构
```
{tree_block}
```

## 编译与烧录

### 编译
在 Keil MDK-ARM v5 中打开 `{uvprojx_rel}`，按 **F7** 编译；
或在命令行：
```
uv4.exe -j0 -b {uvprojx_rel}
```

### 烧录
通过 ST-Link / J-Link / DFU 烧录。在 Keil 中按 **F8**，或：
```
python scripts/flasher.py --project {uvprojx_rel}
```

## 自动生成
此工程由 **stm32-keil skill** 自动生成。
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)


def _check_cubemx_available() -> bool:
    """Quick check if CubeMX is installed."""
    try:
        from cubemx_finder import find_cubemx
        return find_cubemx() is not None
    except Exception:
        return False


def _maybe_generate_ioc_reference(
    project_dir: str, name: str, chip: str, chip_info: Dict,
    skill_dir: Optional[str] = None,
) -> None:
    """Generate a .ioc file for HAL projects so users can open it in CubeMX
    to configure peripherals/clocks later. Does not overwrite existing .ioc."""
    ioc_path = os.path.join(project_dir, f"{name}.ioc")
    if os.path.isfile(ioc_path):
        return

    cubemx_name = chip_info.get("cubemx_name")
    cubemx_package = chip_info.get("cubemx_package")
    family = chip_info.get("family", "")

    if not cubemx_name or not cubemx_package:
        # Try to resolve at runtime
        try:
            from cubemx_mcu_resolver import resolve_cubemx_mcu
            mx_info = resolve_cubemx_mcu(chip)
            if mx_info:
                cubemx_name = mx_info["cubemx_name"]
                cubemx_package = mx_info["cubemx_package"]
                family = mx_info.get("family", family)
        except Exception:
            pass

    if not cubemx_name or not cubemx_package:
        return

    try:
        from cubemx_project_gen import _generate_minimal_ioc
        _generate_minimal_ioc(ioc_path, name, cubemx_name, cubemx_package, family)
        print(f"  Generated .ioc reference: {ioc_path}")
    except Exception as e:
        print(f"  Could not generate .ioc: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a new STM32 Keil project")
    parser.add_argument("--chip", required=True, help="Chip model (e.g., STM32F407ZGT6)")
    parser.add_argument("--name", required=True, help="Project name")
    parser.add_argument("--path", required=True, help="Parent directory for the project")
    parser.add_argument("--library", default="SPL", choices=["SPL", "HAL"],
                        help="Peripheral library: SPL (legacy) or HAL (recommended for new designs)")
    parser.add_argument("--use-cubemx", action="store_true",
                        help="Try CubeMX headless generation for HAL projects (falls back to skeleton)")
    parser.add_argument("--smoke-build", action="store_true", help="Run a test build immediately after creation")
    parser.add_argument("--peripherals", nargs="*", help="List of peripherals to enable in HAL (e.g. TIM ADC SPI)")

    args = parser.parse_args()

    result = create_project(
        chip=args.chip,
        project_name=args.name,
        project_dir=args.path,
        library=args.library,
        use_cubemx=args.use_cubemx,
        smoke_build=args.smoke_build,
        peripherals=args.peripherals
    )
    if result["success"]:
        print(f"Project created: {result['project_path']}")
        print(f"Keil project: {result['uvprojx_path']}")
        print(f"Chip: {result['chip']} ({result['family']}/{result.get('library','SPL')})")
        if args.smoke_build:
            try:
                from keil_builder import compile_project, get_build_summary
                print("\nRunning smoke build...")
                br = compile_project(result["uvprojx_path"], rebuild=False, timeout=180)
                print(get_build_summary(br))
                if not br.success:
                    print("\nSmoke build failed — skeleton may be incomplete.")
                    sys.exit(2)
            except Exception as e:
                print(f"Smoke build skipped: {e}")
    else:
        print(f"Error: {result['error']}")
        sys.exit(1)
