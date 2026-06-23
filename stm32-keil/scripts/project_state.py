"""
Project state persistence for STM32 projects.
Saves/loads project context to .stm32_project.json for incremental development.
"""
import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any


STATE_FILE = ".stm32_project.json"


def state_path(project_dir: str) -> str:
    """Get the full path to the project state file."""
    return os.path.join(project_dir, STATE_FILE)


def save_state(project_dir: str, state: Dict[str, Any]) -> None:
    """Save project state to .stm32_project.json."""
    path = state_path(project_dir)
    state["_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_state(project_dir: str) -> Dict[str, Any]:
    """Load project state from .stm32_project.json."""
    path = state_path(project_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def update_state(project_dir: str, **kwargs) -> Dict[str, Any]:
    """Update specific fields in the project state."""
    state = load_state(project_dir)
    state.update(kwargs)
    save_state(project_dir, state)
    return state


def init_state(
    project_dir: str,
    chip: str,
    library: str,
    name: str,
    peripherals: Optional[list] = None,
    pins: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Initialize a new project state."""
    state = {
        "chip": chip,
        "library": library,
        "name": name,
        "peripherals": peripherals or [],
        "pins": pins or {},
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_build": None,
        "last_flash": None,
        "build_count": 0,
        "flash_count": 0,
        "last_build_errors": 0,
        "last_build_warnings": 0,
    }
    save_state(project_dir, state)
    return state


def record_build(
    project_dir: str,
    success: bool,
    errors: int = 0,
    warnings: int = 0,
    flash_used: str = "",
    ram_used: str = "",
) -> Dict[str, Any]:
    """Record a build result in the project state."""
    state = load_state(project_dir)
    state["last_build"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["last_build_success"] = success
    state["last_build_errors"] = errors
    state["last_build_warnings"] = warnings
    state["build_count"] = state.get("build_count", 0) + 1
    if flash_used:
        state["last_flash_used"] = flash_used
    if ram_used:
        state["last_ram_used"] = ram_used
    save_state(project_dir, state)
    return state


def record_flash(
    project_dir: str,
    success: bool,
    backend: str = "",
) -> Dict[str, Any]:
    """Record a flash result in the project state."""
    state = load_state(project_dir)
    state["last_flash"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["last_flash_success"] = success
    state["last_flash_backend"] = backend
    state["flash_count"] = state.get("flash_count", 0) + 1
    save_state(project_dir, state)
    return state


def get_changed_sources(project_dir: str) -> list:
    """Get list of .c files modified since last build."""
    state = load_state(project_dir)
    last_build = state.get("last_build")
    if not last_build:
        return []  # No previous build, can't determine changes

    last_build_ts = time.mktime(time.strptime(last_build, "%Y-%m-%d %H:%M:%S"))
    changed = []

    for root, dirs, files in os.walk(project_dir):
        # Skip build output directories
        dirs[:] = [d for d in dirs if d not in ("Objects", "Listings", "__pycache__", ".git")]
        for f in files:
            if f.endswith((".c", ".h")):
                fpath = os.path.join(root, f)
                if os.path.getmtime(fpath) > last_build_ts:
                    changed.append(os.path.relpath(fpath, project_dir))

    return changed


def format_state_summary(state: Dict[str, Any]) -> str:
    """Format project state as a readable summary."""
    if not state:
        return "No project state found."

    lines = [
        f"Project: {state.get('name', '?')}",
        f"Chip: {state.get('chip', '?')}",
        f"Library: {state.get('library', '?')}",
    ]

    if state.get("peripherals"):
        lines.append(f"Peripherals: {', '.join(state['peripherals'])}")

    if state.get("pins"):
        pin_str = ", ".join(f"{k}={v}" for k, v in state["pins"].items())
        lines.append(f"Pins: {pin_str}")

    if state.get("last_build"):
        status = "OK" if state.get("last_build_success") else "FAILED"
        lines.append(f"Last build: {state['last_build']} ({status}, "
                     f"{state.get('last_build_errors', 0)} errors, "
                     f"{state.get('last_build_warnings', 0)} warnings)")
    else:
        lines.append("Last build: never")

    if state.get("last_flash"):
        status = "OK" if state.get("last_flash_success") else "FAILED"
        lines.append(f"Last flash: {state['last_flash']} ({status}, "
                     f"backend={state.get('last_flash_backend', '?')})")

    lines.append(f"Builds: {state.get('build_count', 0)}, Flashes: {state.get('flash_count', 0)}")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="STM32 project state manager")
    sub = parser.add_subparsers(dest="cmd")

    # show
    p_show = sub.add_parser("show", help="Show project state")
    p_show.add_argument("--path", default=".", help="Project directory")

    # init
    p_init = sub.add_parser("init", help="Initialize project state")
    p_init.add_argument("--path", default=".", help="Project directory")
    p_init.add_argument("--chip", required=True, help="Chip name")
    p_init.add_argument("--library", required=True, choices=["SPL", "HAL"])
    p_init.add_argument("--name", required=True, help="Project name")
    p_init.add_argument("--peripherals", default="", help="Comma-separated peripherals")
    p_init.add_argument("--pins", default="{}", help="JSON pin assignments")

    # changed
    p_changed = sub.add_parser("changed", help="Show changed files since last build")
    p_changed.add_argument("--path", default=".", help="Project directory")

    args = parser.parse_args()

    if args.cmd == "show":
        state = load_state(args.path)
        print(format_state_summary(state))
    elif args.cmd == "init":
        periph = [p.strip() for p in args.peripherals.split(",") if p.strip()]
        pins = json.loads(args.pins)
        state = init_state(args.path, args.chip, args.library, args.name, periph, pins)
        print("Project state initialized:")
        print(format_state_summary(state))
    elif args.cmd == "changed":
        changed = get_changed_sources(args.path)
        if changed:
            print(f"Changed since last build ({len(changed)} files):")
            for f in changed:
                print(f"  {f}")
        else:
            print("No changes detected (or no previous build).")
    else:
        parser.print_help()
