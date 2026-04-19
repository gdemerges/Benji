# Packaging Benji

## macOS `.app`

```bash
pip install pyinstaller
pyinstaller packaging/benji.spec
open dist/Benji.app
```

On first launch macOS will ask for microphone permission (see `NSMicrophoneUsageDescription` in the spec).

To ship to other users, codesign and notarize:

```bash
codesign --deep --force --options runtime --sign "Developer ID Application: YOUR NAME" dist/Benji.app
xcrun notarytool submit dist/Benji.app --apple-id ... --team-id ... --wait
xcrun stapler staple dist/Benji.app
```

## Windows `.exe`

```powershell
pip install pyinstaller
pyinstaller packaging/benji.spec
.\dist\Benji\Benji.exe
```

Model downloads happen on first run into `~/.cache/benji/` — bundled binaries stay small.
