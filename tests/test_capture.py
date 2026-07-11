"""AudioCapture : le callback CoreAudio ne doit jamais bloquer (queue pleine → drop)."""

from queue import Queue

import numpy as np

from benji.audio.capture import AudioCapture
from benji.stats import SessionStats


def _chunk() -> np.ndarray:
    # Le callback reçoit du (frames, channels) ; on ne garde que le canal 0.
    return np.zeros((4, 1), dtype=np.float32)


def test_callback_drops_when_queue_full():
    stats = SessionStats()
    capture = AudioCapture(Queue(maxsize=1), stats=stats)

    capture._callback(_chunk(), 4, None, None)  # remplit la queue
    capture._callback(_chunk(), 4, None, None)  # queue pleine → drop, pas de blocage

    assert capture.audio_queue.qsize() == 1
    assert stats.snapshot()["drops"] == {"audio_queue_full": 1}


def test_callback_without_stats_still_drops_silently():
    capture = AudioCapture(Queue(maxsize=1))
    capture._callback(_chunk(), 4, None, None)
    capture._callback(_chunk(), 4, None, None)  # ne doit pas lever
    assert capture.audio_queue.qsize() == 1


def test_pause_closes_stream_and_resume_reopens(monkeypatch):
    """pause() ferme le stream (indicateur micro macOS éteint) ; resume() le rouvre."""
    capture = AudioCapture(Queue())
    opened: list[bool] = []
    monkeypatch.setattr(capture, "_open_stream", lambda: opened.append(True) or True)
    closed: list[bool] = []
    monkeypatch.setattr(capture, "_close_stream", lambda: closed.append(True))

    assert not capture.is_paused
    capture.pause()
    assert capture.is_paused
    assert closed == [True]

    capture.pause()  # idempotent : pas de double fermeture
    assert closed == [True]

    capture.resume()
    assert not capture.is_paused
    assert opened == [True]

    capture.resume()  # idempotent : pas de double ouverture
    assert opened == [True]
