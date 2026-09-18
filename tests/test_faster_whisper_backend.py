"""Backend faster-whisper : moteur local hors Mac (Windows/Linux, sans MLX).

Contrairement à Parakeet, faster-whisper rend déjà des mots entiers et accepte
`language=` directement — pas de sous-mots à recoller, pas de relais hybride à
construire. La logique testable ici est donc réduite à l'extraction des mots et
au choix device/compute_type, toutes deux pures.
"""

from dataclasses import dataclass

import benji.stt.backend as backend_mod
from benji.stt.backend import (
    DEFAULT_FASTER_WHISPER_PARTIAL_MODEL,
    _faster_whisper_device,
    _words_from_segments,
    build_backend,
    build_final_backend,
)


def test_cpu_par_defaut_sans_cuda():
    assert _faster_whisper_device(has_cuda=False) == ("cpu", "int8")


def test_cuda_utilise_quand_detecte():
    assert _faster_whisper_device(has_cuda=True) == ("cuda", "float16")


@dataclass
class Word:
    word: str
    start: float | None = None
    end: float | None = None


@dataclass
class Segment:
    words: list


def test_les_mots_sont_deja_entiers_rien_a_recoller():
    """Contrairement à Parakeet : pas de sous-mots, `word_timestamps` suffit."""
    segments = [Segment([Word(" Bonjour", 0.0, 0.4), Word(" tous", 0.4, 0.7)])]

    words = list(_words_from_segments(segments))

    assert words == [
        {"text": "Bonjour", "start": 0.0, "end": 0.4},
        {"text": "tous", "start": 0.4, "end": 0.7},
    ]


def test_les_mots_vides_sont_ignores():
    segments = [Segment([Word("  ", 0.0, 0.1), Word(" ok", 0.1, 0.3)])]

    assert [w["text"] for w in _words_from_segments(segments)] == ["ok"]


def test_un_segment_sans_mots_ne_leve_pas():
    segments = [Segment(words=None)]

    assert list(_words_from_segments(segments)) == []


def test_liste_de_segments_vide():
    assert list(_words_from_segments([])) == []


# --- routage : absence de Parakeet/MLX (Windows/Linux) ---


def test_build_backend_retombe_sur_faster_whisper_sans_parakeet(monkeypatch):
    seen = {}

    def _fake(model_size):
        seen["model_size"] = model_size
        return type("B", (), {"name": "faster-whisper"})()

    monkeypatch.setattr(backend_mod, "_parakeet_available", lambda: False)
    monkeypatch.setattr(backend_mod, "FasterWhisperBackend", _fake)

    backend = build_backend()

    assert backend.name == "faster-whisper"
    assert seen["model_size"] == DEFAULT_FASTER_WHISPER_PARTIAL_MODEL


def test_build_final_backend_ignore_engine_sans_parakeet(monkeypatch):
    """Sans MLX, `language=` est passé directement : aucun relais hybride n'a
    de sens, donc `engine` (hybrid/whisper/parakeet) est ignoré."""
    seen = {}

    def _fake(model_size, language):
        seen["model_size"] = model_size
        seen["language"] = language
        return type("B", (), {"name": "faster-whisper"})()

    monkeypatch.setattr(backend_mod, "_parakeet_available", lambda: False)
    monkeypatch.setattr(backend_mod, "FasterWhisperBackend", _fake)

    backend = build_final_backend("hybrid", "small", "fr")

    assert backend.name == "faster-whisper"
    assert seen == {"model_size": "small", "language": "fr"}
