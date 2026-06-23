"""
Modify MSPM0G3519 .uvprojx (Keil uVision project) XML files.
Standalone, no stm32-keil dependency.
"""
import os
import sys
import re
import json
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from pathlib import Path
from typing import Optional, List, Dict

SCRIPT_DIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, SCRIPT_DIR)
from utils import normalize_path, load_chip_db


CMSIS_DAP_PMON = r"BIN\CMSIS_AGDI.dll"
MSPM0G3519_FLASH_ALGORITHM = (
    r"$$Device:MSPM0G3519$02_Flash_Programming\FlashARM\MSPM0GX51X_MAIN_512KB.FLM"
)
CMSIS_AGDI_OPTIONS = (
    r'-X"Any" -UAny -O206 -S9 -C0 -P00000000 '
    r'-N00("ARM CoreSight SW-DP") -D00(6BA02477) -L00(0) '
    r"-TO65554 -TC10000000 -TT10000000 -TP20 -TDS8007 -TDT0 -TDC1F "
    r"-TIEFFFFFFFF -TIP8 -FO15 -FD20200000 -FC20000 -FN1 "
    r"-FF0MSPM0GX51X_MAIN_512KB.FLM -FS00 -FL080000 "
    rf"-FP0({MSPM0G3519_FLASH_ALGORITHM})"
)
UL2CM3_OPTIONS = (
    r"UL2CM3(-S0 -C0 -P0 -FD20200000 -FC20000 -FN1 "
    r"-FF0MSPM0GX51X_MAIN_512KB -FS00 -FL080000 "
    rf"-FP0({MSPM0G3519_FLASH_ALGORITHM}))"
)


def read_config(uvprojx_path: str) -> Dict:
    """Read a .uvprojx file and return key settings as dict."""
    if not os.path.isfile(uvprojx_path):
        return {"error": f"File not found: {uvprojx_path}"}

    tree = ET.parse(uvprojx_path)
    root = tree.getroot()

    config = {
        "uvprojx_path": normalize_path(uvprojx_path),
        "targets": [],
        "groups": [],
        "defines": {},
    }

    for target in root.iter("Target"):
        tcfg = {}
        tn = target.find("TargetName")
        tcfg["name"] = tn.text if tn is not None else ""

        dev = target.find("Device")
        tcfg["device"] = dev.text if dev is not None else ""

        oname = target.find("OutputName")
        tcfg["output_name"] = oname.text if oname is not None else ""

        # Includes
        inc_paths = []
        for cads_elem in target.iter("Cads"):
            for incp in cads_elem.iter("IncludePath"):
                if incp.text:
                    inc_paths.extend(incp.text.split(";"))
        tcfg["include_paths"] = inc_paths

        # Defines
        for cads_elem in target.iter("Cads"):
            for var in cads_elem.iter("VariousControls"):
                defs = var.find("Define")
                if defs is not None and defs.text:
                    tcfg["defines"] = defs.text

        # Groups
        groups = target.find("Groups")
        if groups is not None:
            for gname_elem in groups.iter("GroupName"):
                gcfg = {"name": gname_elem.text or "", "files": []}
                gfiles_elem = gname_elem.find("Files") if hasattr(gname_elem, 'find') else None
                if gfiles_elem is not None:
                    for fe in gfiles_elem.iter("File"):
                        fcfg = {}
                        fn = fe.find("FileName")
                        fcfg["name"] = fn.text if fn is not None else ""
                        fp = fe.find("FilePath")
                        fcfg["path"] = fp.text if fp is not None else ""
                        ft = fe.find("FileType")
                        fcfg["type"] = ft.text if ft is not None else "1"
                        gcfg["files"].append(fcfg)
                tcfg["groups"].append(gcfg)

        # Pre-build steps
        bm = target.find("BeforeMake")
        if bm is not None:
            rp = bm.find("RunUserProg1")
            if rp is not None:
                dn = rp.find("UserProg1Name")
                if dn is not None and dn.text:
                    tcfg["before_make_cmd"] = dn.text

        config["targets"].append(tcfg)

    return config


