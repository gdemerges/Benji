# Benji

Real-time speech-to-text subtitles that overlay on top of your screen, running entirely on your machine. Optimized for Apple Silicon (Whisper via [MLX](https://github.com/ml-explore/mlx)), with a [faster-whisper](https://github.com/SYSTRAN/faster-whisper) fallback elsewhere.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Streaming word-by-word display** — words appear progressively as you speak, stabilized with LocalAgreement-2 (a word is shown as confirmed once two successive partial passes agree on it)
- **Local transcription** — Whisper runs on-device; no API key, nothing leaves your machine
- **Apple Silicon GPU** via MLX-Whisper (fp16); automatic fallback to faster-whisper (CTranslate2, CUDA or CPU) on other setups
- **French by default** (`STTConfig.language = "fr"`), switchable to any Whisper language or auto-detect
- **Voice Activity Detection** — Silero VAD (ONNX) with an adaptive threshold that lifts above the noise floor in noisy rooms
- **Two launch modes**:
  - **Overlay** — always-on-top, click-through subtitle bar (CLI launch)
  - **Window** — full app with a toolbar and Live / Résumés tabs (when launched as a macOS `.app`)
- **Optional speaker diarization** — built-in pitch-based A/B labeling (no extra deps), or real embeddings via `pyannote`
- **Optional LLM polish** — post-hoc grammar/punctuation correction via MLX-LM (Qwen2.5-1.5B-Instruct-4bit)
- **Live rolling summary** — periodic LLM summary of the running transcript
- **Glossary & AGC** — bias Whisper toward your proper nouns, and peak-normalize quiet microphones
- **History** — every final utterance is saved with a timestamp to `~/.cache/benji/history.jsonl`
- **Privacy-friendly** — everything runs locally

## Architecture

Three inter-thread queues keep the Qt UI thread unblocked:

```
Microphone → AudioCapture → audio_queue → VAD (Silero ONNX) → transcribe_queue → Transcriber (Whisper) → display_queue → DisplayBus → Overlay / Window
              sounddevice                  VAD thread                            STT thread (+ supervisor)              Qt main thread
```

The STT thread runs under a supervisor that restarts it with exponential backoff if it ever dies. Whisper is loaded on a background thread behind a splash screen so the UI stays responsive at startup.

## Requirements

- Python 3.12
- macOS on Apple Silicon (recommended — uses the GPU via MLX), or Windows 10/11 / Linux (faster-whisper on CPU, or CUDA if available)

## Installation

Benji uses [uv](https://docs.astral.sh/uv/) for dependency and Python management. Install it once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then:

```bash
git clone https://github.com/YOUR_USERNAME/benji.git
cd benji
uv sync
```

`uv sync` installs Python 3.12 and all dependencies into `.venv/`. PortAudio ships inside the `sounddevice` wheel on macOS and Windows; if you hit a PortAudio error on macOS, install it with `brew install portaudio`.

Optional extras:

```bash
uv sync --extra diarization   # real speaker diarization via pyannote (pulls in PyTorch; needs HF_TOKEN on first run)
```

Models are downloaded automatically on first run: the Whisper model (size auto-selected, see below) and the Silero VAD ONNX (~2 MB). The MLX-LM model for correction/summary is only fetched if you enable those features.

## Usage

```bash
uv run benji
# or equivalently
uv run python run.py
```

This launches in **overlay** mode (click-through subtitle bar). Packaged as a macOS `.app`, Benji launches in **window** mode instead. You can force either with an environment variable:

```bash
BENJI_LAUNCH_MODE=window uv run benji
```

### Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+H` | Show/hide transcription history |
| `Ctrl+Shift+S` | Show/hide the live summary window |
| `Ctrl+Shift+D` | Dump current macOS window state (diagnostic) |

A menu-bar (tray) icon also provides: show window, history, live summary, and quit.

### What to expect

- macOS prompts for microphone access on first launch — allow it
- Subtitles appear at the bottom-center of the screen on a semi-transparent background
- Words appear progressively as you speak; the text fades out after a period of silence

## Configuration

All settings live in `benji/config.py` (no env vars, no config files). Some common knobs:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `STTConfig.model_size` | Auto-selected | Whisper model — see selection logic below |
| `STTConfig.language` | `"fr"` | Target language; set to `None` for auto-detect, or `"en"`, etc. |
| `STTConfig.diarization` | `False` | Enable speaker labels (`diarization_backend`: `"pitch"` or `"pyannote"`) |
| `STTConfig.llm_correction` | `False` | Grammar/punctuation polish via MLX-LM (Apple Silicon) |
| `STTConfig.live_summary_interval_s` | `0` | Rolling summary every N seconds (`0` = disabled) |
| `STTConfig.glossary` | `[]` | Proper nouns / domain terms biased into Whisper's prompt |
| `VADConfig.silence_duration_ms` | `600` | Silence before a segment is flushed for final transcription |
| `VADConfig.adaptive_threshold` | `True` | Lift the speech threshold above the room's noise floor |
| `UIConfig.font_size` | `28` | Subtitle font size |
| `UIConfig.display_duration_ms` | `8000` | How long subtitles stay visible before fading |
| `UIConfig.bottom_margin` | `80` | Distance from the bottom of the screen (px) |

### Model selection logic

`STTConfig.model_size` is auto-selected at startup from your hardware:

| Condition | Model |
|-----------|-------|
| CUDA GPU detected | `large-v3` |
| ≥ 16 GB RAM | `medium` |
| ≥ 8 GB RAM | `small` |
| otherwise | `base` |

All sizes are available (`tiny`, `base`, `small`, `medium`, `large-v3`). Override the auto-selection by setting `model_size` explicitly in `config.py`.

## How it works

1. **Audio capture** — `sounddevice` records 16 kHz mono into `audio_queue`
2. **VAD** — Silero VAD (ONNX) classifies 32 ms chunks; speech is accumulated and flushed to `transcribe_queue` after ~600 ms of silence (or sooner for long utterances)
3. **Transcription** — the active Whisper backend (MLX on Apple Silicon, else faster-whisper) decodes segments with word timestamps. Partial passes re-decode only the unconfirmed tail (bounded cost), and LocalAgreement-2 commits the prefix two passes agree on
4. **Display** — confirmed words stream to the overlay/window via `display_queue`; the final pass replaces them with post-processed (and optionally LLM-corrected) text
5. **History & summaries** — finals are appended to `~/.cache/benji/history.jsonl`; generated summaries land in `~/.cache/benji/summaries/`

## Development

```bash
uv sync --dev
uv run pytest          # test suite (QT_QPA_PLATFORM=offscreen for headless runs)
uv run ruff check .    # lint
```

CI runs ruff and the test suite on macOS via GitHub Actions (`.github/workflows/ci.yml`). The suite mocks the Silero VAD and never loads a real Whisper model, so it stays fast and offline.

## License

MIT

## Credits

- [MLX](https://github.com/ml-explore/mlx) and [mlx-whisper](https://github.com/ml-explore/mlx-examples) by Apple
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) by Systran
- [Silero VAD](https://github.com/snakers4/silero-vad) by Silero Team
- OpenAI Whisper model
