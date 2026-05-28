#!/usr/bin/env python3
"""
Entry point for the Parakeet PTT GUI.

On first run (venv or model missing) → shows the setup wizard.
Otherwise → launches the system tray app which starts the listener.
"""

import atexit
import os
import sys
from pathlib import Path

# When run directly (not installed) ensure the package root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from parakeet_ptt.config import model_ready, venv_ready

_APP_PID_FILE = Path("/tmp/parakeet-ptt-app.pid")


def _already_running() -> bool:
    """Return True if another instance is already running."""
    if not _APP_PID_FILE.exists():
        return False
    try:
        pid = int(_APP_PID_FILE.read_text().strip())
        # Signal 0 checks existence without sending a signal
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # Stale PID file — process is gone
        _APP_PID_FILE.unlink(missing_ok=True)
        return False


def _write_pid():
    _APP_PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: _APP_PID_FILE.unlink(missing_ok=True))


def main():
    if _already_running():
        print("Parakeet PTT is already running.", file=sys.stderr)
        sys.exit(0)

    _write_pid()

    force_setup = "--setup" in sys.argv
    if force_setup or not venv_ready() or not model_ready():
        _run_wizard()
    else:
        _run_tray()

    Gtk.main()


_tray = None  # module-level ref keeps TrayApp alive for the GTK main loop


def _run_wizard():
    from parakeet_ptt.wizard import SetupWizard

    wizard = SetupWizard(on_complete=_run_tray)
    wizard.show_all()


def _run_tray():
    global _tray
    from parakeet_ptt.tray import TrayApp
    _tray = TrayApp()


if __name__ == "__main__":
    main()
