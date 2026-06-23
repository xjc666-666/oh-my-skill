"""
Flash STM32 firmware via multiple backends.

Supported (in priority order):
  1. STM32_Programmer_CLI  — official, current (ST-Link / J-Link / DFU)
  2. Keil built-in (uv4 -f) — requires .uvprojx + Keil-configured driver
  3. JLink.exe              — Segger, when only J-Link is present
  4. ST-LINK_CLI            — legacy, deprecated 2019 (fallback only)
"""
import os
import sys
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, NamedTuple, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import (
    find_keil_installation, find_stlink_utility, find_cube_programmer,
    find_jlink_exe, run_command, normalize_path, load_chip_db,
)


class FlashResult(NamedTuple):
    success: bool
    verify_ok: bool
    output: str
    backend: str = "unknown"
    error_message: Optional[str] = None


# ─── public entry point ───────────────────────────────────────────────

def flash(
    hex_or_uvprojx: str,
    chip: Optional[str] = None,
    backend: str = "auto",
    interface: str = "swd",
    verify: bool = True,
    timeout: int = 120,
) -> FlashResult:
    """
    Universal flash entry point.

    Args:
        hex_or_uvprojx: .hex/.bin/.elf path OR .uvprojx path (Keil backend).
        chip: chip name (e.g. STM32F407ZGT6) — required for J-Link and PyOCD backends.
        backend: "auto" | "cubeprog" | "keil" | "jlink" | "stlink_cli" | "pyocd"
        interface: "swd" | "jtag" | "dfu" (cubeprog backend)
        verify: ask the backend to verify after programming.
        timeout: seconds.

    Returns:
        FlashResult
    """
    is_uvprojx = hex_or_uvprojx.lower().endswith(".uvprojx")

    if backend == "auto":
        backend = _auto_select_backend(is_uvprojx)

    if backend == "cubeprog":
        path = find_cube_programmer()
        if not path:
            return FlashResult(False, False, "", "cubeprog",
                               "STM32_Programmer_CLI not found.")
        return _flash_cube(path, hex_or_uvprojx, interface, verify, timeout)

    if backend == "keil":
        if not is_uvprojx:
            return FlashResult(False, False, "", "keil",
                               "Keil backend requires .uvprojx path.")
        return _flash_keil(hex_or_uvprojx, verify, timeout)

    if backend == "jlink":
        path = find_jlink_exe()
        if not path:
            return FlashResult(False, False, "", "jlink", "JLink.exe not found.")
        if not chip:
            return FlashResult(False, False, "", "jlink",
                               "J-Link backend requires --chip.")
        return _flash_jlink(path, hex_or_uvprojx, chip, verify, timeout)

    if backend == "stlink_cli":
        path = find_stlink_utility()
        if not path:
            return FlashResult(False, False, "", "stlink_cli", "ST-LINK_CLI not found.")
        return _flash_stlink_cli(path, hex_or_uvprojx, verify, timeout)

    if backend == "pyocd":
        if not chip:
            return FlashResult(False, False, "", "pyocd", "PyOCD backend requires --chip.")
        return _flash_pyocd(hex_or_uvprojx, chip, verify, timeout)

    return FlashResult(False, False, "", backend, f"Unknown backend: {backend}")


