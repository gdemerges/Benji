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

if command -v create-dmg >/dev/null 2>&1; then
  create-dmg \
    --volname "Benji" \
    --window-pos 200 120 \
    --window-size 640 400 \
    --icon-size 128 \
    --icon "Benji.app" 160 200 \
    --app-drop-link 480 200 \
    --no-internet-enable \
    "$DMG" "$APP"
else
  echo "create-dmg not found — falling back to hdiutil (no styling)" >&2
  staging="$(mktemp -d)"
  cp -R "$APP" "$staging/"
  ln -s /Applications "$staging/Applications"
  hdiutil create -volname "Benji" -srcfolder "$staging" -ov -format UDZO "$DMG"
  rm -rf "$staging"
fi

echo "✓ $DMG"
