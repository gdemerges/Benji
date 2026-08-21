"""La feuille de lecture — le plan surélevé sur lequel se pose le transcript.

Ce qui fait qu'une interface de lecture paraît récente n'est pas la teinte du
fond, c'est le **relief** : une fenêtre à un seul aplat se lit comme un panneau
de réglages, deux plans se lisent comme un document posé sur un plan de travail.
Le fond de fenêtre est donc plus profond que la feuille, et la ligne de temps
court sur la feuille — jamais sur le fond.

L'ombre est peinte à la main (quelques rectangles arrondis d'opacité
décroissante) plutôt que confiée à un `QGraphicsDropShadowEffect` : un effet
graphique sur un conteneur qui embarque une zone défilante force un
re-rendu hors écran de tout le sous-arbre à chaque frame de scroll. Ici le coût
est de quatre `drawRoundedRect` par repeint du cadre.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from benji.ui.style import current_theme

_RADIUS = 12
# Épaisseur de l'ombre portée, en px. Volontairement courte : une ombre longue
# fait flotter la feuille, on veut qu'elle soit *posée*.
_SHADOW_SPREAD = 7


class Sheet(QWidget):
    """Conteneur qui se peint en feuille surélevée. `layout` reçoit le contenu."""

    def __init__(self, margins: tuple[int, int, int, int] = (0, 0, 0, 0), parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(0)

    def paintEvent(self, event):
        t = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Ombre : des halos concentriques de plus en plus transparents. Plus
        # marquée en thème clair — dans le sombre, c'est la feuille *plus claire*
        # que le fond qui porte le relief, une ombre noire n'y ferait rien.
        base_alpha = 20 if not t.is_dark else 34
        for i in range(_SHADOW_SPREAD, 0, -1):
            alpha = int(base_alpha * (1 - (i - 1) / _SHADOW_SPREAD) ** 2)
            if alpha <= 0:
                continue
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(i, i + 1, -i, -i + 1),
                _RADIUS + i, _RADIUS + i,
            )

        rect = QRectF(self.rect()).adjusted(
            _SHADOW_SPREAD, _SHADOW_SPREAD, -_SHADOW_SPREAD, -_SHADOW_SPREAD
        )
        painter.setBrush(QColor(t.sheet))
        painter.setPen(QPen(QColor(t.sheet_edge), 1))
        painter.drawRoundedRect(rect, _RADIUS, _RADIUS)
        painter.end()

    def content_margins(self) -> int:
        """Marge à respecter par le contenu pour ne pas déborder de l'ombre."""
        return _SHADOW_SPREAD
