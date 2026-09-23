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

# ─── 1-3. Build a self-contained, portable app bundle ─────────────────────
# Bundles python-build-standalone as Resources/venv (relocatable, no Homebrew
# dependency) and a bash launcher, so the .app runs on any Apple Silicon Mac.
PBS_TAG="20260901"; PBS_PY="3.13.15"
APP="$STAGING/codebone.app"; RES="$APP/Contents/Resources"
mkdir -p "$APP/Contents/MacOS" "$RES/src"

echo "   Fetching portable Python ${PBS_PY}..."
curl -fsSL "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PBS_PY}+${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz" | tar -xz -C "$TMP_DIR"
mv "$TMP_DIR/python" "$RES/venv"

rsync -a --exclude .git --exclude __pycache__ --exclude venv --exclude .venv --exclude dist --exclude build "$REPO_DIR/" "$RES/src/"
cp "$REPO_DIR/resources/AppIcon.icns" "$REPO_DIR/resources/bone_active.png" "$REPO_DIR/resources/bone_inactive.png" "$RES/"

echo "   Installing dependencies (Metal build of llama-cpp-python)..."
export CMAKE_ARGS="-DGGML_METAL=on"
"$RES/venv/bin/python3" -m pip install --quiet --no-cache-dir -r "$REPO_DIR/requirements.txt"
# relative to sys.prefix (Resources/venv) so it survives being moved out of staging
echo "import sys, os; sys.path.append(os.path.join(sys.prefix, '..', 'src'))" > "$RES/venv/lib/python3.13/site-packages/codebone.pth"

cat > "$APP/Contents/Info.plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleName</key><string>codebone</string>
<key>CFBundleDisplayName</key><string>codebone</string>
<key>CFBundleIdentifier</key><string>com.codebone.app</string>
<key>CFBundleVersion</key><string>${VERSION}</string>
<key>CFBundleShortVersionString</key><string>${VERSION}</string>
<key>CFBundleExecutable</key><string>codebone</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>LSUIElement</key><true/>
<key>NSHighResolutionCapable</key><true/>
<key>NSDocumentsFolderUsageDescription</key><string>codebone requires access to your Documents folder to index code repositories located there.</string>
<key>NSDesktopFolderUsageDescription</key><string>codebone requires access to your Desktop folder to index code repositories located there.</string>
<key>NSDownloadsFolderUsageDescription</key><string>codebone requires access to your Downloads folder to index code repositories located there.</string>
<key>NSRemovableVolumesUsageDescription</key><string>codebone requires access to external volumes to index code repositories stored on external drives.</string>
</dict></plist>
PLISTEOF

# Native launcher: Python must run inside the bundle's main executable or macOS
# won't attach the menu-bar icon (a bash launcher that exec's python3 shows no icon).
PYINC=$(echo "$RES"/venv/include/python3.*)
clang -O2 -arch arm64 -I"$PYINC" "$REPO_DIR/scripts/launcher.c" -L"$RES/venv/lib" -lpython3.13 \
  -Wl,-rpath,@executable_path/../Resources/venv/lib -o "$APP/Contents/MacOS/codebone"

# Smoke test: no Homebrew paths, core imports work
if otool -L "$RES/venv/bin/python3" | grep -q /opt/homebrew; then echo "❌ python links Homebrew" >&2; exit 1; fi
if otool -L "$APP/Contents/MacOS/codebone" | grep -q /opt/homebrew; then echo "❌ launcher links Homebrew" >&2; exit 1; fi
"$RES/venv/bin/python3" -c "import fastapi, uvicorn, mcp, rumps, watchdog, httpx, pathspec"

# Precompile so the first launch is fast (no .pyc generation, no lag before the menu-bar icon shows)
"$RES/venv/bin/python3" -m compileall -q -j 0 "$RES/venv/lib" "$RES/src" >/dev/null || true
xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep -s - "$APP"

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
