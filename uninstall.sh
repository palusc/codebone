#!/usr/bin/env bash
# codebone uninstaller for the terminal (the app has the same thing in its menu: Uninstall codebone...).
#
#   ./uninstall.sh [--yes] [--dry-run] [--keep-app]
#
# Removes the app, its data, models, logs, caches, login items and its MCP registrations. Your project files are
# never touched (at most a legacy codebone entry is taken out of an MCP config file in a project folder). It runs
# the bundled Python (python -m src.uninstall) so it does exactly what the app does; if the app is already gone it
# falls back to a self-contained shell path over the same locations.
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# An empty or relative $HOME would turn every path below into a system-wide or project path (/Library, /Applications).
if [[ "${HOME:-}" != /* || "$HOME" == "/" || ! -d "$HOME" ]]; then
  echo "HOME is not set to a real home directory; refusing to run." >&2; exit 2
fi
YES=0; DRY=0; KEEP_APP=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    -n|--dry-run) DRY=1 ;;
    --keep-app) KEEP_APP=1 ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

# ── 1. Same code as the app ────────────────────────────────────────────────
if [[ -z "${CODEBONE_UNINSTALL_SHELL_ONLY:-}" ]]; then
  for py in \
    "$SCRIPT_DIR/../venv/bin/python3" \
    "/Applications/codebone.app/Contents/Resources/venv/bin/python3" \
    "$HOME/Applications/codebone.app/Contents/Resources/venv/bin/python3" \
    "/opt/homebrew/opt/codebone/codebone.app/Contents/Resources/venv/bin/python3" \
    "$HOME/Library/Application Support/codebone/venv/bin/python3"; do
    # -P: never import a `src` package from the current directory
    if [[ -x "$py" ]] && "$py" -P -c "import src.uninstall" >/dev/null 2>&1; then
      exec "$py" -P -m src.uninstall "$@"
    fi
  done
  # a source checkout: the module only needs the standard library
  PY3="$(command -v python3 || true)"
  if [[ -f "$SCRIPT_DIR/src/uninstall.py" && -n "$PY3" ]] && { [[ "$PY3" != /usr/bin/python3 ]] || xcode-select -p >/dev/null 2>&1; }; then
    cd "$SCRIPT_DIR" && PYTHONPATH="$SCRIPT_DIR" exec "$PY3" -m src.uninstall "$@"
  fi
fi

# ── 2. Self-contained shell path ───────────────────────────────────────────
LIB="$HOME/Library"
SUPPORT="$LIB/Application Support"
REAL_HOME="$(dscl . -read "/Users/$(id -un)" NFSHomeDirectory 2>/dev/null | sed 's/^NFSHomeDirectory: //')"
[[ -n "$REAL_HOME" ]] || REAL_HOME="$(eval echo "~$(id -un)")"
# Machine-wide steps (processes, /Applications, claude/brew/npm, TCC) only for the real account home.
SYSTEM=0
[[ "$(cd "$HOME" 2>/dev/null && pwd -P)" == "$(cd "$REAL_HOME" 2>/dev/null && pwd -P)" ]] && SYSTEM=1

FOUND=0; ERRORS=0; SEEN=" "; PROJECT_EDITS=0
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
# A `ps -o pid=,ppid=,command=` line of a codebone process: something running out of an app bundle, or an
# interpreter running the MCP server / a launcher script / the npm bridge. An editor that merely has one of those
# files open does not match.
PROC_RE='^ *[0-9]+ +[0-9]+ +(/.*/(codebone|CodeBone|PUG)\.app/Contents/(MacOS|Resources/venv/bin)/[^/ ]+( |$)|(/.*/)?([Pp]ython[0-9.]*|node) .*((codebone|pug)_mcp[./]server|codebone_main\.py|pug_main\.py|[/ ]codebone-mcp(\.js)?( |$)))'

say() { printf '%s\n' "$*"; }
found() { FOUND=1; }

# remove <label> <path>: files, symlinks (never their target) and directories; each real inode only once
remove() {
  [[ -e "$2" || -L "$2" ]] || return 0
  local id; id="$(stat -f '%d:%i' "$2" 2>/dev/null)"
  case "$SEEN" in *" $id "*) return 0 ;; esac
  SEEN="$SEEN$id "
  found
  if (( DRY )); then say "  would remove $1: $2"; return 0; fi
  # read-only directories inside a tree (rm cannot empty them) get their permissions back and one more try
  if rm -rf -- "$2" 2>/dev/null || { [[ ! -L "$2" ]] && chmod -R u+rwX "$2" 2>/dev/null && rm -rf -- "$2" 2>/dev/null; }; then
    say "  removed $1: $2"
  else say "  could not remove $2 (owned by another user? try: sudo rm -rf $(printf '%q' "$2"))" >&2; ERRORS=1; fi
}

