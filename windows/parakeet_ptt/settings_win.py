"""
Settings window — PyQt5, three tabs: Dictionary, Key Binding, System.
Mirrors the Linux GTK settings_win.py feature-for-feature.
"""

from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QComboBox, QRadioButton, QButtonGroup, QLineEdit,
    QFileDialog, QMessageBox, QAbstractItemView, QSizePolicy,
    QHeaderView,
)
from PyQt5.QtCore import Qt

from .config import (
    DEFAULT_CORRECTIONS, MODEL_CACHE_DEFAULT, PASTE_METHODS, PTT_KEYS,
    load_config, load_corrections, save_config, save_corrections,
)


class SettingsWindow(QDialog):
    def __init__(self, on_save=None, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._cfg         = load_config()
        self._corrections = load_corrections()

        self.setWindowTitle("Parakeet PTT — Settings")
        self.resize(700, 540)

        root = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._tab_dictionary(),  "Dictionary")
        tabs.addTab(self._tab_keybinding(),  "Key Binding")
        tabs.addTab(self._tab_system(),      "System")
        root.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save && Restart Listener")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    # ── Dictionary tab ─────────────────────────────────────────────────────────

    def _tab_dictionary(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        hint = QLabel(
            "Patterns are Python regexes, matched case-insensitively in order. "
            "Changes apply on the next recording — no restart needed."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Regex Pattern", "Replacement"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setDragDropMode(QAbstractItemView.InternalMove)
        for pattern, replacement in self._corrections:
            self._add_table_row(pattern, replacement)
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Rule")
        add_btn.clicked.connect(self._add_rule)
        del_btn = QPushButton("Remove Selected")
        del_btn.clicked.connect(self._remove_rule)
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_corrections)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        btn_row.addWidget(reset_btn)
        layout.addLayout(btn_row)
        return w

    def _add_table_row(self, pattern="", replacement=""):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(pattern))
        self._table.setItem(row, 1, QTableWidgetItem(replacement))

    def _add_rule(self):
        self._add_table_row(r"\bnew_pattern\b", "replacement")
        row = self._table.rowCount() - 1
        self._table.scrollToItem(self._table.item(row, 0))
        self._table.editItem(self._table.item(row, 0))

    def _remove_rule(self):
        rows = sorted({i.row() for i in self._table.selectedItems()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)

    def _reset_corrections(self):
        if QMessageBox.question(self, "Reset?",
            "Replace all rules with built-in defaults?",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self._table.setRowCount(0)
            for pattern, replacement in DEFAULT_CORRECTIONS:
                self._add_table_row(pattern, replacement)

    # ── Key binding tab ────────────────────────────────────────────────────────

    def _tab_keybinding(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignTop)

        layout.addWidget(self._bold_label("Push-to-Talk Key"))
        hint = QLabel("Must be a non-character key (function key, Scroll Lock, Pause, etc.) "
                      "so it doesn't also type into the focused window.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        self._key_combo = QComboBox()
        for key in PTT_KEYS:
            self._key_combo.addItem(key.upper(), key)
        current = self._cfg.get("ptt_key", "f9")
        idx = PTT_KEYS.index(current) if current in PTT_KEYS else 8  # default F9
        self._key_combo.setCurrentIndex(idx)
        self._key_combo.currentIndexChanged.connect(
            lambda i: self._cfg.update({"ptt_key": PTT_KEYS[i]})
        )
        layout.addWidget(self._key_combo)
        return w

    # ── System tab ─────────────────────────────────────────────────────────────

    def _tab_system(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignTop)

        # Paste method
        layout.addWidget(self._bold_label("Paste Shortcut"))
        self._paste_group = QButtonGroup(self)
        for i, (val, label) in enumerate(PASTE_METHODS):
            rb = QRadioButton(label)
            if val == self._cfg.get("paste_method", "ctrl+v"):
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, v=val: self._cfg.update({"paste_method": v}) if checked else None)
            self._paste_group.addButton(rb)
            layout.addWidget(rb)

        layout.addSpacing(12)

        # Model cache path
        layout.addWidget(self._bold_label("Model Cache Directory"))
        hint = QLabel("Where the Whisper model weights are stored. "
                      "Point to an existing download to avoid re-downloading.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        path_row = QHBoxLayout()
        self._model_path_edit = QLineEdit(self._cfg.get("model_cache", str(MODEL_CACHE_DEFAULT)))
        self._model_path_edit.textChanged.connect(lambda t: self._cfg.update({"model_cache": t}))
        path_row.addWidget(self._model_path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._pick_model_dir)
        path_row.addWidget(browse_btn)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(lambda: self._model_path_edit.setText(str(MODEL_CACHE_DEFAULT)))
        path_row.addWidget(reset_btn)
        layout.addLayout(path_row)
        return w

    def _pick_model_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Choose Model Cache Directory",
                                                self._model_path_edit.text())
        if path:
            self._model_path_edit.setText(path)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _bold_label(self, text: str) -> QLabel:
        lbl = QLabel(f"<b>{text}</b>")
        lbl.setTextFormat(Qt.RichText)
        return lbl

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save(self):
        corrections = []
        for row in range(self._table.rowCount()):
            p = self._table.item(row, 0)
            r = self._table.item(row, 1)
            if p and r:
                corrections.append([p.text(), r.text()])
        save_config(self._cfg)
        save_corrections(corrections)
        self.accept()
        if self._on_save:
            self._on_save()
