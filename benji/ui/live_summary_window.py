"""Rolling summary window updated by LiveSummarizer.

Supports both whole-summary appends and token-by-token streaming.
"""

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from benji.ui.style import (
    FONT_MONO,
    current_theme,
    install_theme_listener,
    panel_background_qss,
    text_panel_qss,
)


class LiveSummaryWindow(QWidget):
    _summary_signal = pyqtSignal(str, object)  # (text, datetime)
    _start_signal = pyqtSignal(object)         # datetime
    _chunk_signal = pyqtSignal(str)            # streamed token chunk

    def __init__(self):
        super().__init__()
        self.setObjectName("LiveSummaryWindow")
        self.setWindowTitle("Résumé en direct")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(520, 420)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont(FONT_MONO, 12))
        self.text_edit.setPlainText("En attente du premier résumé…")
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

        self._streaming = False

        self._summary_signal.connect(self._finalize_summary)
        self._start_signal.connect(self._begin_summary)
        self._chunk_signal.connect(self._append_chunk)

        install_theme_listener(self._apply_theme)
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = current_theme()
        self.setStyleSheet(
            panel_background_qss(t, "#LiveSummaryWindow") + text_panel_qss(t)
        )

    # --- Thread-safe entry points ---------------------------------------
    def on_summary(self, text: str, at: datetime):
        self._summary_signal.emit(text, at)

    def on_summary_start(self, at: datetime):
        self._start_signal.emit(at)

    def on_summary_chunk(self, chunk: str):
        self._chunk_signal.emit(chunk)

    # --- Slots ----------------------------------------------------------
    def _begin_summary(self, at: datetime):
        if self.text_edit.toPlainText() == "En attente du premier résumé…":
            self.text_edit.clear()
        self.text_edit.append(f"── {at.strftime('%H:%M')} ──")
        self._streaming = True
        self._scroll_to_end()

    def _append_chunk(self, chunk: str):
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()

    def _finalize_summary(self, text: str, at: datetime):
        # If we never streamed, render the full block now (legacy path).
        if not self._streaming:
            if self.text_edit.toPlainText() == "En attente du premier résumé…":
                self.text_edit.clear()
            self.text_edit.append(f"── {at.strftime('%H:%M')} ──")
            self.text_edit.append(text)
        self.text_edit.append("")
        self._streaming = False
        self._scroll_to_end()

    def _scroll_to_end(self):
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