def flash_with_retry(
    hex_or_uvprojx: str,
    chip: Optional[str] = None,
    interface: str = "swd",
    verify: bool = True,
    timeout: int = 120,
) -> FlashResult:
    """
    Flash with automatic retry across multiple backends.

    Tries each available backend in order. If one fails, tries the next.
    Returns the first successful result, or the last failure.

    Args:
        hex_or_uvprojx: .hex/.bin/.elf or .uvprojx path
        chip: chip name (for J-Link)
        interface: swd/jtag/dfu
        verify: verify after programming
        timeout: seconds per attempt

    Returns:
        FlashResult
    """
    is_uvprojx = hex_or_uvprojx.lower().endswith(".uvprojx")

    # Build list of backends to try
    backends_to_try = []

    # 1. Preferred: Keil (if .uvprojx)
    if is_uvprojx and find_keil_installation():
        backends_to_try.append("keil")

    # 2. PyOCD
    if chip and shutil.which("pyocd"):
        backends_to_try.append("pyocd")

    # 3. STM32CubeProgrammer
    if find_cube_programmer():
        backends_to_try.append("cubeprog")

    # 4. J-Link (needs chip name)
    if chip and find_jlink_exe():
        backends_to_try.append("jlink")

    # 5. ST-LINK_CLI (legacy)
    if find_stlink_utility():
        backends_to_try.append("stlink_cli")

    if not backends_to_try:
        return FlashResult(False, False, "", "none",
                           "没有找到任何烧录工具。请安装 STM32CubeProgrammer、Keil、J-Link 或 ST-LINK_CLI。")

    last_error = ""
    for backend in backends_to_try:
        print(f"尝试烧录后端: {backend} ...")
        result = flash(hex_or_uvprojx, chip, backend, interface, verify, timeout)

        if result.success:
            print(f"烧录成功 (后端: {backend})")
            return result

        last_error = result.error_message or result.output
        print(f"后端 {backend} 失败: {last_error}")

        # Analyze error and provide recovery suggestions
        recovery = _suggest_recovery(last_error, backend)
        if recovery:
            print(f"恢复建议: {recovery}")

    return FlashResult(False, False, "", ",".join(backends_to_try),
                       f"所有烧录后端都失败。最后错误: {last_error}")


def _suggest_recovery(error_msg: str, backend: str) -> str:
    """Suggest recovery actions based on error message."""
    error_lower = error_msg.lower()

    # USB connection issues
    if "no st-link" in error_lower or "no stlink" in error_lower or "usb" in error_lower:
        return ("检查 USB 连接。确认 ST-Link 已连接且驱动已安装。"
                "尝试：拔插 USB 线、更换 USB 端口、重启开发板。")

    # SWD connection issues
    if "swd" in error_lower or "connect" in error_lower or "target" in error_lower:
        return ("SWD 连接失败。检查接线：SWDIO→PA13, SWCLK→PA14, GND→GND, 3V3→3V3。"
                "确认板子已上电。尝试按住复位键再烧录。")

    # Read protection
    if "read out protection" in error_lower or "rdp" in error_lower:
        return ("芯片开启了读保护(RDP)。需要先解除保护："
                "STM32CubeProgrammer → Erase chip → Full chip erase。")

    # Keil specific
    if backend == "keil" and "no target" in error_lower:
        return ("Keil 找不到调试目标。检查 Debug → Settings 里 ST-Link 配置。"
                "确认 .uvprojx 里选对了芯片型号。")

    # File not found
    if "not found" in error_lower or "cannot find" in error_lower:
        return ("找不到烧录文件。确认编译成功且 .hex 文件存在。"
                "如果是 .uvprojx 路径，检查 Project/Objects/ 目录。")

    return ""


def _auto_select_backend(is_uvprojx: bool) -> str:
    """Pick a backend that actually works on this machine.

    Preference: Keil (uses the .uvprojx's own ST-Link config, which is what
    most users set up in Keil's Debug→Settings dialog → "Reset and Run") →
    STM32CubeProgrammer → J-Link → ST-LINK_CLI (legacy fallback).

    Keil is preferred when a .uvprojx is being flashed because it inherits
    debugger and "Reset and Run" settings from the project file.
    """
    if is_uvprojx and find_keil_installation():
        return "keil"
    if shutil.which("pyocd"):
        return "pyocd"
    if find_cube_programmer():
        return "cubeprog"
    if find_jlink_exe():
        return "jlink"
    if find_stlink_utility():
        return "stlink_cli"
    # If none found and user gave a .uvprojx, still try Keil (it can report
    # a clearer error than "no backend").
    return "keil" if is_uvprojx else "cubeprog"


# ─── STM32CubeProgrammer ──────────────────────────────────────────────

