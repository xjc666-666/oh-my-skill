"""
Programmatically modify Keil MDK-ARM v5 .uvprojx XML files.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_chip_db


DEFAULT_STLINK_OPTIONS = (
    '-X"Any" -UAny -O206 -SF4000 -C0 -A0 -I0 -HNlocalhost -HP7184 -P1 '
    '-N00("ARM CoreSight SW-DP") -D00(2BA01477) -L00(0) '
    '-TO131090 -TC10000000 -TT10000000 -TP21 -TDS8007 -TDT0 '
    '-TDC1F -TIEFFFFFFFF -TIP8 -FO15 -WA0 -WE0 -WVCE4 '
    '-WS2710 -WM0 -WP2 -WK0'
)


def read_current_config(uvprojx_path: str) -> Dict[str, Any]:
    """Parse a .uvprojx file and return all key settings as a dict."""
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    ns = {"": ""}
    config = {}

    # Find first target
    target = root.find(".//Target")
    if target is None:
        raise ValueError("No <Target> found in .uvprojx")

    config["target_name"] = target.findtext("TargetName", "")
    config["toolset_number"] = target.findtext("ToolsetNumber", "")
    config["toolset_name"] = target.findtext("ToolsetName", "")

    # Device settings
    tc = target.find(".//TargetCommonOption")
    if tc is not None:
        config["device"] = tc.findtext("Device", "")
        config["vendor"] = tc.findtext("Vendor", "")
        config["pack_id"] = tc.findtext("PackID", "")
        config["cpu"] = tc.findtext("Cpu", "")
        config["flash_driver_dll"] = tc.findtext("FlashDriverDll", "")
        config["svd_file"] = tc.findtext("SFDFile", "")

    # Compiler settings
    cads = target.find(".//Cads")
    if cads is not None:
        vc = cads.find("VariousControls")
        if vc is not None:
            config["defines"] = vc.findtext("Define", "")
            config["include_path"] = vc.findtext("IncludePath", "")
            config["misc_controls"] = vc.findtext("MiscControls", "")

    # uAC6 flag
    config["uac6"] = target.findtext("uAC6", "0")

    # Group structure
    groups = target.find("Groups")
    if groups is not None:
        config["groups"] = []
        for grp in groups.findall("Group"):
            gname = grp.findtext("GroupName", "")
            files = []
            for f in grp.findall(".//File"):
                fn = f.findtext("FileName", "")
                fp = f.findtext("FilePath", "")
                ft = f.findtext("FileType", "1")
                inc = "1"
                cp = f.find(".//IncludeInBuild")
                if cp is not None:
                    inc = cp.text or "1"
                files.append({"name": fn, "path": fp, "type": ft, "include_in_build": inc})
            config["groups"].append({"name": gname, "files": files})

    # Output settings
    config["output_dir"] = target.findtext("OutputDirectory", "")
    config["output_name"] = target.findtext("OutputName", "")
    config["create_hex"] = target.findtext("CreateHexFile", "0")

    # Linker settings
    ldad = target.find(".//LDads")
    if ldad is not None:
        config["scatter_file"] = ldad.findtext("ScatterFile", "")

    return config


def modify_device(uvprojx_path: str, chip_name: str, chip_db_path: Optional[str] = None) -> bool:
    """
    Modify a .uvprojx file to target a specific chip.
    Updates all device-specific fields.
    """
    db = load_chip_db(chip_db_path)
    if chip_name not in db:
        print(f"Error: Chip '{chip_name}' not found in database")
        return False

    chip = dict(db[chip_name])
    chip["flash_driver"] = _normalize_flash_driver(chip)
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        print("Error: No <Target> found")
        return False

    # Update device
    tc = target.find(".//TargetCommonOption")
    if tc is not None:
        _set_or_create(tc, "Device", chip["device"])
        _set_or_create(tc, "PackID", chip["pack_id"])
        _set_or_create(tc, "Cpu", chip["cpu_string"])
        _set_or_create(tc, "FlashDriverDll", chip["flash_driver"])
        _set_or_create(tc, "SFDFile", f"$$Device:{chip['device']}$CMSIS\\SVD\\{chip['svd_file']}")

    # Update preprocessor defines — preserve HAL/SPL choice
    cads = target.find(".//Cads")
    if cads is not None:
        vc = cads.find("VariousControls")
        if vc is not None:
            # Determine if project is HAL-based
            old_defines = vc.findtext("Define", "") or ""
            is_hal = "USE_HAL_DRIVER" in old_defines

            defines = chip["defines"]
            if is_hal:
                # Use hal_device_define if available, otherwise fallback to default behavior
                if "hal_device_define" in chip:
                    hal_device_define = chip["hal_device_define"]
                    defines = f"USE_HAL_DRIVER,{hal_device_define}"
                    # Add other defines (like ARM_MATH_CM4) if present
                    other_defines = [d for d in chip["defines"].split(",") 
                                   if d not in ["USE_STDPERIPH_DRIVER", "USE_HAL_DRIVER"] 
                                   and not d.startswith("STM32F10X_") 
                                   and not d.startswith("STM32F40_41xxx")
                                   and not d.startswith("STM32F411xE")
                                   and not d.startswith("STM32F429_439xx")]
                    if other_defines:
                        defines += "," + ",".join(other_defines)
                else:
                    if "USE_STDPERIPH_DRIVER" in defines:
                        defines = defines.replace("USE_STDPERIPH_DRIVER", "USE_HAL_DRIVER")
                    if "USE_HAL_DRIVER" not in defines:
                        defines = "USE_HAL_DRIVER," + defines
            _set_or_create(vc, "Define", defines)

    # Update DLL simulation arguments
    for dll_el in target.iter():
        if dll_el.tag == "SimDlgDllArguments":
            dll_el.text = chip["sim_dll_args"]

    # Update TargetDllArguments (MPU for CM4, empty for CM3)
    for td in target.iter("TargetDllArguments"):
        if chip.get("has_fpu", False):
            td.text = " -MPU"
        else:
            td.text = ""

    # Update OnChipMemories
    _update_onchip_memories(target, chip)

    # Update IRAM/IROM had flags
    _update_had_flags(target, chip)

    # Write back
    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
    print(f"Device updated to {chip_name}")
    
    # Also update .uvoptx
    uvoptx_path = os.path.splitext(uvprojx_path)[0] + ".uvoptx"
    if os.path.isfile(uvoptx_path):
        _update_uvoptx_device(uvoptx_path, chip)
        
    return True


def _update_uvoptx_device(uvoptx_path: str, chip: Dict) -> None:
    try:
        tree = ET.parse(uvoptx_path)
    except Exception:
        return
    root = tree.getroot()
    chip = dict(chip)
    chip["flash_driver"] = _normalize_flash_driver(chip)
    flash_driver = chip["flash_driver"]
    flash_inner = _flash_driver_inner(flash_driver)
    algorithm_options = _algorithm_options_from_flash_inner(flash_inner)

    target = root.find(".//Target")
    if target is None:
        return

    registry = target.find(".//TargetDriverDllRegistry")
    if registry is None:
        target_option = target.find("TargetOption")
        registry_parent = target_option if target_option is not None else target
        registry = ET.SubElement(registry_parent, "TargetDriverDllRegistry")

    ul2_entry = _get_or_create_setreg_entry(registry, "UL2CM3")
    _set_or_create(ul2_entry, "Number", "0")
    _set_or_create(ul2_entry, "Name", flash_driver)

    st_entry = _get_or_create_setreg_entry(registry, "ST-LINKIII-KEIL_SWO")
    _set_or_create(st_entry, "Number", "0")
    st_name_el = st_entry.find("Name")
    existing_st_name = st_name_el.text if st_name_el is not None and st_name_el.text else ""
    st_name = _merge_stlink_flash_algorithm(existing_st_name, algorithm_options)
    _set_or_create(st_entry, "Name", st_name)

    tree.write(uvoptx_path, encoding="UTF-8", xml_declaration=True)


def ensure_flash_download_config(
    uvprojx_path: str,
    chip_name: Optional[str] = None,
    chip_db_path: Optional[str] = None,
) -> bool:
    """Ensure Keil's Flash Download algorithm exists in both .uvprojx and
    .uvoptx.

    Keil's command-line flash path (`uv4 -f`) uses the ST-Link target-driver
    registry in .uvoptx. It is not enough for .uvprojx to contain
    <FlashDriverDll>; ST-LINKIII-KEIL_SWO must also carry the -FN/-FF/-FS/-FL
    algorithm flags or Keil reports "No Algorithm found for 08000000H".
    """
    chip = _resolve_chip_for_project(uvprojx_path, chip_name, chip_db_path)
    if not chip:
        return False

    chip["flash_driver"] = _normalize_flash_driver(chip)

    try:
        tree = ET.parse(uvprojx_path)
    except Exception:
        return False

    root = tree.getroot()
    target = root.find(".//Target")
    if target is None:
        return False

    tc = target.find(".//TargetCommonOption")
    if tc is not None:
        _set_or_create(tc, "FlashDriverDll", chip["flash_driver"])
        if chip.get("device"):
            _set_or_create(tc, "Device", chip["device"])
        if chip.get("pack_id"):
            _set_or_create(tc, "PackID", chip["pack_id"])
        if chip.get("svd_file"):
            _set_or_create(tc, "SFDFile", f"$$Device:{chip['device']}$CMSIS\\SVD\\{chip['svd_file']}")
        tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)

    uvoptx_path = os.path.splitext(uvprojx_path)[0] + ".uvoptx"
    if os.path.isfile(uvoptx_path):
        _update_uvoptx_device(uvoptx_path, chip)
        return True
    return False


def _resolve_chip_for_project(
    uvprojx_path: str,
    chip_name: Optional[str],
    chip_db_path: Optional[str],
) -> Optional[Dict]:
    db = load_chip_db(chip_db_path)
    if chip_name and chip_name in db:
        return dict(db[chip_name])

    try:
        tree = ET.parse(uvprojx_path)
    except Exception:
        return None

    target = tree.getroot().find(".//Target")
    if target is None:
        return None

    tc = target.find(".//TargetCommonOption")
    project_device = tc.findtext("Device", "") if tc is not None else ""
    project_flash_driver = tc.findtext("FlashDriverDll", "") if tc is not None else ""

    if chip_name:
        for candidate in db.values():
            if _same_keil_device(candidate.get("device", ""), chip_name):
                chip = dict(candidate)
                if project_flash_driver:
                    chip["flash_driver"] = project_flash_driver
                return chip

    for candidate in db.values():
        if _same_keil_device(candidate.get("device", ""), project_device):
            chip = dict(candidate)
            if project_flash_driver:
                chip["flash_driver"] = project_flash_driver
            return chip

    if project_flash_driver:
        return {
            "device": project_device,
            "flash_driver": project_flash_driver,
            "flash_start": "0x08000000",
            "flash_size": "0x00100000",
            "ram_start": "0x20000000",
        }
    return None


def _same_keil_device(left: str, right: str) -> bool:
    return _keil_device_key(left) == _keil_device_key(right)


def _keil_device_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", (value or "").lower())
    return key.rstrip("tx")


def _normalize_flash_driver(chip: Dict) -> str:
    inner = _flash_driver_inner(chip.get("flash_driver", ""))
    inner = _ensure_flash_inner_complete(inner, chip)
    return f"UL2CM3({inner})"


def _flash_driver_inner(flash_driver: str) -> str:
    driver = (flash_driver or "").strip()
    if driver.startswith("UL2CM3("):
        inner = driver[len("UL2CM3("):]
        # Remove the wrapper's final ')' only when the wrapper is balanced.
        if driver.count("(") == driver.count(")") and inner.endswith(")"):
            inner = inner[:-1]
        return inner.strip()
    return driver


def _ensure_flash_inner_complete(inner: str, chip: Dict) -> str:
    options = (inner or "").strip()
    if not options:
        options = "-S0 -C0 -P0"

    if not re.search(r"(?<!\S)-FD[0-9A-Fa-f]+", options):
        options += f" -FD{_hex_without_prefix(chip.get('ram_start', '0x20000000'))}"
    if not re.search(r"(?<!\S)-FC[0-9A-Fa-f]+", options):
        options += " -FC1000"
    if not re.search(r"(?<!\S)-FN\d+", options):
        options += " -FN1"
    if not re.search(r"(?<!\S)-FF0[^\s]+", options):
        options += f" -FF0{_infer_flash_algorithm_name(chip)}"
    if not re.search(r"(?<!\S)-FS0[0-9A-Fa-f]+", options):
        options += f" -FS0{_hex_without_prefix(chip.get('flash_start', '0x08000000'))}"
    if not re.search(r"(?<!\S)-FL0[0-9A-Fa-f]+", options):
        options += f" -FL0{_hex_without_prefix(chip.get('flash_size', '0x00100000'))}"

    ff0_match = re.search(r"(?<!\S)-FF0([^\s]+?)(?:\.FLM)?(?=\s|$)", options, flags=re.IGNORECASE)
    flm_name = ff0_match.group(1) if ff0_match else _infer_flash_algorithm_name(chip)
    flm_name = flm_name[:-4] if flm_name.upper().endswith(".FLM") else flm_name
    fp0_value = f"$$Device:{chip.get('device', '')}$CMSIS\\Flash\\{flm_name}.FLM"

    if re.search(r"(?<!\S)-FP0\([^)]*\)", options):
        options = re.sub(
            r"(?<!\S)-FP0\([^)]*\)",
            lambda _m: f"-FP0({fp0_value})",
            options,
        )
    else:
        options += f" -FP0({fp0_value})"

    return _squash_spaces(options)


def _infer_flash_algorithm_name(chip: Dict) -> str:
    family = str(chip.get("family", "")).upper()
    flash_kb = _flash_kb(chip.get("flash_size", "0x00100000"))

    if family.startswith("F103"):
        if flash_kb <= 32:
            return "STM32F10x_32"
        if flash_kb <= 128:
            return "STM32F10x_128"
        return "STM32F10x_512"
    if family.startswith(("F4", "F407", "F411", "F429")):
        return "STM32F4xx_512" if flash_kb <= 512 else "STM32F4xx_1024"
    if family == "G4":
        return "STM32G4xx_128" if flash_kb <= 128 else "STM32G4xx_512"
    if family == "L4":
        if flash_kb <= 256:
            return "STM32L4xx_256"
        if flash_kb <= 512:
            return "STM32L4xx_512"
        return "STM32L4xx_1024"
    if family == "H7":
        return "STM32H7x_128" if flash_kb <= 128 else "STM32H7x_2048"
    if family == "C0":
        return "STM32C0xx_16" if flash_kb <= 16 else "STM32C0xx_32"
    return "STM32F4xx_1024"


def _flash_kb(value: str) -> int:
    try:
        return int(str(value), 16) // 1024
    except ValueError:
        return 1024


def _hex_without_prefix(value: str) -> str:
    try:
        return f"{int(str(value), 16):08X}"
    except ValueError:
        return str(value).replace("0x", "").replace("0X", "").upper()


def _algorithm_options_from_flash_inner(inner: str) -> str:
    tokens = re.findall(
        r"(?<!\S)-(?:FD[0-9A-Fa-f]+|FC[0-9A-Fa-f]+|FN\d+|"
        r"FF\d[^\s]+|FS\d[0-9A-Fa-f]+|FL\d[0-9A-Fa-f]+|FP\d\([^)]*\))",
        inner,
    )
    return " ".join(tokens)


def _merge_stlink_flash_algorithm(existing: str, algorithm_options: str) -> str:
    base = existing or ""
    base = _remove_stlink_flash_algorithm(base)
    base = _remove_reset_run_flags(base)
    if not base.strip():
        base = DEFAULT_STLINK_OPTIONS
    if "-FO" not in base:
        base = f"{base} -FO15"
    merged = _squash_spaces(f"{base} {algorithm_options}")
    return _ensure_reset_and_run_in_name(merged)


def _remove_stlink_flash_algorithm(value: str) -> str:
    text = value or ""
    patterns = [
        r"(?<!\S)-FD[0-9A-Fa-f]+(?=\s|$)",
        r"(?<!\S)-FC[0-9A-Fa-f]+(?=\s|$)",
        r"(?<!\S)-FN\d+(?=\s|$)",
        r"(?<!\S)-FF\d[^\s]+(?=\s|$)",
        r"(?<!\S)-FS\d[0-9A-Fa-f]+(?=\s|$)",
        r"(?<!\S)-FL\d[0-9A-Fa-f]+(?=\s|$)",
        r"(?<!\S)-FP\d\([^)]*\)(?=\s|$)",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return _squash_spaces(text)


def _remove_reset_run_flags(value: str) -> str:
    text = re.sub(r"-WK([0-9]+)-R[01]\b", r"-WK\1", value or "")
    text = re.sub(r"(?<!\S)-R[01](?=\s|$)", "", text)
    return _squash_spaces(text)


def _ensure_reset_and_run_in_name(value: str) -> str:
    text = _remove_reset_run_flags(value)
    return _squash_spaces(f"{text} -R1")


def _get_or_create_setreg_entry(registry: ET.Element, key: str) -> ET.Element:
    for entry in registry.findall("SetRegEntry"):
        key_el = entry.find("Key")
        if key_el is not None and key_el.text == key:
            return entry
    entry = ET.SubElement(registry, "SetRegEntry")
    _set_or_create(entry, "Number", "0")
    _set_or_create(entry, "Key", key)
    _set_or_create(entry, "Name", "")
    return entry


def _algorithm_options_from_uvoptx(root: ET.Element) -> str:
    for entry in root.iter("SetRegEntry"):
        key_el = entry.find("Key")
        name_el = entry.find("Name")
        if key_el is None or name_el is None or not name_el.text:
            continue
        if key_el.text == "UL2CM3":
            return _algorithm_options_from_flash_inner(_flash_driver_inner(name_el.text))
    return ""


def _has_flash_algorithm_options(value: str) -> bool:
    return "-FF0" in (value or "") and "-FS0" in (value or "") and "-FL0" in (value or "") and "-FP0" in (value or "")


def _squash_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _update_onchip_memories(target: ET.Element, chip: Dict) -> None:
    """Update the OnChipMemories section with correct RAM/ROM sizes."""
    ocm = target.find(".//OnChipMemories")
    if ocm is None:
        return

    ram_size = chip["ram_size"]
    flash_size = chip["flash_size"]

    for mem in ocm:
        mem_type = mem.findtext("Type", "")
        if mem.tag == "IRAM" and mem_type == "0":
            _set_or_create(mem, "Size", ram_size)
        elif mem.tag == "IROM" and mem_type == "1":
            _set_or_create(mem, "Size", flash_size)

    # Update OCR_RVCT4 (ROM) and OCR_RVCT9 (RAM)
    rvct4 = ocm.find("OCR_RVCT4")
    if rvct4 is not None:
        _set_or_create(rvct4, "Size", flash_size)
    rvct9 = ocm.find("OCR_RVCT9")
    if rvct9 is not None:
        _set_or_create(rvct9, "Size", ram_size)

    # OCR_RVCT10 is IRAM2 (CCM), only for F4
    rvct10 = ocm.find("OCR_RVCT10")
    if rvct10 is not None:
        if chip.get("has_iram2", False):
            _set_or_create(rvct10, "StartAddress", "0x10000000")
            _set_or_create(rvct10, "Size", "0x10000")
        else:
            _set_or_create(rvct10, "StartAddress", "0x0")
            _set_or_create(rvct10, "Size", "0x0")


def _update_had_flags(target: ET.Element, chip: Dict) -> None:
    """Update hadIRAM, hadIROM, hadIRAM2 flags."""
    for flag in target.iter():
        if flag.tag == "hadIRAM2":
            flag.text = "1" if chip.get("has_iram2", False) else "0"


def add_source_group(uvprojx_path: str, group_name: str, files: List[Dict[str, str]]) -> bool:
    """
    Add a new Group with source files to the project.

    files: list of {"name": "main.c", "path": "..\\User\\main.c", "type": "1"}
    """
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        return False

    groups = target.find("Groups")
    if groups is None:
        groups = ET.SubElement(target, "Groups")

    # Check if group already exists
    for existing in groups.findall("Group"):
        if existing.findtext("GroupName") == group_name:
            # Group exists, add files
            fe = existing.find("Files")
            if fe is None:
                fe = ET.SubElement(existing, "Files")
            for f in files:
                _add_file_element(fe, f)
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
            return True

    # Create new group
    grp = ET.SubElement(groups, "Group")
    gn = ET.SubElement(grp, "GroupName")
    gn.text = group_name

    fe = ET.SubElement(grp, "Files")
    for f in files:
        _add_file_element(fe, f)

    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
    print(f"Group '{group_name}' added with {len(files)} file(s)")
    return True


def _add_file_element(parent: ET.Element, file_info: Dict[str, str]) -> None:
    """Add a <File> element to a <Files> parent."""
    f_elem = ET.SubElement(parent, "File")
    fn = ET.SubElement(f_elem, "FileName")
    fn.text = file_info.get("name", "")
    ft = ET.SubElement(f_elem, "FileType")
    ft.text = file_info.get("type", "1")
    fp = ET.SubElement(f_elem, "FilePath")
    fp.text = file_info.get("path", "")


def remove_source_group(uvprojx_path: str, group_name: str) -> bool:
    """Remove a Group (and all its files) from the project."""
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        return False

    groups = target.find("Groups")
    if groups is None:
        return False

    for grp in groups.findall("Group"):
        if grp.findtext("GroupName") == group_name:
            groups.remove(grp)
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
            print(f"Group '{group_name}' removed")
            return True

    return False


def add_file_to_group(uvprojx_path: str, group_name: str,
                      file_info: Dict[str, str]) -> bool:
    """Add a single file to an existing group."""
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        return False

    groups = target.find("Groups")
    if groups is None:
        return False

    for grp in groups.findall("Group"):
        if grp.findtext("GroupName") == group_name:
            fe = grp.find("Files")
            if fe is None:
                fe = ET.SubElement(grp, "Files")
            _add_file_element(fe, file_info)
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
            print(f"File '{file_info.get('name')}' added to group '{group_name}'")
            return True

    return False


def update_defines(uvprojx_path: str, defines: str) -> bool:
    """Update the preprocessor defines string."""
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        return False

    cads = target.find(".//Cads")
    if cads is None:
        return False

    vc = cads.find("VariousControls")
    if vc is None:
        vc = ET.SubElement(cads, "VariousControls")

    _set_or_create(vc, "Define", defines)
    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
    return True


def update_include_paths(uvprojx_path: str, paths: str) -> bool:
    """Update the include paths string (semicolon separated)."""
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        return False

    cads = target.find(".//Cads")
    if cads is None:
        return False

    vc = cads.find("VariousControls")
    if vc is None:
        vc = ET.SubElement(cads, "VariousControls")

    _set_or_create(vc, "IncludePath", paths)
    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
    return True


def rename_project(uvprojx_path: str, new_name: str) -> bool:
    """Rename the project target and update OutputName.

    Both <TargetName> and <OutputName> live under <Target>, but OutputName
    is usually a sub-child of <TargetCommonOption>. Use .iter() so we don't
    miss it regardless of nesting depth."""
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    target = root.find(".//Target")
    if target is None:
        return False

    # TargetName (directly under Target)
    tn = target.find("TargetName")
    if tn is not None:
        tn.text = new_name

    # OutputName (under TargetCommonOption, but iter() walks any depth)
    for on_el in target.iter("OutputName"):
        on_el.text = new_name

    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
    print(f"Project renamed to '{new_name}'")
    return True


def enable_reset_and_run(project_dir: str) -> bool:
    """Enable 'Reset and Run' in .uvoptx file so the MCU runs immediately after flash.

    This modifies the ST-Link debug configuration to include '-R1' flag.
    Args:
        project_dir: Path to the project directory containing .uvoptx file
    Returns:
        True if successful, False otherwise
    """
    import glob as glob_mod
    
    # Find .uvoptx file
    uvoptx_files = glob_mod.glob(os.path.join(project_dir, "**", "*.uvoptx"), recursive=True)
    if not uvoptx_files:
        # Try parent directory
        uvoptx_files = glob_mod.glob(os.path.join(project_dir, "..", "*.uvoptx"))
    
    if not uvoptx_files:
        print(f"Warning: No .uvoptx file found in {project_dir}")
        return False
    
    uvoptx_path = uvoptx_files[0]
    
    try:
        tree = ET.parse(uvoptx_path)
    except Exception as e:
        print(f"Error parsing {uvoptx_path}: {e}")
        return False
    
    root = tree.getroot()
    changed = False
    algorithm_options = _algorithm_options_from_uvoptx(root)
    
    # Find TargetDriverDllRegistry and update ST-Link entry
    for sre in root.iter("SetRegEntry"):
        key_el = sre.find("Key")
        name_el = sre.find("Name")
        if key_el is not None and key_el.text == "ST-LINKIII-KEIL_SWO":
            if name_el is not None:
                name = name_el.text or ""
                if algorithm_options and not _has_flash_algorithm_options(name):
                    name_new = _merge_stlink_flash_algorithm(name, algorithm_options)
                else:
                    base = name if name.strip() else DEFAULT_STLINK_OPTIONS
                    name_new = _ensure_reset_and_run_in_name(base)

                if name_new != name:
                    name_el.text = name_new
                    changed = True
                    print("  ST-Link Flash Algorithm / Reset and Run config updated")
                else:
                    print(f"  Reset and Run already enabled (-R1 found)")
    
    if changed:
        tree.write(uvoptx_path, encoding="UTF-8", xml_declaration=True)
        print(f"Reset and Run enabled in: {uvoptx_path}")
    
    return changed


def _set_or_create(parent: ET.Element, tag: str, text: str) -> None:
    """Set element text, creating the element if it doesn't exist."""
    el = parent.find(tag)
    if el is None:
        el = ET.SubElement(parent, tag)
    el.text = text



