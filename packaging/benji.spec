# PyInstaller spec: cross-platform (macOS-first).
# Build: `pyinstaller packaging/benji.spec`
# macOS output: dist/Benji.app · Windows: dist/Benji/Benji.exe

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Single source of truth for the version: benji/__init__.py:__version__.
# The spec runs before `benji` is importable, so parse the file directly.
_init = Path(SPECPATH).parent / "benji" / "__init__.py"
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _init.read_text()).group(1)

hiddenimports = (
    collect_submodules("faster_whisper")
    + collect_submodules("ctranslate2")
    + collect_submodules("onnxruntime")
)

datas = collect_data_files("faster_whisper") + collect_data_files("onnxruntime")

a = Analysis(
    ["../run.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # torch is a declared dep of mlx-whisper but is only used by its PyTorch→MLX
    # *model conversion* path (mlx_whisper/torch_whisper.py). The shipped app runs
    # pre-converted MLX models, so the runtime transcription path never imports
    # torch — excluding it drops ~480 MB from the bundle. Real pyannote diarization
    # (which does need torch) is an opt-in `uv sync --extra diarization` dev path,
    # not bundled; the app falls back to the torch-free pitch tagger.
    excludes=["torch", "torchvision", "torchaudio", "tensorflow"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Benji",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Benji",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Benji.app",
        bundle_identifier="dev.benji.subtitles",
        info_plist={
            "NSMicrophoneUsageDescription": "Benji needs the microphone to transcribe speech in real time.",
            "LSUIElement": True,  # hide dock icon (menu-bar accessory app)
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "13.0",  # Ventura+ (Apple Silicon target)
        },
    )