find_tool() {  # PATH first, then the usual install dirs
  command -v "$1" 2>/dev/null && return 0
  local d; for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin" "$HOME/.claude/local" "$HOME/.npm-global/bin" "$HOME/.volta/bin" "$HOME"/.nvm/versions/node/*/bin; do
    [[ -x "$d/$1" ]] && { echo "$d/$1"; return 0; }
  done
  return 1
}

is_codebone_app() {
  case "$(basename "$1")" in codebone.app|CodeBone.app|PUG.app) return 0 ;; esac
  local id; id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null)"
  [[ "$id" == com.codebone.app || "$id" == com.pug.app ]]
}

outer_app() {  # outermost *.app directory of a path
  perl -MCwd=realpath -e 'print realpath($ARGV[0]) // $ARGV[0]' "$1" 2>/dev/null | awk '{ i = index($0, ".app/"); if (i) print substr($0, 1, i + 3) }'
}

login_items() {  # matched by bundle id, so another vendor's com.pug.* agent is never touched
  local id f uid; uid="$(id -u)"
  for id in com.codebone.app com.pug.app; do
    for f in "$LIB/LaunchAgents/$id".plist "$LIB/LaunchAgents/$id".*.plist "$LIB/LaunchAgents/$id"[-_]*.plist; do
      [[ -e "$f" ]] || continue
      if (( SYSTEM && ! DRY )); then launchctl bootout "gui/$uid" "$f" >/dev/null 2>&1 || launchctl unload "$f" >/dev/null 2>&1; fi
      remove "login item" "$f"
    done
  done
}

processes() {
  (( SYSTEM )) || return 0
  local mine=" $$ " p=$$ line pid cmd pids=""
  while [[ "$p" -gt 1 ]]; do p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"; [[ -n "$p" ]] || break; mine="$mine$p "; done
  while read -r pid _ cmd; do
    case "$mine" in *" $pid "*) continue ;; esac
    found; pids="$pids $pid"
    say "  $( ((DRY)) && echo 'would stop' || echo 'stopping' ) process $pid: ${cmd:0:100}"
  done < <(ps -x -ww -U "$(id -u)" -o pid=,ppid=,command= | grep -E "$PROC_RE" | grep -v 'grep -E')
  (( DRY )) || [[ -z "$pids" ]] && return 0
  kill $pids 2>/dev/null; sleep 2
  for pid in $pids; do kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null; done
}

# JSON-safe removal of codebone's entries from the MCP configs (parses first, writes atomically, never guesses).
IFS= read -r -d '' MCP_PY <<'PYEOF'
import json, os, re, shutil, sys
home, dry = sys.argv[1], sys.argv[2] == "1"
J = os.path.join
NAMES = ("codebone", "pug")

def ours(name, entry):  # "pug" is a common name for other tools: take it only if it points at this app
    return name != "pug" or bool(re.search(r"pug_(?:mcp|main|port)|pug\.app|codebone", json.dumps(entry), re.I))

