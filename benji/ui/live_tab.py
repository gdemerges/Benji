"""Onglet 'Live' : chat-log scrollable des finals + partiel en italique."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget


class LiveTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._partial_text: str = ""
        self._user_scrolled_up = False
        self._build_ui()
        self.log.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _build_ui(self) -> None:
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("QTextEdit { font-size: 14px; }")

        self.partial = QLabel("")
        self.partial.setWordWrap(True)
        self.partial.setStyleSheet("color: gray; font-style: italic; padding: 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.log, 1)
        layout.addWidget(self.partial)

    def on_event(self, item) -> None:
        """Slot abonné au DisplayBus. Met à jour le chat-log et le partiel."""
        if not isinstance(item, dict):
            return
        msg_type = item.get("type")
        if msg_type == "segment_start":
            self._partial_text = ""
            self.partial.setText("")
        elif msg_type == "word":
            text = item.get("text", "")
            if not text:
                return
            sep = "" if (not self._partial_text or self._partial_text.endswith(" ") or text.startswith((".", ",", "!", "?", ";", ":"))) else " "
            self._partial_text = (self._partial_text + sep + text).strip()
            self.partial.setText(self._partial_text)
        elif msg_type == "final_text":
            text = item.get("text", "")
            drop = item.get("drop", False)
            if drop or not text:
                self._partial_text = ""
                self.partial.setText("")
                return
            self._append_final(text)
            self._partial_text = ""
            self.partial.setText("")

    def _append_final(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        html = f'<div style="margin-bottom:6px"><span style="color:#888">{ts}</span>&nbsp;&nbsp;{self._escape(text)}</div>'
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        if not self._user_scrolled_up:
            self._scroll_to_bottom()

    @staticmethod
    def _escape(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def _scroll_to_bottom(self) -> None:
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll(self, value: int) -> None:
        sb = self.log.verticalScrollBar()
        # Si on est à moins de 20 px du bas, on considère "collé en bas"
        self._user_scrolled_up = (sb.maximum() - value) > 20
