"""Onglet 'Live' : chat-log scrollable + bubble partielle."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)

from benji.ui.widgets.chat_item import ChatItem
from benji.ui.widgets.partial_bubble import PartialBubble

_MAX_CONTENT_WIDTH = 720


class LiveTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._partial_text: str = ""
        self._user_scrolled_up = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.viewport_widget = QWidget()
        outer = QHBoxLayout(self.viewport_widget)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.content = QWidget()
        self.content.setMaximumWidth(_MAX_CONTENT_WIDTH)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addStretch(1)
        outer.addWidget(self.content, 0)
        outer.addStretch(1)

        self.scroll.setWidget(self.viewport_widget)

        self.partial = PartialBubble()
        partial_wrap = QHBoxLayout()
        partial_wrap.setContentsMargins(20, 0, 20, 14)
        partial_wrap.addStretch(1)
        self.partial.setMaximumWidth(_MAX_CONTENT_WIDTH)
        partial_wrap.addWidget(self.partial, 1)
        partial_wrap.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.scroll, 1)
        root.addLayout(partial_wrap)

        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet("LiveTab, QScrollArea { background: transparent; border: none; }")
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport_widget.setStyleSheet("background: transparent;")
        self.content.setStyleSheet("background: transparent;")
        for i in range(self.content_layout.count() - 1):
            w = self.content_layout.itemAt(i).widget()
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()
        self.partial.apply_theme()

    def on_event(self, item) -> None:
        if not isinstance(item, dict):
            return
        msg_type = item.get("type")
        if msg_type == "segment_start":
            self._partial_text = ""
            self.partial.set_text("")
        elif msg_type == "word":
            text = item.get("text", "")
            if not text:
                return
            sep = "" if (not self._partial_text or self._partial_text.endswith(" ") or text.startswith((".", ",", "!", "?", ";", ":"))) else " "
            self._partial_text = (self._partial_text + sep + text).strip()
            self.partial.set_text(self._partial_text)
        elif msg_type == "final_text":
            text = item.get("text", "")
            drop = item.get("drop", False)
            if drop or not text:
                self._partial_text = ""
                self.partial.set_text("")
                return
            self._append_final(text)
            self._partial_text = ""
            self.partial.set_text("")

    def _append_final(self, text: str) -> None:
        item = ChatItem(text)
        self.content_layout.insertWidget(self.content_layout.count() - 1, item)
        if not self._user_scrolled_up:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll(self, value: int) -> None:
        sb = self.scroll.verticalScrollBar()
        self._user_scrolled_up = (sb.maximum() - value) > 20
