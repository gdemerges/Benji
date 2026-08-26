#!/usr/bin/env bash
# Package dist/Benji.app into a distributable dist/Benji.dmg.
#
#   ./packaging/make_dmg.sh
#
# Uses `create-dmg` (brew install create-dmg) for a styled window with an
# /Applications drop target; falls back to plain `hdiutil` when it is absent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/Benji.app"
DMG="$ROOT/dist/Benji.dmg"

[ -d "$APP" ] || { echo "error: $APP not found — run pyinstaller first" >&2; exit 1; }
rm -f "$DMG"

# Staging dir in all cases: an unsigned build ships a "first open" note next to
# the app. Without it a beta tester double-clicks, gets "Benji is damaged", and
# concludes the app is broken — the single most likely way to lose a tester.
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
cp -R "$APP" "$staging/"
extra_icon=()
if [ -z "${SIGN_IDENTITY:-}" ]; then
  cp "$ROOT/packaging/first-open.txt" "$staging/À LIRE — première ouverture.txt"
  extra_icon=(--icon "À LIRE — première ouverture.txt" 320 320)
  echo "unsigned build — bundling the first-open note" >&2
fi

if command -v create-dmg >/dev/null 2>&1; then
  create-dmg \
    --volname "Benji" \
    --window-pos 200 120 \
    --window-size 640 400 \
    --icon-size 128 \
    --icon "Benji.app" 160 200 \
    "${extra_icon[@]}" \
    --app-drop-link 480 200 \
    --no-internet-enable \
    "$DMG" "$staging"
else
  echo "create-dmg not found — falling back to hdiutil (no styling)" >&2
  ln -s /Applications "$staging/Applications"
  hdiutil create -volname "Benji" -srcfolder "$staging" -ov -format UDZO "$DMG"
fi

echo "✓ $DMG"
