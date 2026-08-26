# Benji

**Your meetings never leave your Mac.**

Real-time speech-to-text subtitles that overlay on top of your screen, running entirely on your machine — microphone *and* the other participants' audio. No account, no API key, no upload: the transcript exists only on your disk. **Apple Silicon only**, via [MLX](https://github.com/ml-explore/mlx) and [Parakeet TDT](https://huggingface.co/mlx-community/parakeet-tdt-0.6b-v3).

Parakeet weights are licensed CC-BY-4.0 — credit: NVIDIA NeMo `parakeet-tdt-0.6b-v3`.

Every cloud-transcription tool ships your meetings to someone else's server. Benji does not have that option turned on, because it does not need a server to work.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20(Apple%20Silicon)%20%7C%20Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Streaming word-by-word display** — words appear progressively as you speak, stabilized with LocalAgreement-2 (a word is shown as confirmed once two successive partial passes agree on it)
- **Local transcription** — the model runs on-device; no API key, nothing leaves your machine
- **Guided first run** — microphone permission and model download (~4 GB) explained and shown with progress, instead of a frozen window
- **Built for short buffers** — Parakeet decodes only the audio it is given, where Whisper always pads to a 30 s window: ~58 ms per partial pass instead of ~680 ms, measured on an M4 Pro
- **Meeting capture** — mixes your microphone with the system audio of a video call, so both sides of the conversation get transcribed (requires a loopback driver, see below)
- **Apple Silicon GPU** via MLX
- **French by default** (`STTConfig.language = "fr"`) — Parakeet detects the language on its own and cannot be forced, so the final pass **re-reads its output** and only re-runs Whisper (which can be pinned to a language) on segments that drifted
- **User glossary** — proper nouns and in-house jargon are matched phonetically in the final text ("data dogue" → "Datadog"), edited in Preferences, never logged or sent anywhere
- **Voice Activity Detection** — Silero VAD (ONNX) with an adaptive threshold that lifts above the noise floor in noisy rooms
- **Two launch modes**:
  - **Overlay** — always-on-top, click-through subtitle bar (CLI launch)
  - **Window** — full app with a toolbar and Live / Résumés tabs (when launched as a macOS `.app`)
- **Optional speaker diarization** — built-in pitch-based A/B labeling (no extra deps), or real embeddings via `pyannote`
- **Optional LLM polish** — post-hoc grammar/punctuation correction via MLX-LM (Qwen2.5-1.5B-Instruct-4bit)
- **Live rolling summary** — periodic LLM summary of the running transcript
- **AGC** — peak-normalize quiet microphones before transcription
- **History** — every final utterance is saved with a timestamp, tagged with the meeting it belongs to, to `~/Library/Application Support/Benji/history.jsonl` (migrated automatically from the old `~/.cache/benji` location)
- **Searchable meetings** — accent-insensitive full-text search across every meeting, filtering both the list and the transcript
- **Self-naming meetings** — the local model proposes a title from the first sentences; a title you chose is never overwritten
- **Export** — txt / Markdown / SRT, plus **PDF** for the one copy you actually send to someone
- **Private by construction** — no telemetry, no account required, no network call in the default configuration

## Architecture

Three inter-thread queues keep the Qt UI thread unblocked:

```
Microphone   → AudioCapture   ─┐
System audio → SystemCapture ─┴→ AudioMixer → audio_queue → VAD (Silero ONNX) → transcribe_queue → Transcriber (Parakeet) → display_queue → DisplayBus → Overlay / Window
               sounddevice      mixer thread                 VAD thread                            STT thread (+ supervisor)              Qt main thread
```

When system audio is disabled, the mixer is never created and `AudioCapture` writes straight to `audio_queue`. When it is enabled, the mixer is driven by the microphone clock: for each mic chunk it consumes the same number of system samples, padding with silence if the system stream falls behind. The output rate is therefore exactly the mic's, and the VAD keeps receiving its fixed 512-sample chunks.

The STT thread runs under a supervisor that restarts it with exponential backoff if it ever dies. The model is loaded on the **main thread** behind a splash screen (~1.4 s): MLX binds a model to the thread that first evaluates its weights, so loading it on a short-lived background thread leaves it permanently unusable.

## Requirements

- Python 3.12
- macOS on Apple Silicon. Local transcription uses the GPU via MLX and has no CPU fallback — other platforms can only run the app against the (frozen) Benji cloud backend

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

Models are downloaded automatically on first run: Parakeet (~2.5 GB) and the Silero VAD ONNX (~2 MB). The MLX-LM model for correction/summary is only fetched if you enable those features.

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

Those only fire while Benji has focus. Pausing the mic also has a **global** shortcut,
which works from inside a full-screen video call — where you actually need it:

