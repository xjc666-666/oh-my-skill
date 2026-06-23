"""
Terminal Serial Debug Assistant (TUI)
=====================================
Textual-based terminal UI for STM32 serial debugging.

Features:
  - Auto-detect COM port and baud rate
  - Split-pane display: RX log (top) + TX input (bottom)
  - Color-coded: blue=RX, yellow=TX, red=error
  - Command history (up/down arrows)
  - Agent API: reads/writes through JSON buffer + CMD file
  - Non-blocking: runs in separate terminal window

Usage:
  python serial_tui.py                          # auto-detect
  python serial_tui.py --port COM21 --baud 115200
  python serial_tui.py --port COM21 --baud 115200 --project <dir>  # auto-detect baud from project

Keyboard:
  Ctrl+Q / Esc    Quit
  Ctrl+L          Clear display
  Ctrl+S          Toggle auto-scroll
  Ctrl+H          Toggle hex mode
  Enter           Send (when input focused)
  Up/Down         Command history
"""

import os
import sys
import re
import json
import time
import atexit
import threading
import tempfile
import datetime
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Deque
from collections import deque

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: pyserial is required. Install with: pip install pyserial")
    sys.exit(1)

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, RichLog, Input, Static
    from textual.containers import Container, Horizontal
    from textual.binding import Binding
    from textual import events
except ImportError:
    print("Error: textual is required. Install with: pip install textual")
    sys.exit(1)

# ─── Constants ────────────────────────────────────────────────────────────────

BUFFER_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_buffer.json")
CMD_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_cmd.bin")
PID_FILE = os.path.join(tempfile.gettempdir(), "stm32_serial_bridge.pid")
RING_SIZE = 65536
MAX_LINES = 2000
MAX_HISTORY = 200

_RE_KEYVAL = re.compile(r'(\w+)\s*[:=]\s*(-?[\d.]+(?:e[+-]?\d+)?)', re.IGNORECASE)


# ─── Ring Buffer ──────────────────────────────────────────────────────────────

class RingBuffer:
    def __init__(self):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._total = 0
        self._lines: List[str] = []

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

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total

    @property
    def line_count(self) -> int:
        with self._lock:
            return len(self._lines)

    def tail_text(self, n: int = 200) -> str:
        with self._lock:
            return "".join(self._lines[-n:])

    def tail_parsed(self, n: int = 100) -> List[Dict]:
        text = self.tail_text(n)
        results = []
        for line in text.splitlines():
            pairs = dict(_RE_KEYVAL.findall(line))
            if pairs:
                parsed = {}
                for k, v in pairs.items():
                    try:
                        parsed[k] = int(v) if '.' not in v and 'e' not in v.lower() else float(v)
                    except ValueError:
                        parsed[k] = v
                results.append(parsed)
        return results

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "total_bytes": self._total,
                "buffer_bytes": len(self._buf),
                "line_count": len(self._lines),
            }


# ─── Serial Daemon (background thread) ───────────────────────────────────────

class SerialDaemon:
    def __init__(self):
        self._buffer = RingBuffer()
        self._ser: Optional[serial.Serial] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cmd_size = 0
        self._error: Optional[str] = None
        self._connected = False
        self.port: str = ""
        self.baud: int = 115200

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def buffer(self) -> RingBuffer:
        return self._buffer

    def start(self, port: str, baud: int = 115200) -> bool:
        self.port = port
        self.baud = baud
        self._stop.clear()
        self._error = None

        try:
            self._ser = serial.Serial(port, baud, timeout=0.1)
        except serial.SerialException as e:
            self._error = str(e)
            return False

        self._connected = True

        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        try:
            if os.path.isfile(CMD_FILE):
                os.remove(CMD_FILE)
        except OSError:
            pass

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        atexit.register(self.stop)
        return True

    def stop(self):
        if self._stop.is_set():
            return
        self._stop.set()
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._connected = False
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        self._flush_state()

    def send(self, text: str) -> bool:
        if not self._ser or not self._ser.is_open:
            return False
        payload = (text + "\r\n").encode("utf-8", errors="replace")
        try:
            with open(CMD_FILE, "ab") as f:
                f.write(payload)
            return True
        except OSError:
            return False

    def _flush_state(self):
        state = {
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "stats": self._buffer.snapshot(),
            "text": self._buffer.tail_text(500),
            "parsed": self._buffer.tail_parsed(200),
        }
        try:
            tmp = BUFFER_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp, BUFFER_FILE)
        except Exception:
            pass

    def _run(self):
        last_flush = time.time()
        last_cmd_check = time.time()
        cmd_pos = 0

        while not self._stop.is_set():
            try:
                if self._ser and self._ser.is_open:
                    n = self._ser.in_waiting
                    if n > 0:
                        data = self._ser.read(n)
                        self._buffer.feed(data)

                now = time.time()
                if now - last_flush >= 0.3:
                    self._flush_state()
                    last_flush = now

                if now - last_cmd_check >= 0.05:
                    self._drain_commands(cmd_pos)
                    cmd_pos = self._cmd_size
                    last_cmd_check = now

            except serial.SerialException:
                self._error = "Serial disconnected"
                self._connected = False
                break
            except Exception:
                pass

            self._stop.wait(0.01)

    def _drain_commands(self, from_pos: int):
        try:
            if os.path.isfile(CMD_FILE):
                size = os.path.getsize(CMD_FILE)
                if size > from_pos:
                    with open(CMD_FILE, "rb") as f:
                        f.seek(from_pos)
                        data = f.read()
                    if self._ser and self._ser.is_open:
                        try:
                            self._ser.write(data)
                        except Exception:
                            pass
                    self._cmd_size = size
                elif size == 0:
                    self._cmd_size = 0
        except Exception:
            pass


