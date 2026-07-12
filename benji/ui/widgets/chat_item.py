"""Ligne du transcript Live — style document, regroupée par locuteur.

Pas de carte ni de fond : le transcript se lit comme un texte typographié.
La couleur ne code qu'une information : qui parle. L'en-tête (● Nom) n'apparaît
qu'au premier tour de parole d'un groupe (`show_header`), le timestamp en
gouttière seulement quand il change (`show_ts`).
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QPropertyAnimation, Qt
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from benji.ui.style import FONT_MONO, FONT_UI, current_theme, speaker_color

_GUTTER_WIDTH = 56


class ChatItem(QWidget):
    def __init__(self, text: str, ts: datetime | None = None, speaker: str | None = None,
                 show_header: bool = True, show_ts: bool = True, seq: int | None = None,
                 parent=None):
        super().__init__(parent)
        self._text = text
        self._ts = ts or datetime.now()
        self._speaker = speaker
        self._show_header = show_header
        self.seq = seq  # permet à LiveTab de remplacer le texte corrigé

        # Gouttière : timestamp mono discret, vide si la minute n'a pas changé.
        self.ts_label = QLabel(self._ts.strftime("%H:%M") if show_ts else "")
        self.ts_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.ts_label.setFixedWidth(_GUTTER_WIDTH)

        # En-tête de groupe : nom du locuteur dans sa couleur, une seule fois.
        self.speaker_label: QLabel | None = None
        if speaker and show_header:
            self.speaker_label = QLabel(f"● {speaker}")
            self.speaker_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.text_label = QLabel(self._text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(3)
        if self.speaker_label is not None:
            content.addWidget(self.speaker_label)
        content.addWidget(self.text_label)

        layout = QHBoxLayout(self)
        # Nouveau groupe : respiration au-dessus ; suite de groupe : compact.
        top = 14 if show_header else 2
        layout.setContentsMargins(0, top, 0, 2)
        layout.setSpacing(16)
        layout.addWidget(self.ts_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(content, 1)

        self.apply_theme()
        self._fade_in()

    def set_text(self, text: str) -> None:
        """Remplace le texte affiché (correction LLM asynchrone)."""
        self._text = text
        self.text_label.setText(text)

    def apply_theme(self) -> None:
        t = current_theme()
        self.ts_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            f"background: transparent; padding-top: {4 if self.speaker_label is not None else 3}px;"
        )
        if self.speaker_label is not None:
            accent = speaker_color(self._speaker)
            self.speaker_label.setStyleSheet(
                f"font-family: {FONT_UI}; font-size: 12px; font-weight: 600; "
                f"letter-spacing: 0.2px; color: {accent.name()}; background: transparent;"
            )
        self.text_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 15px; line-height: 1.6; "
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