def modify_device(uvprojx_path: str, chip: str = "MSPM0G3519") -> bool:
    """Set the Device tag in .uvprojx from chip_db."""
    chip_db = load_chip_db()
    chip_info = chip_db.get(chip, {})
    device = chip_info.get("device", chip)

    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
        changed = False
        for el in root.iter("Device"):
            if el.text != device:
                el.text = device
                changed = True

        # Also update CPU DLL parameters
        cpu_dll_args = chip_info.get("cpu_string", "")
        if cpu_dll_args:
            for el in root.iter("SimDlls"):
                for param in el.iter("SimDllsArguments"):
                    if param.text and param.text != cpu_dll_args:
                        param.text = cpu_dll_args
                        changed = True

        if changed:
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error modifying device: {e}")
        return False


def rename_project(uvprojx_path: str, new_name: str) -> bool:
    """Update TargetName and OutputName in .uvprojx."""
    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
        changed = False

        for tn in root.iter("TargetName"):
            tn.text = new_name
            changed = True
        for on in root.iter("OutputName"):
            on.text = new_name
            changed = True

        if changed:
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error renaming project: {e}")
        return False


def add_group(uvprojx_path: str, group_name: str, files: List[Dict],
              target_name: Optional[str] = None) -> bool:
    """Add source files to a group in .uvprojx.
    Keil format: <Group><GroupName>X</GroupName><Files><File/>...</Files></Group>
    Source group may use flat format: <GroupName>Source<Files/></GroupName> + <File/> siblings
    files: [{"name": "led.c", "path": "..\\\\BSP\\\\LED\\\\led.c", "type": "1"}, ...]"""
    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()

        for target in root.iter("Target"):
            if target_name and target.find("TargetName").text != target_name:
                continue

            groups = target.find("Groups")
            if groups is None:
                groups = ET.SubElement(target, "Groups")

            # Try Group wrapper format first
            for grp in groups:
                grp_tag = grp.tag.split("}")[-1] if "}" in grp.tag else grp.tag
                if grp_tag != "Group":
                    continue
                gn = grp.find("GroupName")
                if gn is not None and (gn.text or "").strip() == group_name:
                    files_elem = grp.find("Files")
                    if files_elem is None:
                        files_elem = ET.SubElement(grp, "Files")
                    for f in files:
                        fe = ET.SubElement(files_elem, "File")
                        fn = ET.SubElement(fe, "FileName"); fn.text = f["name"]
                        fp = ET.SubElement(fe, "FilePath"); fp.text = f["path"]
                        ft = ET.SubElement(fe, "FileType"); ft.text = f.get("type", "1")
                    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
                    return True

            # Try flat format (used for Source group)
            children = list(groups)
            for i, child in enumerate(children):
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "GroupName" and (child.text or "").strip() == group_name:
                    # Find insertion point (after last File before next GroupName)
                    insert_idx = i + 1
                    while insert_idx < len(children):
                        ntag = children[insert_idx].tag.split("}")[-1] if "}" in children[insert_idx].tag else children[insert_idx].tag
                        if ntag == "GroupName":
                            break
                        insert_idx += 1
                    for f in files:
                        fe = ET.Element("File")
                        fn = ET.SubElement(fe, "FileName"); fn.text = f["name"]
                        fp = ET.SubElement(fe, "FilePath"); fp.text = f["path"]
                        ft = ET.SubElement(fe, "FileType"); ft.text = f.get("type", "1")
                        groups.insert(insert_idx, fe)
                        insert_idx += 1
                    tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
                    return True

            # Group doesn't exist - create in Group wrapper format
            grp = ET.SubElement(groups, "Group")
            gn = ET.SubElement(grp, "GroupName"); gn.text = group_name
            files_elem = ET.SubElement(grp, "Files")
            for f in files:
                fe = ET.SubElement(files_elem, "File")
                fn = ET.SubElement(fe, "FileName"); fn.text = f["name"]
                fp = ET.SubElement(fe, "FilePath"); fp.text = f["path"]
                ft = ET.SubElement(fe, "FileType"); ft.text = f.get("type", "1")

        tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error adding group: {e}")
        return False


