"""
Generate CMake/GCC files from .uvprojx and run a real configure/build.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmake_generator import generate_cmake


def _run(cmd, cwd: Path, timeout: int) -> dict:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           timeout=timeout, shell=False)
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
            "ok": p.returncode == 0,
        }
    except Exception as exc:
        return {"cmd": cmd, "returncode": -1, "stdout": "", "stderr": str(exc), "ok": False}


def verify(uvprojx: str, build_dir: str = "", timeout: int = 240) -> dict:
    cmake = shutil.which("cmake")
    gcc = shutil.which("arm-none-eabi-gcc")
    ninja = shutil.which("ninja")
    if not cmake or not gcc:
        return {
            "ok": False,
            "skipped": True,
            "reason": "cmake or arm-none-eabi-gcc not found in PATH",
            "cmake": cmake,
            "gcc": gcc,
        }

    generated = generate_cmake(uvprojx)
    project_dir = Path(generated["cmake"]).parent
    out_dir = Path(build_dir) if build_dir else project_dir / "build-gcc"
    out_dir.mkdir(parents=True, exist_ok=True)

    configure = [cmake, "-S", str(project_dir), "-B", str(out_dir)]
    if ninja:
        configure += ["-G", "Ninja"]
    build = [cmake, "--build", str(out_dir)]

    c1 = _run(configure, project_dir, timeout)
    if not c1["ok"]:
        return {"ok": False, "skipped": False, "generated": generated, "configure": c1}
    c2 = _run(build, project_dir, timeout)
    return {
        "ok": c2["ok"],
        "skipped": False,
        "generated": generated,
        "configure": c1,
        "build": c2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify CMake/GCC build exported from Keil")
    parser.add_argument("--project", required=True, help=".uvprojx path")
    parser.add_argument("--build-dir", default="")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    result = verify(args.project, args.build_dir, args.timeout)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") or result.get("skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
