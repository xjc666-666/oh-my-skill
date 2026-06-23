"""
Emit reusable peripheral driver skeletons into a generated STM32 project.

Use this to avoid rewriting common .c/.h pairs from scratch. Templates are
intentionally conservative: they provide init functions and protocol hooks that
the agent can adapt to the user's confirmed pins.
"""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from example_searcher import get_init_template, PERIPHERAL_KEYWORDS
from uvprojx_modifier import add_source_group


DEBUG_PROTOCOL_C = r'''#include "debug_protocol.h"
#include <stdio.h>
#include <string.h>

static uint32_t g_boot_counter = 0;

void DBG_InitBanner(const char *project, const char *chip)
{
    g_boot_counter++;
    printf("BOOT_OK project=%s chip=%s boot=%lu\r\n",
           project ? project : "unknown",
           chip ? chip : "unknown",
           (unsigned long)g_boot_counter);
}

void DBG_KeyValueU32(const char *key, uint32_t value)
{
    printf("%s=%lu\r\n", key, (unsigned long)value);
}

void DBG_KeyValueI32(const char *key, int32_t value)
{
    printf("%s=%ld\r\n", key, (long)value);
}

void DBG_KeyValueFloat(const char *key, float value)
{
    printf("%s=%.3f\r\n", key, value);
}

void DBG_Event(const char *name)
{
    printf("event=%s\r\n", name ? name : "unknown");
}

int DBG_CommandMatch(const char *line, const char *command)
{
    if (!line || !command) return 0;
    return strncmp(line, command, strlen(command)) == 0;
}
'''


DEBUG_PROTOCOL_H = r'''#ifndef __DEBUG_PROTOCOL_H
#define __DEBUG_PROTOCOL_H

#include <stdint.h>

void DBG_InitBanner(const char *project, const char *chip);
void DBG_KeyValueU32(const char *key, uint32_t value);
void DBG_KeyValueI32(const char *key, int32_t value);
void DBG_KeyValueFloat(const char *key, float value);
void DBG_Event(const char *name);
int DBG_CommandMatch(const char *line, const char *command);

#endif
'''


def _module_name(peripheral: str, explicit: str = "") -> str:
    raw = explicit or peripheral.lower()
    raw = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    return raw or "driver"


def _detect_layout(project_root: Path) -> Tuple[Path, Path, str, str]:
    drive_include = project_root / "Drive" / "Include"
    drive_source = project_root / "Drive" / "Source"
    if drive_include.exists() or drive_source.exists() or (project_root / "Project").exists():
        drive_include.mkdir(parents=True, exist_ok=True)
        drive_source.mkdir(parents=True, exist_ok=True)
        return drive_include, drive_source, "..\\Drive\\Source\\{name}.c", "Drive"

    hardware = project_root / "HARDWARE"
    hardware.mkdir(parents=True, exist_ok=True)
    return hardware, hardware, "..\\HARDWARE\\{name}\\{name}.c", "Hardware"


def _wrap_template(peripheral: str, family: str, module: str) -> Tuple[str, str]:
    if peripheral.upper() in {"DEBUG", "DEBUG_PROTOCOL", "SERIAL_PROTOCOL"}:
        return DEBUG_PROTOCOL_H, DEBUG_PROTOCOL_C

    tpl = get_init_template(peripheral, family)
    init_code = tpl.get("init_code", "").strip()
    if not init_code:
        init_code = f"void {module}_Init(void)\n{{\n    /* TODO: implement {peripheral} init for {family}. */\n}}\n"

    includes = tpl.get("header_includes", [])
    include_lines = [f'#include "{module}.h"']
    for inc in includes:
        if inc and inc != f"{module}.h":
            if inc.startswith("stm32"):
                include_lines.append(f'#include "{inc}"')
            else:
                include_lines.append(f'#include "{inc}"')

    header_guard = f"__{module.upper()}_H"
    prototypes = _extract_prototypes(init_code)
    if not prototypes:
        prototypes = [f"void {module}_Init(void);"]

    header = [
        f"#ifndef {header_guard}",
        f"#define {header_guard}",
        "",
        "#include <stdint.h>",
        "",
        *prototypes,
        "",
        "#endif",
        "",
    ]
    source = "\n".join(include_lines) + "\n\n" + init_code + "\n"
    return "\n".join(header), source


def _extract_prototypes(source: str) -> list[str]:
    prototypes = []
    pattern = re.compile(
        r"^\s*((?:static\s+)?(?:void|int|uint\d+_t|int\d+_t|u\d+|float|double)\s+"
        r"[A-Za-z_][A-Za-z0-9_]*\s*\([^;{}]*\))\s*\{",
        re.MULTILINE,
    )
    for match in pattern.finditer(source):
        proto = match.group(1).strip()
        if proto.startswith("static "):
            continue
        prototypes.append(proto + ";")
    return prototypes


def emit_template(project: str, peripheral: str, family: str,
                  module: str = "", uvprojx: str = "") -> Dict:
    project_root = Path(project)
    include_dir, source_dir, rel_pattern, group = _detect_layout(project_root)
    module = _module_name(peripheral, module)

    if group == "Hardware":
        include_dir = include_dir / module
        source_dir = source_dir / module
        include_dir.mkdir(parents=True, exist_ok=True)
        source_dir.mkdir(parents=True, exist_ok=True)

    header, source = _wrap_template(peripheral, family, module)
    h_path = include_dir / f"{module}.h"
    c_path = source_dir / f"{module}.c"
    h_path.write_text(header, encoding="utf-8")
    c_path.write_text(source, encoding="utf-8")

    added_to_project = False
    if uvprojx:
        rel_c = rel_pattern.format(name=module)
        added_to_project = add_source_group(
            uvprojx,
            group,
            [{"name": f"{module}.c", "path": rel_c, "type": "1"}],
        )

    return {
        "module": module,
        "header": str(h_path),
        "source": str(c_path),
        "added_to_project": added_to_project,
    }


def list_templates() -> list[str]:
    base = sorted(PERIPHERAL_KEYWORDS.keys())
    return ["DEBUG_PROTOCOL"] + base


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit STM32 peripheral driver templates")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--project", help="Project root directory")
    parser.add_argument("--uvprojx", default="", help="Optional .uvprojx to update")
    parser.add_argument("--peripheral", default="DEBUG_PROTOCOL")
    parser.add_argument("--family", default="F407")
    parser.add_argument("--module", default="")
    args = parser.parse_args()

    if args.list:
        for name in list_templates():
            print(name)
        return 0
    if not args.project:
        parser.error("--project is required unless --list is used")

    result = emit_template(args.project, args.peripheral, args.family,
                           args.module, args.uvprojx)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