def remove_group(uvprojx_path: str, group_name: str) -> bool:
    """Remove a source group from the .uvprojx."""
    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
        
        # Build parent map to easily remove elements
        parent_map = {c: p for p in root.iter() for c in p}
        
        removed = False
        for gn in list(root.iter("GroupName")):
            if (gn.text or "").strip() == group_name:
                parent_group = parent_map.get(gn)
                if parent_group is not None:
                    # Standard Group format: <Group><GroupName>...</GroupName></Group>
                    if parent_group.tag == "Group":
                        grandparent = parent_map.get(parent_group)
                        if grandparent is not None:
                            grandparent.remove(parent_group)
                            removed = True
                    # Flat format: <Groups><GroupName>...</GroupName></Groups>
                    elif parent_group.tag == "Groups":
                        parent_group.remove(gn)
                        removed = True
                break
                
        if removed:
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error removing group: {e}")
        return False


def update_defines(uvprojx_path: str, defines: str) -> bool:
    """Update the Define field in .uvprojx."""
    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
        for cads in root.iter("Cads"):
            for var in cads.iter("VariousControls"):
                defn = var.find("Define")
                if defn is not None:
                    defn.text = defines
        tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error updating defines: {e}")
        return False


def update_includes(uvprojx_path: str, include_paths: str) -> bool:
    """Update IncludePath in .uvprojx."""
    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
        for cads in root.iter("Cads"):
            for incp in cads.iter("IncludePath"):
                incp.text = include_paths
        tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error updating includes: {e}")
        return False


def update_syscfg_bat(uvprojx_path: str, sdk_path: str) -> bool:
    """Update the syscfg.bat pre-build command in .uvprojx with correct SDK path."""
    if not os.path.isfile(uvprojx_path):
        return False

    syscfg_bat = os.path.join(sdk_path, "tools", "keil", "syscfg.bat")
    examples = os.path.join(sdk_path, "examples")
    new_cmd = f'cmd.exe /C "{syscfg_bat} {examples} ../User/config.syscfg"'

    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
        changed = False

        for bm in root.iter("BeforeMake"):
            for rp in bm.iter("RunUserProg1"):
                for dn in rp.iter("UserProg1Name"):
                    dn.text = new_cmd
                    changed = True

        if changed:
            tree.write(uvprojx_path, encoding="UTF-8", xml_declaration=True)
        return True
    except Exception as e:
        print(f"Error updating syscfg.bat: {e}")
        return False


def fix_absolute_paths(project_dir: str) -> bool:
    """Convert absolute Windows paths to relative in .uvprojx/.uvoptx files."""
    # Search in Project/ subdir for .uvprojx/.uvoptx
    proj_dir = os.path.join(project_dir, "Project")
    if not os.path.isdir(proj_dir):
        return False

    for fname in os.listdir(proj_dir):
        if not (fname.endswith(".uvprojx") or fname.endswith(".uvoptx")):
            continue
        full = os.path.join(proj_dir, fname)
        _fix_paths_in_xml(full)

    return True


def _fix_paths_in_xml(xml_path: str) -> None:
    """Fix absolute paths in a .uvprojx or .uvoptx."""
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return
    root = tree.getroot()
    changed = False
    for tag in ("FilePath", "PathWithFileName", "Filename"):
        for elem in root.iter(tag):
            if elem.text and _is_abs_windows_path(elem.text):
                rel = _abs_to_rel(elem.text)
                if rel:
                    elem.text = rel
                    changed = True
    if changed:
        tree.write(xml_path, encoding="UTF-8", xml_declaration=True)