def _flash_cube(cli: str, fw: str, interface: str, verify: bool, timeout: int) -> FlashResult:
    iface = interface.upper()
    fw_abs = os.path.abspath(fw)
    if fw.lower().endswith(".uvprojx"):
        # Derive hex path from project
        hex_path = _hex_from_uvprojx(fw_abs)
        if not hex_path:
            return FlashResult(False, False, "", "cubeprog",
                               "Cannot locate .hex output for project; compile first.")
        fw_abs = hex_path

    if iface == "DFU":
        conn = ["-c", "port=USB1"]
    else:
        conn = ["-c", f"port={iface}", "freq=4000", "mode=UR", "reset=HWrst"]

    cmd = [cli, *conn, "-w", fw_abs, "-rst"]
    if verify:
        cmd.insert(-1, "-v")

    rc, out, err = run_command(cmd, timeout=timeout)
    full = out + "\n" + err

    success = ("File download complete" in full) or ("Programming completed" in full)
    verify_ok = ("Download verified successfully" in full) or ("Verifying...Done" in full)

    if rc != 0 or not success:
        return FlashResult(False, False, full, "cubeprog",
                           _extract_cube_error(full) or f"return code {rc}")
    return FlashResult(True, verify_ok or not verify, full, "cubeprog")


def _extract_cube_error(out: str) -> Optional[str]:
    err_patterns = [
        (r"No STLink detected", "未检测到 ST-Link。检查 USB 连接和驱动。"),
        (r"Error: No debug probe detected", "未检测到调试器。检查连接。"),
        (r"Error: Data read failed", "通信失败。检查 SWD/JTAG 接线。"),
        (r"Error: Cannot get current frequency", "频率检测失败。检查目标板供电。"),
        (r"Error: Programming Error", "写入失败。检查 Flash 解锁状态 (RDP)。"),
        (r"Error: Connection error", "连接错误。检查 BOOT0 / 电源 / 接线。"),
    ]
    for pat, msg in err_patterns:
        if re.search(pat, out):
            return msg
    lines = [l for l in out.splitlines() if l.lower().startswith("error")]
    return lines[-1] if lines else None


def _hex_from_uvprojx(uvprojx_path: str) -> Optional[str]:
    """Look for the .hex file emitted by Keil for this project."""
    pdir = os.path.dirname(uvprojx_path)
    for sub in ("Objects", "Listings"):
        d = os.path.join(pdir, sub)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".hex"):
                    return os.path.join(d, f)
    return None


# ─── Keil uv4 -f ──────────────────────────────────────────────────────

def _flash_keil(uvprojx_path: str, verify: bool, timeout: int) -> FlashResult:
    keil_dir = find_keil_installation()
    if not keil_dir:
        return FlashResult(False, False, "", "keil", "Keil MDK-ARM not found.")
    uv4 = os.path.join(keil_dir, "uv4.exe")
    if not os.path.isfile(uv4):
        return FlashResult(False, False, "", "keil", f"uv4.exe not found at {uv4}")

    try:
        from uvprojx_modifier import ensure_flash_download_config
        ensure_flash_download_config(uvprojx_path)
    except Exception as exc:
        print(f"Warning: Flash Download config preflight skipped: {exc}")

    proj_dir = os.path.dirname(uvprojx_path)
    log_path = os.path.join(proj_dir, "flash.log")
    try:
        if os.path.isfile(log_path):
            os.remove(log_path)
    except OSError:
        pass

    # uv4 -f does not write to stdout. -o <file> dumps the actual
    # erase / program / verify output we need.
    cmd = [uv4, "-j0", "-f", os.path.basename(uvprojx_path),
           "-o", log_path]
    rc, _, _ = run_command(cmd, cwd=proj_dir, timeout=timeout)

    full = ""
    if os.path.isfile(log_path):
        try:
            with open(log_path, "rb") as f:
                data = f.read()
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    full = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        except OSError:
            pass

    success = any(s in full for s in ("Programming Done.", "Flash Load finished",
                                       "Erase Done."))
    verify_ok = any(s in full for s in ("Verify OK.", "Verification OK",
                                         "Application running"))
    success = success and rc == 0

    if not success:
        return FlashResult(False, False, full, "keil", _extract_keil_error(full))
    return FlashResult(True, verify_ok or not verify, full, "keil")


