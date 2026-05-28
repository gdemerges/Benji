"""Pluggable Whisper inference backends."""

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


def build_backend(
    model_size: str,
    beam_size: int,
    cpu_threads: int,
    compute_type: str = "auto",
) -> WhisperBackend:
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
