"""
Convert a Keil .uvprojx project to a GCC-oriented CMake project.

The generator emits both CMakeLists.txt and a small linker script derived from
the Keil memory configuration so cmake_verify.py can perform a real build.
"""
import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_chip_db


def _text(parent, path: str, default: str = "") -> str:
    el = parent.find(path) if parent is not None else None
    return el.text.strip() if el is not None and el.text else default


def _parse_project(uvprojx_path: str) -> Dict:
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()
    target = root.find(".//Target")
    if target is None:
        raise ValueError("No Target found")

    device = _text(target, ".//Device")
    cpu = _text(target, ".//Cpu")
    name = _text(target, "TargetName", Path(uvprojx_path).stem)
    defines = _text(target, ".//Cads/VariousControls/Define")
    includes = _text(target, ".//Cads/VariousControls/IncludePath")

    files = []
    seen_files = set()
    for f in target.findall(".//Group//File"):
        ftype = _text(f, "FileType", "1")
        fpath = _normalize_keil_path(_text(f, "FilePath"))
        if not fpath:
            continue
        if ftype in {"1", "2", "5"}:
            key = fpath.lower()
            if key not in seen_files:
                seen_files.add(key)
                files.append(fpath)

    memory = _read_memory(target, device)
    return {
        "name": name,
        "device": device,
        "cpu": cpu,
        "defines": [d.strip() for d in re.split(r"[,;]", defines) if d.strip()],
        "includes": [_normalize_keil_path(i.strip()) for i in includes.split(";") if i.strip()],
        "files": files,
        "memory": memory,
        "mcu_flags": _mcu_flags(cpu, device),
    }


def _normalize_keil_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    path = path.replace("$PROJ_DIR$/", "")
    path = path.replace("$PROJ_DIR$", ".")
    return path


def _cmake_project_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    if not safe:
        return "stm32_project"
    if safe[0].isdigit():
        return f"stm32_{safe}"
    return safe


def _read_memory(target, device: str) -> Dict:
    flash_start = "0x08000000"
    flash_size = "0x00100000"
    ram_start = "0x20000000"
    ram_size = "0x00020000"

    db = load_chip_db()
    for info in db.values():
        if info.get("device") == device:
            flash_start = info.get("flash_start", flash_start)
            flash_size = info.get("flash_size", flash_size)
            ram_start = info.get("ram_start", ram_start)
            ram_size = info.get("ram_size", ram_size)
            break

    for mem in target.findall(".//OnChipMemories/*"):
        start = _text(mem, "StartAddress")
        size = _text(mem, "Size")
        mtype = _text(mem, "Type")
        if not start or not size:
            continue
        if mtype == "1" or start.lower().startswith("0x080"):
            flash_start, flash_size = start, size
        elif mtype == "0" or start.lower().startswith(("0x200", "0x240")):
            ram_start, ram_size = start, size

    return {
        "flash_start": flash_start,
        "flash_size": flash_size,
        "ram_start": ram_start,
        "ram_size": ram_size,
    }


def _mcu_flags(cpu: str, device: str) -> str:
    blob = (cpu + " " + device).lower()
    if "cortex-m7" in blob or "h7" in blob:
        return "-mcpu=cortex-m7 -mthumb -mfloat-abi=hard -mfpu=fpv5-d16"
    if "cortex-m4" in blob or "f4" in blob or "g4" in blob or "l4" in blob:
        return "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16"
    if "cortex-m0" in blob or "c0" in blob:
        return "-mcpu=cortex-m0plus -mthumb"
    return "-mcpu=cortex-m3 -mthumb"


