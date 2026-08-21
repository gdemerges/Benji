"""Onglets soulignés — 2+ segments mutuellement exclusifs.

Pas une pilule segmentée : sur une app dont tout le propos est un document, un
onglet souligné est le geste juste (on change de vue sur la même matière), et la
pilule grise de macOS est exactement ce qui faisait ressembler Benji à un
panneau de Réglages Système. L'indicateur est un trait d'encre de 2 px sous
l'onglet actif — la même encre que le texte, aucune couleur dépensée ici.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from benji.ui.style import FONT_UI, current_theme


class SegmentedControl(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._base_labels: list[str] = list(labels)
        self._badges: dict[int, bool] = {}
        self._current = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, idx=i: self.setCurrentIndex(idx))
            layout.addWidget(btn, 0)
            self._buttons.append(btn)
        layout.addStretch(1)

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
        ink = t.ink
        muted = t.ink_muted
        self.setStyleSheet(f"""
            SegmentedControl {{ background: transparent; }}
            QPushButton {{
                font-family: {FONT_UI};
                font-size: 13px;
                font-weight: 500;
                color: rgba({muted.red()},{muted.green()},{muted.blue()},{muted.alpha()});
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 2px 7px 2px;
                margin-right: 18px;
            }}
            QPushButton:checked {{
                color: rgba({ink.red()},{ink.green()},{ink.blue()},{ink.alpha()});
                font-weight: 600;
                border-bottom: 2px solid rgba({ink.red()},{ink.green()},{ink.blue()},{ink.alpha()});
            }}
            QPushButton:hover:!checked {{
                color: rgba({ink.red()},{ink.green()},{ink.blue()},{ink.alpha()});
                border-bottom: 2px solid rgba({ink.red()},{ink.green()},{ink.blue()},40);
            }}
        """)
        self.setFixedHeight(32)
