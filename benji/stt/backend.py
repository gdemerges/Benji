"""Moteurs de transcription interchangeables : Whisper (MLX / faster-whisper) et Parakeet.

Tous exposent le même `WhisperBackend` : on leur donne un tampon audio, ils
rendent des mots horodatés. Ce qui les sépare tient en une phrase : **Whisper
encode toujours une fenêtre paddée de 30 s**, quelle que soit la durée réelle du
tampon, là où Parakeet ne paie que l'audio qu'on lui donne. Sur le régime de
Benji — des tampons de 1 à 8 s, re-décodés souvent — c'est un facteur 5 mesuré
(cf. `benji/stt/CLAUDE.md`).

En contrepartie Parakeet n'accepte **aucun conditionnement par le texte** : pas
d'`initial_prompt`, donc pas de glossaire ni de contexte glissant. Le choix se
fait dans les Préférences, section MOTEURS.
"""

from __future__ import annotations

import logging
import platform
from collections.abc import Iterator
from typing import Protocol

log = logging.getLogger(__name__)


class WhisperBackend(Protocol):
    name: str

    def transcribe(
        self,
        audio,
        language: str | None,
        beam_size: int | None = None,
        initial_prompt: str | None = None,
    ) -> Iterator[dict]:
        """Yield word dicts {"text": str, "start": float, "end": float} as they become available.

        start/end are seconds relative to the start of the audio buffer; either may be None
        if the backend did not produce timestamps for that word.
        """
        ...


_MLX_MODEL_MAP = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


class MLXWhisperBackend:
    name = "mlx"

    def __init__(self, model_size: str, default_beam_size: int = 5):
        import mlx_whisper  # noqa: F401  (fail fast if not installed)
        self._mlx = __import__("mlx_whisper")
        self.repo = _MLX_MODEL_MAP.get(model_size, f"mlx-community/whisper-{model_size}-mlx")
        self.default_beam_size = default_beam_size
        log.info("MLX backend using '%s' (Apple Silicon GPU)", self.repo)

    def transcribe(self, audio, language, beam_size=None, initial_prompt=None):
        # mlx-whisper has no beam search (GreedyDecoder only — passing beam_size
        # raises NotImplementedError). The available speed/quality lever is the
        # temperature-fallback chain: a partial pass (beam_size<=1) decodes once
        # at T=0 for minimum latency; a final pass keeps the fallback chain so a
        # bad greedy decode retries at higher temperature.
        effective_beam = beam_size or self.default_beam_size
        temperature = (0.0,) if effective_beam <= 1 else (0.0, 0.2, 0.4)
        result = self._mlx.transcribe(
            audio,
            path_or_hf_repo=self.repo,
            language=language,
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            temperature=temperature,
            verbose=None,
        )
        for seg in result.get("segments", []):
            for w in seg.get("words", []) or []:
                text = (w.get("word") or "").strip()
                if text:
                    yield {"text": text, "start": w.get("start"), "end": w.get("end")}


# Apple Silicon faster-whisper compute type per model size.
# int8 is fastest/lightest on CPU; int8_float32 keeps activations in fp32 for slightly
# better accuracy on smaller models where the speed cost is negligible.
_DARWIN_COMPUTE_TYPE_BY_MODEL = {
    "tiny": "int8_float32",
    "base": "int8_float32",
    "small": "int8_float32",
    "medium": "int8",
    "large-v3": "int8",
    "large-v3-turbo": "int8",
}


class FasterWhisperBackend:
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str,
        default_beam_size: int,
        cpu_threads: int,
        compute_type: str = "auto",
    ):
        import ctranslate2
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model

        try:
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False

        if has_cuda:
            device = "cuda"
            resolved_ct = compute_type if compute_type != "auto" else "float16"
        elif platform.system() == "Darwin":
            device = "cpu"
            resolved_ct = (
                compute_type
                if compute_type != "auto"
                else _DARWIN_COMPUTE_TYPE_BY_MODEL.get(model_size, "int8")
            )
        else:
            device = "cpu"
            resolved_ct = compute_type  # "auto" lets ctranslate2 pick

        try:
            model_path = download_model(model_size, local_files_only=True)
        except Exception:
            model_path = None
            log.info("Model '%s' not found locally. Downloading...", model_size)

        log.info("faster-whisper '%s' on %s (%s)", model_size, device, resolved_ct)
        self.model = WhisperModel(
            model_path or model_size,
            device=device,
            compute_type=resolved_ct,
            cpu_threads=cpu_threads if device == "cpu" else None,
        )
        self.default_beam_size = default_beam_size

    def transcribe(self, audio, language, beam_size=None, initial_prompt=None):
        segments, _ = self.model.transcribe(
            audio,
            language=language,
            beam_size=beam_size or self.default_beam_size,
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            temperature=[0.0, 0.2, 0.4],
        )
        for segment in segments:
            if getattr(segment, "words", None):
                for w in segment.words:
                    text = (w.word or "").strip()
                    if text:
                        yield {
                            "text": text,
                            "start": getattr(w, "start", None),
                            "end": getattr(w, "end", None),
                        }


