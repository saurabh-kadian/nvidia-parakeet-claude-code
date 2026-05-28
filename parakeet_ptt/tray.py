"""
System tray application.
Uses AppIndicator3 for the GNOME top-bar icon and manages the listener subprocess.
"""

import gi
import subprocess

gi.require_version("AppIndicator3", "0.1")
gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import AppIndicator3, GLib, Gtk, Notify

from pathlib import Path
from .config import get_venv_dir

_LISTENER_SCRIPT = Path(__file__).parent / "listener.py"
_ICON_DIR        = Path(__file__).parent.parent / "data" / "icons"
_LOG_FILE        = "/tmp/parakeet_listener.log"
_APP_ID          = "parakeet-ptt"

# Status labels shown in the tray menu
_ST_LOADING = "○ Loading model…"
_ST_READY   = "● Ready"
_ST_RESTART = "○ Restarting…"
_ST_EXITED  = "⚠ Listener stopped — check log"
_ST_FAILED  = "⚠ Failed to start"


class TrayApp:
    def __init__(self):
        Notify.init("Parakeet PTT")
        self._proc        = None
        self._ready_timer = None

        self._indicator = AppIndicator3.Indicator.new(
            _APP_ID,
            _APP_ID,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        # Point AppIndicator at our bundled icons directory
        self._indicator.set_icon_theme_path(str(_ICON_DIR))
        self._indicator.set_icon_full(_APP_ID, "Parakeet PTT")
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_menu(self._build_menu())

        self._start_listener()

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _build_menu(self) -> Gtk.Menu:
        menu = Gtk.Menu()

        self._status_item = Gtk.MenuItem(label=_ST_LOADING)
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        menu.append(Gtk.SeparatorMenuItem())

        settings_item = Gtk.MenuItem(label="Settings…")
        settings_item.connect("activate", self._open_settings)
        menu.append(settings_item)

        stats_item = Gtk.MenuItem(label="Stats…")
        stats_item.connect("activate", self._open_stats)
        menu.append(stats_item)

        log_item = Gtk.MenuItem(label="View Log")
        log_item.connect("activate", self._open_log)
        menu.append(log_item)

        menu.append(Gtk.SeparatorMenuItem())

        restart_item = Gtk.MenuItem(label="Restart Listener")
        restart_item.connect("activate", lambda _: self._restart_listener())
        menu.append(restart_item)

        setup_item = Gtk.MenuItem(label="Re-run Setup Wizard…")
        setup_item.connect("activate", self._open_setup_wizard)
        menu.append(setup_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    # ── Listener management ────────────────────────────────────────────────────

    def _venv_python(self) -> str:
        return str(get_venv_dir() / "bin" / "python")

    def _start_listener(self):
        if self._proc and self._proc.poll() is None:
            return
        try:
            log_fh = open(_LOG_FILE, "a")
            self._proc = subprocess.Popen(
                [self._venv_python(), str(_LISTENER_SCRIPT)],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
            self._set_status(_ST_LOADING)
            # Poll the log to detect when the model is ready
            self._ready_timer = GLib.timeout_add(1000, self._poll_ready)
        except FileNotFoundError:
            self._set_status(_ST_FAILED + " — venv not found, run setup")
        except Exception as exc:
            self._set_status(f"⚠ {exc}")

    def _poll_ready(self) -> bool:
        """Check log for the 'Ready' line; update status label once seen."""
        if self._proc and self._proc.poll() is not None:
            self._set_status(_ST_EXITED)
            return False
        try:
            with open(_LOG_FILE) as f:
                for line in f:
                    if "Ready" in line or "ready" in line:
                        self._set_status(_ST_READY)
                        return False  # stop polling
        except OSError:
            pass
        return True  # keep polling

    def _restart_listener(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait()
        self._set_status(_ST_RESTART)
        self._start_listener()

    def _set_status(self, text: str):
        GLib.idle_add(self._status_item.set_label, text)

    # ── Menu actions ───────────────────────────────────────────────────────────

    def _open_settings(self, _):
        from .settings_win import SettingsWindow
        win = SettingsWindow(on_save=self._restart_listener)
        win.show_all()

    def _open_stats(self, _):
        from .stats_win import StatsWindow
        win = StatsWindow()
        win.show_all()

    def _open_setup_wizard(self, _):
        from .wizard import SetupWizard
        wizard = SetupWizard(on_complete=self._restart_listener)
        wizard.show_all()

    def _open_log(self, _):
        try:
            subprocess.Popen(["xterm", "-e", f"tail -f {_LOG_FILE}"])
        except FileNotFoundError:
            subprocess.Popen(["gnome-terminal", "--", "tail", "-f", _LOG_FILE])

    def _quit(self, _):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        Notify.uninit()
        Gtk.main_quit()
