import platform
import psutil
from dataclasses import dataclass, field

IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


def _default_font() -> str:
    return ".AppleSystemUIFont" if IS_MACOS else "Segoe UI"


def _default_model_size() -> str:
    """Auto-select model size based on available hardware."""
    # Check for GPU
    has_gpu = False
    try:
        import torch
        has_gpu = torch.cuda.is_available()
    except ImportError:
        pass

    # Check RAM
    ram_gb = psutil.virtual_memory().total / (1024**3)

    # Decision tree - favor small for good balance of speed/quality
    if has_gpu:
        # With GPU, small is very fast
        return "small"
    else:
        # CPU-only: depends on RAM
        if ram_gb >= 8:
            return "small"
        else:
            return "base"  # Limited hardware


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 512  # Silero VAD ONNX requires 512 samples (32ms @ 16kHz)
    dtype: str = "float32"


@dataclass
class VADConfig:
    speech_threshold: float = 0.5
    silence_duration_ms: int = 300  # Optimized: -300ms latency for faster response
    min_speech_duration_ms: int = 250
    max_speech_duration_s: float = 15.0
    pre_speech_pad_ms: int = 300


@dataclass
class STTConfig:
    model_size: str = field(default_factory=_default_model_size)
    language: str | None = None  # None = auto-detect language
    beam_size: int = 2  # Optimized: -30% transcription time, minimal accuracy loss
    cpu_threads: int = field(default_factory=lambda: max(1, __import__('os').cpu_count() // 2))  # Dynamic based on CPU
    compute_type: str = "auto"


@dataclass
class UIConfig:
    font_family: str = field(default_factory=_default_font)
    font_size: int = 28
    bg_opacity: int = 160
    display_duration_ms: int = 5000
    fade_duration_ms: int = 1000
    window_width_ratio: float = 0.6
    bottom_margin: int = 80
    streaming_display: bool = True  # Display words progressively
