import platform
from dataclasses import dataclass, field

IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


def _default_font() -> str:
    return ".AppleSystemUIFont" if IS_MACOS else "Segoe UI"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 512
    dtype: str = "float32"


@dataclass
class VADConfig:
    speech_threshold: float = 0.5
    silence_duration_ms: int = 600
    min_speech_duration_ms: int = 250
    max_speech_duration_s: float = 15.0
    pre_speech_pad_ms: int = 300


@dataclass
class STTConfig:
    model_size: str = "small"
    language: str | None = None  # None = auto-detect language
    beam_size: int = 3
    cpu_threads: int = 4
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
