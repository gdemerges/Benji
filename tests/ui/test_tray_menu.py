"""Menu tray : entrées diagnostic (signalement / logs)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

import benji.ui.tray as tray_mod
from benji.config import STTConfig
from benji.stats import SessionStats


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def opened_urls(monkeypatch):
    """Neutralise les effets de bord : aucun mail ni Finder ouvert pendant les tests."""
    urls: list[str] = []
    monkeypatch.setattr(
        tray_mod.QDesktopServices, "openUrl", staticmethod(lambda u: urls.append(u.toString()))
    )
    monkeypatch.setattr(tray_mod, "reveal_logs", lambda: None)
    return urls


def _tray(**kwargs):
    return tray_mod.build_tray(MagicMock(), MagicMock(), session=None, **kwargs)


def _action(tray, needle):
    for a in tray.contextMenu().actions():
        if needle.lower() in a.text().lower():
            return a
    return None


def test_menu_exposes_diagnostic_entries(qapp, opened_urls):
    tray = _tray()
    assert _action(tray, "signaler un problème") is not None
    assert _action(tray, "révéler les logs") is not None
    tray.hide()


def test_report_action_opens_mailto_with_session_stats(qapp, opened_urls):
    stats = SessionStats()
    stats.record_segment(audio_seconds=2.0, latency_ms=120.0)
    stats.record_drop("stt_error")

    tray = _tray(stats=stats, stt_config=STTConfig())
    _action(tray, "signaler un problème").trigger()

    assert len(opened_urls) == 1
    url = opened_urls[0]
    assert url.startswith("mailto:")
    assert "Segments" in url or "Segments" in url.replace("%20", " ")
    tray.hide()


def test_report_action_works_without_stats(qapp, opened_urls):
    # Un signalement doit rester possible même si l'app a échoué tôt (pas de stats).
    tray = _tray()
    _action(tray, "signaler un problème").trigger()

    assert len(opened_urls) == 1
    assert opened_urls[0].startswith("mailto:")
    tray.hide()
