"""
Classify and recover common STM32 workflow failures.

This script ties together build parsing, existing source fixers, flash config
repair, and serial/fault diagnostics into one explicit loop.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keil_builder import compile_project, get_build_summary
from error_fixer import analyze_and_fix, apply_fix_edits
from uvprojx_modifier import ensure_flash_download_config


RULES = [
    ("flash_algorithm", r"No Algorithm found|Flash Download failed", "Run flash-config, verify DFP, retry Keil flash."),
    ("probe_connection", r"Cannot connect|No target connected|SWD Communication Failure|No STLink", "Check USB, SWDIO/SWCLK/GND/3V3, target power, BOOT0."),
    ("dfp_missing", r"Pack .* not installed|Device.*not found|Cannot load flash programming algorithm", "Install the matching Keil DFP pack."),
    ("missing_header", r"cannot open source input file|file not found|No such file", "Fix include paths or add missing driver files."),
    ("undefined_symbol", r"Undefined symbol|undefined reference", "Add source file to .uvprojx or fix function name mismatch."),
    ("undeclared_identifier", r"undeclared identifier|unknown type name|implicit declaration", "Add the correct header or family-specific SPL/HAL include."),
    ("empty_runtime", r"BOOT_OK timeout|no serial output|serial silent", "Check main loop, UART pins/baud, and call DBG_InitBanner after init."),
    ("hardfault", r"HardFault|BusFault|UsageFault|MemManage", "Decode PC/LR with hardfault_analyzer.py and inspect CFSR."),
]


def classify_text(text: str) -> List[Dict]:
    hits = []
    for code, pattern, action in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            hits.append({"code": code, "action": action})
    if not hits and text.strip():
        hits.append({"code": "unknown", "action": "Read the first real error line and avoid changing unrelated files."})
    return hits


def build_recovery_loop(uvprojx: str, project_root: str = "", max_rounds: int = 3,
                        apply: bool = False, rebuild: bool = False) -> Dict:
    project_dir = project_root or str(Path(uvprojx).resolve().parent.parent)
    report = {
        "project": uvprojx,
        "project_root": project_dir,
        "apply": apply,
        "rounds": [],
        "success": False,
    }

    ensure_flash_download_config(uvprojx)

    for round_no in range(1, max_rounds + 1):
        build = compile_project(uvprojx, rebuild=rebuild)
        round_info = {
            "round": round_no,
            "build_success": build.success,
            "errors": [e._asdict() for e in build.errors],
            "warnings": [w._asdict() for w in build.warnings[:20]],
            "summary": get_build_summary(build),
        }
        if build.success:
            report["rounds"].append(round_info)
            report["success"] = True
            return report

        fixes = analyze_and_fix(build.errors, project_dir, verbose=False)
        round_info["fixes"] = [
            {
                "fixed": f.fixed,
                "description": f.description,
                "edits": len(f.file_edits),
            }
            for f in fixes
        ]
        modified, diff = apply_fix_edits(fixes, project_dir, dry_run=not apply)
        round_info["files_modified"] = modified
        round_info["diff"] = diff[:12000]
        round_info["classification"] = classify_text(build.output)
        report["rounds"].append(round_info)

        if not apply or modified == 0:
            return report

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="STM32 build/flash error recovery helper")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("classify", help="Classify a log file or text")
    c.add_argument("--log", help="Log file path")
    c.add_argument("--text", default="")

    b = sub.add_parser("build-loop", help="Compile and optionally apply known safe fixes")
    b.add_argument("--project", required=True, help=".uvprojx path")
    b.add_argument("--project-root", default="")
    b.add_argument("--max-rounds", type=int, default=3)
    b.add_argument("--apply", action="store_true")
    b.add_argument("--rebuild", action="store_true")

    args = parser.parse_args()
    if args.command == "classify":
        text = args.text
        if args.log:
            text += "\n" + Path(args.log).read_text(encoding="utf-8", errors="ignore")
        print(json.dumps(classify_text(text), indent=2, ensure_ascii=False))
        return 0

    if args.command == "build-loop":
        result = build_recovery_loop(args.project, args.project_root,
                                     args.max_rounds, args.apply, args.rebuild)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("success") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
