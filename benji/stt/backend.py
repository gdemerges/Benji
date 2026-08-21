"""Moteurs de transcription : Parakeet pour le direct, Whisper pour l'archive.

Chaque passe a son moteur, parce qu'elles n'ont pas le même cahier des charges.

**Passes partielles → Parakeet TDT.** Le texte y est éphémère : il sera remplacé
par le final. Ce qui compte est la latence, et Parakeet ne paie que l'audio reçu
là où Whisper encode toujours une fenêtre paddée de 30 s — 58 ms contre ~680 ms
sur un tampon de 1,2 s, mesuré sur M4 Pro.

**Passe finale → Whisper, langue forcée.** Le texte y est définitif : il part
dans l'historique, les exports et les résumés. Parakeet fait de la détection
automatique sur 25 langues **sans aucun levier pour la forcer** (confirmé par la
fiche NVIDIA), et bascule en anglais sur des segments difficiles — au milieu
d'une réunion française, on obtient « the utility devient also the chef
d'orchestre ». Whisper accepte `language="fr"` : la dérive devient impossible.

Le repli CPU faster-whisper, lui, reste retiré : Benji est Apple Silicon
exclusivement.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"

_MLX_WHISPER_MODELS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


class STTBackend(Protocol):
    name: str

    def transcribe(self, audio) -> Iterator[dict]:
        """Rend des mots `{"text": str, "start": float, "end": float}`.

        `start`/`end` sont en secondes depuis le début du tampon ; l'une ou
        l'autre peut être None si le moteur n'a pas produit d'horodatage.
        """
        ...


def group_tokens_into_words(tokens) -> list[dict]:
    """Regroupe les sous-mots de Parakeet en mots horodatés.

    Le modèle rend des morceaux de mots (`" De"`, `" c"`, `"ô"`, `"té"`) : un
    token qui commence par une espace ouvre un mot, les suivants s'y collent. Le
    mot hérite du début du premier morceau et de la fin du dernier — c'est ce qui
    permet à l'accord entre passes et à l'export SRT de fonctionner.

    Fonction pure : elle prend n'importe quel objet exposant `.text`, `.start` et
    `.end`, donc elle se teste sans charger le modèle.
    """
    words: list[dict] = []
    for token in tokens:
        text = getattr(token, "text", "") or ""
        if not text.strip():
            continue
        start = getattr(token, "start", None)
        end = getattr(token, "end", None)
        if text.startswith(" ") or not words:
            words.append({"text": text.strip(), "start": start, "end": end})
        else:
            # Suite du mot courant : on étend sa borne de fin.
            words[-1]["text"] += text.strip()
            if end is not None:
                words[-1]["end"] = end
    return words


def words_from_result(result) -> list[dict]:
    """Mots horodatés d'un `AlignedResult`, phrase par phrase.

    Le regroupement est fait **par phrase** et non sur les tokens aplatis : le
    premier morceau d'une phrase ne porte pas toujours l'espace de tête, si bien
    qu'aplatir recollait la fin d'une phrase au début de la suivante
    (« Apple.Ça »).
    """
    words: list[dict] = []
    for sentence in getattr(result, "sentences", []) or []:
        words.extend(group_tokens_into_words(getattr(sentence, "tokens", []) or []))
    return words


class ParakeetBackend:
    """Parakeet TDT, alimenté **en mémoire**.

    L'API publique de `parakeet-mlx` ne transcrit que des chemins de fichiers. On
    passe donc par `get_logmel()` + `generate()` : Benji a déjà l'audio en numpy,
    et écrire les tampons d'une réunion dans un fichier temporaire serait une
    régression de confidentialité. Effet de bord heureux : pas de dépendance à
    ffmpeg.
    """

    name = "parakeet"

    def __init__(self, model_id: str = DEFAULT_MODEL):
        import mlx.core as mx
        from parakeet_mlx import from_pretrained

        self.model_id = model_id
        log.info("Chargement de Parakeet '%s'...", model_id)
        self.model = from_pretrained(model_id)
        self.preprocess = self.model.preprocessor_config

        # Matérialise les poids **sur ce thread**. MLX charge paresseusement et
        # lie les tableaux au stream du thread qui les évalue en premier ; sans
        # cet appel, la liaison n'a lieu qu'au premier décodage réel, et toute
        # inférence depuis un autre thread lève « There is no Stream(gpu, N) in
        # current thread ». Corollaire : ce constructeur doit être appelé depuis
        # un thread qui vit aussi longtemps que l'app (cf. `benji/app.py`).
        mx.eval(self.model.parameters())
        log.info("Parakeet prêt (16 kHz natif, décodage glouton)")

    def transcribe(self, audio) -> Iterator[dict]:
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel

        if audio is None or len(audio) == 0:
            return
        mel = get_logmel(mx.array(audio), self.preprocess)
        for result in self.model.generate(mel):
            yield from words_from_result(result)


class WhisperBackend:
    """Whisper via mlx-whisper, **langue figée à la construction**.

    La langue ne varie pas d'un segment à l'autre au sein d'une session : la
    fixer ici garde le protocole `transcribe(audio)` à un seul argument, commun
    aux deux moteurs.

    Ne sert que sur la passe finale, d'où la chaîne de repli en température : un
    décodage glouton raté est retenté plus chaud, ce qu'on ne peut pas se
    permettre sur une partielle mais qui vaut le coup sur du définitif.
    """

    name = "whisper"

    def __init__(self, model_size: str = "medium", language: str | None = "fr"):
        import mlx_whisper

        self._mlx = mlx_whisper
        self.repo = _MLX_WHISPER_MODELS.get(
            model_size, f"mlx-community/whisper-{model_size}-mlx"
        )
        self.language = language
        log.info("Chargement de Whisper '%s' (langue : %s)...", self.repo, language or "auto")

    def transcribe(self, audio) -> Iterator[dict]:
        if audio is None or len(audio) == 0:
            return
        result = self._mlx.transcribe(
            audio,
            path_or_hf_repo=self.repo,
            language=self.language,
            word_timestamps=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            temperature=(0.0, 0.2, 0.4),
            verbose=None,
        )
        for seg in result.get("segments", []):
            for w in seg.get("words", []) or []:
                text = (w.get("word") or "").strip()
                if text:
                    yield {"text": text, "start": w.get("start"), "end": w.get("end")}


def build_backend(model_id: str = DEFAULT_MODEL) -> STTBackend:
    """Moteur des passes partielles."""
    return ParakeetBackend(model_id)


def build_final_backend(engine: str, model_size: str, language: str | None) -> STTBackend:
    """Moteur de la passe finale — celui dont le texte est conservé.

    `engine="parakeet"` renvoie None : l'appelant réutilise alors le moteur des
    partielles, au prix de la garantie de langue.
    """
    if engine != "whisper":
        return None
    try:
        return WhisperBackend(model_size, language)
    except ImportError:
        log.warning(
            "mlx-whisper absent : la passe finale retombe sur Parakeet, dont la "
            "langue n'est pas garantie."
        )
        return None
