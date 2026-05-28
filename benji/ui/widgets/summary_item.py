"""Item de la liste des résumés."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from benji.ui.style import FONT_MONO, FONT_UI, current_theme


class SummaryItem(QWidget):
    def __init__(self, dt: datetime, snippet: str, parent=None):
        super().__init__(parent)
        self._dt = dt
        self._snippet = snippet

        self.date_label = QLabel(self._format_date(dt))
        self.time_label = QLabel(dt.strftime("%H:%M"))
        self.snippet_label = QLabel(snippet)
        self.snippet_label.setTextFormat(Qt.TextFormat.PlainText)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self.date_label, 0)
        top.addWidget(self.time_label, 0)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        layout.addLayout(top)
        layout.addWidget(self.snippet_label)

        self.apply_theme()

    @staticmethod
    def _format_date(dt: datetime) -> str:
        return dt.strftime("%d %b").lstrip("0")

    def apply_theme(self) -> None:
        t = current_theme()
        self.date_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 13px; font-weight: 600; "
            f"color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()}); "
            "background: transparent;"
        )
        self.time_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent;"
        )
        self.snippet_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
