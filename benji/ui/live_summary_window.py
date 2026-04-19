"""Rolling summary window updated every N minutes by LiveSummarizer."""

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget


class LiveSummaryWindow(QWidget):
    _summary_signal = pyqtSignal(str, object)  # (text, datetime)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Résumé en direct")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(500, 400)

        layout = QVBoxLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("monospace", 10))
        self.text_edit.setPlainText("En attente du premier résumé…")
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        self._summary_signal.connect(self._append_summary)

    def on_summary(self, text: str, at: datetime):
        """Thread-safe entry point for LiveSummarizer."""
        self._summary_signal.emit(text, at)

    def _append_summary(self, text: str, at: datetime):
        if self.text_edit.toPlainText() == "En attente du premier résumé…":
            self.text_edit.clear()
        self.text_edit.append(f"── {at.strftime('%H:%M')} ──")
        self.text_edit.append(text)
        self.text_edit.append("")
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