# ─── Port/Baud Detection ──────────────────────────────────────────────────────

def list_serial_ports() -> List[Dict]:
    ports = []
    for p in serial.tools.list_ports.comports():
        is_bt = "BTHENUM" in (p.hwid or "")
        if not is_bt:
            ports.append({
                "device": p.device,
                "description": p.description,
            })
    return ports


def auto_detect_port() -> Optional[str]:
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
        if "BTHENUM" not in (p.hwid or ""):
            return p.device
    return None


def detect_baud_from_project(project_dir: str) -> Optional[int]:
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


# ─── Status Bar Widget ────────────────────────────────────────────────────────

class StatusBar(Static):
    """Custom status bar showing connection info and stats."""

    def __init__(self):
        super().__init__("", id="status-bar")

    def update_status(self, port: str, baud: int, connected: bool,
                      rx_bytes: int, lines: int, error: str = ""):
        if connected:
            status = f"[bold green]●[/] CONNECTED"
        else:
            status = f"[bold red]●[/] DISCONNECTED"
            if error:
                status += f" ({error})"

        port_str = port or "?"
        self.update(
            f" {status}  │  [bold]{port_str}[/] @ [bold]{baud}[/] baud  │  "
            f"Rx: [bold]{rx_bytes}[/] B  │  Lines: [bold]{lines}[/]  │  "
            f"[dim]^Q Quit  ^L Clear  ^S AutoScroll  ^H Hex[/]"
        )


# ─── Main TUI App ─────────────────────────────────────────────────────────────

class SerialTUI(App):
    """Terminal Serial Debug Assistant."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #status-bar {
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }

    #rx-pane {
        height: 1fr;
        border: solid $primary;
        background: $surface-darken-1;
    }

    #tx-container {
        height: 3;
        border: solid $secondary;
        background: $surface;
    }

    #tx-input {
        width: 1fr;
        border: none;
    }

    #send-btn {
        width: 8;
        min-width: 8;
    }

    #hint-bar {
        height: 1;
        background: $surface;
        color: $text-disabled;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        Binding("escape", "quit_app", "Quit", show=False),
        Binding("ctrl+l", "clear_log", "Clear", show=True),
        Binding("ctrl+s", "toggle_autoscroll", "AutoScroll", show=True),
        Binding("ctrl+h", "toggle_hex", "Hex", show=True),
        Binding("f1", "show_help", "Help", show=True),
    ]

    def __init__(self, port: str = "", baud: int = 115200):
        super().__init__()
        self._port_arg = port
        self._baud_arg = baud
        self._daemon = SerialDaemon()
        self._auto_scroll = True
        self._hex_mode = False
        self._history: Deque[str] = deque(maxlen=MAX_HISTORY)
        self._history_idx = -1
        self._last_text_len = 0

    def compose(self) -> ComposeResult:
        yield StatusBar()
        yield RichLog(id="rx-pane", highlight=True, wrap=True, max_lines=5000)
        with Horizontal(id="tx-container"):
            yield Input(id="tx-input", placeholder="Type command, Enter to send...")
        yield Static("", id="hint-bar")

    def on_mount(self):
        port = self._port_arg or auto_detect_port() or ""
        baud = self._baud_arg

        self.query_one("#hint-bar", Static).update(
            f" [dim]Auto-detected: {port or 'none'} @ {baud}  |  "
            f"Starting daemon...[/]"
        )

        if port:
            ok = self._daemon.start(port, baud)
            if ok:
                self._log_rx(f"[bold green]Connected to {port} @ {baud} baud[/]")
            else:
                self._log_rx(
                    f"[bold red]Failed to open {port}: {self._daemon.error}[/]"
                )
        else:
            self._log_rx("[bold red]No serial port found. Use --port to specify.[/]")

        self.set_interval(0.1, self._poll_serial)
        self._update_status()

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return

        self._history.append(text)
        self._history_idx = -1

        self._daemon.send(text)
        self._log_tx(text)

        event.input.value = ""

    def on_input_changed(self, event: Input.Changed):
        pass

    def action_quit_app(self):
        self._daemon.stop()
        self.exit()

    def action_clear_log(self):
        self.query_one("#rx-pane", RichLog).clear()
        self._last_text_len = 0

    def action_toggle_autoscroll(self):
        self._auto_scroll = not self._auto_scroll
        state = "ON" if self._auto_scroll else "OFF"
        self._log_rx(f"[dim]Auto-scroll: {state}[/]")

    def action_toggle_hex(self):
        self._hex_mode = not self._hex_mode
        state = "ON" if self._hex_mode else "OFF"
        self._log_rx(f"[dim]Hex mode: {state}[/]")

    def action_show_help(self):
        help_text = """
