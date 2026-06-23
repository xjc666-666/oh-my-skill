"""
Offline packaging check for the mspm0g3519 skill.

This validates the skill structure without requiring Keil, SysConfig, a debug
probe, or MSPM0G3519 hardware.
"""
import argparse
import compileall
import json
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"

REQUIRED_FILES = [
    "SKILL.md",
    "chip_db.json",
    "requirements.txt",
    "references/hardware_pin_map.json",
    "references/peripheral_db.json",
    "references/bsp_index.json",
    "references/clock_tree_ref.json",
    "references/error_patterns.json",
    "references/sdk_paths.json",
    "skeleton/empty/Project/empty.uvprojx",
    "skeleton/empty/User/config.syscfg",
    "skeleton/empty/User/main.c",
]

JSON_FILES = [
    "chip_db.json",
    "references/hardware_pin_map.json",
    "references/peripheral_db.json",
    "references/bsp_index.json",
    "references/clock_tree_ref.json",
    "references/error_patterns.json",
    "references/sdk_paths.json",
]

HELP_SCRIPTS = [
    "clock_calculator.py",
    "code_checker.py",
    "code_writer.py",
    "dfp_checker.py",
    "driverlib_manager.py",
    "error_fixer.py",
    "flasher.py",
    "hardfault_analyzer.py",
    "hardfault_watcher.py",
    "keil_builder.py",
    "project_creator.py",
    "sdk_detector.py",
    "serial_bridge.py",
    "serial_monitor.py",
    "syscfg_generator.py",
    "syscfg_parser.py",
    "uvprojx_modifier.py",
]


def run_checks() -> dict:
    """Run all offline self-checks."""
    issues = []

    for rel in REQUIRED_FILES:
        if not (SKILL_DIR / rel).exists():
            issues.append({"check": "required_file", "path": rel, "error": "missing"})

    _check_skill_frontmatter(issues)
    _check_json_files(issues)
    _check_python_compile(issues)
    _check_script_help(issues)

    return {
        "success": not issues,
        "skill_dir": str(SKILL_DIR),
        "issues": issues,
    }


def _check_skill_frontmatter(issues: list) -> None:
    path = SKILL_DIR / "SKILL.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        issues.append({"check": "frontmatter", "path": "SKILL.md", "error": "missing opening ---"})
        return
    end = text.find("\n---", 4)
    if end < 0:
        issues.append({"check": "frontmatter", "path": "SKILL.md", "error": "missing closing ---"})
        return
    frontmatter = text[4:end]
    if "name: mspm0g3519" not in frontmatter:
        issues.append({"check": "frontmatter", "path": "SKILL.md", "error": "name must be mspm0g3519"})
    if "description:" not in frontmatter:
        issues.append({"check": "frontmatter", "path": "SKILL.md", "error": "description is required"})


def _check_json_files(issues: list) -> None:
    for rel in JSON_FILES:
        path = SKILL_DIR / rel
        if not path.exists():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append({"check": "json", "path": rel, "error": str(exc)})


def _check_python_compile(issues: list) -> None:
    ok = compileall.compile_dir(str(SCRIPTS_DIR), quiet=1)
    if not ok:
        issues.append({"check": "python_compile", "path": "scripts", "error": "compileall failed"})


def _check_script_help(issues: list) -> None:
    for name in HELP_SCRIPTS:
        path = SCRIPTS_DIR / name
        if not path.exists():
            issues.append({"check": "script_help", "path": f"scripts/{name}", "error": "missing"})
            continue
        proc = subprocess.run(
            [sys.executable, str(path), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=15,
        )
        if proc.returncode != 0:
            issues.append({
                "check": "script_help",
                "path": f"scripts/{name}",
                "error": proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}",
            })


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline self-check for mspm0g3519 skill")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    result = run_checks()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["success"]:
            print("mspm0g3519 self-check passed.")
        else:
            print("mspm0g3519 self-check failed:")
            for issue in result["issues"]:
                print(f"- {issue['check']} {issue.get('path', '')}: {issue['error']}")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
