# Packaging & distribution — Benji (macOS)

Public download flow: **git tag `vX.Y.Z` → GitHub Actions builds/signs/notarizes →
DMG published to GitHub Releases**. Your website links to the latest asset:

```
https://github.com/<owner>/Benji/releases/latest/download/Benji.dmg
```

The version is single-sourced from `benji/__init__.py:__version__` (pyproject and
the PyInstaller spec both read it). Bump it there before tagging.

## Files

- `benji.spec` — PyInstaller build. Excludes `torch` (~480 MB): it's a declared
  mlx-whisper dep but only used by its PyTorch→MLX *conversion* path, never at
  runtime with pre-converted MLX models. Verified: the frozen app loads the STT
  model and runs without torch.
- `entitlements.plist` — hardened-runtime entitlements (mic + unsigned dylib
  loading + JIT) required to notarize a PyInstaller bundle.
- `make_dmg.sh` — `dist/Benji.app` → `dist/Benji.dmg` (styled via `create-dmg`,
  `hdiutil` fallback). When `SIGN_IDENTITY` is unset it also bundles
  `first-open.txt` in the DMG (see *Beta testing* below).
- `first-open.txt` — right-click → Open instructions, shipped **inside unsigned
  DMGs only**. A signed build must not carry it: telling users to bypass
  Gatekeeper when they don't have to teaches the wrong habit.
- `sign_and_notarize.sh` — codesign + notarize + staple. No-op (unsigned build)
  when `SIGN_IDENTITY` is unset.

## Build locally

```bash
uv run --with pyinstaller pyinstaller --noconfirm packaging/benji.spec
brew install create-dmg          # optional, nicer DMG window
./packaging/make_dmg.sh
open dist/Benji.dmg
```

First launch runs the onboarding assistant (`benji/onboarding.py`): microphone
permission, then the model download (~4 GB) with a progress bar. The weights go
to the Hugging Face cache (`~/.cache/huggingface/hub`), not into the bundle —
`~/.cache/benji` only holds the Silero VAD file.

## Signing & notarization (required for public download)

An **unsigned** DMG downloaded from a website is rejected by Gatekeeper
(*"Benji is damaged"*), because the browser sets the quarantine flag. To ship
publicly you need an **Apple Developer account (99 $/yr)** and a *Developer ID
Application* certificate.

The release workflow signs automatically once these repo secrets exist
(Settings → Secrets and variables → Actions):

| Secret | What |
|---|---|
| `APPLE_CERT_P12` | Developer ID Application cert exported as `.p12`, base64-encoded |
| `APPLE_CERT_PASSWORD` | password used when exporting the `.p12` |
| `SIGN_IDENTITY` | `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID` | Apple account email |
| `APPLE_TEAM_ID` | 10-char team id |
| `APPLE_APP_PASSWORD` | app-specific password (appleid.apple.com) |

Without the secrets the workflow still builds and publishes an **unsigned** DMG
(useful for testing the pipeline, and for beta testers — see below).

Export the cert to base64:

```bash
security find-identity -v -p codesigning        # find the identity name
# Export it from Keychain Access as Certificates.p12, then:
base64 -i Certificates.p12 | pbcopy             # paste into APPLE_CERT_P12
```

## Beta testing without an Apple account

The 99 $/yr account is the only thing standing between the current build and a
public download. It is **not** in the way of putting Benji in front of a handful
of testers, and their feedback is worth more than a signature right now.

An unsigned DMG installs fine as long as the tester opens it the right way:

```bash
uv run --with pyinstaller pyinstaller --noconfirm packaging/benji.spec
./packaging/make_dmg.sh          # SIGN_IDENTITY unset → bundles the note
```

Send the DMG directly (AirDrop, a link) and tell them: drag to Applications,
then **right-click → Open** the first time. `first-open.txt` ships inside the
DMG and says exactly that, including the `xattr -dr com.apple.quarantine`
fallback for the "Benji is damaged" case.

This is fine for a dozen people you can talk to. It is **not** a public download
path: an unsigned DMG behind a website link loses most visitors at the first
scary dialog.

## Cut a release

```bash
# bump benji/__init__.py __version__ first, commit, then:
git tag v0.1.0
git push origin v0.1.0
```

## Windows

Deferred. The spec stays cross-platform (`dist/Benji/Benji.exe`), but Windows
has no mlx — it would run on faster-whisper (CPU/CUDA), a separate code path to
validate, plus its own Authenticode signing. Not wired into CI yet.
