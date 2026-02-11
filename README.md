# Benji

Real-time speech-to-text subtitles that overlay on top of your screen. Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running locally on your machine.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Streaming word-by-word display** -- words appear progressively as you speak (not all at once)
- **Real-time transcription** using OpenAI Whisper (local, no API key needed)
- **GPU acceleration** -- auto-detects CUDA/MPS for faster transcription
- **Auto language detection** -- supports 90+ languages, no manual selection needed
- **Always-on-top overlay** with transparent background and click-through
- **Voice Activity Detection** (Silero VAD ONNX) to avoid transcribing silence
- **Transcription history** -- saves all transcriptions with timestamps (`Ctrl+Shift+H` to view)
- **Low latency** (~200ms for first word, streaming thereafter)
- **Lightweight** -- 555MB dependencies (no PyTorch, uses ONNX for VAD)
- **Privacy-friendly** -- everything runs locally, no data leaves your machine

## Architecture

```
Microphone → AudioCapture → VAD (Silero ONNX) → Transcriber (Whisper) → Overlay (PyQt6)
              sounddevice      Thread 1              Thread 2              Main thread
                              (word timestamps)      (streaming words)
```

## Requirements

- Python 3.11+
- macOS or Windows 10/11
- Optional: NVIDIA GPU (CUDA) for 3-5x faster transcription

## Installation

### macOS

```bash
git clone https://github.com/YOUR_USERNAME/benji.git
cd benji

brew install portaudio

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows

```powershell
git clone https://github.com/YOUR_USERNAME/benji.git
cd benji

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> **Note**: On Windows, PortAudio is bundled with the `sounddevice` package -- no extra install needed.

The Whisper model (~500MB for `small`) and Silero VAD ONNX (~2MB) are downloaded automatically on first run.

## Usage

```bash
# macOS
source .venv/bin/activate
python run.py

# Windows
.venv\Scripts\activate
python run.py
```

### Keyboard Shortcuts

- **Ctrl+Shift+H** -- Show/hide transcription history

### What to expect

- macOS will prompt for microphone access on first launch -- allow it
- On Windows, ensure your microphone is enabled in Settings > Privacy > Microphone
- Subtitles appear at the bottom center of the screen with a semi-transparent background
- Words appear progressively as you speak (streaming mode)
- Text fades out after 5 seconds of silence

## Configuration

Edit `benji/config.py` to customize:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_size` | `small` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `language` | `None` | Target language (`None` = auto-detect, or `"en"`, `"fr"`, etc.) |
| `silence_duration_ms` | `600` | Silence needed before transcribing a segment |
| `font_size` | `28` | Subtitle font size |
| `display_duration_ms` | `5000` | How long subtitles stay visible |
| `bottom_margin` | `80` | Distance from bottom of screen (px) |
| `streaming_display` | `True` | Display words progressively (vs all at once) |

## How it works

1. **Audio Capture**: `sounddevice` records from the microphone at 16kHz mono
2. **VAD**: Silero VAD (ONNX) detects speech vs silence in real-time. Audio is accumulated during speech and flushed to the transcriber after 600ms of silence
3. **Transcription**: `faster-whisper` (CTranslate2 backend) transcribes complete speech segments with word-level timestamps
4. **Streaming Display**: Words are displayed progressively based on their timestamps, simulating real-time transcription
5. **History**: All transcriptions are saved to `~/.cache/benji/history.jsonl` with timestamps

## Performance

| Hardware | Model | Speed | Quality |
|----------|-------|-------|---------|
| M4 Pro (CPU) | `small` | ~90ms/3s audio | Very good |
| M4 Pro (CPU) | `medium` | ~240ms/3s audio | Excellent |
| RTX 4090 (CUDA) | `small` | ~30ms/3s audio | Very good |
| RTX 4090 (CUDA) | `large-v3` | ~120ms/3s audio | Best |

## Dependencies Breakdown

- **Total**: 555MB (vs 971MB with PyTorch)
- Core: `faster-whisper` (CTranslate2 + ONNX Runtime)
- VAD: Silero VAD ONNX (no PyTorch needed)
- UI: PyQt6
- Audio: sounddevice + numpy

## License

MIT

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) by Systran
- [Silero VAD](https://github.com/snakers4/silero-vad) by Silero Team
- OpenAI Whisper model
