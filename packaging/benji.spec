# PyInstaller spec: cross-platform.
# Build: `pyinstaller packaging/benji.spec`
# macOS output: dist/Benji.app · Windows: dist/Benji/Benji.exe

import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

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
            "LSUIElement": True,  # hide dock icon
            "CFBundleShortVersionString": "0.1.0",
        },
    )
