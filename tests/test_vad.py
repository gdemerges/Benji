"""VAD state-transition tests with a mocked Silero model."""

from queue import Queue
from unittest.mock import patch

import numpy as np
import pytest

from benji.audio.vad import VADProcessor
from benji.config import AudioConfig, VADConfig


@pytest.fixture
def chunks():
    # 512-sample chunks of silence (Silero VAD expected size)
    return [np.zeros(512, dtype=np.float32) for _ in range(40)]


def _make_vad(speech_series, audio_cfg=None, vad_cfg=None):
    """Build a VADProcessor whose model returns speech_series values in order."""
    audio_q = Queue()
    tx_q = Queue()
    display_q = Queue()

    audio_cfg = audio_cfg or AudioConfig()
    vad_cfg = vad_cfg or VADConfig(
        partial_interval_ms=0,  # disable partials by default for deterministic tests
        min_speech_duration_ms=0,
    )

    with patch("benji.audio.vad._download_model", return_value="/dev/null"), \
         patch("benji.audio.vad.SileroVADOnnx") as MockModel:
        instance = MockModel.return_value
        instance.side_effect = iter(speech_series)
        instance.reset_state = lambda: None
        vad = VADProcessor(audio_q, tx_q, audio_cfg, vad_cfg, display_q)
    return vad, tx_q, display_q


def test_speech_then_silence_flushes_final(chunks):
    # 10 "speech" confidences, then 30 "silence"
    series = [0.9] * 10 + [0.1] * 30
    vad, tx_q, _ = _make_vad(series)

    for c in chunks:
        vad.process_chunk(c)

    assert not tx_q.empty()
    item = tx_q.get()
    assert item["is_final"] is True
    assert isinstance(item["audio"], np.ndarray)


def test_pure_silence_emits_nothing(chunks):
    series = [0.1] * 40
    vad, tx_q, _ = _make_vad(series)
    for c in chunks:
        vad.process_chunk(c)
    assert tx_q.empty()


def test_partial_emitted_during_speech(chunks):
    series = [0.9] * 40
    # partial every ~64ms → emits during accumulation
    cfg = VADConfig(
        partial_interval_ms=64,
        min_speech_duration_ms=0,
        silence_duration_ms=5000,
        max_speech_duration_s=60.0,
    )
    vad, tx_q, _ = _make_vad(series, vad_cfg=cfg)
    for c in chunks[:20]:  # 20 * 32ms = 640ms
        vad.process_chunk(c)
    # Expect at least one partial queued
    items = []
    while not tx_q.empty():
        items.append(tx_q.get())
    assert any(not it["is_final"] for it in items)


def test_max_duration_forces_flush(chunks):
    series = [0.9] * 200
    cfg = VADConfig(
        partial_interval_ms=0,
        min_speech_duration_ms=0,
        silence_duration_ms=5000,
        max_speech_duration_s=0.1,  # 100ms → flushes almost immediately
    )
    vad, tx_q, _ = _make_vad(series, vad_cfg=cfg)
    for c in chunks[:20]:
        vad.process_chunk(c)
    assert not tx_q.empty()
    assert tx_q.get()["is_final"] is True