def _write_linker_script(path: Path, memory: Dict) -> None:
    content = f"""ENTRY(Reset_Handler)

MEMORY
{{
  FLASH (rx)  : ORIGIN = {memory['flash_start']}, LENGTH = {memory['flash_size']}
  RAM   (xrw) : ORIGIN = {memory['ram_start']}, LENGTH = {memory['ram_size']}
}}

_estack = ORIGIN(RAM) + LENGTH(RAM);
_Min_Heap_Size = 0x400;
_Min_Stack_Size = 0x800;

SECTIONS
{{
  .isr_vector :
  {{
    KEEP(*(.isr_vector))
  }} > FLASH

  .text :
  {{
    *(.text*)
    *(.rodata*)
    KEEP(*(.init))
    KEEP(*(.fini))
    _etext = .;
  }} > FLASH

  .ARM.extab : {{ *(.ARM.extab* .gnu.linkonce.armextab.*) }} > FLASH
  .ARM.exidx : {{ *(.ARM.exidx* .gnu.linkonce.armexidx.*) }} > FLASH

  _sidata = LOADADDR(.data);
  .data :
  {{
    _sdata = .;
    *(.data*)
    _edata = .;
  }} > RAM AT > FLASH

  .bss :
  {{
    _sbss = .;
    *(.bss*)
    *(COMMON)
    _ebss = .;
  }} > RAM

  ._user_heap_stack :
  {{
    . = ALIGN(8);
    PROVIDE ( end = . );
    PROVIDE ( _end = . );
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  }} > RAM
}}
"""
    path.write_text(content, encoding="utf-8")


def _cmake_quote(path: str) -> str:
    return '"' + path.replace('"', '\\"') + '"'


def generate_cmake(uvprojx_path: str) -> Dict:
    info = _parse_project(uvprojx_path)
    project_dir = Path(uvprojx_path).resolve().parent
    linker = project_dir / "gcc_linker.ld"
    _write_linker_script(linker, info["memory"])

    sources = "\n".join(f"  {_cmake_quote(src)}" for src in info["files"])
    includes = "\n".join(f"  {_cmake_quote(inc)}" for inc in info["includes"])
    defines = "\n".join(f"  {d}" for d in info["defines"])

    project_name = _cmake_project_name(info["name"])

    content = f"""cmake_minimum_required(VERSION 3.20)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_OBJCOPY arm-none-eabi-objcopy)
set(CMAKE_SIZE arm-none-eabi-size)

project({project_name} C ASM)

set(MCU_FLAGS "{info['mcu_flags']}")
set(COMMON_FLAGS "${{MCU_FLAGS}} -ffunction-sections -fdata-sections -Wall -Wextra -g3 -Os")
set(CMAKE_C_FLAGS "${{COMMON_FLAGS}}" CACHE INTERNAL "")
set(CMAKE_ASM_FLAGS "${{MCU_FLAGS}} -x assembler-with-cpp" CACHE INTERNAL "")
set(CMAKE_EXE_LINKER_FLAGS "${{MCU_FLAGS}} -T${{CMAKE_CURRENT_LIST_DIR}}/gcc_linker.ld -Wl,--gc-sections -Wl,-Map=${{PROJECT_NAME}}.map --specs=nosys.specs" CACHE INTERNAL "")

set(SOURCES
{sources}
)

add_executable(${{PROJECT_NAME}}.elf ${{SOURCES}})

target_compile_definitions(${{PROJECT_NAME}}.elf PRIVATE
{defines}
)

target_include_directories(${{PROJECT_NAME}}.elf PRIVATE
{includes}
)

add_custom_command(TARGET ${{PROJECT_NAME}}.elf POST_BUILD
  COMMAND ${{CMAKE_OBJCOPY}} -O ihex ${{PROJECT_NAME}}.elf ${{PROJECT_NAME}}.hex
  COMMAND ${{CMAKE_OBJCOPY}} -O binary ${{PROJECT_NAME}}.elf ${{PROJECT_NAME}}.bin
  COMMAND ${{CMAKE_SIZE}} ${{PROJECT_NAME}}.elf
)
"""
    cmake_path = project_dir / "CMakeLists.txt"
    cmake_path.write_text(content, encoding="utf-8")
    return {
        "cmake": str(cmake_path),
        "linker": str(linker),
        "target": project_name,
        "keil_target": info["name"],
        "device": info["device"],
        "source_count": len(info["files"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Keil .uvprojx to CMake/GCC files")
    parser.add_argument("project", help="Path to .uvprojx file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = generate_cmake(args.project)
    if args.json:
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Generated {result['cmake']}")
        print(f"Generated {result['linker']}")
        print(f"Sources: {result['source_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