def _extract_keil_error(out: str) -> str:
    patterns = [
        (r"No Algorithm found", "Keil Flash Download Algorithm is missing from the active ST-Link config; run uvprojx_modifier.py flash-config and flash again."),
        (r"Cannot connect to target", "无法连接目标。检查 ST-Link/接线/供电/BOOT0。"),
        (r"Flash Timeout", "烧录超时。检查连接和供电。"),
        (r"Error: Flash Download failed", "Flash 下载失败。检查芯片型号和 Flash 算法。"),
        (r"SWD Communication Failure", "SWD 通信失败。检查接线和供电。"),
        (r"No target connected", "未检测到目标芯片。"),
        (r"ST-LINK error", "ST-Link 错误。检查驱动。"),
    ]
    for pat, msg in patterns:
        if re.search(pat, out, re.IGNORECASE):
            return msg
    lines = [l.strip() for l in out.splitlines() if "error" in l.lower()]
    return lines[-1] if lines else "未知烧录错误"


# ─── J-Link ────────────────────────────────────────────────────────────

def _flash_jlink(jlink: str, fw: str, chip: str, verify: bool, timeout: int) -> FlashResult:
    # Map chip → J-Link device name (e.g. STM32F407ZG)
    db = load_chip_db()
    device_name = db.get(chip, {}).get("device", chip).rstrip("x")
    # JLink device names drop trailing x; STM32F407ZGTx → STM32F407ZG
    device_name = re.sub(r"x+$", "", device_name)

    script = _write_jlink_script(fw, device_name, verify)
    cmd = [jlink, "-Device", device_name, "-If", "SWD", "-Speed", "4000",
           "-CommandFile", script]
    rc, out, err = run_command(cmd, timeout=timeout)
    full = out + "\n" + err
    success = ("O.K." in full or "Programming flash" in full) and rc == 0
    if not success:
        return FlashResult(False, False, full, "jlink", "J-Link programming failed.")
    return FlashResult(True, True, full, "jlink")


def _write_jlink_script(hex_path: str, device: str, verify: bool) -> str:
    lines = [
        "r", "halt",
        f"loadfile \"{hex_path}\"",
    ]
    if verify:
        lines.append(f"verify \"{hex_path}\"")
    lines += ["r", "g", "q"]
    fd, path = tempfile.mkstemp(suffix=".jlink")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines))
    return path


# ─── PyOCD ─────────────────────────────────────────────────────────────

def _flash_pyocd(fw: str, chip: str, verify: bool, timeout: int) -> FlashResult:
    # Map chip → pyocd_target (e.g. stm32f407zg)
    db = load_chip_db()
    pyocd_target = db.get(chip, {}).get("pyocd_target", chip.lower().rstrip("tx"))
    
    fw_abs = os.path.abspath(fw)
    if fw.lower().endswith(".uvprojx"):
        hex_path = _hex_from_uvprojx(fw_abs)
        if not hex_path:
            return FlashResult(False, False, "", "pyocd", "Cannot locate .hex output for project; compile first.")
        fw_abs = hex_path

    cmd = [sys.executable, "-m", "pyocd", "flash", fw_abs, "--target", pyocd_target]
    if verify:
        cmd.append("--verify")
    rc, out, err = run_command(cmd, timeout=timeout)
    full = out + "\n" + err
    success = "programmed" in full.lower() and rc == 0
    verify_ok = "verified" in full.lower() if verify else False
    if not success:
        return FlashResult(False, False, full, "pyocd", "PyOCD programming failed. Check target name and probe.")
    return FlashResult(True, verify_ok, full, "pyocd")


