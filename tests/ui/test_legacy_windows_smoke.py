"""Smoke : les fenêtres héritées restylées s'instancient et se peignent."""

from __future__ import annotations

from datetime import datetime

import pytest

from benji.ui import history_window
from benji.ui.history_window import HistoryWindow
from benji.ui.live_summary_window import LiveSummaryWindow


def test_history_window_paints(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(history_window.Path, "home", lambda: tmp_path)
    w = HistoryWindow(session_start=datetime.now())
    qtbot.addWidget(w)
    assert w.windowTitle() == "Historique"
    # Un thème est appliqué (feuille de style non vide) ; rendu sans crash.
    assert w.styleSheet()
    w._apply_theme()  # re-thème (simule un changement système) : ne doit pas lever
    assert not w.grab().isNull()


def test_live_summary_window_paints(qtbot):
    w = LiveSummaryWindow()
    qtbot.addWidget(w)
    assert w.windowTitle() == "Résumé en direct"
    assert w.styleSheet()
    w.on_summary_start(datetime.now())
    w.on_summary_chunk("Un résumé.")
    w.on_summary(" Fin.", datetime.now())
    w._apply_theme()
    assert not w.grab().isNull()
