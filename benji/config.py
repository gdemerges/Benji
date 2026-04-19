import os
import platform
import psutil
from dataclasses import dataclass, field

IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


def _default_font() -> str:
    return ".AppleSystemUIFont" if IS_MACOS else "Segoe UI"


def _default_model_size() -> str:
    """Auto-select model size based on available hardware."""
    has_gpu = False
    try:
        import ctranslate2
        has_gpu = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass

    ram_gb = psutil.virtual_memory().total / (1024**3)

    if has_gpu:
        return "large-v3"
    if IS_MACOS and ram_gb >= 16:
        # Apple Silicon with MLX handles medium comfortably
        return "medium"
    if ram_gb >= 16:
        return "medium"
    if ram_gb >= 8:
        return "small"
    return "base"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 512  # Silero VAD ONNX requires 512 samples (32ms @ 16kHz)
    dtype: str = "float32"


@dataclass
class VADConfig:
    speech_threshold: float = 0.5
    silence_duration_ms: int = 600  # Wait longer before cutting, reduces fragmentation
    min_speech_duration_ms: int = 300  # Keep short interjections ("oui", "ok", "non")
    max_speech_duration_s: float = 8.0  # Force flush sooner for long utterances
    pre_speech_pad_ms: int = 200  # Less pre-context = smaller audio buffer = faster inference
    partial_interval_ms: int = 800  # Re-transcribe partial audio every N ms (0 = disabled)


@dataclass
class STTConfig:
    model_size: str = field(default_factory=_default_model_size)
    language: str | None = "fr"  # Force French by default
    beam_size: int = 5  # Final-pass beam size (quality)
    partial_beam_size: int = 1  # Partial-pass beam size (speed)
    context_words: int = 6  # Sliding context injected as initial_prompt
    cpu_threads: int = field(default_factory=lambda: max(1, os.cpu_count() // 2))
    compute_type: str = "auto"
    diarization: bool = False  # Pitch-based A/B speaker labeling
    llm_correction: bool = False  # Post-hoc grammar/punctuation fix via MLX-LM
    live_summary_interval_s: int = 0  # 0 = disabled; e.g. 300 = every 5 min


@dataclass
class UIConfig:
    font_family: str = field(default_factory=_default_font)
    font_size: int = 28
    bg_opacity: int = 160
    display_duration_ms: int = 8000
    fade_duration_ms: int = 1000
    window_width_ratio: float = 0.6
    bottom_margin: int = 80
    streaming_display: bool = True  # Display words progressively
