"""
Auto-detect STM32CubeMX installation.

Searches in this order:
  1. CUBEMX_PATH environment variable
  2. Known installation directories (D:/Cube, C:/Program Files/..., etc.)
  3. Windows registry (HKCU/HKLM)
  4. PATH (for STM32CubeMX.exe)
  5. Default IzPack installer marker (C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX)

Returns the path to STM32CubeMX.exe. If not found, emits a message for the
caller to ask the user interactively.
"""
import os
import sys
from pathlib import Path
from typing import Optional


# Known installation directories (checked in order)
_KNOWN_CUBEMX_PATHS = [
    r"D:\Cube",
    r"E:\Cube",
    r"F:\Cube",
    r"C:\Cube",
    r"D:\STM32CubeMX",
    r"C:\STM32CubeMX",
    r"D:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX",
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX",
    r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeMX",
    r"D:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeMX",
]


def _check_dir(path: str) -> Optional[str]:
    """Check if a directory contains STM32CubeMX.exe."""
    exe = os.path.join(path, "STM32CubeMX.exe")
    if os.path.isfile(exe):
        return exe
    # Also check for .exe in a 'bin' subdirectory
    exe = os.path.join(path, "bin", "STM32CubeMX.exe")
    if os.path.isfile(exe):
        return exe
    return None


def _try_registry_cubemx() -> Optional[str]:
    r"""Try to find CubeMX path from Windows registry.

    CubeMX (IzPack-based installer) may write to:
      HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\STM32CubeMX
    """
    try:
        import winreg
    except ImportError:
        return None

    keys_to_try = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\STM32CubeMX"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\STM32CubeMX"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\STM32CubeMX"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\STMicroelectronics\STM32CubeMX"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\STMicroelectronics\STM32CubeMX"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\STMicroelectronics\STM32CubeMX"),
    ]
    for hkey, subkey in keys_to_try:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                # Try common value names
                for val_name in ("InstallLocation", "InstallPath", "Path",
                                 "UninstallString", "DisplayIcon"):
                    try:
                        val, _ = winreg.QueryValueEx(key, val_name)
                        if val:
                            # UninstallString / DisplayIcon may point to the exe
                            if val.lower().endswith(".exe"):
                                parent = os.path.dirname(val)
                                exe = _check_dir(parent)
                                if exe:
                                    return exe
                            else:
                                exe = _check_dir(val)
                                if exe:
                                    return exe
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def find_cubemx() -> Optional[str]:
    """Search for STM32CubeMX installation.

    Returns the full path to STM32CubeMX.exe, or None if not found.
    """
    # 1. Environment variable
    env = os.environ.get("CUBEMX_PATH", "") or os.environ.get("STM32CUBEMX_PATH", "")
    if env:
        if os.path.isfile(env) and env.lower().endswith(".exe"):
            return env
        exe = _check_dir(env)
        if exe:
            return exe

    # 2. Known installation directories
    for p in _KNOWN_CUBEMX_PATHS:
        exe = _check_dir(p)
        if exe:
            return exe

    # 3. Windows registry
    result = _try_registry_cubemx()
    if result:
        return result

    # 4. Search PATH
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(path_dir, "STM32CubeMX.exe")
        if os.path.isfile(exe):
            return exe

    # 5. Try all drive letters D-Z for Cube/ directory
    for drive_letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        p = f"{drive_letter}:\\Cube"
        exe = _check_dir(p)
        if exe:
            return exe

    return None


def get_cubemx_or_ask() -> str:
    """Get CubeMX path. Returns the path or a marker indicating ask-user is needed.

    This function is suitable for use in scripts that run non-interactively;
    it will print a JSON status line that the skill runner can parse to know
    whether to AskUserQuestion for the path.

    Returns:
        Path to STM32CubeMX.exe on success.
        On failure, prints JSON with status="ask_user" to stdout and
        returns empty string.
    """
    exe = find_cubemx()
    if exe:
        return exe

    # Not found — emit a structured message for the skill runner
    import json
    print(json.dumps({
        "status": "ask_user",
        "message": (
            "未找到 STM32CubeMX 安装路径。请提供 STM32CubeMX 的安装目录"
            "（包含 STM32CubeMX.exe 的文件夹）。\n"
            "可以从 https://www.st.com/stm32cubemx 下载安装。"
        ),
        "env_var": "CUBEMX_PATH",
        "known_paths": _KNOWN_CUBEMX_PATHS,
    }, ensure_ascii=False))
    return ""


def get_cubemx_version(cubemx_exe: str) -> Optional[str]:
    """Extract CubeMX version from the .installationinformation file."""
    install_dir = os.path.dirname(cubemx_exe)
    info_file = os.path.join(install_dir, ".installationinformation")
    if os.path.isfile(info_file):
        try:
            with open(info_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            # Look for APP_VER key
            import re
            m = re.search(r'APP_VER.*?([\d.]+)', content)
            if m:
                return m.group(1)
        except Exception:
            pass
    return None


if __name__ == "__main__":
    exe = find_cubemx()
    if exe:
        ver = get_cubemx_version(exe) or "unknown"
        print(f"CubeMX found: {exe}")
        print(f"Version: {ver}")
    else:
        print("CubeMX not found.")
        result = get_cubemx_or_ask()
        if not result:
            print("Run with --ask flag to locate manually.")
        sys.exit(1)
