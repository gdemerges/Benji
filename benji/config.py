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
    partial_interval_ms: int = 400  # Re-transcribe partial audio every N ms (0 = disabled)
    # Each partial re-transcribes the whole growing buffer, so a fixed interval
    # makes total partial cost quadratic in segment length. Space partials out as
    # the buffer grows: effective interval = partial_interval_ms + growth_factor *
    # current_buffer_ms. The final pass re-transcribes everything anyway, so backing
    # off on long segments costs almost no perceived quality. 0.0 = fixed interval.
    partial_growth_factor: float = 0.5
    # Adaptive threshold: lifts speech_threshold above the noise floor in noisy rooms.
    # Effective threshold = max(speech_threshold, p95(non_speech_conf) + adaptive_margin).
    adaptive_threshold: bool = True
    adaptive_margin: float = 0.10
    adaptive_window_seconds: float = 5.0  # Rolling window for noise-floor estimation


@dataclass
class STTConfig:
    model_size: str = field(default_factory=_default_model_size)
    language: str | None = "fr"  # Force French by default
    beam_size: int = 5  # Final-pass beam size (quality)
    partial_beam_size: int = 1  # Partial-pass beam size (speed)
    context_words: int = 6  # Sliding context injected as initial_prompt
    cpu_threads: int = field(default_factory=lambda: max(1, os.cpu_count() // 2))
    compute_type: str = "auto"
    diarization: bool = False  # Enable speaker labeling
    # "pitch" (built-in F0 clustering, no extra deps) or "pyannote" (real embeddings,
    # requires `pip install pyannote.audio` and HF token via env HF_TOKEN).
    diarization_backend: str = "pitch"
    diarization_max_speakers: int = 4  # Cap for pyannote clustering (pitch is hard-capped at 2)
    llm_correction: bool = False  # Post-hoc grammar/punctuation fix via MLX-LM
    live_summary_interval_s: int = 0  # 0 = disabled; e.g. 300 = every 5 min
    # User glossary: proper nouns / domain terms injected as initial_prompt context
    # to bias Whisper toward correct spellings (e.g. ["Demergès", "Anthropic", "MLX"]).
    glossary: list[str] = field(default_factory=list)
    # Audio gain control before STT: peak-normalize quiet segments to this target.
    # 0.0 disables. Useful for low-gain microphones.
    agc_target_peak: float = 0.7
    agc_min_peak: float = 0.3  # Only boost when current peak is below this


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