[bold]STM32 Serial Debug Assistant[/]

[bold]Keyboard shortcuts:[/]
  [bold]Ctrl+Q[/] / Esc    Quit
  [bold]Ctrl+L[/]          Clear display
  [bold]Ctrl+S[/]          Toggle auto-scroll
  [bold]Ctrl+H[/]          Toggle hex display
  [bold]Enter[/]           Send command
  [bold]Up/Down[/]         Command history
  [bold]F1[/]              Show this help

[bold]Agent API (via serial_agent.py):[/]
  [bold]serial_read(n)[/]      Read last N lines
  [bold]serial_send(text)[/]   Send text to board
  [bold]serial_parse(n)[/]     Get parsed key:value pairs
  [bold]serial_wait_for(s)[/]  Wait for sync string
"""
        self._log_rx(help_text)

    def _poll_serial(self):
        buf = self._daemon.buffer
        text = buf.tail_text(500)
        new_len = len(text)

        if new_len > self._last_text_len:
            chunk = text[self._last_text_len:]
            log = self.query_one("#rx-pane", RichLog)

            if self._hex_mode:
                hex_lines = []
                for b in chunk.encode("utf-8", errors="replace"):
                    hex_lines.append(f"0x{b:02X}")
                for hl in hex_lines:
                    log.write(hl)
            else:
                for line in chunk.splitlines(True):
                    stripped = line.rstrip("\r\n")
                    if stripped:
                        log.write(f"[dim]{self._ts()}[/] [cornflower_blue]←[/] {stripped}")

            self._last_text_len = new_len

        self._update_status()

    def _log_rx(self, msg: str):
        self.query_one("#rx-pane", RichLog).write(
            f"[dim]{self._ts()}[/] {msg}"
        )

    def _log_tx(self, text: str):
        self.query_one("#rx-pane", RichLog).write(
            f"[dim]{self._ts()}[/] [bold yellow]→[/] {text}"
        )

    def _update_status(self):
        buf = self._daemon.buffer
        bar = self.query_one("#status-bar", StatusBar)
        bar.update_status(
            port=self._daemon.port,
            baud=self._daemon.baud,
            connected=self._daemon.connected,
            rx_bytes=buf.total_bytes,
            lines=buf.line_count,
            error=self._daemon.error or "",
        )

    @staticmethod
    def _ts() -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def on_key(self, event: events.Key):
        if event.key == "up":
            self._navigate_history(-1)
            event.prevent_default()
        elif event.key == "down":
            self._navigate_history(1)
            event.prevent_default()

    def _navigate_history(self, direction: int):
        if not self._history:
            return
        inp = self.query_one("#tx-input", Input)
        if direction == -1:
            if self._history_idx == -1:
                self._history_idx = len(self._history) - 1
            elif self._history_idx > 0:
                self._history_idx -= 1
        else:
            if self._history_idx < len(self._history) - 1:
                self._history_idx += 1
            else:
                self._history_idx = -1

        if self._history_idx >= 0:
            inp.value = self._history[self._history_idx]
        else:
            inp.value = ""


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="STM32 Serial Debug Assistant (TUI)"
    )
    parser.add_argument("--port", default=None,
                        help="COM port (auto-detect if omitted)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="Baud rate (default: 115200)")
    parser.add_argument("--project", default=None,
                        help="Project directory for auto baud detection")
    parser.add_argument("--list", action="store_true",
                        help="List available ports and exit")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-detect both port and baud rate")
    args = parser.parse_args()

    if args.list:
        ports = list_serial_ports()
        if not ports:
            print("No serial ports found.")
        else:
            print("Available serial ports:")
            for p in ports:
                print(f"  {p['device']:8s}  {p['description']}")
            best = auto_detect_port()
            if best:
                print(f"\nBest guess: {best}")
        return

    port = args.port
    baud = args.baud

    if args.auto:
        port = port or auto_detect_port() or ""
        if args.project:
            detected = detect_baud_from_project(args.project)
            if detected:
                baud = detected
                print(f"Auto-detected baud from project: {baud}")
        if not port:
            print("Error: No serial port detected.")
            sys.exit(1)

    if args.project and not args.auto:
        detected = detect_baud_from_project(args.project)
        if detected:
            baud = detected
            print(f"Auto-detected baud from project: {baud}")

    app = SerialTUI(port=port or "", baud=baud)
    app.run()


if __name__ == "__main__":
    main()
