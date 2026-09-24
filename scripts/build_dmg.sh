#!/bin/bash
# build_dmg.sh — Builds a distributable codebone-vX.X.X-arm64.dmg
# Usage: ./scripts/build_dmg.sh
# Requires: hdiutil (built-in), create-dmg (optional for fancy layout). Also writes the ZIP the in-app updater and Homebrew use.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO_DIR/src/__init__.py")"
DMG_NAME="codebone-v${VERSION}-arm64"
DMG_DIR="$REPO_DIR/dist"
DMG_FINAL="$DMG_DIR/${DMG_NAME}.dmg"
TMP_DIR="$(mktemp -d)"
STAGING="$TMP_DIR/staging"

mkdir -p "$STAGING" "$DMG_DIR"

echo "🦴 Building codebone v${VERSION} DMG..."

# ─── 1-3. Build the app: the exact same recipe install.sh uses ─────────────
"$REPO_DIR/scripts/build_bundle.sh" "$STAGING"

# ─── 4. Write README inside the DMG ───────────────────────────────────────
cat > "$STAGING/Installation Instructions.txt" << 'READMEEOF'
──────────────────────────────────────────────────────────────────
  codebone — Installation Instructions
──────────────────────────────────────────────────────────────────

STEP 1 — Drag codebone.app into your Applications folder.

STEP 2 — Open codebone.
  • Double-click codebone.app in Applications.
  • If macOS shows "codebone can't be opened because it is from
    an unidentified developer", follow the steps below.

──────────────────────────────────────────────────────────────────
  GATEKEEPER / SECURITY WARNING — HOW TO ALLOW THE APP
──────────────────────────────────────────────────────────────────

Option A — Right-Click Method (easiest):
  1. Right-click (or Control-click) codebone.app
  2. Select "Open" from the menu
  3. Click "Open" again in the dialog that appears
  codebone will open and macOS remembers the exception.

Option B — System Settings Method:
  1. Try to open codebone.app (it will be blocked).
  2. Open:  System Settings → Privacy & Security
  3. Scroll down to the "Security" section.
  4. You will see:
     '"codebone" was blocked from use because it is not
     from an identified developer.'
  5. Click "Open Anyway".
  6. Authenticate with your password or Touch ID.
  codebone is now permanently allowed.

Option C — Terminal (advanced users):
  Run this command in Terminal.app:
    xattr -cr /Applications/codebone.app

──────────────────────────────────────────────────────────────────
  WHY IS THERE A SECURITY WARNING?
──────────────────────────────────────────────────────────────────
codebone is open-source and free. We are not enrolled in Apple's
paid Developer Program ($99/year), so the app is not notarized.
It is completely safe — source code is publicly available at:
  https://github.com/palusc/codebone

──────────────────────────────────────────────────────────────────
  AUTO-UPDATES
──────────────────────────────────────────────────────────────────
codebone checks GitHub for updates automatically.
When an update is available, you'll see a notification in the
menu bar. Click "Update" to install it in the background.

Manual check: Click the 🦴 icon → "Check for Updates"
──────────────────────────────────────────────────────────────────
READMEEOF

# ─── 5. Applications symlink (drag-install UX) ────────────────────────────
ln -s /Applications "$STAGING/Applications"

# ─── 6. Build DMG ─────────────────────────────────────────────────────────
rm -f "$DMG_FINAL"

if command -v create-dmg >/dev/null 2>&1; then
  echo "   Using create-dmg for fancy layout..."
  create-dmg \
    --volname "codebone v${VERSION}" \
    --window-pos 200 120 \
    --window-size 660 400 \
    --icon-size 128 \
    --icon "codebone.app" 160 185 \
    --hide-extension "codebone.app" \
    --app-drop-link 500 185 \
    --no-internet-enable \
    "$DMG_FINAL" \
    "$STAGING" 2>/dev/null || true
fi

# Fallback: plain hdiutil (always available on macOS)
if [[ ! -f "$DMG_FINAL" ]]; then
  echo "   Using hdiutil (plain layout)..."
  TMP_DMG="$TMP_DIR/rw.dmg"
  hdiutil create \
    -srcfolder "$STAGING" \
    -volname "codebone v${VERSION}" \
    -fs HFS+ \
    -fsargs "-c c=64,a=16,b=16" \
    -format UDRW \
    "$TMP_DMG" >/dev/null 2>&1

  hdiutil convert "$TMP_DMG" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_FINAL" >/dev/null 2>&1
fi

# ZIP of the same bundle: consumed by the DMG's own "Applications" drag-install and the Homebrew formula
ZIP_FINAL="$DMG_DIR/codebone-macos-arm64.zip"
rm -f "$ZIP_FINAL"
ditto -c -k --keepParent "$STAGING/codebone.app" "$ZIP_FINAL"
cp "$DMG_FINAL" "$DMG_DIR/codebone-macos-arm64.dmg"
(cd "$DMG_DIR" && shasum -a 256 codebone-macos-arm64.zip > codebone-macos-arm64.zip.sha256)

# ─── 7. Lightweight update package (what the in-app updater actually downloads) ───
# An already-installed copy already has a valid, checksummed copy of the bundled model on disk
# (src/model_fetch.py checks that before ever looking at the app bundle or the network), so
# re-shipping the ~490 MB model on every release — even a one-line code fix — is pure waste.
# This variant is the same signed app with Contents/Resources/models stripped out and re-signed.
echo "   Building lightweight update package (no bundled model)..."
UPDATE_STAGING="$TMP_DIR/update-staging"
mkdir -p "$UPDATE_STAGING"
ditto "$STAGING/codebone.app" "$UPDATE_STAGING/codebone.app"
rm -rf "$UPDATE_STAGING/codebone.app/Contents/Resources/models"
xattr -cr "$UPDATE_STAGING/codebone.app" 2>/dev/null || true
codesign --force --deep -s - "$UPDATE_STAGING/codebone.app"

UPDATE_ZIP_FINAL="$DMG_DIR/codebone-macos-arm64-update.zip"
rm -f "$UPDATE_ZIP_FINAL"
ditto -c -k --keepParent "$UPDATE_STAGING/codebone.app" "$UPDATE_ZIP_FINAL"
(cd "$DMG_DIR" && shasum -a 256 codebone-macos-arm64-update.zip > codebone-macos-arm64-update.zip.sha256)

rm -rf "$TMP_DIR"

FILE_SIZE=$(du -sh "$DMG_FINAL" | awk '{print $1}')
echo ""
echo "✅ DMG built!"
echo "   File:    $DMG_FINAL"
echo "   Size:    $FILE_SIZE"
echo "   Version: v${VERSION}"
echo "   ZIP:     $ZIP_FINAL"
echo "   Update:  $UPDATE_ZIP_FINAL ($(du -sh "$UPDATE_ZIP_FINAL" | awk '{print $1}'), no bundled model — what the in-app updater downloads)"
echo "   Formula: set url .../v${VERSION}/codebone-macos-arm64.zip and sha256 $(shasum -a 256 "$ZIP_FINAL" | awk '{print $1}')"
echo ""
echo "   Upload to GitHub Releases:"
echo "   https://github.com/palusc/codebone/releases/new"
echo ""