_PARAKEET_DEFAULT_REPO = "mlx-community/parakeet-tdt-0.6b-v3"


def group_tokens_into_words(tokens) -> list[dict]:
    """Regroupe les sous-mots de Parakeet en mots horodatés.

    Le modèle rend des morceaux de mots (`" De"`, `" c"`, `"ô"`, `"té"`) : un
    token qui commence par une espace ouvre un mot, les suivants s'y collent. Le
    mot hérite du début du premier morceau et de la fin du dernier — c'est ce qui
    permet au découpage incrémental et à l'export SRT de continuer à fonctionner.

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
    """Parakeet TDT sur Apple Silicon (MLX), alimenté **en mémoire**.

    L'API publique de `parakeet-mlx` ne transcrit que des chemins de fichiers.
    On passe donc par `get_logmel()` + `generate()` : Benji a déjà l'audio en
    numpy, et écrire les tampons d'une réunion dans un fichier temporaire serait
    une régression de confidentialité — la règle du projet est que rien de ce qui
    est dit ne se retrouve sur le disque en dehors de l'historique chiffré par
    les permissions. Effet de bord heureux : pas de dépendance à ffmpeg.
    """

    name = "parakeet"

    def __init__(self, model_id: str = _PARAKEET_DEFAULT_REPO):
        import mlx.core as mx
        from parakeet_mlx import from_pretrained  # noqa: F401 (échoue vite si absent)

        self.model_id = model_id
        log.info("Chargement de Parakeet '%s'...", model_id)
        self.model = from_pretrained(model_id)
        self.preprocess = self.model.preprocessor_config
        self._warned_prompt = False

        # Matérialise les poids **sur ce thread**. MLX charge paresseusement et
        # lie les tableaux au stream du thread qui les évalue en premier ; sans
        # cet appel, la liaison n'a lieu qu'au premier décodage réel, et toute
        # inférence depuis un autre thread lève « There is no Stream(gpu, N) in
        # current thread ». On ne peut pas s'en remettre à `warmup()` : il
        # préchauffe sur du silence, dont Parakeet ne décode aucun token — le
        # décodeur ne tourne donc jamais et rien n'est lié.
        # Corollaire : ce constructeur doit être appelé depuis un thread qui vit
        # aussi longtemps que l'app (cf. `BenjiApplication.loads_model_inline`).
        mx.eval(self.model.parameters())
        log.info("Parakeet prêt (16 kHz natif, décodage glouton)")

    def transcribe(self, audio, language, beam_size=None, initial_prompt=None):
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel

        if initial_prompt and not self._warned_prompt:
            # Une fois par session : sinon le message part à chaque segment.
            log.info(
                "Parakeet ignore initial_prompt : le glossaire et le contexte "
                "glissant sont sans effet sur ce moteur."
            )
            self._warned_prompt = True

        if audio is None or len(audio) == 0:
            return
        mel = get_logmel(mx.array(audio), self.preprocess)
        for result in self.model.generate(mel):
            yield from words_from_result(result)


def build_backend(
    model_size: str,
    beam_size: int,
    cpu_threads: int,
    compute_type: str = "auto",
    engine: str = "whisper",
    parakeet_model: str = _PARAKEET_DEFAULT_REPO,
) -> WhisperBackend:
    if engine == "parakeet":
        try:
            return ParakeetBackend(parakeet_model)
        except ImportError:
            log.warning(
                "parakeet-mlx absent (uv sync --extra parakeet) — repli sur Whisper"
            )
        except Exception as e:
            log.warning("Parakeet indisponible (%s) — repli sur Whisper", e)

    if platform.system() == "Darwin":
        try:
            # MLX-Whisper is fp16 on Apple GPU — `compute_type` is a no-op here,
            # logged for transparency.
            log.debug("compute_type=%s ignored by MLX backend (MLX is fp16)", compute_type)
            return MLXWhisperBackend(model_size, default_beam_size=beam_size)
        except ImportError:
            log.warning("mlx-whisper not installed, falling back to faster-whisper")
        except Exception as e:
            log.warning("MLX backend failed (%s), falling back to faster-whisper", e)
    return FasterWhisperBackend(model_size, beam_size, cpu_threads, compute_type=compute_type)
