"""
Settings window — three tabs:
  Dictionary  — editable corrections table (regex → replacement)
  Key Binding — PTT key picker
  System      — paste shortcut and clipboard tool
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .config import (
    CLIPBOARD_TOOLS, DEFAULT_CORRECTIONS, MODEL_CACHE_DEFAULT, PASTE_METHODS, PTT_KEYS,
    load_config, load_corrections, save_config, save_corrections,
)


class SettingsWindow(Gtk.Window):
    def __init__(self, on_save=None):
        super().__init__(title="Parakeet PTT — Settings")
        self._on_save = on_save
        self.set_default_size(680, 520)
        self.set_border_width(12)
        self.set_resizable(True)

        self._cfg         = load_config()
        self._corrections = load_corrections()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(root)

        nb = Gtk.Notebook()
        root.pack_start(nb, True, True, 0)

        nb.append_page(self._tab_dictionary(), Gtk.Label(label="Dictionary"))
        nb.append_page(self._tab_keybinding(), Gtk.Label(label="Key Binding"))
        nb.append_page(self._tab_system(),     Gtk.Label(label="System"))

        # Buttons
        btn_row = Gtk.Box(spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        btn_row.set_margin_top(4)

        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _: self.destroy())
        btn_row.pack_start(cancel, False, False, 0)

        save = Gtk.Button(label="Save & Restart Listener")
        save.get_style_context().add_class("suggested-action")
        save.connect("clicked", self._save)
        btn_row.pack_start(save, False, False, 0)

        root.pack_end(btn_row, False, False, 0)

    # ── Dictionary tab ─────────────────────────────────────────────────────────

    def _tab_dictionary(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        hint = Gtk.Label(label="Patterns are Python regexes, matched case-insensitively in order. "
                               "Changes apply on the next recording — no restart needed.")
        hint.set_line_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        self._store = Gtk.ListStore(str, str)
        for row in self._corrections:
            self._store.append(row[:2])

        self._tv = Gtk.TreeView(model=self._store)
        self._tv.set_reorderable(True)
        self._tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

        for col_idx, title in enumerate(["Regex Pattern", "Replacement"]):
            renderer = Gtk.CellRendererText()
            renderer.set_property("editable", True)
            renderer.set_property("ellipsize", 3)  # PANGO_ELLIPSIZE_END
            renderer.connect("edited", self._cell_edited, col_idx)
            col = Gtk.TreeViewColumn(title, renderer, text=col_idx)
            col.set_expand(True)
            col.set_resizable(True)
            self._tv.append_column(col)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self._tv)
        box.pack_start(sw, True, True, 0)

        btn_row = Gtk.Box(spacing=6)
        add_btn = Gtk.Button(label="Add Rule")
        add_btn.connect("clicked", self._add_rule)
        del_btn = Gtk.Button(label="Remove Selected")
        del_btn.connect("clicked", self._remove_rule)
        reset_btn = Gtk.Button(label="Reset to Defaults")
        reset_btn.connect("clicked", self._reset_corrections)
        btn_row.pack_start(add_btn,   False, False, 0)
        btn_row.pack_start(del_btn,   False, False, 0)
        btn_row.pack_end(reset_btn,   False, False, 0)
        box.pack_end(btn_row, False, False, 0)

        return box

    def _cell_edited(self, _renderer, path, new_text, col):
        self._store[path][col] = new_text

    def _add_rule(self, _):
        it = self._store.append([r"\bnew_pattern\b", "replacement"])
        path = self._store.get_path(it)
        self._tv.set_cursor(path, self._tv.get_column(0), start_editing=True)

    def _remove_rule(self, _):
        _model, it = self._tv.get_selection().get_selected()
        if it:
            self._store.remove(it)

    def _reset_corrections(self, _):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Reset to defaults?",
        )
        dialog.format_secondary_text("All current rules will be replaced with the built-in defaults.")
        if dialog.run() == Gtk.ResponseType.YES:
            self._store.clear()
            for row in DEFAULT_CORRECTIONS:
                self._store.append(list(row[:2]))
        dialog.destroy()

    # ── Key binding tab ────────────────────────────────────────────────────────

    def _tab_keybinding(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(16)

        title = Gtk.Label()
        title.set_markup("<b>Push-to-Talk Key</b>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        hint = Gtk.Label(label="Must be a non-character key (function key, Scroll Lock, Pause, etc.) "
                               "so it doesn't also type into the focused window.")
        hint.set_line_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        combo = Gtk.ComboBoxText()
        for key in PTT_KEYS:
            combo.append(key, key.upper())
        current = self._cfg.get("ptt_key", "f9")
        combo.set_active_id(current if current in PTT_KEYS else "f9")
        combo.connect("changed", lambda w: self._cfg.update({"ptt_key": w.get_active_id()}))
        box.pack_start(combo, False, False, 0)

        return box

    # ── System tab ─────────────────────────────────────────────────────────────

    def _tab_system(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(16)

        box.pack_start(self._radio_group(
            "<b>Paste Shortcut</b>",
            PASTE_METHODS,
            self._cfg.get("paste_method", "ctrl+shift+v"),
            "paste_method",
        ), False, False, 0)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        box.pack_start(self._radio_group(
            "<b>Clipboard Tool</b>",
            CLIPBOARD_TOOLS,
            self._cfg.get("clipboard_tool", "xclip"),
            "clipboard_tool",
        ), False, False, 0)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 4)

        box.pack_start(self._model_path_row(), False, False, 0)

        return box

    def _model_path_row(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        title = Gtk.Label()
        title.set_markup("<b>Model Cache Directory</b>")
        title.set_halign(Gtk.Align.START)
        vbox.pack_start(title, False, False, 0)

        hint = Gtk.Label(
            label="Where the Parakeet TDT model weights are stored. "
                  "Point this to an existing download to avoid re-downloading."
        )
        hint.set_line_wrap(True)
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dim-label")
        vbox.pack_start(hint, False, False, 0)

        row = Gtk.Box(spacing=8)
        current_path = self._cfg.get("model_cache", str(MODEL_CACHE_DEFAULT))
        self._model_path_lbl = Gtk.Label(label=current_path)
        self._model_path_lbl.set_halign(Gtk.Align.START)
        self._model_path_lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self._model_path_lbl.set_xalign(0)
        row.pack_start(self._model_path_lbl, True, True, 0)

        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.connect("clicked", self._pick_model_dir)
        row.pack_start(browse_btn, False, False, 0)

        reset_btn = Gtk.Button(label="Reset")
        reset_btn.connect("clicked", self._reset_model_dir)
        row.pack_start(reset_btn, False, False, 0)

        vbox.pack_start(row, False, False, 0)
        return vbox

    def _pick_model_dir(self, _):
        dialog = Gtk.FileChooserDialog(
            title="Choose Model Cache Directory",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            "Select", Gtk.ResponseType.OK,
        )
        current = self._cfg.get("model_cache", str(MODEL_CACHE_DEFAULT))
        dialog.set_filename(current)

        if dialog.run() == Gtk.ResponseType.OK:
            chosen = dialog.get_filename()
            self._cfg["model_cache"] = chosen
            self._model_path_lbl.set_text(chosen)
        dialog.destroy()

    def _reset_model_dir(self, _):
        default = str(MODEL_CACHE_DEFAULT)
        self._cfg["model_cache"] = default
        self._model_path_lbl.set_text(default)

    def _radio_group(self, markup: str, options: list, current: str, cfg_key: str) -> Gtk.Box:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        lbl = Gtk.Label()
        lbl.set_markup(markup)
        lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(lbl, False, False, 0)
        group = []
        for val, text in options:
            rb = Gtk.RadioButton.new_with_label_from_widget(
                group[0] if group else None, text
            )
            if val == current:
                rb.set_active(True)
            rb.connect(
                "toggled",
                lambda w, v=val, k=cfg_key: self._cfg.update({k: v}) if w.get_active() else None,
            )
            vbox.pack_start(rb, False, False, 0)
            group.append(rb)
        return vbox

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save(self, _):
        self._corrections = [[row[0], row[1]] for row in self._store]
        save_config(self._cfg)
        save_corrections(self._corrections)
        self.destroy()
        if self._on_save:
            self._on_save()
