"""Onglet 'Live' : transcript style document + ligne partielle + état vide.

Le transcript est regroupé par prise de parole : l'en-tête coloré (● Nom)
n'apparaît que lorsque le locuteur change, le timestamp en gouttière seulement
quand la minute change. Une correction LLM asynchrone *remplace* la ligne
d'origine (repérée par `seq`) au lieu de s'ajouter en double.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
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
from benji.ui.widgets.partial_bubble import PartialBubble
from benji.ui.widgets.waveform import WaveformDot

# Largeur de lecture confortable (mesure ~75 caractères à 15px).
_MAX_CONTENT_WIDTH = 720
# Au-delà de ce silence, on rouvre un groupe même si le locuteur n'a pas changé.
_GROUP_GAP = timedelta(minutes=3)
# Nombre d'items conservés pour le remplacement par correction (borne mémoire).
_MAX_CORRECTABLE = 24


class _EmptyState(QWidget):
    """Écran d'accueil du Live : forme d'onde + invitation à parler."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wave = WaveformDot(bar_width=3, gap=3, height=24)
        self.title = QLabel("Benji écoute")
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.sub = QLabel("La transcription apparaît ici dès que quelqu'un parle.")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        layout = QVBoxLayout(self)
        layout.addStretch(3)
        layout.addWidget(self.wave, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(14)
        layout.addWidget(self.title)
        layout.addSpacing(4)
        layout.addWidget(self.sub)
        layout.addStretch(4)

        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        self.wave.set_color(t.accent)
        self.title.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 16px; font-weight: 600; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
        self.sub.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 13px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent;"
        )


class LiveTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._partial_text: str = ""
        self._user_scrolled_up = False
        # État de regroupement du transcript.
        self._last_speaker: str | None = None
        self._last_time: datetime | None = None
        self._last_minute: str | None = None
        # Derniers items encore remplaçables par une correction (seq → item).
        self._correctable: list[ChatItem] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.viewport_widget = QWidget()
        outer = QHBoxLayout(self.viewport_widget)
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.content = QWidget()
        self.content.setMaximumWidth(_MAX_CONTENT_WIDTH)
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addStretch(1)
        outer.addWidget(self.content, 8)
        outer.addStretch(1)

        self.scroll.setWidget(self.viewport_widget)
        self.scroll.setVisible(False)

        self.empty = _EmptyState()

        self.partial = PartialBubble()
        partial_wrap = QHBoxLayout()
        partial_wrap.setContentsMargins(16, 0, 16, 14)
        partial_wrap.addStretch(1)
        self.partial.setMaximumWidth(_MAX_CONTENT_WIDTH)
        self.partial.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        partial_wrap.addWidget(self.partial, 8)
        partial_wrap.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.empty, 1)
        root.addWidget(self.scroll, 1)
        root.addLayout(partial_wrap)

        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet("LiveTab, QScrollArea { background: transparent; border: none; }")
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport_widget.setStyleSheet("background: transparent;")
        self.content.setStyleSheet("background: transparent;")
        for i in range(self.content_layout.count() - 1):
            w = self.content_layout.itemAt(i).widget()
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()
        self.empty.apply_theme()
        self.partial.apply_theme()

    def on_event(self, item) -> None:
        if not isinstance(item, dict):
            return
        msg_type = item.get("type")
        if msg_type == "vad_status":
            # L'onde de l'état vide danse dès que la voix est détectée :
            # feedback immédiat « le micro m'entend » avant le premier mot.
            self.empty.wave.set_active(bool(item.get("speaking")))
        elif msg_type == "segment_start":
            self._partial_text = ""
            self.partial.set_text("")
        elif msg_type == "word":
            text = item.get("text", "")
            if not text:
                return
            sep = "" if (not self._partial_text or self._partial_text.endswith(" ") or text.startswith((".", ",", "!", "?", ";", ":"))) else " "
            self._partial_text = (self._partial_text + sep + text).strip()
            self.partial.set_text(self._partial_text)
        elif msg_type == "final_text":
            text = item.get("text", "")
            drop = item.get("drop", False)
            if drop or not text:
                self._partial_text = ""
                self.partial.set_text("")
                return
            if item.get("corrected"):
                self._apply_correction(item.get("seq"), text)
                return
            self._append_final(text, item.get("speaker"), item.get("seq"))
            self._partial_text = ""
            self.partial.set_text("")

    def _apply_correction(self, seq, text: str) -> None:
        """Remplace le texte d'une ligne déjà affichée (correction LLM async)."""
        if seq is None:
            return
        for chat_item in self._correctable:
            if chat_item.seq == seq:
                chat_item.set_text(text)
                return
        # Ligne trop ancienne ou inconnue : on ignore (jamais de doublon).

    def _append_final(self, text: str, speaker: str | None = None, seq=None) -> None:
        now = datetime.now()
        new_group = (
            self._last_time is None
            or speaker != self._last_speaker
            or (now - self._last_time) > _GROUP_GAP
        )
        minute = now.strftime("%H:%M")
        show_ts = new_group and minute != self._last_minute
        if show_ts:
            self._last_minute = minute

        item = ChatItem(text, ts=now, speaker=speaker,
                        show_header=new_group, show_ts=show_ts, seq=seq)
        self.content_layout.insertWidget(self.content_layout.count() - 1, item)
        self._last_speaker = speaker
        self._last_time = now

        if seq is not None:
            self._correctable.append(item)
            if len(self._correctable) > _MAX_CORRECTABLE:
                self._correctable.pop(0)

        if not self.scroll.isVisible():
            self.empty.setVisible(False)
            self.scroll.setVisible(True)
        if not self._user_scrolled_up:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll(self, value: int) -> None:
        sb = self.scroll.verticalScrollBar()
        self._user_scrolled_up = (sb.maximum() - value) > 20
