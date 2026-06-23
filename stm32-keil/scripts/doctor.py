"""
Environment doctor for stm32-keil.

Checks Keil, DFP, CubeMX, flash backends, Python dependencies, and optional
GCC/CMake tooling in one pass.
"""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    find_keil_installation, find_stlink_utility, find_cube_programmer,
    find_jlink_exe, list_pack_dirs,
)
from dfp_checker import check_dfp
from cubemx_finder import find_cubemx


def _check(name: str, ok: bool, detail: str = "", required: bool = False) -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "required": required,
        "detail": detail,
        "status": "OK" if ok else ("MISSING" if required else "OPTIONAL_MISSING"),
    }


def run_doctor(chip: str = "STM32F407ZGT6") -> dict:
    checks = []

    checks.append(_check("python", sys.version_info >= (3, 9),
                         sys.version.replace("\n", " "), True))
    for module, required in [("serial", False), ("fitz", False), ("textual", False)]:
        checks.append(_check(f"python:{module}",
                             importlib.util.find_spec(module) is not None,
                             "pip install -r requirements.txt", required))

    keil = find_keil_installation()
    checks.append(_check("Keil UV4", bool(keil), keil or "Set KEIL_PATH or install MDK-ARM", True))

    dfp = check_dfp(chip)
    checks.append(_check(f"DFP:{chip}", dfp.installed, dfp.message, True))

    packs = list_pack_dirs()
    checks.append(_check("CMSIS pack roots", bool(packs), "; ".join(packs), True))

    cubemx = find_cubemx()
    checks.append(_check("STM32CubeMX", bool(cubemx), cubemx or "Optional for HAL/CubeMX flow"))

    cubeprog = find_cube_programmer()
    checks.append(_check("STM32CubeProgrammer", bool(cubeprog),
                         cubeprog or "Recommended flash fallback"))

    stlink_cli = find_stlink_utility()
    checks.append(_check("ST-LINK_CLI", bool(stlink_cli),
                         stlink_cli or "Legacy optional fallback"))

    jlink = find_jlink_exe()
    checks.append(_check("J-Link", bool(jlink), jlink or "Optional"))

    for exe in ("pyocd", "cmake", "ninja", "arm-none-eabi-gcc",
                "arm-none-eabi-addr2line", "llvm-addr2line", "addr2line"):
        path = shutil.which(exe)
        checks.append(_check(exe, bool(path), path or "not in PATH"))

    required_failures = [c for c in checks if c["required"] and not c["ok"]]
    return {
        "chip": chip,
        "ok": not required_failures,
        "required_failures": required_failures,
        "checks": checks,
    }


def format_report(report: dict) -> str:
    lines = [f"stm32-keil doctor chip={report['chip']} ok={report['ok']}"]
    for c in report["checks"]:
        mark = "OK" if c["ok"] else ("FAIL" if c["required"] else "WARN")
        lines.append(f"[{mark}] {c['name']}: {c['detail']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check stm32-keil environment")
    parser.add_argument("--chip", default="STM32F407ZGT6")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_doctor(args.chip)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
