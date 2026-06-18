"""Item ligne du chat-log Live : timestamp + texte."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QPropertyAnimation, Qt
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from benji.ui.style import FONT_MONO, FONT_UI, Theme, current_theme, speaker_color


class ChatItem(QWidget):
    def __init__(self, text: str, ts: datetime | None = None, speaker: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._text = text
        self._ts = ts or datetime.now()
        self._speaker = speaker

        self.ts_label = QLabel(self._ts.strftime("%H:%M"))
        self.ts_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.ts_label.setFixedWidth(52)

        # Colored speaker badge ("● A"), only when diarization tagged this line.
        self.speaker_label: QLabel | None = None
        if speaker:
            self.speaker_label = QLabel(f"● {speaker}")
            self.speaker_label.setAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            self.speaker_label.setFixedWidth(34)

        self.text_label = QLabel(self._text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(14)
        layout.addWidget(self.ts_label, 0)
        if self.speaker_label is not None:
            layout.setSpacing(8)
            layout.addWidget(self.speaker_label, 0)
        layout.addWidget(self.text_label, 1)

        self.apply_theme()
        self._fade_in()

    def apply_theme(self) -> None:
        t = current_theme()
        # Accent = speaker color when diarized, otherwise the system accent so
        # untagged lines still read as a coherent card.
        accent = speaker_color(self._speaker) if self._speaker else t.accent
        tint = Theme.color_alpha(accent, 16 if t.is_dark else 10)
        rail = Theme.color_alpha(accent, 90 if t.is_dark else 75)

        self.ts_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent; padding-top: 11px;"
        )
        if self.speaker_label is not None:
            self.speaker_label.setStyleSheet(
                f"font-family: {FONT_UI}; font-size: 13px; font-weight: 600; "
                f"color: {accent.name()}; background: transparent; padding-top: 10px;"
            )
        self.text_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 15px; line-height: 1.5; "
            f"color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()}); "
            f"background-color: rgba({tint.red()},{tint.green()},{tint.blue()},{tint.alpha()}); "
            f"border-left: 3px solid rgba({rail.red()},{rail.green()},{rail.blue()},{rail.alpha()}); "
            "border-top-left-radius: 4px; border-bottom-left-radius: 4px; "
            "border-top-right-radius: 10px; border-bottom-right-radius: 10px; "
            "padding: 9px 14px;"
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
