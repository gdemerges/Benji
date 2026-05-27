"""Smoke test : la MainWindow s'instancie sans erreur."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication


class FakeBus(QObject):
    event = pyqtSignal(object)


class FakeWorker(QObject):
    started = pyqtSignal(str)
    chunk = pyqtSignal(str, str)
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def request(self, **kwargs):
        pass


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_instantiates(qapp):
    from benji.ui.main_window import MainWindow

    history = MagicMock()
    history.get_since.return_value = []
    bus = FakeBus()
    worker = FakeWorker()

    w = MainWindow(
        bus=bus,
        history=history,
        session_start=datetime.now(),
        summary_worker=worker,
        on_minimize=lambda: None,
    )
    assert w.windowTitle() == "Benji"
    assert w.segmented.currentIndex() in (0, 1)
    w.close()


def test_status_pill_switches(qapp):
    from benji.ui.widgets.status_pill import StatusPill

    pill = StatusPill(datetime.now())
    pill.set_speaking(True)
    assert pill.status_label.text() == "En écoute"
    pill.set_speaking(False)
    assert pill.status_label.text() == "En attente"