if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Modify Keil .uvprojx files")
    sub = parser.add_subparsers(dest="command")

    # Read config
    read_p = sub.add_parser("read", help="Read project configuration")
    read_p.add_argument("--project", required=True, help="Path to .uvprojx")

    # Modify device
    dev_p = sub.add_parser("device", help="Change target device")
    dev_p.add_argument("--project", required=True)
    dev_p.add_argument("--chip", required=True, help="Chip model (e.g., STM32F407ZGT6)")

    flash_p = sub.add_parser("flash-config", help="Repair Keil Flash Download algorithm config")
    flash_p.add_argument("--project", required=True)
    flash_p.add_argument("--chip", help="Chip model (auto-detected from .uvprojx if omitted)")

    # Add group
    grp_p = sub.add_parser("add-group", help="Add source group")
    grp_p.add_argument("--project", required=True)
    grp_p.add_argument("--name", required=True, help="Group name")
    grp_p.add_argument("--files", required=True, help="JSON array of file dicts")

    # Remove group
    rm_p = sub.add_parser("remove-group", help="Remove source group")
    rm_p.add_argument("--project", required=True)
    rm_p.add_argument("--name", required=True)

    # Update defines
    def_p = sub.add_parser("defines", help="Update preprocessor defines")
    def_p.add_argument("--project", required=True)
    def_p.add_argument("--defines", required=True)

    # Update include paths
    inc_p = sub.add_parser("includes", help="Update include paths")
    inc_p.add_argument("--project", required=True)
    inc_p.add_argument("--paths", required=True)

    args = parser.parse_args()

    if args.command == "read":
        config = read_current_config(args.project)
        print(json.dumps(config, indent=2, ensure_ascii=False))
    elif args.command == "device":
        modify_device(args.project, args.chip)
    elif args.command == "flash-config":
        ok = ensure_flash_download_config(args.project, args.chip)
        print("Flash Download config OK" if ok else "Failed to repair Flash Download config")
        sys.exit(0 if ok else 1)
    elif args.command == "add-group":
        files = json.loads(args.files)
        add_source_group(args.project, args.name, files)
    elif args.command == "remove-group":
        remove_source_group(args.project, args.name)
    elif args.command == "defines":
        update_defines(args.project, args.defines)
    elif args.command == "includes":
        update_include_paths(args.project, args.paths)
    else:
        parser.print_help()
