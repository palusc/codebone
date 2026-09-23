#!/usr/bin/env bash
# ==============================================================================
# codebone — Native macOS Application & DMG Packaging Pipeline
# ==============================================================================
# Builds and packages codebone into a standalone macOS drag-and-drop DMG installer
# and ZIP archive for GitHub Releases distribution.
#
# Usage:
#   ./scripts/build_dmg.sh [--release [vX.Y.Z]]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="codebone"
VERSION=$(git describe --tags --always 2>/dev/null || echo "1.0.0")

echo "🦴 Building $APP_NAME DMG Package (version: $VERSION)..."

# Ensure dist directory
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

STAGE_APP="$DIST_DIR/$APP_NAME.app"
DMG_NAME="$APP_NAME-macos-arm64-$VERSION.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
ZIP_PATH="$DIST_DIR/$APP_NAME-macos-arm64-$VERSION.zip"

# Check if prebuilt /Applications/codebone.app exists, or build fresh
if [[ -d "/Applications/$APP_NAME.app" ]]; then
  echo "📦 Sourcing bundle from /Applications/$APP_NAME.app..."
  cp -R "/Applications/$APP_NAME.app" "$STAGE_APP"
else
  echo "🔨 Creating application bundle at $STAGE_APP..."
  mkdir -p "$STAGE_APP/Contents/MacOS"
  mkdir -p "$STAGE_APP/Contents/Resources"
  cp -R "$ROOT_DIR/src" "$STAGE_APP/Contents/Resources/"
  cp -R "$ROOT_DIR/resources" "$STAGE_APP/Contents/Resources/"
  if [[ -f "$ROOT_DIR/resources/AppIcon.icns" ]]; then
    cp "$ROOT_DIR/resources/AppIcon.icns" "$STAGE_APP/Contents/Resources/"
  fi
  cat <<'EOF' > "$STAGE_APP/Contents/MacOS/codebone"
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/../Resources/src/codebone_main.py"
EOF
  chmod +x "$STAGE_APP/Contents/MacOS/codebone"
fi

# Clean up build artifacts that invalidate bundle structure or inflate size
rm -rf "$STAGE_APP/Contents/MacOS"/*.dSYM
find "$STAGE_APP" -name ".DS_Store" -delete 2>/dev/null || true
find "$STAGE_APP" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Ensure clean permissions
chmod -R 755 "$STAGE_APP"

# Sanitize bundle symlinks: macOS Gatekeeper strictly rejects bundles containing symlinks that resolve outside the bundle.
echo "🧹 Resolving external bundle symlinks..."
find "$STAGE_APP" -type l | while IFS= read -r link; do
  if [[ -L "$link" ]]; then
    resolved=$(python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" "$link" 2>/dev/null || true)
    if [[ -n "$resolved" ]]; then
      case "$resolved" in
        "$STAGE_APP"/*)
          # Internal relative symlink within bundle is permitted
          ;;
        *)
          # External symlink pointing outside bundle -> replace with actual file
          rm -f "$link"
          cp -L "$resolved" "$link"
          ;;
      esac
    fi
  fi
done

# Strip all quarantine attributes and macOS provenance metadata
xattr -cr "$STAGE_APP" 2>/dev/null || true

# Ad-hoc sign the entire bundle structure so macOS Gatekeeper / installcoordinationd passes verification
echo "🔏 Code-signing application bundle..."
codesign --force --deep -s - "$STAGE_APP"
codesign --verify --deep --strict "$STAGE_APP"

# 1. Create ZIP Package
echo "📦 Compressing $APP_NAME.app to $ZIP_PATH..."
(cd "$DIST_DIR" && zip -q -r "$ZIP_PATH" "$APP_NAME.app")

# 2. Build Drag-and-Drop DMG
echo "💿 Building Apple Disk Image ($DMG_NAME)..."
DMG_TMP="$DIST_DIR/dmg_staging"
rm -rf "$DMG_TMP"
mkdir -p "$DMG_TMP"

# Copy App to staging
cp -R "$STAGE_APP" "$DMG_TMP/"

# Create symlink to /Applications for drag-and-drop install
ln -s /Applications "$DMG_TMP/Applications"

# Create disk image
hdiutil create -volname "$APP_NAME" \
  -srcfolder "$DMG_TMP" \
  -ov -format UDZO \
  "$DMG_PATH"

rm -rf "$DMG_TMP"

# Provide consistent unversioned artifact aliases
GENERIC_DMG="$DIST_DIR/$APP_NAME-macos-arm64.dmg"
GENERIC_ZIP="$DIST_DIR/$APP_NAME-macos-arm64.zip"
cp "$DMG_PATH" "$GENERIC_DMG"
cp "$ZIP_PATH" "$GENERIC_ZIP"

echo ""
echo "✅ Build Complete!"
echo "   DMG: $DMG_PATH ($(du -sh "$DMG_PATH" | cut -f1))"
echo "   ZIP: $ZIP_PATH ($(du -sh "$ZIP_PATH" | cut -f1))"
echo ""

# Optional GitHub Release upload
if [[ "${1:-}" == "--release" ]]; then
  TAG="${2:-$VERSION}"
  echo "🚀 Uploading to GitHub Release $TAG via gh CLI..."
  if command -v gh >/dev/null 2>&1; then
    gh release upload "$TAG" "$GENERIC_DMG" "$GENERIC_ZIP" --clobber || \
    gh release create "$TAG" "$GENERIC_DMG" "$GENERIC_ZIP" --title "codebone $TAG" --notes "Native Apple Silicon release of codebone."
    echo "🎉 Successfully published release $TAG to GitHub!"
  else
    echo "⚠️ gh CLI not found. Upload $DMG_PATH manually to GitHub Releases."
  fi
fi
