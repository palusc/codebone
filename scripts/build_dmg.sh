#!/bin/bash
# build_dmg.sh — Builds a distributable codebone-vX.X.X-arm64.dmg
# Usage: ./scripts/build_dmg.sh
# Requires: hdiutil (built-in), create-dmg (optional for fancy layout)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=$(grep -o 'CURRENT_VERSION = "[^"]*"' "$REPO_DIR/src/updater.py" 2>/dev/null | grep -o '"[^"]*"' | tr -d '"' || echo "1.0.0")
DMG_NAME="codebone-v${VERSION}-arm64"
DMG_DIR="$REPO_DIR/dist"
DMG_FINAL="$DMG_DIR/${DMG_NAME}.dmg"
TMP_DIR="$(mktemp -d)"
STAGING="$TMP_DIR/staging"

mkdir -p "$STAGING" "$DMG_DIR"

echo "🦴 Building codebone v${VERSION} DMG..."

# ─── 1. Find app bundle ────────────────────────────────────────────────────
APP_BUNDLE=""
for candidate in "/Applications/codebone.app" "$HOME/Applications/codebone.app"; do
  if [[ -d "$candidate" && -f "$candidate/Contents/MacOS/codebone" ]]; then
    APP_BUNDLE="$candidate"
    break
  fi
done

if [[ -z "$APP_BUNDLE" ]]; then
  echo "❌ codebone.app not found. Run ./install.sh first, then ./scripts/build_dmg.sh" >&2
  exit 1
fi
echo "   Source: $APP_BUNDLE"

# ─── 2. Copy app into staging ─────────────────────────────────────────────
cp -R "$APP_BUNDLE" "$STAGING/codebone.app"

# ─── 3. Strip quarantine & re-sign ────────────────────────────────────────
xattr -cr "$STAGING/codebone.app" 2>/dev/null || true
codesign --force --deep -s - "$STAGING/codebone.app" 2>/dev/null || true

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
    -size 400m \
    "$TMP_DMG" >/dev/null 2>&1

  hdiutil convert "$TMP_DMG" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_FINAL" >/dev/null 2>&1
fi

rm -rf "$TMP_DIR"

FILE_SIZE=$(du -sh "$DMG_FINAL" | awk '{print $1}')
echo ""
echo "✅ DMG built!"
echo "   File:    $DMG_FINAL"
echo "   Size:    $FILE_SIZE"
echo "   Version: v${VERSION}"
echo ""
echo "   Upload to GitHub Releases:"
echo "   https://github.com/palusc/codebone/releases/new"
echo ""
