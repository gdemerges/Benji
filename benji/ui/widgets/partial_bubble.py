"""Carte flottante du texte partiel avec curseur clignotant."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from benji.ui.style import FONT_UI, current_theme


class PartialBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text: str = ""
        self._cursor_on = True

        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.cursor_label = QLabel("▌")
        self.cursor_label.setFixedWidth(8)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.cursor_label, 0, Qt.AlignmentFlag.AlignBottom)

        self._blink = QTimer(self)
        self._blink.setInterval(600)
        self._blink.timeout.connect(self._toggle_cursor)
        self._blink.start()

        self.apply_theme()
        self.setVisible(False)

    def set_text(self, text: str) -> None:
        self._text = text
        self.text_label.setText(text)
        self.setVisible(bool(text))

    def apply_theme(self) -> None:
        t = current_theme()
        bg = t.accent_alpha(16 if t.is_dark else 10)
        rail = t.accent_alpha(90 if t.is_dark else 75)
        self.setStyleSheet(f"""
            PartialBubble {{
                background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});
                border-left: 3px solid rgba({rail.red()},{rail.green()},{rail.blue()},{rail.alpha()});
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
        """)
        self.text_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 14px; font-style: italic; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
        self.cursor_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 14px; "
            f"color: rgba({t.accent.red()},{t.accent.green()},{t.accent.blue()},{t.accent.alpha()}); "
            "background: transparent;"
        )

    def _toggle_cursor(self) -> None:
        self._cursor_on = not self._cursor_on
        self.cursor_label.setVisible(self._cursor_on)