def _is_abs_windows_path(p: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", p))


def _abs_to_rel(abs_path: str) -> Optional[str]:
    """Convert absolute path to relative path from project directory."""
    p = abs_path.replace("/", "\\")
    markers = ["User\\", "BSP\\", "Source\\", "Project\\", "Output\\"]
    for marker in markers:
        idx = p.lower().find(marker.lower())
        if idx >= 0:
            rest = p[idx:]
            return f"..\\{rest}"
    return None


def add_source_group(uvprojx_path: str, files: List[str]) -> bool:
    """Add DriverLib .c files to the Source group in .uvprojx."""
    file_entries = []
    for f in sorted(files):
        name = os.path.basename(f)
        file_entries.append({
            "name": name,
            "path": f"..\\\\Source\\\\ti\\\\driverlib\\\\{name}",
            "type": "1"
        })
    return add_group(uvprojx_path, "Source", file_entries)


def ensure_cmsis_dap_debug_config(
    uvprojx_path: str,
    project_name: Optional[str] = None,
) -> Dict:
    """Configure Keil debug options for CMSIS-DAP and write the matching .uvoptx.

    Keil stores most Debug dialog state in .uvoptx, while the .uvprojx keeps the
    target utilities/flash-driver wiring. This function updates both files.
    """
    if not os.path.isfile(uvprojx_path):
        return {"success": False, "error": f"File not found: {uvprojx_path}"}

    if project_name is None:
        project_name = _read_first_target_name(uvprojx_path)
    if not project_name:
        project_name = os.path.splitext(os.path.basename(uvprojx_path))[0]

    uvprojx_changed = _patch_uvprojx_debug_settings(uvprojx_path)
    uvoptx_path = os.path.splitext(uvprojx_path)[0] + ".uvoptx"
    _write_cmsis_dap_uvoptx(uvoptx_path, project_name)

    return {
        "success": True,
        "uvprojx_path": normalize_path(uvprojx_path),
        "uvoptx_path": normalize_path(uvoptx_path),
        "target_name": project_name,
        "cmsis_dap": True,
        "run_to_main": True,
        "flash_algorithm": "MSPM0GX51X_MAIN_512KB.FLM",
        "uvprojx_changed": uvprojx_changed,
    }


def _read_first_target_name(uvprojx_path: str) -> Optional[str]:
    try:
        tree = ET.parse(uvprojx_path)
    except Exception:
        return None

    target = tree.getroot().find(".//TargetName")
    if target is None:
        return None
    return (target.text or "").strip() or None


def _patch_uvprojx_debug_settings(uvprojx_path: str) -> bool:
    with open(uvprojx_path, "r", encoding="utf-8") as f:
        text = f.read()
    original = text

    replacements = {
        "UseTargetDll": "1",
        "UseExternalTool": "0",
        "RunIndependent": "0",
        "UpdateFlashBeforeDebugging": "1",
        "Capability": "1",
        "DriverSelection": "4096",
        "bUseTDR": "1",
        "Flash2": r"BIN\UL2CM3.DLL",
    }
    for tag, value in replacements.items():
        text = re.sub(
            rf"<{tag}>[^<]*</{tag}>",
            lambda _m, tag=tag, value=value: f"<{tag}>{value}</{tag}>",
            text,
        )

    text = re.sub(
        r"<Flash1>.*?</Flash1>",
        lambda m: re.sub(r"\n\s*<RunToMain>[^<]*</RunToMain>", "", m.group(0)),
        text,
        flags=re.S,
    )

    if text != original:
        with open(uvprojx_path, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    return False


def _write_cmsis_dap_uvoptx(uvoptx_path: str, project_name: str) -> None:
    target_name = escape(project_name)
    cmsis_options = escape(CMSIS_AGDI_OPTIONS)
    ul2cm3_options = escape(UL2CM3_OPTIONS)
    pmon = escape(CMSIS_DAP_PMON)

    content = f"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<ProjectOpt xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="project_optx.xsd">

  <SchemaVersion>1.0</SchemaVersion>

  <Header>### uVision Project, (C) Keil Software</Header>

  <Extensions>
    <cExt>*.c</cExt>
    <aExt>*.s*; *.src; *.a*</aExt>
    <oExt>*.obj; *.o</oExt>
    <lExt>*.lib</lExt>
    <tExt>*.txt; *.h; *.inc; *.md</tExt>
    <pExt>*.plm</pExt>
    <CppX>*.cpp; *.cc; *.cxx</CppX>
    <nMigrate>0</nMigrate>
  </Extensions>

  <DaveTm>
    <dwLowDateTime>0</dwLowDateTime>
    <dwHighDateTime>0</dwHighDateTime>
  </DaveTm>

  <Target>
    <TargetName>{target_name}</TargetName>
    <ToolsetNumber>0x4</ToolsetNumber>
    <ToolsetName>ARM-ADS</ToolsetName>
    <TargetOption>
      <CLKADS>12000000</CLKADS>
      <OPTTT>
        <gFlags>1</gFlags>
        <BeepAtEnd>1</BeepAtEnd>
        <RunSim>0</RunSim>
        <RunTarget>1</RunTarget>
        <RunAbUc>0</RunAbUc>
      </OPTTT>
      <OPTFL>
        <tvExp>1</tvExp>
        <tvExpOptDlg>0</tvExpOptDlg>
        <IsCurrentTarget>1</IsCurrentTarget>
      </OPTFL>
      <CpuCode>4</CpuCode>
      <DebugOpt>
        <uSim>0</uSim>
        <uTrg>1</uTrg>
        <sLdApp>1</sLdApp>
        <sGomain>1</sGomain>
        <sRbreak>1</sRbreak>
        <sRwatch>1</sRwatch>
        <sRmem>1</sRmem>
        <sRfunc>1</sRfunc>
        <sRbox>1</sRbox>
        <tLdApp>1</tLdApp>
        <tGomain>1</tGomain>
        <tRbreak>1</tRbreak>
        <tRwatch>1</tRwatch>
        <tRmem>1</tRmem>
        <tRfunc>0</tRfunc>
        <tRbox>1</tRbox>
        <tRtrace>1</tRtrace>
        <sRSysVw>1</sRSysVw>
        <tRSysVw>1</tRSysVw>
        <sRunDeb>0</sRunDeb>
        <sLrtime>0</sLrtime>
        <bEvRecOn>1</bEvRecOn>
        <bSchkAxf>0</bSchkAxf>
        <bTchkAxf>0</bTchkAxf>
        <nTsel>3</nTsel>
        <sDll></sDll>
        <sDllPa></sDllPa>
        <sDlgDll></sDlgDll>
        <sDlgPa></sDlgPa>
        <sIfile></sIfile>
        <tDll></tDll>
        <tDllPa></tDllPa>
        <tDlgDll></tDlgDll>
        <tDlgPa></tDlgPa>
        <tIfile></tIfile>
        <pMon>{pmon}</pMon>
      </DebugOpt>
      <TargetDriverDllRegistry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>ARMRTXEVENTFLAGS</Key>
          <Name>-L70 -Z18 -C0 -M0 -T1</Name>
        </SetRegEntry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>DLGTARM</Key>
          <Name>(1010=-1,-1,-1,-1,0)(1007=-1,-1,-1,-1,0)(1008=-1,-1,-1,-1,0)(1012=-1,-1,-1,-1,0)(1009=-1,-1,-1,-1,0)</Name>
        </SetRegEntry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>ARMDBGFLAGS</Key>
          <Name></Name>
        </SetRegEntry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>DLGUARM</Key>
          <Name></Name>
        </SetRegEntry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>CMSIS_AGDI</Key>
          <Name>{cmsis_options}</Name>
        </SetRegEntry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>UL2CM3</Key>
          <Name>{ul2cm3_options}</Name>
        </SetRegEntry>
      </TargetDriverDllRegistry>
      <Breakpoint/>
      <Tracepoint>
        <THDelay>0</THDelay>
      </Tracepoint>
      <DebugFlag>
        <trace>0</trace>
        <periodic>0</periodic>
        <aLwin>1</aLwin>
        <aCover>0</aCover>
        <aSer1>0</aSer1>
        <aSer2>0</aSer2>
        <aPa>0</aPa>
        <viewmode>1</viewmode>
        <vrSel>0</vrSel>
        <aSym>0</aSym>
        <aTbox>0</aTbox>
        <AscS1>0</AscS1>
        <AscS2>0</AscS2>
        <AscS3>0</AscS3>
        <aSer3>0</aSer3>
        <eProf>0</eProf>
        <aLa>0</aLa>
        <aPa1>0</aPa1>
        <AscS4>0</AscS4>
        <aSer4>0</aSer4>
        <StkLoc>0</StkLoc>
        <TrcWin>0</TrcWin>
        <newCpu>0</newCpu>
        <uProt>0</uProt>
      </DebugFlag>
      <DebugDescription>
        <Enable>1</Enable>
        <EnableFlashSeq>1</EnableFlashSeq>
        <EnableLog>0</EnableLog>
        <Protocol>2</Protocol>
        <DbgClock>5000000</DbgClock>
      </DebugDescription>
    </TargetOption>
  </Target>
</ProjectOpt>
"""
    with open(uvoptx_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Modify Keil .uvprojx project files")
    sub = parser.add_subparsers(dest="command")

    sp_read = sub.add_parser("read")
    sp_read.add_argument("--project", required=True)

    sp_dev = sub.add_parser("device")
    sp_dev.add_argument("--project", required=True)
    sp_dev.add_argument("--chip", default="MSPM0G3519")

    sp_rename = sub.add_parser("rename")
    sp_rename.add_argument("--project", required=True)
    sp_rename.add_argument("--name", required=True)

    sp_add = sub.add_parser("add-group")
    sp_add.add_argument("--project", required=True)
    sp_add.add_argument("--name", required=True, help="Group name")
    sp_add.add_argument("--files", required=True, help="JSON array of file objects")

    sp_rm = sub.add_parser("remove-group")
    sp_rm.add_argument("--project", required=True)
    sp_rm.add_argument("--name", required=True)

    sp_def = sub.add_parser("defines")
    sp_def.add_argument("--project", required=True)
    sp_def.add_argument("--defines", required=True)

    sp_inc = sub.add_parser("includes")
    sp_inc.add_argument("--project", required=True)
    sp_inc.add_argument("--paths", required=True)

    sp_sys = sub.add_parser("update-syscfg-bat")
    sp_sys.add_argument("--project", required=True)
    sp_sys.add_argument("--sdk-path", required=True)

    sp_fix = sub.add_parser("fix-paths")
    sp_fix.add_argument("--project-dir", required=True)

    sp_dbg = sub.add_parser("debug-config")
    sp_dbg.add_argument("--project", required=True)
    sp_dbg.add_argument("--name", default=None, help="Target/project name for .uvoptx")

    args = parser.parse_args()

    if args.command == "read":
        config = read_config(args.project)
        print(json.dumps(config, indent=2, ensure_ascii=False))
    elif args.command == "device":
        modify_device(args.project, args.chip)
    elif args.command == "rename":
        rename_project(args.project, args.name)
    elif args.command == "add-group":
        files = json.loads(args.files)
        add_group(args.project, args.name, files)
    elif args.command == "remove-group":
        remove_group(args.project, args.name)
    elif args.command == "defines":
        update_defines(args.project, args.defines)
    elif args.command == "includes":
        update_includes(args.project, args.paths)
    elif args.command == "update-syscfg-bat":
        update_syscfg_bat(args.project, args.sdk_path)
    elif args.command == "fix-paths":
        fix_absolute_paths(args.project_dir)
    elif args.command == "debug-config":
        result = ensure_cmsis_dap_debug_config(args.project, args.name)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result.get("success"):
            sys.exit(1)
    else:
        parser.print_help()
