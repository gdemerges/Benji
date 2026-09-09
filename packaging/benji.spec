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

# faster-whisper / ctranslate2 left with Whisper when the CPU fallback was
# dropped (Apple Silicon only). mlx_whisper and parakeet_mlx are imported lazily
# from benji/stt/backend.py, so PyInstaller cannot see them by static analysis.
hiddenimports = (
    collect_submodules("onnxruntime")
    + collect_submodules("mlx_whisper")
    + collect_submodules("parakeet_mlx")
)

datas = collect_data_files("onnxruntime") + collect_data_files("mlx_whisper")

a = Analysis(
    ["../run.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # torch and librosa are declared deps of mlx-whisper / parakeet-mlx that the
    # runtime never reaches; both are now dropped from the resolution itself by
    # `[tool.uv] override-dependencies` in pyproject.toml, so they are normally
    # absent from the build venv already. The excludes stay as a belt: a dev who
    # ran `uv sync --extra diarization` before building would otherwise ship
    # ~430 MB of dead weight. librosa's single use — the mel filterbank — lives
    # in benji/stt/mel_filters.py; pyannote diarization is a dev-only extra and
    # is not bundled (the app falls back to the torch-free pitch tagger).
    #
    # Qt: benji imports exactly four modules (QtCore, QtGui, QtWidgets, QtSvg).
    # PySide6-Essentials still ships QML, Quick, PDF, Designer and a bundled
    # ffmpeg for QtMultimedia — measured at ~145 MB of frameworks nothing in the
    # app can reach. PyInstaller's PySide6 hook prunes by import graph, but not
    # the QML runtime or the translations, so they are named here explicitly.
    excludes=[
        "torch", "torchvision", "torchaudio", "tensorflow",
        "librosa", "sklearn", "scikit_learn", "soundfile", "pooch", "soxr",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
        "PySide6.QtQuickControls2", "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtDesigner", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtSql", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtTest",
    ],
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
