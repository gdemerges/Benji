"""Onglet 'Live' : transcript style document + ligne partielle + état vide.

Le transcript est regroupé par prise de parole : l'en-tête coloré (● Nom)
n'apparaît que lorsque le locuteur change, le timestamp en gouttière seulement
quand la minute change. Une correction LLM asynchrone *remplace* la ligne
d'origine (repérée par `seq`) au lieu de s'ajouter en double.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benji import search
from benji.stt.postprocessing import join_words
from benji.ui.style import (
    FONT_UI,
    current_theme,
    field_qss,
    meta_qss,
    primary_button_qss,
    secondary_button_qss,
)
from benji.ui.widgets.chat_item import ChatItem
from benji.ui.widgets.partial_bubble import PartialBubble
from benji.ui.widgets.waveform import WaveformDot

# Largeur de lecture confortable (mesure ~75 caractères à 15px).
_MAX_CONTENT_WIDTH = 720
# Au-delà de ce silence, on rouvre un groupe même si le locuteur n'a pas changé.
_GROUP_GAP = timedelta(minutes=3)
# Nombre d'items conservés pour le remplacement par correction (borne mémoire).
_MAX_CORRECTABLE = 24
# Nombre de lignes gardées à l'écran. Sans plafond, une réunion de deux heures
# laisse plus d'un millier de QWidget vivants : la mémoire grimpe et chaque
# nouvelle ligne relayoute une pile de plus en plus lourde. Les lignes retirées
# de l'affichage restent dans l'historique sur disque — rien n'est perdu.
_MAX_ITEMS = 500


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


class _ConsentBanner(QWidget):
    """« J'écoute, je ne garde pas encore » — et le geste pour changer d'avis.

    Écouter et garder ne sont pas le même geste : Benji transcrit dès le
    lancement, mais rien ne part sur disque sans accord (cf. benji/recording.py).
    Le bandeau dit l'état courant plutôt que de le laisser deviner — un utilisateur
    qui croit enregistrer alors que non est le pire des deux états.

    Pas de rouge ici, malgré l'envie : le rouge ne signifie qu'« on prend au mot,
    maintenant », et c'est précisément ce qui n'a pas lieu. L'action est un aplat
    d'encre, comme partout ailleurs.
    """

    accepted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("Benji écoute — rien n'est encore conservé.")
        self.button = QPushButton("Enregistrer")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(self.accepted)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 0)
        row.setSpacing(10)
        row.addStretch(1)
        row.addWidget(self.label, 0)
        row.addWidget(self.button, 0)
        row.addStretch(1)
        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        self.label.setStyleSheet(meta_qss(t, size=12))
        self.button.setStyleSheet(primary_button_qss(t))


class LiveTab(QWidget):
    save_requested = pyqtSignal()

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
        # Suivre le bas sur `rangeChanged`, pas juste après l'ajout du widget :
        # une ligne qui vient d'être insérée n'a pas encore sa hauteur (le
        # retour à la ligne se calcule au layout), si bien qu'un scroll immédiat
        # visait un maximum périmé et laissait la dernière phrase sous le pli.
        self.scroll.verticalScrollBar().rangeChanged.connect(self._on_range_changed)

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
        # Le ressort est en HAUT : le transcript se tasse vers le bas, si bien que
        # la ligne en cours suit toujours la dernière phrase dite au lieu de
        # flotter à des centaines de pixels sous un début de réunion.
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

        self.consent = _ConsentBanner()
        self.consent.accepted.connect(self.save_requested)
        self.consent.setVisible(False)

        # Recherche : masquée par défaut, appelée par ⌘F. Le Live est un
        # instrument, pas un tableau de bord — une barre en permanence coûterait
        # de la place à ce qui se dit, pour un geste qu'on fait rarement.
        self.search_bar = QWidget()
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Rechercher dans la réunion…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self._on_search_changed)
        self.search_count = QLabel("")
        search_row = QHBoxLayout(self.search_bar)
        search_row.setContentsMargins(16, 8, 16, 0)
        search_row.setSpacing(8)
        search_row.addStretch(1)
        search_row.addWidget(self.search_field, 8)
        search_row.addWidget(self.search_count, 0)
        search_row.addStretch(1)
        self.search_bar.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.consent)
        root.addWidget(self.search_bar)
        root.addWidget(self.empty, 1)
        root.addWidget(self.scroll, 1)
        root.addLayout(partial_wrap)

        # Retour au direct : posé **par-dessus** le transcript (pas dans le
        # layout), il n'apparaît que lorsqu'on a décroché du bas. Sans lui, le
        # défilement automatique laisse l'utilisateur sans issue : rien ne dit
        # qu'on ne suit plus, et il faut redescendre à la main.
        self.jump_btn = QPushButton("↓  En direct", self)
        self.jump_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.jump_btn.clicked.connect(self._resume_follow)
        self.jump_btn.setVisible(False)

        # Le transcript est fait de QLabel indépendants : une sélection ne
        # franchit pas la ligne. Copier tout ce qui est à l'écran est donc le
        # seul geste qui rende le direct exploitable sans passer par la fenêtre
        # Réunions — où l'on n'est justement pas pendant une réunion.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)
        QShortcut(QKeySequence("Ctrl+F"), self, self.toggle_search)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self.copy_transcript)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search_field, self.close_search)

        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet("LiveTab, QScrollArea { background: transparent; border: none; }")
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport_widget.setStyleSheet("background: transparent;")
        self.content.setStyleSheet("background: transparent;")
        for i in range(self.content_layout.count()):
            w = self.content_layout.itemAt(i).widget()
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()
        self.empty.apply_theme()
        self.partial.apply_theme()
        self.consent.apply_theme()
        t = current_theme()
        self.search_field.setStyleSheet(field_qss(t))
        self.search_count.setStyleSheet(meta_qss(t))
        self.jump_btn.setStyleSheet(secondary_button_qss(t))
        self.jump_btn.adjustSize()

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
        elif msg_type == "partial":
            # Une passe entière en un message (cf. stt/transcriber.py) : on
            # remplace la ligne vivante d'un coup au lieu de la recomposer mot
            # à mot, chacun repeignant la bulle.
            self._partial_text = join_words(w.get("text", "") for w in item.get("words", []))
            self.partial.set_text(self._partial_text)
        elif msg_type == "word":
            # Mot à mot : chemin du mode remote (cf. stt/remote.py).
            text = item.get("text", "")
            if not text:
                return
            self._partial_text = join_words([self._partial_text, text])
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
        self.content_layout.addWidget(item)
        self._last_speaker = speaker
        self._last_time = now

        if seq is not None:
            self._correctable.append(item)
            if len(self._correctable) > _MAX_CORRECTABLE:
                self._correctable.pop(0)

        self._trim_items()

        if not self.scroll.isVisible():
            self.empty.setVisible(False)
            self.scroll.setVisible(True)
        # Une recherche en cours filtre aussi ce qui arrive : sinon une phrase
        # hors résultat s'insérerait au milieu d'une liste filtrée.
        if self.search_bar.isVisible():
            item.setVisible(
                search.entry_matches(
                    {"text": text, "speaker": speaker or ""},
                    search.terms(self.search_field.text()),
                )
            )
        # Le suivi du bas est assuré par `_on_range_changed` dès que la
        # nouvelle ligne a été mise en page.

    def _trim_items(self) -> None:
        """Retire les lignes les plus anciennes au-delà de `_MAX_ITEMS`.

        Le ressort occupe l'index 0 : le plus ancien widget est juste après.
        """
        while self.content_layout.count() - 1 > _MAX_ITEMS:
            widget = None
            for i in range(self.content_layout.count()):
                candidate = self.content_layout.itemAt(i)
                if candidate is not None and candidate.widget() is not None:
                    widget = candidate.widget()
                    self.content_layout.takeAt(i)
                    break
            if widget is None:
                return

            # Une ligne retirée ne peut plus recevoir de correction : couper la
            # référence avant `deleteLater`, sinon `_apply_correction` toucherait
            # un objet C++ déjà détruit.
            self._correctable = [c for c in self._correctable if c is not widget]
            widget.setParent(None)
            widget.deleteLater()

    def _on_range_changed(self, _minimum: int, _maximum: int) -> None:
        """La hauteur du transcript a changé : recoller au bas si on le suivait."""
        if not self._user_scrolled_up:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll(self, value: int) -> None:
        sb = self.scroll.verticalScrollBar()
        self._user_scrolled_up = (sb.maximum() - value) > 20
        self._sync_jump_button()

    # --- Conservation ------------------------------------------------------
    def set_consent_pending(self, pending: bool) -> None:
        """Affiche (ou retire) l'invitation à conserver la réunion en cours."""
        self.consent.setVisible(pending)

    # --- Retour au direct -------------------------------------------------
    def _sync_jump_button(self) -> None:
        """Le bouton n'existe que dans l'état où il sert : décroché du bas."""
        visible = self._user_scrolled_up and self.scroll.isVisible()
        self.jump_btn.setVisible(visible)
        if visible:
            self._place_jump_button()
            self.jump_btn.raise_()

    def _place_jump_button(self) -> None:
        geo = self.scroll.geometry()
        size = self.jump_btn.sizeHint()
        self.jump_btn.setFixedSize(size)
        self.jump_btn.move(
            geo.right() - size.width() - 20,
            geo.bottom() - size.height() - 12,
        )

    def _resume_follow(self) -> None:
        self._user_scrolled_up = False
        self._scroll_to_bottom()
        self._sync_jump_button()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.jump_btn.isVisible():
            self._place_jump_button()

    # --- Recherche --------------------------------------------------------
    def toggle_search(self) -> None:
        if self.search_bar.isVisible():
            self.close_search()
            return
        self.search_bar.setVisible(True)
        self.search_field.setFocus()
        self.search_field.selectAll()

    def close_search(self) -> None:
        """Fermer la recherche rend le transcript entier, jamais un filtre orphelin."""
        self.search_field.clear()
        self.search_bar.setVisible(False)

    def _on_search_changed(self, query: str) -> None:
        needles = search.terms(query)
        items = self._items()
        shown = 0
        for item in items:
            match = search.entry_matches(
                {"text": item._text, "speaker": item._speaker or ""}, needles
            )
            item.setVisible(match)
            shown += match
        if not needles:
            self.search_count.setText("")
        else:
            self.search_count.setText(
                f"{shown} sur {len(items)}" if items else "aucune ligne"
            )
        # Chercher, c'est relire : on ne se fait pas ramener au bas par la phrase
        # suivante pendant qu'on lit un résultat.
        self._user_scrolled_up = bool(needles)
        self._sync_jump_button()

    # --- Copie ------------------------------------------------------------
    def _items(self) -> list[ChatItem]:
        out = []
        for i in range(self.content_layout.count()):
            widget = self.content_layout.itemAt(i).widget()
            if widget is not None:
                out.append(widget)
        return out

    def transcript_text(self) -> str:
        """Le transcript affiché, tel qu'on le collerait dans un compte rendu.

        Ce qui est filtré par la recherche est exclu : les actions portent sur ce
        qui est à l'écran, comme dans la fenêtre Réunions.
        """
        lines = []
        for item in self._items():
            if not item.isVisible() and self.search_bar.isVisible():
                continue
            stamp = item._ts.strftime("%H:%M")
            who = f"{item._speaker} : " if item._speaker else ""
            lines.append(f"[{stamp}] {who}{item._text}")
        return "\n".join(lines)

    def copy_transcript(self) -> None:
        text = self.transcript_text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def _open_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy = menu.addAction("Copier le transcript")
        copy.setEnabled(bool(self._items()))
        copy.triggered.connect(self.copy_transcript)
        find = menu.addAction("Rechercher…")
        find.triggered.connect(self.toggle_search)
        menu.exec(self.mapToGlobal(pos))
