"""Une prise de parole, posée le long de la ligne de temps.

L'élément signature de Benji : la gouttière n'est pas une marge, c'est une
**ligne de temps continue**. Chaque item peint son propre segment de filet, si
bien que les items empilés forment un trait ininterrompu du haut du transcript
jusqu'à la ligne en cours. S'y accrochent deux marques, qui portent chacune une
information vraie plutôt qu'un ornement :

- un **tick** horizontal quand la minute change (l'heure est écrite en regard,
  dans la gouttière) ;
- une **tige** colorée, à la couleur du locuteur, qui court sur toute la hauteur
  de sa prise de parole — on voit donc *qui* a parlé et *combien de temps* en
  parcourant la marge des yeux, sans lire une ligne.

La pastille ● devant le nom a disparu : la tige dit déjà la couleur, et deux
marques pour la même information, c'est une de trop.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from benji.ui.style import FONT_UI, current_theme, meta_qss, reading_qss, speaker_color

# Gouttière de l'heure, puis la ligne de temps, puis la tige du locuteur.
_GUTTER_WIDTH = 52
_SPINE_X = _GUTTER_WIDTH + 10   # abscisse du filet vertical
_STEM_X = _SPINE_X + 9          # abscisse de la tige colorée
_TEXT_X = _STEM_X + 14          # début du texte
_TICK_HALF = 3                  # demi-longueur du tick horizontal


class ChatItem(QWidget):
    def __init__(self, text: str, ts: datetime | None = None, speaker: str | None = None,
                 show_header: bool = True, show_ts: bool = True, seq: int | None = None,
                 parent=None):
        super().__init__(parent)
        self._text = text
        self._ts = ts or datetime.now()
        self._speaker = speaker
        self._show_header = show_header
        self._show_ts = show_ts
        self.seq = seq  # permet à LiveTab de remplacer le texte corrigé

        # Gouttière : l'heure, en mono, seulement quand la minute change.
        self.ts_label = QLabel(self._ts.strftime("%H:%M") if show_ts else "")
        self.ts_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.ts_label.setFixedWidth(_GUTTER_WIDTH)

        # En-tête de groupe : le nom seul, en capitales espacées — c'est une
        # étiquette de partition, pas un titre.
        self.speaker_label: QLabel | None = None
        if speaker and show_header:
            self.speaker_label = QLabel(speaker.upper())
            self.speaker_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.text_label = QLabel(self._text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(2)
        if self.speaker_label is not None:
            content.addWidget(self.speaker_label)
        content.addWidget(self.text_label)

        layout = QHBoxLayout(self)
        # Nouveau groupe : de l'air au-dessus ; suite du même groupe : serré.
        top = 16 if show_header else 1
        layout.setContentsMargins(0, top, 0, 1)
        layout.setSpacing(0)
        layout.addWidget(self.ts_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addSpacing(_TEXT_X - _GUTTER_WIDTH)
        layout.addLayout(content, 1)

        self.apply_theme()
        self._fade_in()

    def set_text(self, text: str) -> None:
        """Remplace le texte affiché (correction LLM asynchrone)."""
        self._text = text
        self.text_label.setText(text)

    # --- peinture de la ligne de temps ---

    def paintEvent(self, event):
        """Peint le segment de filet, le tick de minute et la tige du locuteur.

        Chaque item peint de `y=0` à `y=height()` : mis bout à bout, les segments
        ne laissent aucun trou et le filet paraît continu sur tout le transcript.
        """
        super().paintEvent(event)
        t = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(QPen(t.spine, 1))
        painter.drawLine(_SPINE_X, 0, _SPINE_X, self.height())

        if self._show_ts:
            y = self._first_line_y()
            painter.drawLine(_SPINE_X - _TICK_HALF, y, _SPINE_X + _TICK_HALF, y)

        if self._speaker:
            # Une prise de parole s'étale sur plusieurs items (un par segment
            # final). La tige part du haut de l'item quand celui-ci prolonge le
            # groupe : mises bout à bout, les tiges forment un ruban continu qui
            # dit la durée réelle du tour de parole, pas la hauteur d'une ligne.
            stem_top = (self._first_line_y() - 5) if self._show_header else 0
            stem_bottom = self.height()
            if stem_bottom > stem_top:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(speaker_color(self._speaker)))
                painter.drawRoundedRect(
                    _STEM_X, stem_top, 2, stem_bottom - stem_top, 1, 1
                )
        painter.end()

    def _first_line_y(self) -> int:
        """Ordonnée de la première ligne de texte, tick et tige s'y accrochent."""
        return self.text_label.y() + 9

    def apply_theme(self) -> None:
        t = current_theme()
        self.ts_label.setStyleSheet(meta_qss(t) + " padding-top: 8px;")
        if self.speaker_label is not None:
            self.speaker_label.setStyleSheet(
                f"font-family: {FONT_UI}; font-size: 10px; font-weight: 700; "
                f"letter-spacing: 1.1px; color: {_rgba(speaker_color(self._speaker))}; "
                "background: transparent;"
            )
        self.text_label.setStyleSheet(reading_qss(t))
        self.update()

    def _fade_in(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def _rgba(color: QColor) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"
