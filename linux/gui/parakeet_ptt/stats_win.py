"""
Stats window — displays the usage report in a scrollable monospace text view.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .stats import load_events, report


class StatsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Parakeet PTT — Stats")
        self.set_default_size(500, 540)
        self.set_border_width(12)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(vbox)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tv = Gtk.TextView()
        tv.set_editable(False)
        tv.set_cursor_visible(False)
        tv.set_monospace(True)
        tv.set_left_margin(8)
        tv.set_top_margin(8)
        sw.add(tv)
        vbox.pack_start(sw, True, True, 0)

        events = load_events()
        if events:
            text = report(events)
        else:
            text = "No telemetry recorded yet.\n\nMake a few recordings first."
        tv.get_buffer().set_text(text)

        btn_row = Gtk.Box(spacing=8)
        btn_row.set_halign(Gtk.Align.END)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda _: self._refresh(tv))
        btn_row.pack_start(refresh_btn, False, False, 0)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _: self.destroy())
        btn_row.pack_start(close_btn, False, False, 0)

        vbox.pack_end(btn_row, False, False, 0)

    def _refresh(self, tv: Gtk.TextView):
        events = load_events()
        text = report(events) if events else "No telemetry yet."
        tv.get_buffer().set_text(text)
