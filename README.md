# Benji

**Your meetings never leave your Mac.**

Real-time speech-to-text subtitles that overlay on top of your screen, running entirely on your machine — microphone *and* the other participants' audio. No account, no API key, no upload: the transcript exists only on your disk. Optimized for Apple Silicon via [MLX](https://github.com/ml-explore/mlx): [Parakeet TDT](https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v3) by default, Whisper on demand, with a [faster-whisper](https://github.com/SYSTRAN/faster-whisper) fallback elsewhere.

Parakeet weights are licensed CC-BY-4.0 — credit: NVIDIA NeMo `parakeet-tdt-0.6b-v3`.

Every cloud-transcription tool ships your meetings to someone else's server. Benji does not have that option turned on, because it does not need a server to work.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Streaming word-by-word display** — words appear progressively as you speak, stabilized with LocalAgreement-2 (a word is shown as confirmed once two successive partial passes agree on it)
- **Local transcription** — the model runs on-device; no API key, nothing leaves your machine
- **Two local engines** — Parakeet TDT by default (roughly 5× faster on the short buffers Benji works with), or Whisper if you need the glossary, which Parakeet cannot use
- **Meeting capture** — mixes your microphone with the system audio of a video call, so both sides of the conversation get transcribed (requires a loopback driver, see below)
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
- **History** — every final utterance is saved with a timestamp, tagged with the meeting it belongs to, to `~/Library/Application Support/Benji/history.jsonl` (migrated automatically from the old `~/.cache/benji` location)
- **Private by construction** — no telemetry, no account required, no network call in the default configuration

## Architecture

Three inter-thread queues keep the Qt UI thread unblocked:

```
Microphone   → AudioCapture   ─┐
System audio → SystemCapture ─┴→ AudioMixer → audio_queue → VAD (Silero ONNX) → transcribe_queue → Transcriber (Whisper) → display_queue → DisplayBus → Overlay / Window
               sounddevice      mixer thread                 VAD thread                            STT thread (+ supervisor)              Qt main thread
```

When system audio is disabled, the mixer is never created and `AudioCapture` writes straight to `audio_queue`. When it is enabled, the mixer is driven by the microphone clock: for each mic chunk it consumes the same number of system samples, padding with silence if the system stream falls behind. The output rate is therefore exactly the mic's, and the VAD keeps receiving its fixed 512-sample chunks.

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

Models are downloaded automatically on first run: the transcription model (Parakeet, ~1.2 GB — or a Whisper model, size auto-selected, if you switch engines) and the Silero VAD ONNX (~2 MB). The MLX-LM model for correction/summary is only fetched if you enable those features.

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

## Capturing a meeting (system audio)

By default Benji only hears your microphone — in a video call, that means only
**you** get transcribed. To capture the other participants, Benji reads the Mac's
audio output through a loopback driver.

macOS deliberately exposes no public API to record system output, so this step
requires a one-time setup:

1. **Install [BlackHole](https://existential.audio/blackhole/)** (free, open source).
2. Open **Audio MIDI Setup** → **+** → *Create Multi-Output Device*, and tick both
   your usual output (speakers/headphones) **and** BlackHole. Without this, the sound
   is routed to BlackHole only and you stop hearing the call.
3. Select that Multi-Output Device as your Mac's sound output.
4. In Benji: **Preferences → Audio système → Capter le son des visios**, then restart.

Benji auto-detects the loopback device; you can pin a specific one in the same panel.
The Preferences panel tells you which of the three states you are in, and pausing
the microphone also stops system capture — a paused mic never means "still recording".

Everything stays on-device: the mixed audio goes straight to the local Whisper model.

## Configuration

All settings live in `benji/config.py` (no env vars, no config files). Some common knobs:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `STTConfig.stt_provider` | `"parakeet"` | `"parakeet"` (default, fast, no glossary), `"local"` (Whisper), `"remote"` (Benji cloud) |
| `STTConfig.model_size` | Auto-selected | Whisper model — see selection logic below |
| `STTConfig.language` | `"fr"` | Target language; set to `None` for auto-detect, or `"en"`, etc. |
| `STTConfig.diarization` | `False` | Enable speaker labels (`diarization_backend`: `"pitch"` or `"pyannote"`) |
| `STTConfig.llm_correction` | `False` | Grammar/punctuation polish via MLX-LM (Apple Silicon) |
| `STTConfig.live_summary_interval_s` | `0` | Rolling summary every N seconds (`0` = disabled) |
| `STTConfig.glossary` | `[]` | Proper nouns / domain terms biased into Whisper's prompt |
| `AudioConfig.system_audio` | `False` | Capture system audio (meetings) and mix it with the mic |
| `AudioConfig.system_audio_device` | `None` | Loopback device name substring; `None` = auto-detect |
| `AudioConfig.system_audio_gain` | `1.0` | Gain applied to the system stream before mixing |
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

1. **Audio capture** — `sounddevice` records 16 kHz mono into `audio_queue`; with meeting capture on, a second stream reads the loopback device and both are summed (with saturation, not normalization, so the adaptive VAD doesn't read level pumping as noise)
2. **VAD** — Silero VAD (ONNX) classifies 32 ms chunks; speech is accumulated and flushed to `transcribe_queue` after ~600 ms of silence (or sooner for long utterances)
3. **Transcription** — the active Whisper backend (MLX on Apple Silicon, else faster-whisper) decodes segments with word timestamps. Partial passes re-decode only the unconfirmed tail (bounded cost), and LocalAgreement-2 commits the prefix two passes agree on
4. **Display** — confirmed words stream to the overlay/window via `display_queue`; the final pass replaces them with post-processed (and optionally LLM-corrected) text
5. **History & summaries** — finals are appended to `~/Library/Application Support/Benji/history.jsonl`, each tagged with its meeting id; generated summaries land in `~/Library/Application Support/Benji/summaries/`. Meetings themselves (title, start, end) live in `meetings.json` next to them

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
