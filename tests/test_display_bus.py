from queue import Queue

import pytest

from benji.ui.display_bus import DisplayBus


@pytest.fixture
def app(qtbot):
    # qtbot fixture from pytest-qt instantiates a QApplication automatically
    return qtbot


def test_event_dispatched_to_subscribers(app):
    q: Queue = Queue()
    bus = DisplayBus(q, poll_ms=5)
    received_a, received_b = [], []
    bus.event.connect(received_a.append)
    bus.event.connect(received_b.append)
    bus.start()

    q.put({"type": "word", "text": "hello"})
    app.wait(50)

    assert received_a == [{"type": "word", "text": "hello"}]
    assert received_b == [{"type": "word", "text": "hello"}]
    bus.stop()


def test_failing_slot_does_not_block_others(app):
    q: Queue = Queue()
    bus = DisplayBus(q, poll_ms=5)
    received = []
    bus.subscribe(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.event.connect(received.append)
    bus.start()

    q.put({"type": "word", "text": "hi"})
    app.wait(50)

    assert received == [{"type": "word", "text": "hi"}]
    bus.stop()


def test_none_sentinel_ignored(app):
    q: Queue = Queue()
    bus = DisplayBus(q, poll_ms=5)
    received = []
    bus.event.connect(received.append)
    bus.start()

    q.put(None)
    q.put({"type": "word", "text": "x"})
    app.wait(50)

    assert received == [{"type": "word", "text": "x"}]
    bus.stop()
