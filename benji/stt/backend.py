"""Moteur de transcription : Parakeet TDT sur Apple Silicon (MLX).

Benji a longtemps porté deux moteurs Whisper (mlx-whisper et faster-whisper).
Ils ont été retirés : sur le régime de l'app — des tampons de 1 à 8 s, re-décodés
souvent — Whisper encode toujours une fenêtre **paddée de 30 s** quelle que soit
la durée réelle du tampon, quand Parakeet ne paie que l'audio reçu. Mesuré sur
M4 Pro : 58 ms contre ~680 ms sur un tampon de 1,2 s, à mémoire équivalente.

Ce qui a disparu avec eux : `initial_prompt`, donc le glossaire et le contexte
glissant — Parakeet n'accepte aucun conditionnement par le texte. Et le repli CPU
faster-whisper, donc Benji est désormais Apple Silicon **exclusivement**.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"


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


def build_backend(model_id: str = DEFAULT_MODEL) -> STTBackend:
    return ParakeetBackend(model_id)
