#!/usr/bin/env bash
# Codesign (hardened runtime) + notarize + staple.
#
#   ./packaging/sign_and_notarize.sh
#
# Reads the following from the environment (set them as CI secrets):
#   SIGN_IDENTITY        "Developer ID Application: Your Name (TEAMID)"
#   APPLE_ID             Apple account email used for notarization
#   APPLE_TEAM_ID        10-char team id
#   APPLE_APP_PASSWORD   app-specific password (appleid.apple.com)
#
# If SIGN_IDENTITY is unset the script is a no-op success: the build still
# produces an *unsigned* .app/.dmg (fine for local smoke-testing, NOT for
# public download — Gatekeeper will reject it). Wire the secrets once the
# Apple Developer account is ready and this path activates automatically.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/Benji.app"
DMG="$ROOT/dist/Benji.dmg"
ENTITLEMENTS="$ROOT/packaging/entitlements.plist"

if [ -z "${SIGN_IDENTITY:-}" ]; then
  echo "⚠  SIGN_IDENTITY unset — skipping signing/notarization (unsigned build)." >&2
  exit 0
fi

echo "→ Signing $APP"
# Sign nested code inside-out, then the bundle, with the hardened runtime.
codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$SIGN_IDENTITY" "$APP"
codesign --verify --strict --verbose=2 "$APP"

echo "→ Building DMG"
"$ROOT/packaging/make_dmg.sh"

echo "→ Signing DMG"
codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"

echo "→ Notarizing (this can take a few minutes)"
xcrun notarytool submit "$DMG" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_PASSWORD" \
  --wait

echo "→ Stapling"
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"

echo "✓ Signed, notarized, stapled: $DMG"