# ─── ST-LINK CLI (legacy) ─────────────────────────────────────────────

def _flash_stlink_cli(cli: str, fw: str, verify: bool, timeout: int) -> FlashResult:
    fw_abs = os.path.abspath(fw)
    cmd = [cli, "-c", "SWD", "-P", fw_abs]
    if verify:
        cmd.append("-V")
    cmd.append("-Rst")
    rc, out, err = run_command(cmd, timeout=timeout)
    full = out + "\n" + err
    success = "Programming done." in full or "Flash programming completed" in full
    verify_ok = "Verification... OK" in full or "Verify OK" in full
    if rc != 0 or not success:
        return FlashResult(False, False, full, "stlink_cli",
                           _extract_stlink_error(full))
    return FlashResult(True, verify_ok or not verify, full, "stlink_cli")


def _extract_stlink_error(out: str) -> str:
    if re.search(r"cannot connect", out, re.IGNORECASE):
        return "无法连接 ST-Link。检查 USB / 驱动 / 设备管理器。"
    if "target connection" in out.lower() and "failed" in out.lower():
        return "无法连接目标。检查 SWD 接线 / 供电 / BOOT0。"
    lines = out.strip().splitlines()
    return lines[-1] if lines else "未知错误"


# ─── output formatting ────────────────────────────────────────────────

def format_flash_result(result: FlashResult) -> str:
    if result.success:
        verify_str = "校验通过" if result.verify_ok else "校验未确认"
        return f"[{result.backend}] 烧录成功！{verify_str}"
    return f"[{result.backend}] 烧录失败: {result.error_message or '未知错误'}"


def get_troubleshooting_guide() -> str:
    return """
## STM32 烧录故障排查

### 1. 检查工具链是否安装
- STM32CubeProgrammer (推荐): https://www.st.com/en/development-tools/stm32cubeprog.html
- ST-Link 驱动: https://www.st.com/en/development-tools/stsw-link009.html
- Segger J-Link: https://www.segger.com/downloads/jlink/

### 2. SWD 接线
```
ST-Link / J-Link      目标板
  SWCLK   ->  SWCLK / PA14
  SWDIO   ->  SWDIO / PA13
  GND     ->  GND
  3.3V    ->  VDD (3.3V)
```

### 3. BOOT 配置
- BOOT0 = GND  → 从 Flash 启动（正常）
- BOOT0 = 3.3V → 从系统存储器 (DFU/UART boot loader)

### 4. RDP 读保护
若 Flash 已被 RDP Level 1 保护：
```
STM32_Programmer_CLI -c port=SWD -ob RDP=0xAA
```
（会触发 mass-erase；Level 2 不可逆，禁止设置）
"""


# ─── back-compat shims ────────────────────────────────────────────────

def flash_via_keil(uvprojx_path: str, **kwargs) -> FlashResult:
    return flash(uvprojx_path, backend="keil", **kwargs)


def flash_via_stlink_cli(hex_path: str, **kwargs) -> FlashResult:
    return flash(hex_path, backend="stlink_cli", **kwargs)


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Flash STM32 firmware")
    parser.add_argument("--project", help="Path to .uvprojx (any backend)")
    parser.add_argument("--hex", help="Path to .hex/.bin (cubeprog/jlink/stlink)")
    parser.add_argument("--chip", help="Chip name (required for jlink and pyocd)")
    parser.add_argument("--backend", default="auto",
                        choices=["auto", "cubeprog", "keil", "jlink", "stlink_cli", "pyocd"])
    parser.add_argument("--interface", default="swd", choices=["swd", "jtag", "dfu"])
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    target = args.project or args.hex
    if not target:
        print("Error: --project or --hex required")
        sys.exit(1)

    res = flash(target, chip=args.chip, backend=args.backend,
                interface=args.interface, verify=not args.no_verify,
                timeout=args.timeout)
    print(format_flash_result(res))
    if not res.success:
        print(get_troubleshooting_guide())
    sys.exit(0 if res.success else 1)
