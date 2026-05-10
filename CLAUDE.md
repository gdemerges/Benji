# Benji

macOS real-time transcription app. Pipeline: mic → VAD → STT → subtitle overlay.

## Rules

- Python 3.12, PyQt6, Apple Silicon (mlx). No mypy, no type stubs.
- Dependency management: **uv** (`pyproject.toml` is source of truth). `uv sync` to install, `uv run benji` to launch.
- All config is in `benji/config.py` — no env vars, no config files.
- Three inter-thread queues: `audio_queue` → `transcribe_queue` → `display_queue`. Never block the Qt thread.
- `STTConfig.language` defaults to `"fr"`. Keep French in mind when touching STT logic.
- macOS: accessory policy must be set before `QApplication()` — see `benji/main.py:9`.
- Run: `uv run benji`. Tests: `uv run pytest`.

## Modules

- [benji/](benji/CLAUDE.md) — core package, entry point, config, history, stats
- [benji/audio/](benji/audio/CLAUDE.md) — mic capture + Silero VAD
- [benji/stt/](benji/stt/CLAUDE.md) — Whisper transcription, diarization, post-processing
- [benji/ui/](benji/ui/CLAUDE.md) — PyQt6 overlay, tray, history window, live summary
