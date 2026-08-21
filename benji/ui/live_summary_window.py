"""Résumé en direct : ce que la réunion a dit jusqu'ici, réécrit à intervalle.

La fenêtre affichait le markdown brut dans une boîte monospace — on y lisait
`**Décision**` au lieu de voir une décision. Elle rend désormais le même
markdown, avec la même feuille de style, que l'onglet Résumés.

Le texte arrive soit d'un coup, soit jeton par jeton (streaming) : dans les deux
cas la source markdown est accumulée puis re-rendue, ce qui permet de voir la
mise en forme se composer pendant l'écriture.
"""

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from benji.ui.style import (
    FONT_UI,
    current_theme,
    install_theme_listener,
    meta_qss,
    panel_background_qss,
)
from benji.ui.widgets.markdown_view import MarkdownView
from benji.ui.widgets.waveform import WaveformDot

_PLACEHOLDER = "En attente du premier résumé…"


class LiveSummaryWindow(QWidget):
    _summary_signal = pyqtSignal(str, object)  # (text, datetime)
    _start_signal = pyqtSignal(object)         # datetime
    _chunk_signal = pyqtSignal(str)            # streamed token chunk

    def __init__(self):
        super().__init__()
        self.setObjectName("LiveSummaryWindow")
        self.setWindowTitle("Résumé en direct")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(560, 460)

        # En-tête : l'onde bat pendant la rédaction, l'heure dit de quand date
        # ce qu'on lit — un résumé sans horodatage ne veut rien dire.
        self.wave = WaveformDot(bar_width=2, gap=2, height=12)
        self.title = QLabel("Résumé en direct")
        self.stamp = QLabel("")

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.wave, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.title, 0)
        head.addStretch(1)
        head.addWidget(self.stamp, 0)

        self.view = MarkdownView()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(self.view, 1)

        self._markdown = ""
        self._streaming = False

        self._summary_signal.connect(self._finalize_summary)
        self._start_signal.connect(self._begin_summary)
        self._chunk_signal.connect(self._append_chunk)

        install_theme_listener(self._apply_theme)
        self._apply_theme()
        self.view.set_markdown(f"_{_PLACEHOLDER}_")

    def _apply_theme(self) -> None:
        t = current_theme()
        self.setStyleSheet(panel_background_qss(t, "#LiveSummaryWindow"))
        self.title.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; font-weight: 600; "
            f"color: rgba({t.ink.red()},{t.ink.green()},{t.ink.blue()},{t.ink.alpha()}); "
            "background: transparent;"
        )
        self.stamp.setStyleSheet(meta_qss(t))
        self.wave.set_color(t.record)
        self.view.apply_theme(t)

    # --- Points d'entrée thread-safe ------------------------------------
    def on_summary(self, text: str, at: datetime):
        self._summary_signal.emit(text, at)

    def on_summary_start(self, at: datetime):
        self._start_signal.emit(at)

    def on_summary_chunk(self, chunk: str):
        self._chunk_signal.emit(chunk)

    # --- Slots ----------------------------------------------------------
    def _begin_summary(self, at: datetime):
        self._markdown = ""
        self._streaming = True
        self.stamp.setText(at.strftime("%H:%M"))
        self.wave.set_active(True)
        self.view.set_markdown("")

    def _append_chunk(self, chunk: str):
        self._markdown += chunk
        self.view.set_markdown(self._markdown)
        self._scroll_to_end()

    def _finalize_summary(self, text: str, at: datetime):
        # Sans streaming, le texte complet arrive d'un coup.
        if not self._streaming:
            self._markdown = text
        else:
            self._markdown += text
        self._streaming = False
        self.stamp.setText(at.strftime("%H:%M"))
        self.wave.set_active(False)
        self.view.set_markdown(self._markdown or f"_{_PLACEHOLDER}_")
        self._scroll_to_end()

    def _scroll_to_end(self):
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
