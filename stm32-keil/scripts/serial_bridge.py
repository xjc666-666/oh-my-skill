"""
Serial data engine for stm32-keil skill.

Opens a COM port, maintains a ring buffer, and exposes data via a JSON
state file for the skill to read. Supports structured parsing (key:value,
CSV patterns) for feedback-loop parameter tuning.

Usage:
    python serial_bridge.py --port COM5 --baud 115200        # start daemon
    python serial_bridge.py --list                            # list ports
    python serial_bridge.py --tail 30                         # read last 30 lines
    python serial_bridge.py --tail 20 --parse                 # parsed data points
    python serial_bridge.py --status                          # daemon stats
    python serial_bridge.py --stop                            # kill daemon
"""
import os
import sys
import re
import time
import json
import signal
import shutil
import threading
import tempfile
import datetime
import subprocess
import struct
from pathlib import Path
from typing import Optional, List, Dict, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import ensure_dir, find_keil_installation

# ─── constants ────────────────────────────────────────────────────────

BUFFER_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_buffer.json")
PID_FILE    = os.path.join(tempfile.gettempdir(), "stm32_serial_bridge.pid")
CMD_FILE    = os.path.join(tempfile.gettempdir(), "stm32_serial_cmd.bin")
RING_SIZE   = 65536   # bytes
MAX_LINES   = 2000

# Patterns for structured data parsing
_RE_KEYVAL = re.compile(r'(\w+)\s*[:=]\s*(-?[\d.]+(?:e[+-]?\d+)?)', re.IGNORECASE)
_RE_NUMBER = re.compile(r'-?[\d.]+(?:e[+-]?\d+)?')
_RE_HARDFAULT = re.compile(r'(?:HardFault|Fault).*?(?:PC|pc)\s*[=:]\s*(0x[0-9a-fA-F]+)', re.IGNORECASE)

VOFA_TAIL = b'\x00\x00\x80\x7f'


# ─── ring buffer ──────────────────────────────────────────────────────

class RingBuffer:
    def __init__(self):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._total = 0
        self._lines: List[str] = []
        self._vofa_frames: List[List[float]] = []
        self._bin_buf = bytearray()

    def feed(self, data: bytes) -> None:
        with self._lock:
            self._buf.extend(data)
            self._total += len(data)
            if len(self._buf) > RING_SIZE:
                self._buf = self._buf[-RING_SIZE // 2:]
            try:
                text = data.decode("utf-8", errors="replace")
                for line in text.splitlines(True):
                    self._lines.append(line)
            except Exception:
                pass
            if len(self._lines) > MAX_LINES:
                self._lines = self._lines[-MAX_LINES:]

            # Binary Vofa+ parsing
            self._bin_buf.extend(data)
            search_start = 0
            while True:
                idx = self._bin_buf.find(VOFA_TAIL, search_start)
                if idx == -1:
                    break
                frame_data = self._bin_buf[:idx]
                if len(frame_data) % 4 == 0:
                    if len(frame_data) > 0:
                        try:
                            floats = struct.unpack(f"<{len(frame_data)//4}f", frame_data)
                            self._vofa_frames.append(list(floats))
                        except Exception:
                            pass
                    self._bin_buf = self._bin_buf[idx + 4:]
                    search_start = 0
                else:
                    search_start = idx + 1
            
            if len(self._bin_buf) > 4096:
                self._bin_buf = self._bin_buf[-4096:]
            if len(self._vofa_frames) > MAX_LINES:
                self._vofa_frames = self._vofa_frames[-MAX_LINES:]

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total

    @property
    def line_count(self) -> int:
        with self._lock:
            return len(self._lines)

    def tail_text(self, n: int = 100) -> str:
        with self._lock:
            return "".join(self._lines[-n:])

    def tail_parsed(self, n: int = 100) -> List[Dict]:
        """Extract structured key:value pairs from recent lines."""
        text = self.tail_text(n)
        results = []
        for line in text.splitlines():
            pairs = dict(_RE_KEYVAL.findall(line))
            if pairs:
                # Convert numeric strings to float/int
                parsed = {}
                for k, v in pairs.items():
                    try:
                        parsed[k] = int(v) if '.' not in v and 'e' not in v.lower() else float(v)
                    except ValueError:
                        parsed[k] = v
                results.append(parsed)
        return results

    def tail_numbers(self, n: int = 100) -> List[List[float]]:
        """Extract all numeric values from each line."""
        text = self.tail_text(n)
        results = []
        for line in text.splitlines():
            nums = [float(m) for m in _RE_NUMBER.findall(line)]
            if nums:
                results.append(nums)
        return results

    def tail_vofa(self, n: int = 200) -> List[List[float]]:
        with self._lock:
            return self._vofa_frames[-n:]

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "total_bytes": self._total,
                "buffer_bytes": len(self._buf),
                "line_count": len(self._lines),
            }


