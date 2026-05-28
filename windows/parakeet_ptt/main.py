"""
Entry point for Parakeet PTT on Windows.

Single-instance guard → wizard on first run → pystray tray app.
PyQt5 windows (settings, stats, wizard) are driven from this main thread
via a queue; pystray runs in its own thread.
"""

import atexit
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parakeet_ptt.config import model_ready, venv_ready
from parakeet_ptt.tray import _ui_queue

_PID_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) \
            / "parakeet-ptt" / "app.pid"


def _already_running() -> bool:
    if not _PID_FILE.exists():
        return False
    try:
        pid = int(_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        _PID_FILE.unlink(missing_ok=True)
        return False


def _write_pid():
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: _PID_FILE.unlink(missing_ok=True))


def main():
    if _already_running():
        print("Parakeet PTT is already running.", file=sys.stderr)
        sys.exit(0)

    _write_pid()

    # PyQt5 app must be created on the main thread before any widgets
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running even when all windows close

    force_setup = "--setup" in sys.argv
    if force_setup or not venv_ready() or not model_ready():
        _run_wizard(app)
    else:
        _run_tray()

    # Main thread event loop — services UI requests from the pystray thread
    _main_loop(app)


_tray = None


def _run_wizard(app):
    from parakeet_ptt.wizard import SetupWizard
    wizard = SetupWizard(on_complete=_run_tray)
    wizard.show()


def _run_tray():
    global _tray
    import threading
    from parakeet_ptt.tray import TrayApp
    _tray = TrayApp()
    threading.Thread(target=_tray.run, daemon=True).start()


def _main_loop(app):
    """
    Process UI requests pushed by the pystray thread, then drive Qt's event loop.
    Uses a QTimer to drain the queue without blocking Qt.
    """
    from PyQt5.QtCore import QTimer

    def _drain():
        while not _ui_queue.empty():
            kind, callback = _ui_queue.get_nowait()
            if kind == "settings":
                from parakeet_ptt.settings_win import SettingsWindow
                w = SettingsWindow(on_save=callback)
                w.exec_()
            elif kind == "stats":
                from parakeet_ptt.stats_win import StatsWindow
                w = StatsWindow()
                w.exec_()
            elif kind == "wizard":
                from parakeet_ptt.wizard import SetupWizard
                w = SetupWizard(on_complete=callback)
                w.exec_()

    timer = QTimer()
    timer.timeout.connect(_drain)
    timer.start(100)  # check queue every 100 ms

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
