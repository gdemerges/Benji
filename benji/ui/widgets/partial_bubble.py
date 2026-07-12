"""Ligne du texte en cours de transcription : forme d'onde + texte streamé.

Plus de carte : la phrase en train de s'écrire est la dernière ligne du
document, précédée de la forme d'onde signature qui danse pendant que Benji
écoute. Un fin filet au-dessus la sépare du transcript figé. Le curseur ▏ est
fusionné au texte (rich text) pour suivre le dernier mot — statique : la forme
d'onde suffit à dire « en cours ».
"""

from __future__ import annotations

from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from benji.ui.style import FONT_UI, current_theme
from benji.ui.widgets.waveform import WaveformDot


class PartialBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text: str = ""

        self.rule = QFrame()
        self.rule.setFrameShape(QFrame.Shape.HLine)
        self.rule.setFixedHeight(1)

        self.wave = WaveformDot(bar_width=2, gap=2, height=14)
        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(Qt.TextFormat.RichText)

        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.wave, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.text_label, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.rule)
        layout.addLayout(row)

        self.apply_theme()
        self.setVisible(False)

    def set_text(self, text: str) -> None:
        self._text = text
        self._render()
        visible = bool(text)
        self.setVisible(visible)
        self.wave.set_active(visible)

    def _render(self) -> None:
        if not self._text:
            self.text_label.setText("")
            return
        t = current_theme()
        accent = f"rgba({t.accent.red()},{t.accent.green()},{t.accent.blue()},255)"
        # Curseur accent collé au dernier mot ; texte échappé (peut contenir <, &).
        self.text_label.setText(
            f'{escape(self._text)}<span style="color:{accent};"> ▏</span>'
        )

    def apply_theme(self) -> None:
        t = current_theme()
        sep = t.separator
        self.rule.setStyleSheet(
            f"background-color: rgba({sep.red()},{sep.green()},{sep.blue()},{sep.alpha()}); border: none;"
        )
        self.wave.set_color(t.accent)
        self.text_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 15px; line-height: 1.6; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
        self._render()
