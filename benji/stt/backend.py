"""Moteurs de transcription : Parakeet pour le direct, Whisper pour l'archive.

Chaque passe a son moteur, parce qu'elles n'ont pas le même cahier des charges.

**Passes partielles → Parakeet TDT.** Le texte y est éphémère : il sera remplacé
par le final. Ce qui compte est la latence, et Parakeet ne paie que l'audio reçu
là où Whisper encode toujours une fenêtre paddée de 30 s — 58 ms contre ~680 ms
sur un tampon de 1,2 s, mesuré sur M4 Pro.

**Passe finale → Parakeet, rattrapé par Whisper.** Le texte y est définitif : il
part dans l'historique, les exports et les résumés. Parakeet fait de la
détection automatique sur 25 langues **sans aucun levier pour la forcer**
(confirmé par la fiche NVIDIA), et bascule en anglais sur des segments
difficiles — au milieu d'une réunion française, on obtient « the utility devient
also the chef d'orchestre ». Whisper accepte `language="fr"` : la dérive devient
impossible, mais il coûte ~5× plus cher sur *tous* les segments.

D'où le moteur hybride (`HybridFinalBackend`, défaut) : décoder avec Parakeet,
puis **relire le texte produit** et ne relancer Whisper que sur les segments qui
ont visiblement dérivé (cf. `benji/stt/language.py`). La garantie est conservée
là où elle se joue ; le coût n'est payé que là où il sert.

Le repli CPU faster-whisper, lui, reste retiré : Benji est Apple Silicon
exclusivement.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from benji.stt.language import drifts_from

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
    # False = ne pas préchauffer au démarrage (le backend charge ses poids
    # paresseusement, et le préchauffage annulerait ce gain). Absent = True.
    eager_warmup: bool

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

    **Chargement paresseux.** `mlx_whisper.transcribe` charge et met en cache le
    modèle au premier appel ; construire ce backend ne coûte donc qu'un import,
    et les ~1,5 Go de poids ne sont payés que si un segment en a réellement
    besoin. En moteur hybride, une réunion française entière peut se dérouler
    sans jamais les charger.
    """

    name = "whisper"
    # Le préchauffage forcerait le chargement des poids au démarrage, ce que le
    # chargement paresseux existe précisément pour éviter.
    eager_warmup = False

    def __init__(self, model_size: str = "medium", language: str | None = "fr"):
        self._mlx = None
        self.repo = _MLX_WHISPER_MODELS.get(
            model_size, f"mlx-community/whisper-{model_size}-mlx"
        )
        self.language = language
        log.info("Whisper '%s' armé (langue : %s) — poids chargés au 1er usage",
                 self.repo, language or "auto")

    def _engine(self):
        if self._mlx is None:
            import mlx_whisper

            self._mlx = mlx_whisper
        return self._mlx

    def transcribe(self, audio) -> Iterator[dict]:
        if audio is None or len(audio) == 0:
            return
        result = self._engine().transcribe(
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


class HybridFinalBackend:
    """Parakeet d'abord, Whisper **seulement si la langue a dérivé**.

    Le compromis précédent était binaire : payer ~800 ms de Whisper sur *chaque*
    segment final pour se prémunir d'une dérive qui ne concerne qu'une poignée
    d'entre eux, ou garder Parakeet partout et laisser passer « the utility
    devient also the chef d'orchestre » dans l'historique.

    Ici l'arbitrage se fait **sur le texte produit** : on décode avec Parakeet
    (~150 ms), on regarde les mots-outils du résultat (cf. `stt/language.py`), et
    on ne relance Whisper que si le segment n'est visiblement pas dans la langue
    attendue — ou si Parakeet n'a rien rendu. Sur une réunion française propre,
    la passe lourde ne se déclenche presque jamais et ses poids ne sont même pas
    chargés.

    Le prix : la passe finale ne streame plus mot à mot, puisqu'il faut avoir lu
    tout le texte de Parakeet pour décider s'il est recevable. C'est sans effet
    visible — les mots de l'énoncé sont déjà à l'écran, posés par les passes
    partielles, et le final les remplace en bloc de toute façon.

    **Whisper tourne sur un thread dédié, créé une fois pour toutes.** MLX lie
    ses tableaux au stream du thread qui les évalue en premier : chargé depuis le
    thread STT, le modèle deviendrait inutilisable si le superviseur relançait ce
    thread après un incident (cf. `benji/app.py`). Un worker qui vit aussi
    longtemps que le backend supprime la question.
    """

    name = "hybrid"
    eager_warmup = False

    def __init__(self, fast: STTBackend, slow: STTBackend, language: str | None):
        self.fast = fast
        self.slow = slow
        self.language = language
        self._pool: ThreadPoolExecutor | None = None

    def _slow_pool(self) -> ThreadPoolExecutor:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="STT-whisper"
            )
        return self._pool

    def transcribe(self, audio) -> Iterator[dict]:
        words = list(self.fast.transcribe(audio))
        text = " ".join(w["text"] for w in words)
        if words and not drifts_from(text, self.language):
            yield from words
            return

        reason = "aucun mot rendu" if not words else "langue dérivée"
        log.info("Passe finale reprise par Whisper (%s)", reason)
        try:
            # `list(...)` DANS le worker : le générateur ne doit pas être
            # consommé depuis le thread appelant, sinon l'inférence repartirait
            # sur le mauvais stream MLX.
            rescued = self._slow_pool().submit(lambda: list(self.slow.transcribe(audio))).result()
        except Exception as e:
            log.warning("Repli Whisper impossible (%s) — on garde Parakeet", e)
            yield from words
            return
        yield from (rescued or words)

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None


def build_backend(model_id: str = DEFAULT_MODEL) -> STTBackend:
    """Moteur des passes partielles."""
    return ParakeetBackend(model_id)


def _whisper_available() -> bool:
    """Présence de mlx-whisper, sans en charger les poids.

    `WhisperBackend` n'importe plus le module à la construction (chargement
    paresseux) : sans cette sonde, l'absence du paquet ne se manifesterait qu'au
    premier segment, en pleine réunion.
    """
    return importlib.util.find_spec("mlx_whisper") is not None


def build_final_backend(
    engine: str, model_size: str, language: str | None, fast: STTBackend | None = None
) -> STTBackend:
    """Moteur de la passe finale — celui dont le texte est conservé.

    - `"hybrid"` (défaut) — Parakeet, relayé par Whisper sur les seuls segments
      qui ont dérivé. Exige `fast`, le moteur des partielles, qu'il réutilise.
    - `"whisper"` — Whisper sur tous les finals : la garantie maximale, au prix
      fort. Le repli si l'hybride déçoit en réunion.
    - `"parakeet"` — renvoie None : l'appelant réutilise le moteur des
      partielles, au prix de la garantie de langue.
    """
    if engine == "parakeet":
        return None
    if not _whisper_available():
        log.warning(
            "mlx-whisper absent : la passe finale retombe sur Parakeet, dont la "
            "langue n'est pas garantie."
        )
        return None
    whisper = WhisperBackend(model_size, language)
    if engine == "whisper":
        return whisper
    if fast is None:
        log.warning("Moteur hybride demandé sans moteur rapide — Whisper seul.")
        return whisper
    return HybridFinalBackend(fast, whisper, language)