# ─── daemon ───────────────────────────────────────────────────────────

_buffer: Optional[RingBuffer] = None
_stop_event: Optional[threading.Event] = None


def _flush_loop(buffer_file: str, interval: float = 0.5) -> None:
    """Periodically write buffer state to JSON file."""
    while not _stop_event.is_set():
        _stop_event.wait(interval)
        try:
            state = {
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "stats": _buffer.snapshot(),
                "text": _buffer.tail_text(500),
                "parsed": _buffer.tail_parsed(200),
                "vofa": _buffer.tail_vofa(200),
            }
            tmp = buffer_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp, buffer_file)
        except Exception:
            pass


def run_daemon(port: str, baudrate: int = 115200,
               buffer_file: Optional[str] = None) -> None:
    """Open COM port and run the data collection daemon. Blocks until stopped."""
    global _buffer, _stop_event

    if buffer_file is None:
        buffer_file = BUFFER_FILE

    _buffer = RingBuffer()
    _stop_event = threading.Event()

    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Reset command file
    try:
        if os.path.isfile(CMD_FILE):
            os.remove(CMD_FILE)
    except OSError:
        pass

    # Start flush thread
    flush_thread = threading.Thread(
        target=_flush_loop, args=(buffer_file,), daemon=True
    )
    flush_thread.start()

    # Open serial
    try:
        ser = serial.Serial(port, baudrate, timeout=0.1)
    except serial.SerialException as e:
        print(f"Error opening {port}: {e}")
        _cleanup(buffer_file)
        sys.exit(1)

    # Start outgoing command thread (host → board)
    send_thread = threading.Thread(
        target=_send_loop, args=(ser, CMD_FILE, _stop_event), daemon=True
    )
    send_thread.start()

    # Write stopped state on exit
    def _on_exit():
        _stop_event.set()
        try:
            ser.close()
        except Exception:
            pass
        _cleanup(buffer_file)
    import atexit
    atexit.register(_on_exit)

    print(f"[{_ts()}] Serial daemon: {port} @ {baudrate} baud")
    print(f"[{_ts()}] Buffer: {buffer_file}")
    print(f"[{_ts()}] Ctrl+C to stop")

    try:
        while True:
            try:
                n = ser.in_waiting
                if n > 0:
                    _buffer.feed(ser.read(n))
                else:
                    time.sleep(0.01)
            except serial.SerialException as e:
                print(f"\n[{_ts()}] Serial error: {e}")
                break
    except KeyboardInterrupt:
        print(f"\n[{_ts()}] Stopped.")
    finally:
        _on_exit()


