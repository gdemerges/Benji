import os
import platform
from dataclasses import dataclass, field

import psutil

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
    # "local" : Whisper sur le Mac (défaut). "remote" : transcription via le
    # backend Benji (cf. docs/api-contract.md ; coordonnées dans LLMConfig).
    stt_provider: str = "local"
    model_size: str = field(default_factory=_default_model_size)
    language: str | None = "fr"  # Force French by default
    beam_size: int = 5  # Final-pass beam size (quality)
    partial_beam_size: int = 1  # Partial-pass beam size (speed)
    context_words: int = 6  # Sliding context injected as initial_prompt
    cpu_threads: int = field(default_factory=lambda: max(1, os.cpu_count() // 2))
    compute_type: str = "auto"
    diarization: bool = True  # Enable speaker labeling
    # "pitch" (built-in F0 clustering, no extra deps) or "pyannote" (real embeddings,
    # requires `uv sync --extra diarization` and HF token via env HF_TOKEN).
    diarization_backend: str = "pyannote"
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
class LLMConfig:
    # Choix du moteur de résumé :
    #   "local"  — mlx-lm, 100 % sur le Mac (défaut)
    #   "cloud"  — API Claude en direct (clé sur le poste ; pour dev/test)
    #   "remote" — via le backend Benji (clé côté serveur ; chemin production)
    summary_provider: str = "local"
    # --- mode "cloud" (Claude direct) ---
    # Modèle Claude. Haiku 4.5 : rapide et peu coûteux, suffisant pour du résumé
    # (cf. docs/cloud-architecture.md). Sonnet/Opus pour plus de qualité.
    cloud_model: str = "claude-haiku-4-5"
    # None → l'SDK anthropic lit la clé depuis l'environnement (ANTHROPIC_API_KEY).
    # Ne jamais committer une clé en clair ici.
    anthropic_api_key: str | None = None
    cloud_max_tokens: int = 2048
    # --- mode "remote" (via backend) ---
    backend_url: str = "http://127.0.0.1:8000"
    backend_token: str | None = None          # jeton Bearer du backend
    summary_model_alias: str = "haiku"        # alias logique envoyé au backend


_LOCAL_HOSTS = {"localhost", "::1"}


def ensure_secure_backend_url(url: str) -> str:
    """Valide que l'URL backend est en HTTPS dès qu'elle sort du poste.

    Par ce canal transitent identifiants, jetons Bearer et transcriptions :
    en clair (http/ws), une URL de prod mal saisie exposerait tout. Seul le
    loopback (dev local) est exempté. Lève ValueError sinon — on échoue au
    démarrage plutôt que de fuiter silencieusement.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL backend invalide (schéma {parsed.scheme!r}) : {url}")
    host = parsed.hostname or ""
    is_local = host in _LOCAL_HOSTS or host.startswith("127.")
    if parsed.scheme == "http" and not is_local:
        raise ValueError(
            f"URL backend non locale en HTTP refusée (jetons et transcriptions "
            f"transiteraient en clair) : {url} — utilise https://"
        )
    return url


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
    # Multi-monitor: anchor the overlay on the screen under the cursor (the
    # user's active display), re-evaluated between utterances. False = primary.
    follow_active_screen: bool = True
    # Diagnostic only: verbose macOS window-state dump every 5s (off in prod).
    # Same info is available on demand via Ctrl+Shift+D.
    debug_macos_window: bool = False
