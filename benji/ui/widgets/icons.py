"""SVG inline → QIcon. Couleur adaptée au thème courant."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_DOC_TEXT = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <path d='M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z'
        fill='none' stroke='COLOR' stroke-width='1.6' stroke-linejoin='round'/>
  <path d='M14 3v5h5' fill='none' stroke='COLOR' stroke-width='1.6'/>
  <path d='M8 13h8M8 16h8M8 10h4' stroke='COLOR' stroke-width='1.4' stroke-linecap='round'/>
</svg>
"""

_MINIMIZE = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <path d='M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7'
        fill='none' stroke='COLOR' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/>
</svg>
"""

_CLIPBOARD = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <rect x='6' y='4' width='12' height='17' rx='2' fill='none' stroke='COLOR' stroke-width='1.6'/>
  <rect x='9' y='2' width='6' height='4' rx='1' fill='COLOR' fill-opacity='0.15' stroke='COLOR' stroke-width='1.6'/>
</svg>
"""

_FOLDER_ARROW = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <path d='M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z'
        fill='none' stroke='COLOR' stroke-width='1.6' stroke-linejoin='round'/>
  <path d='M11 14l3-3-3-3M14 11H8' fill='none' stroke='COLOR' stroke-width='1.6' stroke-linecap='round'/>
</svg>
"""


def _render(svg: str, color_hex: str, size: int = 18) -> QIcon:
    data = svg.replace("COLOR", color_hex).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(data))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    renderer.render(p)
    p.end()
    return QIcon(pixmap)


def doc_text_icon(color_hex: str) -> QIcon:
    return _render(_DOC_TEXT, color_hex)


def minimize_icon(color_hex: str) -> QIcon:
    return _render(_MINIMIZE, color_hex)


def clipboard_icon(color_hex: str) -> QIcon:
    return _render(_CLIPBOARD, color_hex)


def folder_arrow_icon(color_hex: str) -> QIcon:
    return _render(_FOLDER_ARROW, color_hex)
