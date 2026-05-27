"""Fenêtre principale : toolbar + onglets Live/Résumés (style macOS natif)."""

from __future__ import annotations

import logging
import platform
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, QPushButton, QSizePolicy, QStackedWidget,
    QToolBar, QVBoxLayout, QWidget,
)

from benji.ui.live_tab import LiveTab
from benji.ui.summaries_tab import SummariesTab
from benji.ui.style import (
    apply_window_vibrancy, current_theme, install_theme_listener,
    FONT_UI,
)
from benji.ui.widgets.icons import doc_text_icon, minimize_icon
from benji.ui.widgets.segmented_control import SegmentedControl
from benji.ui.widgets.status_pill import StatusPill

log = logging.getLogger(__name__)

_SETTINGS_ORG = "benji"
_SETTINGS_APP = "benji"
_GEOM_KEY = "main_window/geometry"
_TAB_KEY = "main_window/tab_index"


class MainWindow(QMainWindow):
    def __init__(
        self,
        bus,
        history,
        session_start: datetime,
        summary_worker,
        on_minimize=None,
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
        self._vibrancy_applied = False

        self._build_ui()
        self._wire_worker()
        self._restore_state()

        if platform.system() == "Darwin":
            self.setUnifiedTitleAndToolBarOnMac(True)

        install_theme_listener(self._apply_theme)
        self._apply_theme()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._vibrancy_applied:
            apply_window_vibrancy(self)
            self._vibrancy_applied = True

    def _build_ui(self) -> None:
        # === Toolbar ===
        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.status_pill = StatusPill(self._session_start)
        tb.addWidget(self.status_pill)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self.summarize_btn = QPushButton("Résumer")
        self.summarize_btn.setObjectName("summarize_btn")
        self.summarize_btn.clicked.connect(self._request_summary)
        tb.addWidget(self.summarize_btn)

        self.minimize_btn = QPushButton("Réduire")
        self.minimize_btn.setObjectName("minimize_btn")
        self.minimize_btn.clicked.connect(self._minimize)
        tb.addWidget(self.minimize_btn)

        # === Central ===
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(8)

        seg_wrap = QHBoxLayout()
        seg_wrap.addStretch(1)
        self.segmented = SegmentedControl(["Live", "Résumés"])
        self.segmented.setFixedWidth(260)
        seg_wrap.addWidget(self.segmented)
        seg_wrap.addStretch(1)
        v.addLayout(seg_wrap)

        self.stack = QStackedWidget()
        self.live_tab = LiveTab()
        self.summaries_tab = SummariesTab()
        self.stack.addWidget(self.live_tab)
        self.stack.addWidget(self.summaries_tab)
        v.addWidget(self.stack, 1)

        self.segmented.currentChanged.connect(self.stack.setCurrentIndex)
        self.segmented.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(central)

        # === Bus wiring ===
        self._bus.event.connect(self.live_tab.on_event)
        self._bus.event.connect(self._update_vad_indicator)
        self._bus.event.connect(self._maybe_refresh_summarize_enabled)

        self._refresh_summarize_enabled()

    def _apply_theme(self) -> None:
        if platform.system() == "Darwin":
            self.setStyleSheet("""
                QMainWindow { background: transparent; }
                QToolBar { background: transparent; border: none; padding: 8px 12px; spacing: 8px; }
            """)
        else:
            bg = current_theme().window_background
            self.setStyleSheet(f"""
                QMainWindow {{ background-color: rgb({bg.red()},{bg.green()},{bg.blue()}); }}
                QToolBar {{ background: transparent; border: none; padding: 8px 12px; spacing: 8px; }}
            """)
        self.status_pill.apply_theme()
        self.segmented.apply_theme()
        self._apply_toolbar_button_styles()
        if hasattr(self.live_tab, "apply_theme"):
            self.live_tab.apply_theme()
        if hasattr(self.summaries_tab, "apply_theme"):
            self.summaries_tab.apply_theme()

    def _apply_toolbar_button_styles(self) -> None:
        t = current_theme()
        accent = t.accent
        on_accent = "#ffffff"
        hover = t.label_alpha(8)
        label = t.label
        self.summarize_btn.setIcon(doc_text_icon(on_accent))
        self.summarize_btn.setStyleSheet(f"""
            QPushButton#summarize_btn {{
                font-family: {FONT_UI};
                font-size: 12px;
                font-weight: 500;
                color: {on_accent};
                background-color: rgb({accent.red()},{accent.green()},{accent.blue()});
                border: none;
                padding: 6px 14px;
                border-radius: 6px;
            }}
            QPushButton#summarize_btn:hover {{
                background-color: rgba({accent.red()},{accent.green()},{accent.blue()},220);
            }}
            QPushButton#summarize_btn:disabled {{
                background-color: rgba({accent.red()},{accent.green()},{accent.blue()},90);
                color: rgba(255,255,255,160);
            }}
        """)
        self.minimize_btn.setIcon(minimize_icon(f"#{label.red():02x}{label.green():02x}{label.blue():02x}"))
        self.minimize_btn.setStyleSheet(f"""
            QPushButton#minimize_btn {{
                font-family: {FONT_UI};
                font-size: 12px;
                font-weight: 500;
                color: rgba({label.red()},{label.green()},{label.blue()},{label.alpha()});
                background: transparent;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QPushButton#minimize_btn:hover {{
                background-color: rgba({hover.red()},{hover.green()},{hover.blue()},{hover.alpha()});
            }}
        """)

    def _wire_worker(self) -> None:
        self._worker.started.connect(self._on_summary_started)
        self._worker.chunk.connect(self._on_summary_chunk)
        self._worker.finished.connect(self._on_summary_finished)
        self._worker.failed.connect(self._on_summary_failed)

    def _update_vad_indicator(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "vad_status":
            self.status_pill.set_speaking(bool(item.get("speaking")))

    def _maybe_refresh_summarize_enabled(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "final_text" and item.get("text"):
            self._refresh_summarize_enabled()

    def _refresh_summarize_enabled(self) -> None:
        try:
            has_history = bool(self._history.get_since(self._session_start))
        except Exception:
            has_history = False
        idle = self._pending_summary_id is None
        self.summarize_btn.setEnabled(has_history and idle)

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
        self._has_unread_summary = (self.segmented.currentIndex() != 1)
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
        has_badge = self._pending_summary_id is not None or self._has_unread_summary
        self.segmented.setBadge(1, has_badge)

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
                self.resize(960, 640)
        else:
            self.resize(960, 640)
        tab = s.value(_TAB_KEY, 0, type=int)
        self.segmented.setCurrentIndex(tab)
        self.stack.setCurrentIndex(tab)

    def closeEvent(self, event) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue(_GEOM_KEY, self.saveGeometry())
        s.setValue(_TAB_KEY, self.segmented.currentIndex())
        super().closeEvent(event)
