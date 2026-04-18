"""Pluggable Whisper inference backends."""

from __future__ import annotations

import platform
from typing import Iterator, Protocol


class WhisperBackend(Protocol):
    name: str

    def transcribe(self, audio, language: str | None) -> Iterator[str]:
        """Yield transcribed words as they become available."""
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

    def __init__(self, model_size: str):
        import mlx_whisper  # noqa: F401  (fail fast if not installed)
        self._mlx = __import__("mlx_whisper")
        self.repo = _MLX_MODEL_MAP.get(model_size, f"mlx-community/whisper-{model_size}-mlx")
        print(f"[STT] MLX backend using '{self.repo}' (Apple Silicon GPU)")

    def transcribe(self, audio, language):
        result = self._mlx.transcribe(
            audio,
            path_or_hf_repo=self.repo,
            language=language,
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
                    yield text


class FasterWhisperBackend:
    name = "faster-whisper"

    def __init__(self, model_size: str, beam_size: int, cpu_threads: int):
        import ctranslate2
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model

        # Device detection via ctranslate2 (no torch dep)
        try:
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False

        if has_cuda:
            device, compute_type = "cuda", "float16"
        elif platform.system() == "Darwin":
            device, compute_type = "cpu", "int8"
        else:
            device, compute_type = "cpu", "auto"

        try:
            model_path = download_model(model_size, local_files_only=True)
        except Exception:
            model_path = None
            print(f"[STT] Model '{model_size}' not found locally. Downloading...")

        print(f"[STT] faster-whisper '{model_size}' on {device} ({compute_type})")
        self.model = WhisperModel(
            model_path or model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads if device == "cpu" else None,
        )
        self.beam_size = beam_size

    def transcribe(self, audio, language):
        segments, _ = self.model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            word_timestamps=True,
            condition_on_previous_text=False,
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
                        yield text


def build_backend(model_size: str, beam_size: int, cpu_threads: int) -> WhisperBackend:
    """Select best available backend. Prefer MLX on macOS, fall back to faster-whisper."""
    if platform.system() == "Darwin":
        try:
            return MLXWhisperBackend(model_size)
        except ImportError:
            print("[STT] mlx-whisper not installed, falling back to faster-whisper")
        except Exception as e:
            print(f"[STT] MLX backend failed ({e}), falling back to faster-whisper")
    return FasterWhisperBackend(model_size, beam_size, cpu_threads)