projects = []
for n in ("codebone", "CodeBone", "PUG"):
    try:
        cfg = json.load(open(J(home, "Library", "Application Support", n, "config.json"), encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(cfg, dict):
        continue
    recent = cfg.get("recent_projects")
    for p in (recent if isinstance(recent, list) else []) + [cfg.get("project_path")]:
        if isinstance(p, str) and os.path.isabs(p) and os.path.isdir(p) and p not in projects:
            projects.append(p)

# (path, directories to prune when the file goes, may delete the file, look in projects.*, lives in a project)
files = [
    (J(home, ".claude.json"), [], False, True, False),
    (J(home, "Library", "Application Support", "Claude", "claude_desktop_config.json"), [], True, False, False),
    (J(home, ".cursor", "mcp.json"), [J(home, ".cursor")], True, False, False),
    (J(home, ".gemini", "config", "mcp_config.json"), [J(home, ".gemini", "config"), J(home, ".gemini")], True, False, False),
    (J(home, ".gemini", "antigravity-ide", "mcp_config.json"), [J(home, ".gemini", "antigravity-ide"), J(home, ".gemini")], True, False, False),
]
for p in projects:
    for d, f in ((".cursor", "mcp.json"), (".gemini", "mcp_config.json"), (".agents", "mcp_config.json")):
        files.append((J(p, d, f), [J(p, d)], True, False, True))

def maps(data, nested):
    holders = [data] + ([v for v in data["projects"].values() if isinstance(v, dict)]
                        if nested and isinstance(data.get("projects"), dict) else [])
    return [h["mcpServers"] for h in holders if isinstance(h.get("mcpServers"), dict)]

def prune(dirs, gone):
    for d in dirs:
        if os.path.islink(d):  # a dotfiles-managed directory is not ours to remove
            return
        try:
            names = set(os.listdir(d))
        except OSError:
            return
        if names - gone - {".DS_Store"}:
            return
        if not dry:
            for n in names - gone:
                os.unlink(J(d, n))
            os.rmdir(d)
        print("  %s empty directory: %s" % ("would remove" if dry else "removed", d))
        gone = {os.path.basename(d)}

seen, project_edit = set(), False
for path, dirs, deletable, nested, in_project in files:
    if not os.path.lexists(path) or os.path.realpath(path) in seen:  # a project can be the home directory itself
        continue
    seen.add(os.path.realpath(path))
    try:
        raw = open(path, "rb").read()
    except OSError:
        if os.path.isfile(path):
            print("  left %s alone (cannot be read); check it for a codebone entry" % path)
        continue
    try:
        text = raw.decode("utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception:
        if re.search(r"codebone|\"pug\"", raw.decode("utf-8", "replace"), re.I):
            print("  left %s alone (not valid JSON); remove its codebone entry by hand" % path)
        continue
    hits = []
    for m in maps(data, nested):
        for n in NAMES:
            if n in m and ours(n, m[n]):
                hits.append(n)
                del m[n]
    if not hits:
        continue
    project_edit = project_edit or in_project
    verb = "would remove" if dry else "removed"
    if data in ({}, {"mcpServers": {}}) and deletable and not os.path.islink(path):
        if not dry:
            os.unlink(path)
        print("  %s MCP config (only codebone was in it): %s" % (verb, path))
        prune(dirs, {os.path.basename(path)})
        continue
    if not dry:
        m = re.search(r"^([ \t]+)\S", text, re.M)
        out = json.dumps(data, indent=m.group(1) if m else None, ensure_ascii=False) + ("\n" if text.endswith("\n") else "")
        target = os.path.realpath(path)
        tmp = target + ".codebone-tmp"
        try:
            open(tmp, "w", encoding="utf-8").write(out)
            shutil.copymode(target, tmp)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    print("  %s MCP entry %s in %s" % (verb, ", ".join(sorted(set(hits))), path))
sys.exit(3 if project_edit else 0)
PYEOF

mcp_entries() {
  local claude
  if (( SYSTEM && ! DRY )) && claude="$(find_tool claude)"; then
    "$claude" mcp remove -s user codebone </dev/null >/dev/null 2>&1  # a legacy `pug` entry is left to the JSON edit below
  fi
  local py; py="$(command -v python3)"
  if [[ -z "$py" ]] || { [[ "$py" == /usr/bin/python3 ]] && ! xcode-select -p >/dev/null 2>&1; }; then
    say "  no python3 available: remove the \"codebone\" entry from ~/.claude.json, Claude Desktop, Cursor and Gemini configs by hand"
    return 0
  fi
  local out rc; out="$("$py" -c "$MCP_PY" "$HOME" "$DRY")"; rc=$?
  (( rc == 3 )) && PROJECT_EDITS=1
  (( rc != 0 && rc != 3 )) && { say "  could not edit the MCP configs (exit $rc); check them for a codebone entry" >&2; ERRORS=1; }
  [[ -n "$out" ]] && { found; say "$out"; }
}

packages() {
  (( SYSTEM )) || return 0
  local brew npm; brew="$(find_tool brew)"; npm="$(find_tool npm)"
  if [[ -n "$brew" ]]; then
    export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1
    if "$brew" list codebone >/dev/null 2>&1; then
      found; if (( DRY )); then say "  would remove package: Homebrew formula codebone"
      else "$brew" uninstall codebone >/dev/null 2>&1 && say "  removed package: Homebrew formula codebone" || { say "  brew uninstall codebone failed" >&2; ERRORS=1; }; fi
    fi
    if "$brew" tap 2>/dev/null | grep -qx 'palusc/codebone'; then
      found; if (( DRY )); then say "  would remove package: Homebrew tap palusc/codebone"
      else "$brew" untap palusc/codebone >/dev/null 2>&1 && say "  removed package: Homebrew tap palusc/codebone" || { say "  brew untap failed" >&2; ERRORS=1; }; fi
    fi
  fi
  if [[ -n "$npm" ]] && "$npm" ls -g --depth=0 codebone-mcp 2>/dev/null | grep -q 'codebone-mcp@'; then
    found; if (( DRY )); then say "  would remove package: npm codebone-mcp (global)"
    else "$npm" uninstall -g codebone-mcp >/dev/null 2>&1 && say "  removed package: npm codebone-mcp (global)" || { say "  npm uninstall -g codebone-mcp failed" >&2; ERRORS=1; }; fi
  fi
}

data() {
  local n id g d
  for n in codebone CodeBone PUG; do
    remove "data" "$SUPPORT/$n"
    remove "logs" "$LIB/Logs/$n"
  done
  remove "caches" "$LIB/Caches/codebone-build"
  for id in com.codebone.app com.pug.app; do
    if (( SYSTEM && ! DRY )) && [[ -e "$LIB/Preferences/$id.plist" ]]; then defaults delete "$id" >/dev/null 2>&1; fi
    remove "caches" "$LIB/Caches/$id"
    remove "preferences" "$LIB/Preferences/$id.plist"
    remove "saved state" "$LIB/Saved Application State/$id.savedState"
    remove "saved state" "$LIB/HTTPStorages/$id"
    remove "saved state" "$LIB/HTTPStorages/$id.binarycookies"
    remove "saved state" "$LIB/WebKit/$id"
    remove "saved state" "$LIB/Containers/$id"
    for g in "$LIB/Group Containers"/*"$id"; do remove "saved state" "$g"; done
  done
  # npx keeps a copy of codebone-mcp; delete the entry only when it holds nothing else
  for d in "$HOME"/.npm/_npx/*; do
    [[ -d "$d/node_modules/codebone-mcp" && "$(ls "$d/node_modules" | wc -l | tr -d ' ')" == 1 ]] && remove "cache" "$d"
  done
}

# Finds every bundle. Must run before data(): the symlinks it follows live in Application Support.
find_apps() {
  local roots=("$HOME/Applications") root n l app
  (( SYSTEM )) && roots=("/Applications" "${roots[@]}")
  APP_CANDS=()
  for root in "${roots[@]}"; do
    for n in codebone CodeBone PUG "Uninstall codebone" "Uninstall CodeBone" "Uninstall PUG"; do APP_CANDS+=("$root/$n.app"); done
  done
  # bundles kept anywhere else are found through the symlinks codebone left in Application Support
  for n in codebone CodeBone PUG; do
    for l in "$SUPPORT/$n/venv" "$SUPPORT/$n/src" "$SUPPORT/$n"/models/*.gguf; do
      [[ -L "$l" ]] || continue
      app="$(outer_app "$l")"
      case "$app" in "$SCRIPT_DIR"/*) continue ;; esac  # a build inside this checkout is a project file
      [[ -n "$app" ]] && is_codebone_app "$app" && APP_CANDS+=("$app")
    done
  done
  (( SYSTEM )) && { app="$(outer_app "$SCRIPT_DIR")"; [[ -n "$app" ]] && is_codebone_app "$app" && APP_CANDS+=("$app"); }
}

apps() {
  local app
  for app in "${APP_CANDS[@]}"; do
    [[ -e "$app" || -L "$app" ]] || continue
    if (( KEEP_APP )); then say "  left in place: $app"; continue; fi
    (( SYSTEM && ! DRY )) && [[ ! -L "$app" ]] && "$LSREGISTER" -u "$app" >/dev/null 2>&1
    remove "app" "$app"
  done
  if (( SYSTEM && ! DRY && ! KEEP_APP && FOUND )); then
    tccutil reset All com.codebone.app >/dev/null 2>&1; tccutil reset All com.pug.app >/dev/null 2>&1
  fi
}

run_all() {
  find_apps; login_items; processes; mcp_entries; packages; data; apps
}

summary() {
  if (( ! FOUND )); then say "Nothing to remove. codebone is not installed on this Mac (or was already removed)."
  elif (( DRY )); then say "Dry run: nothing was changed."
  elif (( ERRORS )); then say "codebone was removed except for the problems listed above."
  elif (( PROJECT_EDITS )); then say "codebone has been removed from this Mac. In your project folders only codebone's own MCP entries (listed above) were taken out; nothing else there was changed."
  else say "codebone has been removed from this Mac. Your project folders were not touched."; fi
}

if (( DRY )); then
  run_all; summary; exit 0
fi
if (( ! YES )); then
  DRY=1; run_all
  (( FOUND )) || { summary; exit 0; }
  printf '\nRemove everything listed above? [y/N] '
  read -r answer
  case "$answer" in y|Y|yes|YES) ;; *) say "Cancelled."; exit 1 ;; esac
  DRY=0; FOUND=0; SEEN=" "; PROJECT_EDITS=0
fi
run_all
summary
exit "$ERRORS"