| Shortcut | Action |
|----------|--------|
| `⌃⌥⌘B` | Pause / resume the microphone (system-wide) |

A menu-bar (tray) icon also provides: show window, history, live summary, and quit.

### What to expect

- On first launch, a short assistant explains what Benji does, asks for microphone access, and downloads the model weights with a progress bar (~4 GB, once)
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

Everything stays on-device: the mixed audio goes straight to the local model.

## Configuration

All settings live in `benji/config.py` (no env vars, no config files). Some common knobs:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `STTConfig.stt_provider` | `"parakeet"` | `"parakeet"` (on this Mac) or `"remote"` (Benji cloud) |
| `STTConfig.model` | `parakeet-tdt-0.6b-v3` | Local model weights (partial passes) |
| `STTConfig.final_engine` | `"hybrid"` | Final pass: `"hybrid"` (Parakeet + Whisper rescue on language drift), `"whisper"` (always, slower, safest), `"parakeet"` (fastest, no language guarantee) |
| `STTConfig.glossary` | `True` | Apply `glossary.txt` to the final text |
| `STTConfig.auto_title` | `True` | Name a meeting from its first sentences via the local model |
| `STTConfig.language` | `"fr"` | Target language; set to `None` for auto-detect, or `"en"`, etc. |
| `STTConfig.diarization` | `False` | Enable speaker labels (`diarization_backend`: `"pitch"` or `"pyannote"`) |
| `STTConfig.llm_correction` | `False` | Grammar/punctuation polish via MLX-LM (Apple Silicon) |
| `STTConfig.live_summary_interval_s` | `0` | Rolling summary every N seconds (`0` = disabled) |
| `AudioConfig.system_audio` | `False` | Capture system audio (meetings) and mix it with the mic |
| `AudioConfig.system_audio_device` | `None` | Loopback device name substring; `None` = auto-detect |
| `AudioConfig.system_audio_gain` | `1.0` | Gain applied to the system stream before mixing |
| `VADConfig.silence_duration_ms` | `600` | Silence before a segment is flushed for final transcription |
| `VADConfig.adaptive_threshold` | `True` | Lift the speech threshold above the room's noise floor |
| `UIConfig.font_size` | `28` | Subtitle font size |
| `UIConfig.display_duration_ms` | `8000` | How long subtitles stay visible before fading |
| `UIConfig.bottom_margin` | `80` | Distance from the bottom of the screen (px) |
| `UIConfig.global_hotkey_pause` | `"Ctrl+Alt+Cmd+B"` | System-wide pause shortcut; `""` disables it |

### Where the weights live

Model weights are downloaded once into the Hugging Face cache
(`~/.cache/huggingface/hub`); `~/.cache/benji` only holds the Silero VAD file. None of
it is bundled in the app. Deleting either directory just triggers a re-download.

## How it works

1. **Audio capture** — `sounddevice` records 16 kHz mono into `audio_queue`; with meeting capture on, a second stream reads the loopback device and both are summed (with saturation, not normalization, so the adaptive VAD doesn't read level pumping as noise)
2. **VAD** — Silero VAD (ONNX) classifies 32 ms chunks; speech is accumulated and flushed to `transcribe_queue` after ~600 ms of silence (or sooner for long utterances)
3. **Transcription** — Parakeet decodes segments with word timestamps. Every partial pass re-decodes the whole buffer (~123 ms for 8 s), and LocalAgreement-2 commits the prefix two successive passes agree on, so text already on screen never rewrites itself
4. **Display** — confirmed words stream to the overlay/window via `display_queue`; the final pass replaces them with post-processed (and optionally LLM-corrected) text
5. **History & summaries** — finals are appended to `~/Library/Application Support/Benji/history.jsonl`, each tagged with its meeting id; generated summaries land in `~/Library/Application Support/Benji/summaries/`. Meetings themselves (title, start, end) live in `meetings.json` next to them

## Development

```bash
uv sync --dev
uv run pytest          # test suite (QT_QPA_PLATFORM=offscreen for headless runs)
uv run ruff check .    # lint
```

CI runs ruff and the test suite on macOS via GitHub Actions (`.github/workflows/ci.yml`). The suite mocks the Silero VAD and never loads a real model, so it stays fast and offline.

## License

MIT

## Credits

- [MLX](https://github.com/ml-explore/mlx) by Apple, and [parakeet-mlx](https://github.com/senstella/parakeet-mlx) by senstella
- [Silero VAD](https://github.com/snakers4/silero-vad) by Silero Team
- [NVIDIA NeMo `parakeet-tdt-0.6b-v3`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (CC-BY-4.0)
