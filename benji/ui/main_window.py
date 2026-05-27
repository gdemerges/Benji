"""Fenêtre principale : toolbar + onglets Live/Résumés."""

from __future__ import annotations

import logging
import platform
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QLabel, QMainWindow, QSizePolicy, QTabWidget, QToolBar, QWidget,
)

from benji.ui.live_tab import LiveTab
from benji.ui.summaries_tab import SummariesTab

log = logging.getLogger(__name__)

_SETTINGS_ORG = "benji"
_SETTINGS_APP = "benji"
_GEOM_KEY = "main_window/geometry"
_TAB_KEY = "main_window/tab_index"


class MainWindow(QMainWindow):
    def __init__(
        self,
        bus,
        history,                       # TranscriptionHistory
        session_start: datetime,
        summary_worker,                # SummaryWorker
        on_minimize=None,              # callable() → bascule overlay
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Benji")
        self._bus = bus
        self._history = history
        self._session_start = session_start
        self._worker = summary_worker
        self._on_minimize = on_minimize
        self._pending_summary_id: str | None = None
        self._has_unread_summary = False

        self._build_ui()
        self._wire_worker()
        self._restore_state()

        if platform.system() == "Darwin":
            self.setUnifiedTitleAndToolBarOnMac(True)

    def _build_ui(self) -> None:
        # Onglets
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.live_tab = LiveTab()
        self.summaries_tab = SummariesTab()
        self.tabs.addTab(self.live_tab, "Live")
        self.tabs.addTab(self.summaries_tab, "Résumés")
        self.setCentralWidget(self.tabs)

        # DisplayBus → LiveTab + VAD indicator
        self._bus.event.connect(self.live_tab.on_event)
        self._bus.event.connect(self._update_vad_indicator)
        # Réactiver le bouton "Résumer" dès qu'un final arrive
        self._bus.event.connect(self._maybe_refresh_summarize_enabled)

        # Toolbar
        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.vad_label = QLabel("● Session démarrée")
        self.vad_label.setStyleSheet("color: gray; padding-left: 8px;")
        tb.addWidget(self.vad_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self.summarize_action = QAction("📝 Résumer maintenant", self)
        self.summarize_action.triggered.connect(self._request_summary)
        tb.addAction(self.summarize_action)

        self.minimize_action = QAction("↘ Réduire", self)
        self.minimize_action.triggered.connect(self._minimize)
        tb.addAction(self.minimize_action)

        # Tab badge dirty bit
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Bouton "Résumer" désactivé tant qu'aucun final accumulé
        self._refresh_summarize_enabled()

    def _wire_worker(self) -> None:
        self._worker.started.connect(self._on_summary_started)
        self._worker.chunk.connect(self._on_summary_chunk)
        self._worker.finished.connect(self._on_summary_finished)
        self._worker.failed.connect(self._on_summary_failed)

    def _update_vad_indicator(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "vad_status":
            if item.get("speaking"):
                self.vad_label.setText("🔴 En écoute")
                self.vad_label.setStyleSheet("color: #e44; padding-left: 8px;")
            else:
                self.vad_label.setText("● En attente")
                self.vad_label.setStyleSheet("color: gray; padding-left: 8px;")

    def _maybe_refresh_summarize_enabled(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "final_text" and item.get("text"):
            self._refresh_summarize_enabled()

    def _refresh_summarize_enabled(self) -> None:
        try:
            has_history = bool(self._history.get_since(self._session_start))
        except Exception:
            has_history = False
        idle = self._pending_summary_id is None
        self.summarize_action.setEnabled(has_history and idle)

    def _request_summary(self) -> None:
        entries = self._history.get_since(self._session_start)
        if not entries:
            return
        sid = uuid.uuid4().hex
        self._pending_summary_id = sid
        self._refresh_summarize_enabled()
        self.summaries_tab.begin_pending(sid)
        self._refresh_tab_badge()
        self._worker.request(entries=entries, summary_id=sid)

    def _on_summary_started(self, sid: str) -> None:
        log.info("Summary started: %s", sid)

    def _on_summary_chunk(self, sid: str, chunk: str) -> None:
        self.summaries_tab.append_chunk(sid, chunk)

    def _on_summary_finished(self, sid: str, path: Path) -> None:
        self.summaries_tab.finalize_pending(sid, path)
        self._pending_summary_id = None
        self._has_unread_summary = (self.tabs.currentIndex() != 1)
        self._refresh_tab_badge()
        self._refresh_summarize_enabled()

    def _on_summary_failed(self, sid: str, err: str) -> None:
        self.summaries_tab.fail_pending(sid, err)
        self._pending_summary_id = None
        self._refresh_tab_badge()
        self._refresh_summarize_enabled()

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 1:
            self._has_unread_summary = False
            self._refresh_tab_badge()

    def _refresh_tab_badge(self) -> None:
        base = "Résumés"
        if self._pending_summary_id is not None:
            self.tabs.setTabText(1, f"{base} (1●)")
        elif self._has_unread_summary:
            self.tabs.setTabText(1, f"{base} ●")
        else:
            self.tabs.setTabText(1, base)

    def _minimize(self) -> None:
        if self._on_minimize is not None:
            self._on_minimize()

    def _restore_state(self) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        geom = s.value(_GEOM_KEY)
        if geom is not None:
            try:
                self.restoreGeometry(geom)
            except Exception:
                self.resize(900, 600)
        else:
            self.resize(900, 600)
        tab = s.value(_TAB_KEY, 0, type=int)
        self.tabs.setCurrentIndex(tab)

    def closeEvent(self, event) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue(_GEOM_KEY, self.saveGeometry())
        s.setValue(_TAB_KEY, self.tabs.currentIndex())
        super().closeEvent(event)
