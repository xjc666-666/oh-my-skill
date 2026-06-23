"""
Serial Agent API
================
Non-blocking API for the opencode Agent to interact with the serial daemon.

All read functions read from the JSON buffer file written by the daemon.
All write functions write to the command file consumed by the daemon.
This means the Agent NEVER blocks on serial I/O.

Usage (from within opencode):
    from serial_agent import serial_read, serial_send, serial_parse, serial_status

    # Read last 30 lines from serial
    data = serial_read(30)
    print(data)

    # Send a command to the board
    serial_send("set kp 1.5")

    # Wait for board to boot
    serial_wait_for("BOOT_OK", timeout=10)

    # Get parsed key:value data
    points = serial_parse(50)
    # -> [{"temp": 25.3, "vcc": 3.3}, ...]
"""

import os
import re
import json
import time
import signal
import atexit
import tempfile
import datetime
import subprocess
from typing import Optional, List, Dict
from pathlib import Path

# ─── Constants ────────────────────────────────────────────────────────────────

BUFFER_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_buffer.json")
CMD_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_cmd.bin")
PID_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_bridge.pid")

_RE_KEYVAL = re.compile(r'(\w+)\s*[:=]\s*(-?[\d.]+(?:e[+-]?\d+)?)', re.IGNORECASE)
_RE_NUMBER = re.compile(r'-?[\d.]+(?:e[+-]?\d+)?')

# ─── Reading (non-blocking) ────────────────────────────────────────────────────

def _read_state() -> Dict:
    try:
        with open(BUFFER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"timestamp": "", "stats": {}, "text": "", "parsed": []}


def serial_read(n: int = 50) -> str:
    """Read last N lines of serial output. Non-blocking."""
    state = _read_state()
    lines = state.get("text", "").splitlines(True)
    return "".join(lines[-n:])


def serial_parse(n: int = 50) -> List[Dict]:
    """Get last N parsed key:value data points. Non-blocking."""
    state = _read_state()
    return state.get("parsed", [])[-n:]


def serial_numbers(n: int = 50) -> List[List[float]]:
    """Get last N lines as numeric arrays. Non-blocking."""
    state = _read_state()
    text = state.get("text", "")
    results = []
    for line in text.splitlines()[-n:]:
        nums = [float(m) for m in _RE_NUMBER.findall(line)]
        if nums:
            results.append(nums)
    return results


def serial_status() -> Dict:
    """Get daemon status: connected, bytes, lines, timestamp."""
    state = _read_state()
    return {
        "connected": serial_is_connected(),
        "timestamp": state.get("timestamp", ""),
        "total_bytes": state.get("stats", {}).get("total_bytes", 0),
        "line_count": state.get("stats", {}).get("line_count", 0),
    }


def serial_is_connected() -> bool:
    """Check if the serial daemon is currently running."""
    if not os.path.isfile(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5
            )
            return f'"{pid}"' in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


# ─── Writing (non-blocking) ────────────────────────────────────────────────────

def serial_send(text: str, append_newline: bool = True) -> bool:
    """Queue text for sending to the serial port. Non-blocking.
    Returns True if queued successfully."""
    payload = (text + ("\r\n" if append_newline else "")).encode("utf-8", errors="replace")
    try:
        with open(CMD_FILE, "ab") as f:
            f.write(payload)
        return True
    except OSError:
        return False


def serial_send_raw(data: bytes) -> bool:
    """Queue raw bytes for sending to the serial port. Non-blocking."""
    try:
        with open(CMD_FILE, "ab") as f:
            f.write(data)
        return True
    except OSError:
        return False


# ─── Synchronization ──────────────────────────────────────────────────────────

def serial_wait_for(magic: str, timeout: float = 10.0, poll_interval: float = 0.15) -> bool:
    """Block until `magic` appears in the serial stream after this call.
    Used to sync with board boot (e.g. wait for 'BOOT_OK').
    Returns True on match, False on timeout."""
    base = len(_read_state().get("text", ""))
    start = time.time()
    while time.time() - start < timeout:
        text = _read_state().get("text", "")
        if len(text) > base and magic in text[base:]:
            return True
        time.sleep(poll_interval)
    return False


# ─── Port Management ──────────────────────────────────────────────────────────

def serial_list_ports() -> List[Dict]:
    """List all available serial ports. Non-blocking."""
    try:
        import serial.tools.list_ports
        ports = []
        for p in serial.tools.list_ports.comports():
            is_bt = "BTHENUM" in (p.hwid or "")
            ports.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "is_bluetooth": is_bt,
            })
        return ports
    except ImportError:
        return []


