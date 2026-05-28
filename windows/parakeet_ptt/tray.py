"""
Windows system tray app — uses pystray + PIL instead of AppIndicator3/GTK.
pystray runs its own thread; PyQt5 windows are launched from the main thread
via a queue so they don't clash with pystray's Win32 message pump.
"""

import queue
import subprocess
import threading
from pathlib import Path

import pystray
from PIL import Image

from .config import get_venv_dir, load_corrections

_LISTENER_SCRIPT = Path(__file__).parent / "listener.py"
_ICON_PATH       = Path(__file__).parent.parent / "data" / "icons" / "parakeet-ptt.png"
_LOG_FILE        = str(Path(__file__).parent.parent.parent / "listener.log")  # %LOCALAPPDATA%

_ST_LOADING = "○ Loading model…"
_ST_READY   = "● Ready"
_ST_RESTART = "○ Restarting…"
_ST_EXITED  = "⚠ Listener stopped"

# Queue used to push UI actions (open windows) back to the main thread
_ui_queue: queue.Queue = queue.Queue()


class TrayApp:
    def __init__(self):
        load_corrections()  # write defaults to disk if first run
        self._proc        = None
        self._status      = _ST_LOADING
        self._icon        = None

        icon_image = Image.open(_ICON_PATH) if _ICON_PATH.exists() else _default_icon()
        self._icon = pystray.Icon(
            "parakeet-ptt",
            icon_image,
            "Parakeet PTT",
            menu=self._build_menu(),
        )

    def run(self):
        """Start the listener then hand control to pystray (blocking)."""
        self._start_listener()
        self._icon.run(setup=self._on_icon_ready)

    def _on_icon_ready(self, icon):
        """Called by pystray once the tray icon is visible."""
        pass

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda _: self._status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings…",           self._cmd_settings),
            pystray.MenuItem("Stats…",              self._cmd_stats),
            pystray.MenuItem("View Log",            self._cmd_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart Listener",    self._cmd_restart),
            pystray.MenuItem("Re-run Setup Wizard…",self._cmd_wizard),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",                self._cmd_quit),
        )

    # ── Listener management ────────────────────────────────────────────────────

    def _venv_python(self) -> str:
        return str(get_venv_dir() / "Scripts" / "python.exe")

    def _start_listener(self):
        if self._proc and self._proc.poll() is None:
            return
        try:
            from .config import DATA_DIR
            log_fh = open(DATA_DIR / "listener.log", "a")
            self._proc = subprocess.Popen(
                [self._venv_python(), str(_LISTENER_SCRIPT)],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._set_status(_ST_LOADING)
            threading.Thread(target=self._poll_ready, daemon=True).start()
        except FileNotFoundError:
            self._set_status("⚠ Venv not found — run setup")
        except Exception as exc:
            self._set_status(f"⚠ {exc}")

    def _poll_ready(self):
        from .config import DATA_DIR
        log_path = DATA_DIR / "listener.log"
        while self._proc and self._proc.poll() is None:
            try:
                with open(log_path) as f:
                    if any("Ready" in line or "ready" in line for line in f):
                        self._set_status(_ST_READY)
                        return
            except OSError:
                pass
            threading.Event().wait(1)
        self._set_status(_ST_EXITED)

    def _restart_listener(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait()
        self._set_status(_ST_RESTART)
        self._start_listener()

    def _set_status(self, text: str):
        self._status = text
        if self._icon:
            self._icon.update_menu()

    # ── Menu commands (run in pystray's thread → push to main thread for Qt) ──

    def _cmd_settings(self):
        _ui_queue.put(("settings", self._restart_listener))

    def _cmd_stats(self):
        _ui_queue.put(("stats", None))

    def _cmd_wizard(self):
        _ui_queue.put(("wizard", self._restart_listener))

    def _cmd_restart(self):
        threading.Thread(target=self._restart_listener, daemon=True).start()

    def _cmd_log(self):
        from .config import DATA_DIR
        subprocess.Popen(["notepad.exe", str(DATA_DIR / "listener.log")])

    def _cmd_quit(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._icon.stop()


def _default_icon() -> Image.Image:
    """Fallback 22×22 white microphone icon if the PNG file is missing."""
    img = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
    return img
