"""Menu compte de MainWindow : login (état déconnecté) vs abonnement (connecté)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from benji.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeBus(QObject):
    event = pyqtSignal(object)


class FakeWorker(QObject):
    started = pyqtSignal(str)
    chunk = pyqtSignal(str, str)
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def request(self, **k):
        pass


class FakeSession:
    def __init__(self, authenticated=False, email=None):
        self.is_authenticated = authenticated
        self.email = email

    def access_token(self):
        return "tok" if self.is_authenticated else None


def _window(session, on_prefs=None):
    h = MagicMock()
    h.get_since.return_value = []
    return MainWindow(
        bus=FakeBus(), history=h, session_start=datetime.now(),
        summary_worker=FakeWorker(), on_open_preferences=on_prefs,
        session=session, backend_url="http://x",
    )


def _labels(menu):
    return [a.text() for a in menu.actions() if a.text()]


def test_menu_logged_out_offers_login(qapp):
    w = _window(FakeSession(authenticated=False))
    labels = _labels(w._build_account_menu())
    assert any("connecter" in x.lower() for x in labels)
    assert not any("pro" in x.lower() for x in labels)
    w.close()


def test_menu_logged_in_offers_subscription(qapp):
    w = _window(FakeSession(authenticated=True, email="a@b.com"))
    labels = _labels(w._build_account_menu())
    assert "a@b.com" in labels
    assert any("pro" in x.lower() for x in labels)
    assert any("abonnement" in x.lower() for x in labels)
    assert any("déconnecter" in x.lower() for x in labels)
    w.close()


def test_no_account_menu_without_session(qapp):
    w = _window(session=None)
    assert w._build_account_menu() is None
    assert w._account is None
    w.close()


def test_settings_button_invokes_callback(qapp):
    called = []
    w = _window(FakeSession(), on_prefs=lambda: called.append(True))
    w._open_preferences()
    assert called == [True]
    w.close()