def serial_detect_port() -> Optional[str]:
    """Auto-detect the best serial port. Non-blocking."""
    try:
        import serial.tools.list_ports
        keywords = ["stlink", "ch340", "ch341", "usb-serial",
                    "usb serial", "usb2.0-serial", "stmicroelectronics"]
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            combined = desc + " " + hwid
            for kw in keywords:
                if kw in combined:
                    return p.device
        for p in serial.tools.list_ports.comports():
            if "BTHENUM" not in (p.hwid or ""):
                return p.device
    except ImportError:
        pass
    return None


def serial_detect_baud(project_dir: str) -> Optional[int]:
    """Scan a Keil project for the USART baud rate. Prioritizes user code."""
    patterns = [
        r'uart_init\s*\(\s*(\d+)\s*\)',
        r'USART1_Init\s*\(\s*(\d+)\s*\)',
        r'USART_BaudRate\s*=\s*(\d+)',
        r'huart.*\.Init\.BaudRate\s*=\s*(\d+)',
        r'#define\s+BAUD_RATE\s+(\d+)',
        r'#define\s+USART_BAUD\s+(\d+)',
    ]

    def _scan_dir(search_dir: str) -> Optional[int]:
        try:
            for root, dirs, files in os.walk(search_dir):
                for f in files:
                    if f.endswith(('.c', '.h')):
                        try:
                            with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as fh:
                                content = fh.read()
                            for pat in patterns:
                                m = re.search(pat, content)
                                if m:
                                    val = int(m.group(1))
                                    if val > 0:
                                        return val
                        except Exception:
                            continue
        except Exception:
            pass
        return None

    for subdir in ("User", "Drive"):
        d = os.path.join(project_dir, subdir)
        if os.path.isdir(d):
            result = _scan_dir(d)
            if result:
                return result

    return _scan_dir(project_dir)


# ─── Daemon Control ────────────────────────────────────────────────────────────

def serial_start_daemon(port: str, baud: int = 115200) -> bool:
    """Start the serial daemon in background. Returns True on success."""
    if serial_is_connected():
        return True

    script_dir = Path(__file__).resolve().parent
    tui_script = script_dir / "serial_tui.py"

    script_path = str(tui_script) if tui_script.exists() else "serial_tui.py"

    if os.name == "nt":
        try:
            subprocess.Popen(
                ["pythonw", script_path, "--port", port, "--baud", str(baud)],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            )
        except Exception:
            subprocess.Popen(
                ["python", script_path, "--port", port, "--baud", str(baud)],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
    else:
        subprocess.Popen(
            ["python3", script_path, "--port", port, "--baud", str(baud)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    time.sleep(1.0)
    return serial_is_connected()


def serial_stop_daemon() -> bool:
    """Stop the serial daemon. Returns True if daemon was running."""
    if not os.path.isfile(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        return True
    except (OSError, ValueError):
        return False


# ─── Convenience ──────────────────────────────────────────────────────────────

def serial_launch_tui(port: str = "", baud: int = 115200,
                      project_dir: str = "") -> bool:
    """Launch the Serial TUI in a separate terminal window.
    The TUI runs independently and the Agent can still read/write via this API.
    Returns True if launched successfully."""
    script_dir = Path(__file__).resolve().parent
    tui_script = script_dir / "serial_tui.py"
    script_path = str(tui_script)

    args = [script_path]
    if port:
        args.extend(["--port", port])
    else:
        args.append("--auto")
    if baud and baud != 115200:
        args.extend(["--baud", str(baud)])
    if project_dir:
        args.extend(["--project", project_dir])

    if os.name == "nt":
        try:
            cmd = f'cmd /c "python \"{script_path}\"'
            for a in args[1:]:
                cmd += f' {a}'
            cmd += '"'
            subprocess.Popen(
                f'start "STM32 Serial Debug" {cmd}',
                shell=True,
            )
            return True
        except Exception as e:
            print(f"Failed to launch TUI: {e}")
            return False
    else:
        try:
            terminal = os.environ.get("TERMINAL", "x-terminal-emulator")
            subprocess.Popen(
                [terminal, "-e", "python3"] + args,
                start_new_session=True,
            )
            return True
        except Exception as e:
            print(f"Failed to launch TUI: {e}")
            return False


def serial_get_value(key: str, default=None):
    """Extract the latest value of a key from parsed data. Non-blocking."""
    parsed = serial_parse(100)
    for pt in reversed(parsed):
        if key in pt:
            return pt[key]
    return default


def serial_watch_data(keys: List[str], n: int = 50) -> Dict[str, List]:
    """Get time-series of specified keys from parsed data. Non-blocking."""
    parsed = serial_parse(n)
    result = {k: [] for k in keys}
    for pt in parsed:
        for k in keys:
            result[k].append(pt.get(k, None))
    return result
