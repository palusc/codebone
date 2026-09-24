#!/bin/bash
# codebone installer (terminal). Builds the exact same codebone.app as the DMG (scripts/build_bundle.sh):
# bundled Python, pinned packages, pinned model, native launcher. Nothing here depends on Homebrew or system Python.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEBONE_HOME="$HOME/Library/Application Support/codebone"
APP_NAME="codebone.app"

ok()   { echo "   ✅  $*"; }
fail() { echo "   ❌  $*" >&2; }

[[ "$(uname -s)" == "Darwin" ]] || { fail "codebone is macOS only (Metal / menu bar)."; exit 1; }
[[ "$(uname -m)" == "arm64" ]] || { fail "codebone needs Apple Silicon (arm64)."; exit 1; }

COMMIT="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo "local")"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO_DIR/src/__init__.py")"
echo "🦴 Installing codebone v$VERSION ($COMMIT)"

echo "0/4 Preflight"
if ! xcode-select -p >/dev/null 2>&1 || ! command -v clang >/dev/null 2>&1; then
  fail "Xcode Command Line Tools are required (compiler for the native launcher and llama.cpp)."
  fail "A system dialog will open. Install, then re-run ./install.sh"
  xcode-select --install 2>/dev/null || true
  exit 1
fi
ok "Xcode CLT — clang present"
command -v curl >/dev/null 2>&1 || { fail "curl not found"; exit 1; }
ok "curl"

TARGET_DIR="/Applications"
[[ -w "$TARGET_DIR" ]] || TARGET_DIR="$HOME/Applications"
mkdir -p "$TARGET_DIR"
APP_BUNDLE="$TARGET_DIR/$APP_NAME"

echo "1/4 Building codebone.app (Python + pinned packages + model; first run takes several minutes)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
"$REPO_DIR/scripts/build_bundle.sh" "$BUILD_DIR"

echo "2/4 Installing to $APP_BUNDLE"
# Only ever touch apps that really are codebone/PUG (bundle id), never something that merely has a similar name
is_ours() {
  local id
  id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null || true)"
  [[ "$id" == com.codebone.app || "$id" == com.pug.app ]]
}
for old in "$TARGET_DIR/codebone.app" "$TARGET_DIR/CodeBone.app" "$TARGET_DIR/PUG.app" \
           "/Applications/CodeBone.app" "/Applications/PUG.app" "$HOME/Applications/CodeBone.app" "$HOME/Applications/PUG.app"; do
  if [[ -d "$old" ]] && is_ours "$old"; then
    pkill -f "$old/Contents/MacOS/" >/dev/null 2>&1 || true
    [[ "$old" == "$APP_BUNDLE" ]] || rm -rf "$old"
  fi
done
sleep 0.5
launchctl unload "$HOME/Library/LaunchAgents/com.pug.app.plist" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.pug.app.plist"

rm -rf "$APP_BUNDLE"
ditto "$BUILD_DIR/$APP_NAME" "$APP_BUNDLE"
xattr -cr "$APP_BUNDLE" 2>/dev/null || true

echo "3/4 Preparing Application Support and MCP"
RES="$APP_BUNDLE/Contents/Resources"
PY="$RES/venv/bin/python3"
mkdir -p "$CODEBONE_HOME/models" "$HOME/Library/Logs/codebone"
if [[ -f "$CODEBONE_HOME/pug.sqlite3" && ! -f "$CODEBONE_HOME/codebone.sqlite3" ]]; then
  mv "$CODEBONE_HOME/pug.sqlite3" "$CODEBONE_HOME/codebone.sqlite3" 2>/dev/null || true
fi
for link in venv src; do
  [[ -e "$CODEBONE_HOME/$link" && ! -L "$CODEBONE_HOME/$link" ]] && rm -rf "${CODEBONE_HOME:?}/$link"
done
ln -sfn "$RES/venv" "$CODEBONE_HOME/venv"
ln -sfn "$RES/src" "$CODEBONE_HOME/src"
# Model: linked from the bundle (verified against the pinned SHA-256), same as a DMG install does on first launch
"$PY" "$RES/src/scripts/download_model.py"

if command -v claude >/dev/null 2>&1; then
  claude mcp remove -s user pug >/dev/null 2>&1 || true
  claude mcp remove -s user codebone >/dev/null 2>&1 || true
  claude mcp add -s user codebone -- "$PY" -m codebone_mcp.server >/dev/null 2>&1 \
    && ok "Registered with Claude Code" || fail "Could not register with Claude Code (the app retries on every start)"
fi
# Claude Desktop / Cursor / Gemini configs are patched by the app itself on every start (same for DMG installs).

/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_BUNDLE" >/dev/null 2>&1 || true
touch "$APP_BUNDLE"

echo "4/4 Starting codebone"
open "$APP_BUNDLE" || true
for _ in {1..20}; do
  if curl -s -m 1 http://127.0.0.1:8053/codebone/status >/dev/null 2>&1; then
    echo "🟢 codebone server is responding on http://127.0.0.1:8053"
    break
  fi
  sleep 0.5
done

echo ""
echo "✨ codebone v$VERSION installed"
echo "   App:         $APP_BUNDLE"
echo "   Uninstall:   codebone menu > Settings > Uninstall codebone..."
echo "   Logs:        $HOME/Library/Logs/codebone/codebone.log"
