"""Tests for the incremental streaming logic in Transcriber (LocalAgreement-2).

The transcriber decodes only the *unconfirmed tail* of a growing audio buffer
and commits the prefix that two successive partial passes agree on. These tests
drive that state machine with a scripted fake backend — no Whisper model, no
audio decoding — so the agreement / slicing / timestamp-shifting logic is
exercised in isolation.
"""

from queue import Queue

import numpy as np
import pytest

import benji.stt.transcriber as transcriber_mod
from benji.config import STTConfig
from benji.stt.transcriber import Transcriber

SR = 16000


class FakeBackend:
    """Yields a scripted word list per transcribe() call.

    Each scripted word is ``(text, start, end)`` with start/end in seconds
    relative to the *slice* it is handed. The audio argument is ignored: these
    tests exercise the agreement bookkeeping, not real decoding. The length of
    each audio slice is recorded in ``calls`` so tests can assert that the cut
    point actually advances (decoding a shorter slice each time).
    """

    name = "fake"

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls: list[int] = []

    def transcribe(self, audio, language, beam_size=None, initial_prompt=None):
        self.calls.append(len(audio))
        words = self._scripts.pop(0) if self._scripts else []
        for text, start, end in words:
            yield {"text": text, "start": start, "end": end}


def _audio(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def _make(monkeypatch, scripts, **cfg) -> tuple[Transcriber, FakeBackend]:
    backend = FakeBackend(scripts)
    monkeypatch.setattr(transcriber_mod, "build_backend", lambda **kw: backend)
    t = Transcriber(Queue(), Queue(), STTConfig(**cfg), stats=None, sample_rate=SR)
    return t, backend


def _drain(q: Queue) -> list[dict]:
    out = []
    while not q.empty():
        out.append(q.get())
    return out


def test_first_partial_commits_nothing(monkeypatch):
    # With no previous tail to agree against, the first partial confirms nothing;
    # all words become the pending tail for the next pass to corroborate.
    t, backend = _make(monkeypatch, [[("bonjour", 0.0, 0.4), ("le", 0.4, 0.6), ("monde", 0.6, 1.0)]])

    t._run_partial(_audio(1.0))

    assert t._committed_words == []
    assert t._prev_tail_texts == ["bonjour", "le", "monde"]
    assert t._committed_samples == 0
    assert backend.calls == [SR]  # decoded the whole buffer (nothing committed yet)


def test_second_partial_commits_agreed_prefix(monkeypatch):
    # Two passes agreeing on "bonjour le monde" → that prefix is committed and
    # the audio cut point advances past the last committed word.
    t, _ = _make(monkeypatch, [
        [("bonjour", 0.0, 0.4), ("le", 0.4, 0.6), ("monde", 0.6, 1.0)],
        [("bonjour", 0.0, 0.4), ("le", 0.4, 0.6), ("monde", 0.6, 1.0), ("est", 1.0, 1.4)],
    ])

    t._run_partial(_audio(1.0))
    t._run_partial(_audio(1.4))

    assert [w["text"] for w in t._committed_words] == ["bonjour", "le", "monde"]
    assert t._committed_samples == int(1.0 * SR)  # advanced past "monde" (end=1.0s)
    assert t._prev_tail_texts == ["est"]  # only the unconfirmed tail remains


def test_slice_offset_applied_to_committed_timestamps(monkeypatch):
    # After the cut point advances, later slices start mid-utterance. Words
    # committed from those slices must have their timestamps shifted back into
    # absolute (segment-relative) time, and the decoded slice must be shorter.
    t, backend = _make(monkeypatch, [
        [("bonjour", 0.0, 0.4), ("le", 0.4, 0.6), ("monde", 0.6, 1.0)],
        [("bonjour", 0.0, 0.4), ("le", 0.4, 0.6), ("monde", 0.6, 1.0), ("est", 1.0, 1.4)],
        # Slice now starts at 1.0s; timestamps are relative to the slice.
        [("est", 0.0, 0.4), ("là", 0.4, 0.8)],
    ])

    t._run_partial(_audio(1.0))
    t._run_partial(_audio(1.4))
    t._run_partial(_audio(1.8))

    assert [w["text"] for w in t._committed_words] == ["bonjour", "le", "monde", "est"]
    # "est" was decoded at slice-relative end 0.4s but lives at 1.4s absolute.
    assert t._committed_words[-1]["end"] == pytest.approx(1.4)
    assert t._committed_samples == int(1.4 * SR)  # 1.0s prior cut + 0.4s of "est"
    assert t._prev_tail_texts == ["là"]
    # Third pass decoded only the tail (1.8s - 1.0s cut = 0.8s), not the full buffer.
    assert backend.calls[-1] == int(0.8 * SR)


def test_agreement_ignores_case_and_punctuation(monkeypatch):
    # Whisper flips capitalization / attaches punctuation between passes; the
    # agreement check normalizes those away, but the committed word keeps its
    # raw display text.
    t, _ = _make(monkeypatch, [
        [("Bonjour", 0.0, 0.5)],
        [("bonjour,", 0.0, 0.5), ("le", 0.5, 0.9)],
    ])

    t._run_partial(_audio(0.5))
    t._run_partial(_audio(0.9))

    assert [w["text"] for w in t._committed_words] == ["bonjour,"]  # raw text preserved
    assert t._prev_tail_texts == ["le"]


def test_short_tail_is_skipped(monkeypatch):
    # A new tail shorter than the minimum (0.3s) isn't worth a decode pass.
    t, backend = _make(monkeypatch, [[("x", 0.0, 0.1)]])

    t._run_partial(_audio(0.2))  # 0.2s < 0.3s min tail

    assert backend.calls == []  # backend never invoked
    assert t._committed_words == []


def test_final_segment_postprocesses_and_resets(monkeypatch):
    # A final pass post-processes the full text, persists it, emits final_text,
    # and clears the per-segment streaming state for the next utterance.
    t, _ = _make(monkeypatch, [
        [("bonjour", 0.0, 0.4), ("le", 0.4, 0.6), ("monde", 0.6, 1.0)],
    ])
    saved: list[str] = []
    monkeypatch.setattr(t.history, "add", lambda text: saved.append(text))

    # Pretend we were mid-stream so we can prove the reset.
    t._committed_words = [{"text": "stale", "start": 0.0, "end": 0.1}]
    t._committed_samples = 1234
    t._prev_tail_texts = ["stale"]

    t._run_segment(_audio(1.0), is_final=True)

    events = _drain(t.display_queue)
    final = [e for e in events if e.get("type") == "final_text"]
    assert final and final[0]["text"] == "Bonjour le monde"
    assert saved == ["Bonjour le monde"]

    # Streaming state fully reset for the next utterance.
    assert t._committed_words == []
    assert t._committed_samples == 0
    assert t._prev_tail_texts == []


def test_final_segment_drops_hallucination(monkeypatch):
    # Known Whisper hallucination on the final pass → emit a drop instead of
    # leaving the streamed words on screen, and don't persist anything.
    t, _ = _make(monkeypatch, [
        [("Merci", 0.0, 0.4), ("d'avoir", 0.4, 0.8), ("regardé", 0.8, 1.2)],
    ])
    saved: list[str] = []
    monkeypatch.setattr(t.history, "add", lambda text: saved.append(text))

    t._run_segment(_audio(1.2), is_final=True)

    events = _drain(t.display_queue)
    final = [e for e in events if e.get("type") == "final_text"]
    assert final and final[0]["text"] == "" and final[0]["drop"] is True
    assert saved == []  # nothing persisted
