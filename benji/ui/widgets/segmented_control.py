"""Segmented control style macOS — 2+ segments mutually exclusive."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from benji.ui.style import current_theme, FONT_UI


class SegmentedControl(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._base_labels: list[str] = list(labels)
        self._badges: dict[int, bool] = {}
        self._current = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)

        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, idx=i: self.setCurrentIndex(idx))
            layout.addWidget(btn, 1)
            self._buttons.append(btn)

        self.setCurrentIndex(0)
        self.apply_theme()

    def setCurrentIndex(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._buttons):
            return
        for i, b in enumerate(self._buttons):
            b.setChecked(i == idx)
        if idx != self._current:
            self._current = idx
            self.currentChanged.emit(idx)
        self._refresh_labels()

    def currentIndex(self) -> int:
        return self._current

    def setBadge(self, idx: int, has_badge: bool) -> None:
        self._badges[idx] = has_badge
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        for i, b in enumerate(self._buttons):
            base = self._base_labels[i]
            b.setText(f"{base}  •" if self._badges.get(i) else base)

    def apply_theme(self) -> None:
        t = current_theme()
        track = t.label_alpha(7)
        active = t.label_alpha(14)
        label = t.label
        secondary = t.secondary_label
        self.setStyleSheet(f"""
            SegmentedControl {{
                background-color: rgba({track.red()},{track.green()},{track.blue()},{track.alpha()});
                border-radius: 8px;
            }}
            QPushButton {{
                font-family: {FONT_UI};
                font-size: 12px;
                font-weight: 500;
                color: rgba({secondary.red()},{secondary.green()},{secondary.blue()},{secondary.alpha()});
                background: transparent;
                border: none;
                padding: 4px 14px;
                border-radius: 6px;
            }}
            QPushButton:checked {{
                background-color: rgba({active.red()},{active.green()},{active.blue()},{active.alpha()});
                color: rgba({label.red()},{label.green()},{label.blue()},{label.alpha()});
            }}
            QPushButton:hover:!checked {{
                color: rgba({label.red()},{label.green()},{label.blue()},{label.alpha()});
            }}
        """)
        self.setFixedHeight(30)
