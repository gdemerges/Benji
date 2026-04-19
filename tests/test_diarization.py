import numpy as np

from benji.stt.diarization import SpeakerTagger, _estimate_f0


def _sine(freq: float, duration_s: float = 1.0, sample_rate: int = 16000) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_estimate_f0_on_sine():
    audio = _sine(150.0)
    est = _estimate_f0(audio)
    assert est is not None
    assert abs(est - 150.0) < 10


def test_estimate_f0_on_silence():
    audio = np.zeros(16000, dtype=np.float32)
    assert _estimate_f0(audio) is None


def test_speaker_tagger_two_voices():
    tagger = SpeakerTagger(f0_gap_hz=30.0)
    low = _sine(120.0)
    high = _sine(220.0)

    assert tagger.label(low) == "A"
    assert tagger.label(low) == "A"
    assert tagger.label(high) == "B"
    assert tagger.label(low) == "A"


def test_speaker_tagger_same_voice_stable():
    tagger = SpeakerTagger(f0_gap_hz=40.0)
    a1 = _sine(150.0)
    a2 = _sine(160.0)  # slight drift, same speaker
    assert tagger.label(a1) == "A"
    assert tagger.label(a2) == "A"
