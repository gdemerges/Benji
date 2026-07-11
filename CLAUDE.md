# Benji

macOS real-time transcription app. Pipeline: mic → VAD → STT → subtitle overlay.

## Rules

- Python 3.12, PyQt6, Apple Silicon (mlx). No mypy, no type stubs.
- Dependency management: **uv** (`pyproject.toml` is source of truth). `uv sync` to install, `uv run benji` to launch.
- Tunable config lives in `benji/config.py` (dataclasses), not config files. A few operational/secret settings are read from env vars instead: `BENJI_LAUNCH_MODE`, `BENJI_LOG_LEVEL`, `BENJI_VIBRANCY`, `HF_TOKEN`/`HUGGINGFACE_HUB_TOKEN` (diarization), `ANTHROPIC_API_KEY` (cloud summary).
- Three inter-thread queues: `audio_queue` → `transcribe_queue` → `display_queue`. Never block the Qt thread.
- `STTConfig.language` defaults to `"fr"`. Keep French in mind when touching STT logic.
- macOS: accessory policy must be set before `QApplication()` — see `benji/main.py:9`.
- Run: `uv run benji`. Tests: `uv run pytest`.

## Vault Obsidian

Le suivi de ce projet est documenté dans : `/Users/guillaumedemerges/Documents/Life/wiki/projects/Benji`

**Règle** : à la fin d'une session de travail significative (feature terminée, architecture changée, checklist publication avancée), mets à jour la note concernée avec les changements. Garde le format existant (frontmatter, sections, checkboxes cochées/décochées).

## Modules

- [benji/](benji/CLAUDE.md) — core package, entry point, config, history, stats
- [benji/audio/](benji/audio/CLAUDE.md) — mic capture + Silero VAD
- [benji/stt/](benji/stt/CLAUDE.md) — Whisper transcription, diarization, post-processing
- [benji/ui/](benji/ui/CLAUDE.md) — PyQt6 overlay, tray, history window, live summary
