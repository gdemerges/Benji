"""Item ligne du chat-log Live : timestamp + texte."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from benji.ui.style import current_theme, FONT_UI, FONT_MONO


class ChatItem(QWidget):
    def __init__(self, text: str, ts: datetime | None = None, parent=None):
        super().__init__(parent)
        self._text = text
        self._ts = ts or datetime.now()

        self.ts_label = QLabel(self._ts.strftime("%H:%M"))
        self.ts_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.ts_label.setFixedWidth(52)

        self.text_label = QLabel(self._text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(14)
        layout.addWidget(self.ts_label, 0)
        layout.addWidget(self.text_label, 1)

        self.apply_theme()
        self._fade_in()

    def apply_theme(self) -> None:
        t = current_theme()
        self.ts_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent; padding-top: 2px;"
        )
        self.text_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 15px; line-height: 1.5; "
            f"color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()}); "
            "background: transparent;"
        )

    def _fade_in(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._fade_anim = anim
