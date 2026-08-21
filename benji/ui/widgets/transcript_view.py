"""Transcript figé, composé exactement comme le direct.

L'archive et le live partagent `ChatItem`, donc la même ligne de temps, les
mêmes tiges de locuteur et la même face à lire. Rouvrir une réunion d'il y a
trois semaines doit donner la même page que celle qu'on regardait pendant
qu'elle se disait — c'est ce qui fait qu'un historique se lit au lieu de se
consulter.

Là où `LiveTab` groupe au fil de l'eau (il ne connaît pas la suite), cette vue
groupe un lot d'entrées d'un coup ; les règles de regroupement sont les mêmes :
un en-tête quand le locuteur change ou après un long silence, une heure quand la
minute change.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benji.ui.style import FONT_UI, current_theme
from benji.ui.widgets.chat_item import ChatItem

_MAX_CONTENT_WIDTH = 720
_GROUP_GAP = timedelta(minutes=3)


def _parse_ts(entry: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(entry["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None


class TranscriptView(QWidget):
    """Colonne scrollable de prises de parole, ou un mot quand il n'y a rien."""

    def __init__(self, empty_text: str = "Rien n'a encore été dit.", parent=None):
        super().__init__(parent)
        self._items: list[ChatItem] = []

        self.empty = QLabel(empty_text)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        viewport = QWidget()
        outer = QHBoxLayout(viewport)
        outer.setContentsMargins(4, 8, 4, 16)
        outer.setSpacing(0)

        self.content = QWidget()
        self.content.setMaximumWidth(_MAX_CONTENT_WIDTH)
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        outer.addWidget(self.content, 8)
        outer.addStretch(1)
        self.content_layout.addStretch(1)

        self.scroll.setWidget(viewport)
        # Sans ça, Qt peint le fond de base sous le viewport : un panneau gris
        # apparaît derrière le transcript, et la page se met à ressembler à une
        # carte posée sur le papier au lieu d'être la page elle-même.
        self.scroll.setAutoFillBackground(False)
        self.scroll.viewport().setAutoFillBackground(False)
        viewport.setAutoFillBackground(False)
        viewport.setStyleSheet("background: transparent;")
        self.content.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.empty, 1)
        root.addWidget(self.scroll, 1)

        self.apply_theme()
        self.set_entries([])

    def set_entries(self, entries: list[dict],
                    speaker_names: dict[str, str] | None = None) -> None:
        """Recompose entièrement la vue à partir d'entrées d'historique."""
        self._clear()
        rows = [e for e in entries if e.get("text", "").strip()]
        rows.sort(key=lambda e: _parse_ts(e) or datetime.min)

        self.empty.setVisible(not rows)
        self.scroll.setVisible(bool(rows))
        if not rows:
            return

        last_speaker: str | None = None
        last_time: datetime | None = None
        last_minute: str | None = None
        for entry in rows:
            ts = _parse_ts(entry) or datetime.min
            raw_speaker = entry.get("speaker")
            speaker = raw_speaker
            if raw_speaker and speaker_names and speaker_names.get(raw_speaker, "").strip():
                speaker = speaker_names[raw_speaker].strip()

            new_group = (
                last_time is None
                or raw_speaker != last_speaker
                or (ts - last_time) > _GROUP_GAP
            )
            minute = ts.strftime("%H:%M")
            show_ts = new_group and minute != last_minute
            if show_ts:
                last_minute = minute

            item = ChatItem(entry["text"].strip(), ts=ts, speaker=speaker,
                            show_header=new_group, show_ts=show_ts)
            self.content_layout.insertWidget(self.content_layout.count() - 1, item)
            self._items.append(item)
            last_speaker = raw_speaker
            last_time = ts

    def plain_text(self) -> str:
        """Le texte affiché, à plat — pratique pour les tests et l'accessibilité."""
        return "\n".join(item._text for item in self._items)

    def _clear(self) -> None:
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items = []

    def apply_theme(self) -> None:
        t = current_theme()
        self.setStyleSheet("QScrollArea, TranscriptView { background: transparent; border: none; }")
        self.empty.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 13px; "
            f"color: rgba({t.ink_faint.red()},{t.ink_faint.green()},"
            f"{t.ink_faint.blue()},{t.ink_faint.alpha()}); background: transparent;"
        )
        for item in self._items:
            item.apply_theme()
