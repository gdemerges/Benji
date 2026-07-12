"""Forme d'onde miniature animée — l'élément signature de Benji.

Cinq barres verticales qui dansent quand la voix est détectée, posées à plat
sinon. Utilisée partout où l'app « écoute » : status pill, ligne de texte
partiel, overlay. Peinture QPainter pure, un seul QTimer actif uniquement
pendant l'animation (rien ne tourne au repos).
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

# Phases décalées pour que les barres ne battent pas en chœur.
_PHASES = (0.0, 1.9, 0.8, 2.6, 1.3)
# Vitesses légèrement différentes : le motif ne boucle jamais visiblement.
_SPEEDS = (1.00, 1.31, 1.13, 1.47, 1.22)


class WaveformDot(QWidget):
    """Mini forme d'onde à 5 barres. `set_active(True)` anime, sinon repos plat."""

    def __init__(self, bar_width: int = 2, gap: int = 2, height: int = 14, parent=None):
        super().__init__(parent)
        self._bar_w = bar_width
        self._gap = gap
        self._active = False
        self._t = 0.0
        self._color = QColor(150, 150, 150)
        self.setFixedSize(5 * bar_width + 4 * gap, height)

        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20 fps : fluide et léger
        self._timer.timeout.connect(self._tick)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        if active:
            self._timer.start()
        else:
            self._timer.stop()
            self.update()

    def _tick(self) -> None:
        self._t += 0.05
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        h = self.height()
        min_h = max(2, self._bar_w)
        for i in range(5):
            if self._active:
                # Sinus par barre : amplitude entre ~25 % et 100 % de la hauteur.
                wave = 0.5 + 0.5 * math.sin(self._t * 2 * math.pi * _SPEEDS[i] + _PHASES[i])
                bar_h = min_h + (h - min_h) * (0.25 + 0.75 * wave)
            else:
                bar_h = float(min_h)
            x = i * (self._bar_w + self._gap)
            y = (h - bar_h) / 2
            radius = self._bar_w / 2
            p.drawRoundedRect(int(x), int(y), self._bar_w, int(bar_h), radius, radius)
