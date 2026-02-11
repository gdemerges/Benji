# Benji

Real-time speech-to-text subtitles that overlay on top of your screen. Powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running locally on your machine.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![Platform](https://img.shields.io/badge/Platform-macOS-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Real-time transcription** using OpenAI Whisper (local, no API key needed)
- **Always-on-top overlay** with transparent background and click-through
- **Voice Activity Detection** (Silero VAD) to avoid transcribing silence
- **Low latency** (~750ms from end of speech to displayed subtitle)
- **French-first** but supports all Whisper languages
- **Privacy-friendly** -- everything runs locally, no data leaves your machine

## Architecture

```
Microphone → AudioCapture → VAD (Silero) → Transcriber (Whisper) → Overlay (PyQt6)
              sounddevice     Thread 1          Thread 2             Main thread
```

## Requirements

- Python 3.11+
- macOS (Windows support planned)
- [PortAudio](https://www.portaudio.com/) (`brew install portaudio`)

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/benji.git
cd benji

# Install system dependency
brew install portaudio

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The Whisper model (~500MB for `small`) and Silero VAD (~2MB) are downloaded automatically on first run.

## Usage

```bash
source .venv/bin/activate
python run.py
```

macOS will prompt for microphone access on first launch -- allow it.

Subtitles appear at the bottom center of the screen with a semi-transparent background. They fade out after 5 seconds of silence.

## Configuration

Edit `benji/config.py` to customize:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_size` | `small` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `language` | `fr` | Target language for transcription |
| `silence_duration_ms` | `600` | Silence needed before transcribing a segment |
| `font_size` | `28` | Subtitle font size |
| `display_duration_ms` | `5000` | How long subtitles stay visible |
| `bottom_margin` | `80` | Distance from bottom of screen (px) |

## How it works

1. **Audio Capture**: `sounddevice` records from the microphone at 16kHz mono
2. **VAD**: Silero VAD detects speech vs silence in real-time. Audio is accumulated during speech and flushed to the transcriber after 600ms of silence
3. **Transcription**: `faster-whisper` (CTranslate2 backend) transcribes complete speech segments
4. **Display**: PyQt6 renders subtitles in a frameless, transparent, click-through overlay window

## License

MIT
