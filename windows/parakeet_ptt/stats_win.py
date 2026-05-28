"""Stats window — PyQt5."""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QHBoxLayout, QPushButton

from .stats import load_events, report


class StatsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parakeet PTT — Stats")
        self.resize(500, 540)

        layout = QVBoxLayout(self)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(self._monospace_font())
        layout.addWidget(self._text)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        btn_row.addWidget(refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        btn_row.addWidget(close)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        events = load_events()
        self._text.setPlainText(report(events) if events else "No telemetry recorded yet.")

    @staticmethod
    def _monospace_font():
        from PyQt5.QtGui import QFont
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        return f
