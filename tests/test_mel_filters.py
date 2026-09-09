"""Le banc de filtres mel maison doit rester *identique* à celui de librosa.

librosa n'est plus installé (cf. `override-dependencies` dans `pyproject.toml`) :
la référence est gelée dans `tests/data/mel_reference.npz`, produite avec
librosa 1.0.0. Si ce test casse, le pré-traitement de Parakeet a changé — donc
la qualité de transcription — sans que rien d'autre ne le signale.
"""

import builtins
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from benji.stt import mel_filters

REFERENCE = Path(__file__).parent / "data" / "mel_reference.npz"


@pytest.fixture(scope="module")
def reference():
    data = np.load(REFERENCE)
    return json.loads(str(data["meta"])), data


def test_matches_frozen_librosa_reference(reference):
    meta, data = reference
    for i, case in enumerate(meta):
        expected = data[f"case{i}"]
        actual = mel_filters.mel(**case)
        assert actual.dtype == expected.dtype, case
        assert actual.shape == expected.shape, case
        # Égalité exacte, pas `allclose` : l'ordre des opérations est calqué sur
        # celui de librosa précisément pour que ce soit tenable.
        assert np.array_equal(actual, expected), case


def test_slaney_filters_have_unit_area():
    """Chaque filtre normalisé intègre à ~1 : la propriété que `norm` garantit.

    Vérifiée sur une configuration *résolue* (n_fft 2048, 40 mels). Avec les
    réglages de Parakeet — n_fft 512, 128 mels — les filtres graves sont plus
    étroits qu'un bin FFT et la somme discrète ne vaut plus l'intégrale : c'est
    un artefact d'échantillonnage présent à l'identique chez librosa, pas un
    écart d'implémentation. C'est le test d'égalité ci-dessus qui couvre ce cas.
    """
    sr, n_fft = 16000, 2048
    weights = mel_filters.mel(sr=sr, n_fft=n_fft, n_mels=40, fmax=sr / 2)
    areas = weights.sum(axis=1) * (sr / n_fft)
    assert np.allclose(areas, 1.0, rtol=0.01)


def test_unsupported_conventions_raise():
    """Une panne franche plutôt qu'un pré-traitement silencieusement faux."""
    with pytest.raises(NotImplementedError):
        mel_filters.mel(sr=16000, n_fft=512, htk=True)
    with pytest.raises(NotImplementedError):
        mel_filters.mel(sr=16000, n_fft=512, norm="inf")


def test_stub_exposes_mel_and_nothing_else():
    stub, filters = mel_filters._make_stub()
    assert filters.mel is mel_filters.mel
    assert stub.__benji_stub__ is True
    # Si parakeet-mlx se mettait à demander autre chose, on veut un
    # `AttributeError` bruyant plutôt qu'un silence.
    for absent in ("stft", "load", "resample", "feature"):
        assert not hasattr(stub, absent)


def test_install_is_idempotent_and_never_evicts_a_real_librosa(monkeypatch):
    sentinel = types.ModuleType("librosa")
    monkeypatch.setitem(sys.modules, "librosa", sentinel)
    mel_filters.install()
    mel_filters.install()
    assert sys.modules["librosa"] is sentinel


def test_install_registers_the_stub_when_librosa_is_absent(monkeypatch):
    monkeypatch.delitem(sys.modules, "librosa", raising=False)
    monkeypatch.delitem(sys.modules, "librosa.filters", raising=False)

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "librosa" or name.startswith("librosa."):
            raise ImportError("librosa is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    mel_filters.install()
    assert sys.modules["librosa"].__benji_stub__ is True
    assert sys.modules["librosa"].filters.mel is mel_filters.mel


def test_parakeet_can_build_its_filterbank_without_librosa(monkeypatch):
    """Le vrai contrat : `PreprocessArgs` doit se construire avec le stub seul."""
    parakeet_audio = pytest.importorskip("parakeet_mlx.audio")
    args = parakeet_audio.PreprocessArgs(
        sample_rate=16000,
        normalize="per_feature",
        window_size=0.025,
        window_stride=0.01,
        window="hann",
        features=128,
        n_fft=512,
        dither=0.0,
    )
    assert args._filterbanks.shape == (128, 257)
