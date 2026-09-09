"""Banc de filtres mel — le seul morceau de librosa dont Parakeet ait besoin.

`parakeet_mlx.audio.PreprocessArgs` appelle `librosa.filters.mel(...)` **une
fois**, au chargement du modèle, pour construire la matrice qui projette un
spectre linéaire sur l'échelle mel. C'est un appel, et il coûte librosa entier
dans l'arbre de dépendances : scikit-learn, soundfile, pooch, soxr, joblib,
msgpack — une quarantaine de mégaoctets embarqués dans le DMG pour une matrice
de 128×257 flottants qu'on sait calculer en trente lignes de numpy.

`install()` place donc un module `librosa` minimal dans `sys.modules` avant que
`parakeet_mlx` ne soit importé. Ce n'est pas un remplacement de librosa : c'est
la seule fonction que l'appelant utilise, et rien d'autre n'est exposé — un
`librosa.stft` sur ce module lèverait `AttributeError`, ce qui est le
comportement voulu si parakeet-mlx venait à en demander plus.

**Contrat numérique.** La sortie doit être *identique bit à bit* à celle de
librosa : c'est le pré-traitement du moteur de transcription, une dérive silen-
cieuse dégraderait la reconnaissance sans rien casser de visible. La convention
Slaney (`htk=False`, `norm="slaney"`) est celle que Parakeet demande, et
`tests/test_mel_filters.py` verrouille l'égalité contre une référence gelée.
"""

from __future__ import annotations

import sys
import types

import numpy as np

# Constantes de la conversion Hz→mel « Slaney » (Auditory Toolbox), reprises
# telles quelles de librosa : linéaire jusqu'à 1 kHz, logarithmique au-delà.
_F_SP = 200.0 / 3
_MIN_LOG_HZ = 1000.0
_MIN_LOG_MEL = _MIN_LOG_HZ / _F_SP
_LOGSTEP = np.log(6.4) / 27.0


def _hz_to_mel(freq):
    # `np.where` plutôt qu'une affectation masquée : l'appelant passe aussi bien
    # un scalaire (`fmin`) qu'un tableau, et un scalaire numpy n'est pas mutable.
    freq = np.asanyarray(freq, dtype=float)
    log_region = freq >= _MIN_LOG_HZ
    safe = np.where(log_region, freq, _MIN_LOG_HZ)  # évite log(0) sous le masque
    return np.where(
        log_region,
        _MIN_LOG_MEL + np.log(safe / _MIN_LOG_HZ) / _LOGSTEP,
        freq / _F_SP,
    )


def _mel_to_hz(mels):
    mels = np.asanyarray(mels, dtype=float)
    log_region = mels >= _MIN_LOG_MEL
    return np.where(
        log_region,
        _MIN_LOG_HZ * np.exp(_LOGSTEP * (mels - _MIN_LOG_MEL)),
        _F_SP * mels,
    )


def mel(
    *,
    sr: int,
    n_fft: int,
    n_mels: int = 128,
    fmin: float = 0.0,
    fmax: float | None = None,
    htk: bool = False,
    norm: str | None = "slaney",
    dtype=np.float32,
) -> np.ndarray:
    """Matrice `(n_mels, 1 + n_fft // 2)` projetant un spectre sur l'échelle mel.

    Seules les conventions utilisées par Parakeet sont implémentées ; `htk=True`
    et les normes autres que Slaney lèvent plutôt que de renvoyer un résultat
    approché — mieux vaut une panne franche qu'un pré-traitement faux.
    """
    if htk:
        raise NotImplementedError("échelle HTK non implémentée (Parakeet utilise Slaney)")
    if norm not in (None, "slaney"):
        raise NotImplementedError(f"norme {norm!r} non implémentée")
    if fmax is None:
        fmax = float(sr) / 2

    fftfreqs = np.fft.rfftfreq(n=n_fft, d=1.0 / sr)
    # n_mels + 2 bornes : chaque filtre triangulaire s'appuie sur ses voisins.
    mel_f = _mel_to_hz(np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2))

    fdiff = np.diff(mel_f)
    ramps = np.subtract.outer(mel_f, fftfreqs)

    lower = -ramps[:-2] / fdiff[:-1, np.newaxis]
    upper = ramps[2:] / fdiff[1:, np.newaxis]
    # L'arrondi vers `dtype` a lieu *avant* la normalisation, comme chez librosa :
    # normaliser en float64 puis arrondir donne un dernier bit différent sur la
    # moitié des coefficients. C'est inaudible, mais l'égalité exacte est ce qui
    # rend le test de non-régression utile.
    weights = np.zeros((n_mels, int(1 + n_fft // 2)), dtype=dtype)
    weights[:] = np.maximum(0, np.minimum(lower, upper))

    if norm == "slaney":
        # Aire unitaire par filtre, sinon les mels hauts — plus larges — pèsent
        # mécaniquement davantage que les bas.
        enorm = 2.0 / (mel_f[2 : n_mels + 2] - mel_f[:n_mels])
        weights *= enorm[:, np.newaxis]

    return weights


def install() -> None:
    """Enregistre le module `librosa` minimal, si le vrai n'est pas déjà chargé.

    Idempotent, et non destructif : si un librosa complet est installé (venv de
    développement, extra `diarization`), on le laisse gagner — le but est de
    pouvoir s'en passer, pas de l'interdire.
    """
    if "librosa" in sys.modules:
        return
    try:
        import librosa  # noqa: F401  (present pour de vrai : rien à faire)

        return
    except ImportError:
        pass

    stub, filters = _make_stub()
    sys.modules["librosa"] = stub
    sys.modules["librosa.filters"] = filters


def _make_stub():
    """Construit le couple `(librosa, librosa.filters)` — isolé pour les tests."""
    filters = types.ModuleType("librosa.filters")
    filters.mel = mel

    stub = types.ModuleType("librosa")
    stub.filters = filters
    stub.__all__ = ["filters"]
    # Marqueur pour le diagnostic : un `librosa.__benji_stub__` vrai dans un
    # rapport de bug explique pourquoi la pile d'appel n'a pas l'air normale.
    stub.__benji_stub__ = True
    return stub, filters