def _cleanup(buffer_file: str) -> None:
    """Remove PID file and write final buffer state."""
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    if _buffer:
        try:
            state = {
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "stats": _buffer.snapshot(),
                "text": _buffer.tail_text(500),
                "parsed": _buffer.tail_parsed(200),
                "vofa": _buffer._vofa_frames[-200:],
            }
            with open(buffer_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
        except Exception:
            pass


# ─── public API (used by skill at runtime) ────────────────────────────

def is_running() -> bool:
    """Check if daemon is currently running."""
    if not os.path.isfile(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if sys.platform == "win32":
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


def stop_daemon() -> bool:
    """Kill the running daemon. Returns True if daemon was running."""
    if not os.path.isfile(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        os.remove(PID_FILE)
        return True
    except (OSError, ValueError):
        return False


def read_state(buffer_file: Optional[str] = None) -> Dict:
    """Read current buffer state from the daemon."""
    if buffer_file is None:
        buffer_file = BUFFER_FILE
    try:
        with open(buffer_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"timestamp": "", "stats": {}, "text": "", "parsed": []}


def tail(n: int = 30) -> str:
    """Return last N lines of text from the daemon."""
    state = read_state()
    lines = state.get("text", "").splitlines(True)
    return "".join(lines[-n:])


def tail_parsed(n: int = 50) -> List[Dict]:
    """Return last N parsed key:value data points."""
    state = read_state()
    return state.get("parsed", [])[-n:]


def tail_numbers(n: int = 50) -> List[List[float]]:
    """Return last N lines as numeric arrays."""
    state = read_state()
    text = state.get("text", "")
    results = []
    for line in text.splitlines()[-n:]:
        nums = [float(m) for m in _RE_NUMBER.findall(line)]
        if nums:
            results.append(nums)
    return results


def send_to_daemon(text: str, append_newline: bool = True) -> bool:
    """Append a payload to the command file; the daemon will write it
    to the serial port. Works cross-process (e.g. Claude in another shell)."""
    payload = (text + ("\r\n" if append_newline else "")).encode("utf-8", errors="replace")
    try:
        with open(CMD_FILE, "ab") as f:
            f.write(payload)
        return True
    except OSError:
        return False


def wait_for_sync(magic: str, timeout: float = 10.0, poll: float = 0.1) -> bool:
    """Wait until `magic` appears in the incoming text after the moment of
    this call. Returns True on match, False on timeout. Used to skip stale
    data from a previous run (e.g. board reset).
    """
    base = len(read_state().get("text", ""))
    start = time.time()
    while time.time() - start < timeout:
        text = read_state().get("text", "")
        if len(text) > base and magic in text[base:]:
            return True
        time.sleep(poll)
    return False


def _send_loop(ser, cmd_file: str, stop_event: threading.Event) -> None:
    """Drain the command file and write its tail to the serial port."""
    last_size = 0
    while not stop_event.is_set():
        try:
            if os.path.isfile(cmd_file):
                size = os.path.getsize(cmd_file)
                if size > last_size:
                    with open(cmd_file, "rb") as f:
                        f.seek(last_size)
                        data = f.read()
                    try:
                        ser.write(data)
                    except Exception:
                        pass
                    last_size = size
                elif size == 0:
                    last_size = 0
            stop_event.wait(0.05)
        except Exception:
            stop_event.wait(0.1)


# ─── port listing ─────────────────────────────────────────────────────

def list_ports() -> List[Dict]:
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


def find_stm32_port() -> Optional[str]:
    """Find the best candidate for an STM32 serial port."""
    keywords = ["stlink", "ch340", "ch341", "usb-serial", "usb serial",
                "usb2.0-serial", "stmicroelectronics"]
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        combined = desc + " " + hwid
        for kw in keywords:
            if kw in combined:
                return p.device
    for p in serial.tools.list_ports.comports():
        hwid = p.hwid or ""
        if "BTHENUM" not in hwid:
            return p.device
    return None


def detect_baud_from_project(project_dir: str) -> Optional[int]:
    """Scan a Keil project for the USART baud rate from init code.
    Prioritizes User/Drive dirs over library files."""
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

    # Priority 1: User/ directory
    user_dir = os.path.join(project_dir, "User")
    if os.path.isdir(user_dir):
        result = _scan_dir(user_dir)
        if result:
            return result

    # Priority 2: Drive/ directory
    drive_dir = os.path.join(project_dir, "Drive")
    if os.path.isdir(drive_dir):
        result = _scan_dir(drive_dir)
        if result:
            return result

    # Priority 3: Full project scan
    return _scan_dir(project_dir)


# ─── helpers ──────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")

def _safe(text: str) -> str:
    """Strip characters that can't be encoded in the console codepage."""
    return text.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(
        sys.stdout.encoding or 'utf-8', errors='replace')

def _print(*args, **kwargs):
    """Print safely, handling encoding issues."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [_safe(str(a)) for a in args]
        print(*safe_args, **kwargs)


# ─── live watch ───────────────────────────────────────────────────────

def _find_addr2line() -> Optional[str]:
    """Auto-discover addr2line from PATH, Keil toolchain, or GNU ARM."""
    # 1. Check PATH
    a2l = shutil.which("arm-none-eabi-addr2line")
    if a2l:
        return a2l

    # 2. Probe common GCC toolchain installs
    import glob
    for env_var in ("GNU_ARM_PATH", "ARM_NONE_EABI_PATH"):
        env_dir = os.environ.get(env_var, "")
        if env_dir and os.path.isdir(env_dir):
            for p in glob.glob(os.path.join(env_dir, "**", "arm-none-eabi-addr2line*"), recursive=True):
                return p

    gnu_dirs = []
    for prog in ("Program Files", "Program Files (x86)"):
        for drive in ("C", "D", "E"):
            gnu_dirs.append(os.path.join(f"{drive}:\\", prog, "GNU Arm Embedded Toolchain"))
    gnu_dirs.append(r"C:\msys64\mingw64\bin")
    for base in gnu_dirs:
        for p in glob.glob(os.path.join(base, "**", "arm-none-eabi-addr2line*"), recursive=True):
            return p

    # 3. fromelf (Keil's own) — limited but can decode addresses
    keil_uv4 = find_keil_installation()
    if keil_uv4:
        # keil_uv4 is <root>\UV4; fromelf lives at <root>\ARM\ARMCLANG\bin\fromelf.exe
        keil_root = os.path.normpath(os.path.join(keil_uv4, ".."))
        for sub in (r"ARM\ARMCLANG\bin\fromelf.exe", r"ARM\ARMCC\bin\fromelf.exe"):
            fe = os.path.join(keil_root, sub)
            if os.path.isfile(fe):
                return fe

    return None


def _resolve_hardfault(elf_path: str, pc_addr: str) -> None:
    """Run addr2line on the given PC address and print the result."""
    tool = _find_addr2line()
    if not tool:
        print(f"\n[{_ts()}] HardFault detected PC={pc_addr} but no addr2line found. Install arm-none-eabi-gcc or set PATH.")
        return
    try:
        if tool.endswith("fromelf.exe"):
            # Keil fromelf: fromelf --text -e <elf> | find the address
            cmd = [tool, "--text", "-a", "-c", elf_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                # Search for the PC address in the disassembly
                clean_addr = pc_addr.lower()
                if clean_addr.startswith("0x"):
                    clean_addr = clean_addr[2:]
                for line in res.stdout.splitlines():
                    if clean_addr in line.lower():
                        print(f"\n[{_ts()}] \U0001f525 HardFault Analyser: PC={pc_addr} => {line.strip()}")
                        return
                print(f"\n[{_ts()}] \U0001f525 HardFault detected PC={pc_addr} (address not resolved in fromelf output)")
        else:
            cmd = [tool, "-e", elf_path, "-f", "-C", pc_addr]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().splitlines()
                if len(lines) >= 2:
                    func = lines[0]
                    loc = lines[1]
                    print(f"\n[{_ts()}] \U0001f525 HardFault Analyser: PC={pc_addr} => {func} at {loc}")
    except Exception as e:
        print(f"\n[{_ts()}] HardFault addr2line error: {e}")


def watch(parse: bool = False, interval: float = 0.3,
          buffer_file: Optional[str] = None, elf_path: Optional[str] = None) -> None:
    """
    Like tail -f: continuously poll daemon buffer and print new data.
    Press Ctrl+C to stop.
    """
    last_bytes = 0
    last_parsed = 0
    mode = "parsed" if parse else "text"
    print(f"[{_ts()}] Watching {mode}... (Ctrl+C to stop)")
    print("-" * 50)

    try:
        while True:
            state = read_state(buffer_file)
            stats = state.get("stats", {})

            if parse:
                parsed = state.get("parsed", [])
                if len(parsed) > last_parsed:
                    for pt in parsed[last_parsed:]:
                        line = ", ".join(f"{k}={v}" for k, v in pt.items())
                        print(f"[{_ts()}] {line}")
                    last_parsed = len(parsed)
            else:
                total = stats.get("total_bytes", 0)
                if total > last_bytes:
                    text = state.get("text", "")
                    new_bytes = total - last_bytes
                    chunk = text[-(new_bytes):]
                    # Sanitize for console: strip non-ASCII binary garbage
                    safe = ''.join(
                        c if (32 <= ord(c) < 127) or c in '\r\n\t' else ''
                        for c in chunk
                    )
                    if safe.strip():
                        print(safe, end="", flush=True)
                        if elf_path:
                            for line in safe.splitlines():
                                match = _RE_HARDFAULT.search(line)
                                if match:
                                    pc = match.group(1)
                                    threading.Thread(target=_resolve_hardfault, args=(elf_path, pc), daemon=True).start()
                    last_bytes = total
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n[{_ts()}] Watch stopped.")


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding=sys.stdout.encoding or 'utf-8',
        errors='replace', line_buffering=True
    )
    import argparse

    p = argparse.ArgumentParser(description="STM32 Serial Data Engine")
    p.add_argument("--port", default=None, help="COM port")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate")
    p.add_argument("--list", action="store_true", help="List ports and exit")
    p.add_argument("--status", action="store_true", help="Show daemon status")
    p.add_argument("--tail", type=int, default=None, help="Read last N lines")
    p.add_argument("--parse", action="store_true", help="Parse key:value pairs")
    p.add_argument("--numbers", action="store_true", help="Extract numeric arrays")
    p.add_argument("--watch", action="store_true", help="Continuously watch live data")
    p.add_argument("--plot", action="store_true", help="Real-time matplotlib oscilloscope for Vofa+ JustFloat protocol")
    p.add_argument("--stop", action="store_true", help="Stop daemon")
    p.add_argument("--send", default=None,
                   help="Send text to board (daemon must be running)")
    p.add_argument("--no-newline", action="store_true",
                   help="Don't append \\r\\n to --send payload")
    p.add_argument("--sync-on", default=None,
                   help="Wait until magic string appears in incoming stream")
    p.add_argument("--sync-timeout", type=float, default=10.0,
                   help="Timeout for --sync-on (seconds)")
    p.add_argument("--buffer-file", default=None, help="Buffer file path")
    p.add_argument("--detect-baud", default=None, help="Project dir to auto-detect baud rate")
    p.add_argument("--elf", default=None, help="Path to .elf or .axf for HardFault analysis during watch")
    args = p.parse_args()

    if args.detect_baud:
        baud = detect_baud_from_project(args.detect_baud)
        if baud:
            print(f"Detected baud rate: {baud}")
        else:
            print("No baud rate found in project.")
        sys.exit(0)

    if args.list:
        ports = list_ports()
        if not ports:
            print("No serial ports found.")
        else:
            print(f"{len(ports)} port(s):")
            for pt in ports:
                tag = "USB" if not pt["is_bluetooth"] else "BT "
                print(f"  {tag} {pt['device']:8s}  {pt['description']}")
            best = find_stm32_port()
            if best:
                print(f"\nBest guess: {best}")
        sys.exit(0)

    if args.status:
        if is_running():
            state = read_state(args.buffer_file)
            s = state.get("stats", {})
            print(f"Daemon running:")
            print(f"  bytes: {s.get('total_bytes', 0)}")
            print(f"  lines: {s.get('line_count', 0)}")
            print(f"  updated: {state.get('timestamp', '?')}")
        else:
            print("Daemon not running.")
        sys.exit(0)

    if args.stop:
        if stop_daemon():
            print("Daemon stopped.")
        else:
            print("No daemon running.")
        sys.exit(0)

    if args.send is not None:
        if not is_running():
            print("Daemon not running. Start it first.")
            sys.exit(1)
        ok = send_to_daemon(args.send, append_newline=not args.no_newline)
        print("Sent." if ok else "Failed to queue send.")
        sys.exit(0 if ok else 1)

    if args.sync_on is not None:
        if not is_running():
            print("Daemon not running. Start it first.")
            sys.exit(1)
        ok = wait_for_sync(args.sync_on, timeout=args.sync_timeout)
        print(f"Sync {'matched' if ok else 'timed out'}: {args.sync_on!r}")
        sys.exit(0 if ok else 2)

    if args.watch:
        if not is_running():
            print("Daemon not running. Start it first:")
            print(f"  python {__file__} --port COMx --baud 115200 &")
            sys.exit(1)
        watch(parse=args.parse, buffer_file=args.buffer_file, elf_path=args.elf)
        sys.exit(0)

    if args.plot:
        if not is_running():
            print("Daemon not running. Start it first.")
            sys.exit(1)
        try:
            import matplotlib.pyplot as plt
            import matplotlib.animation as animation
        except ImportError:
            print("Error: matplotlib is required. pip install matplotlib")
            sys.exit(1)
            
        fig, ax = plt.subplots()
        ax.set_title("Vofa+ JustFloat Virtual Oscilloscope")
        lines = []

        def update(frame):
            state = read_state(args.buffer_file)
            vofa = state.get("vofa", [])
            if not vofa:
                return lines
            
            num_channels = len(vofa[-1])
            while len(lines) < num_channels:
                line, = ax.plot([], [], label=f"Ch {len(lines)}")
                lines.append(line)
                ax.legend(loc="upper right")
                
            for i in range(num_channels):
                ydata = [f[i] for f in vofa if len(f) > i]
                lines[i].set_data(range(len(ydata)), ydata)
                
            ax.relim()
            ax.autoscale_view()
            return lines

        ani = animation.FuncAnimation(fig, update, interval=50, blit=False)
        plt.show()
        sys.exit(0)

    if args.tail is not None:
        if not is_running():
            print("Daemon not running. Start it first:")
            print(f"  python {__file__} --port COMx --baud 115200 &")
            sys.exit(1)

        if args.numbers:
            data = tail_numbers(args.tail)
            if data:
                print(f"[{len(data)} numeric rows]")
                for row in data[-args.tail:]:
                    print(", ".join(f"{v:.3f}" for v in row))
            else:
                print("(no numeric data)")
        elif args.parse:
            data = tail_parsed(args.tail)
            if data:
                print(f"[{len(data)} parsed points]")
                keys = list(data[-1].keys()) if data else []
                print(f"Fields: {keys}")
                for pt in data[-args.tail:]:
                    print("  " + ", ".join(f"{k}={v}" for k, v in pt.items()))
            else:
                print("(no parseable data)")
        else:
            text = tail(args.tail)
            if text.strip():
                print(text, end="")
            else:
                print("(no data)")
        sys.exit(0)

    # Default: run daemon
    port = args.port
    if port is None:
        port = find_stm32_port()
        if port is None:
            print("Error: no COM port found. Use --port COMx or --list")
            sys.exit(1)
        print(f"Auto-detected port: {port}")

    if args.detect_baud:
        baud = detect_baud_from_project(args.detect_baud)
        if baud:
            args.baud = baud
            print(f"Auto-detected baud: {baud}")

    run_daemon(port, args.baud, args.buffer_file)
