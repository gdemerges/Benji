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
    chunk_size: int = 512  # Silero VAD ONNX requires 512 samples (32ms @ 16kHz)
    dtype: str = "float32"
    # Capture de l'audio système (son des autres participants en visio), mixé
    # avec le micro avant le VAD. Nécessite un pilote de boucle installé par
    # l'utilisateur — cf. benji/audio/loopback.py. Désactivé => chemin micro
    # seul strictement inchangé.
    system_audio: bool = False
    # Sous-chaîne du nom du périphérique de boucle. None = auto-détection.
    system_audio_device: str | None = None
    # Gain appliqué au flux système avant sommation. 1.0 convient quand la
    # sortie est à un niveau normal ; baisser si la visio sature le mixage.
    system_audio_gain: float = 1.0


@dataclass
class VADConfig:
    speech_threshold: float = 0.5
    silence_duration_ms: int = 600  # Wait longer before cutting, reduces fragmentation
    min_speech_duration_ms: int = 300  # Keep short interjections ("oui", "ok", "non")
    max_speech_duration_s: float = 8.0  # Force flush sooner for long utterances
    pre_speech_pad_ms: int = 200  # Less pre-context = smaller audio buffer = faster inference
    partial_interval_ms: int = 400  # Re-transcribe partial audio every N ms (0 = disabled)
    # Espacement progressif des passes partielles à mesure que le tampon grandit :
    # intervalle effectif = partial_interval_ms + growth_factor * durée_tampon_ms.
    # Hérité de Whisper, dont une passe sur 8 s coûtait ~800 ms : sans ce frein, le
    # coût total devenait intenable. Parakeet décode le même tampon en ~150 ms, soit
    # ~38 % d'occupation à cadence fixe — le frein ne protège plus rien et rendait le
    # direct poussif (jusqu'à 4,4 s entre deux rafraîchissements en fin d'énoncé).
    # Remis à 0 = cadence fixe. Le mécanisme reste là si un moteur plus lourd revient.
    partial_growth_factor: float = 0.0
    # Adaptive threshold: lifts speech_threshold above the noise floor in noisy rooms.
    # Effective threshold = max(speech_threshold, p95(non_speech_conf) + adaptive_margin).
    adaptive_threshold: bool = True
    adaptive_margin: float = 0.10
    adaptive_window_seconds: float = 5.0  # Rolling window for noise-floor estimation


@dataclass
class STTConfig:
    # "parakeet" : Parakeet TDT sur le Mac (défaut). "remote" : transcription via
    # le backend Benji (cf. docs/api-contract.md ; coordonnées dans LLMConfig).
    stt_provider: str = "parakeet"
    # Poids du moteur des **passes partielles** (le texte vivant, éphémère).
    model: str = "mlx-community/parakeet-tdt-0.6b-v3"
    # Moteur de la **passe finale** — celle dont le texte part dans l'historique,
    # les exports et les résumés.
    #   "whisper"  — langue forcée (défaut). Parakeet fait de la détection auto
    #                sur 25 langues sans aucun levier pour la contraindre, et
    #                bascule en anglais sur des segments difficiles : au milieu
    #                d'une réunion française on récupère « the utility devient
    #                also the chef d'orchestre ». Whisper rend ça impossible.
    #   "parakeet" — réutilise le moteur des partielles : ~5× plus rapide sur le
    #                final, mais la langue n'est plus garantie.
    final_engine: str = "whisper"
    final_model_size: str = "medium"
    # Langue imposée à la passe finale, et langue du post-traitement (nombres,
    # interjections) et de la correction LLM. None = détection automatique.
    language: str | None = "fr"
    diarization: bool = True  # Enable speaker labeling
    # "pitch" (built-in F0 clustering, no extra deps) or "pyannote" (real embeddings,
    # requires `uv sync --extra diarization` and HF token via env HF_TOKEN).
    diarization_backend: str = "pyannote"
    diarization_max_speakers: int = 4  # Cap for pyannote clustering (pitch is hard-capped at 2)
    llm_correction: bool = False  # Post-hoc grammar/punctuation fix via MLX-LM
    live_summary_interval_s: int = 0  # 0 = disabled; e.g. 300 = every 5 min
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
