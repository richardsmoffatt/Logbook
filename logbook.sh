#!/usr/bin/env bash
# Logbook - run from anywhere:  ./logbook.sh setup | serve | app | install-app | uninstall-app
#                               | import <export.xlsx> [--corrections file.json] [--replace] | test
set -euo pipefail
cd "$(dirname "$0")"
PY="$PWD/.venv/bin/python"   # absolute: newer Python warns about "backend/../.venv"

# Build the app screens if they are missing, or older than their sources (e.g. after a git pull)
ensure_screens() {
  if [ -f frontend/dist/index.html ] && \
     [ -z "$(find frontend/src frontend/index.html frontend/package.json -newer frontend/dist/index.html 2>/dev/null | head -1)" ]; then
    return
  fi
  command -v npm >/dev/null || { echo "Install Node.js 20+ (e.g. sudo dnf install nodejs npm) first"; return 1; }
  echo "Updating the app screens..."
  (cd frontend && { [ -d node_modules ] || npm install --silent; } && npm run build --silent >/dev/null) \
    || { echo "Could not build the screens - run ./logbook.sh setup and send me the output"; return 1; }
}

# Make sure .venv exists and has the app's packages. It can go missing or break after a Python
# upgrade (e.g. a Fedora update) or when .venv isn't synced; it only holds packages, never data.
ensure_python() {
  if [ -x "$PY" ] && "$PY" -c "import fastapi, uvicorn, openpyxl, multipart" 2>/dev/null; then return; fi
  command -v python3 >/dev/null || { echo "Install Python 3.10+ first"; return 1; }
  echo "Setting up the app's Python packages (one-off, takes a minute)..."
  if ! { [ -x "$PY" ] && "$PY" -c "" 2>/dev/null; }; then python3 -m venv --clear .venv || return 1; fi
  "$PY" -m pip install -q --upgrade pip || return 1
  "$PY" -m pip install -q -r backend/requirements-dev.txt || return 1
}

case "${1:-serve}" in
  setup)
    command -v python3 >/dev/null || { echo "Install Python 3.10+ first"; exit 1; }
    command -v npm >/dev/null || { echo "Install Node.js 20+ (e.g. sudo dnf install nodejs npm) first"; exit 1; }
    ensure_python || exit 1
    (cd frontend && npm install --silent && npm run build --silent)
    echo "Setup complete. Start the app with: ./logbook.sh"
    ;;
  serve)
    shift || true
    ensure_python || exit 1
    ensure_screens || exit 1
    cd backend && exec "$PY" -m logbook serve "$@"
    ;;
  app)
    # What the menu icon runs: no terminal, so progress goes to notifications and a log file
    shift || true
    LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/logbook"; mkdir -p "$LOG_DIR"
    exec >>"$LOG_DIR/app.log" 2>&1
    echo "--- $(date '+%F %T') starting"
    notify() { command -v notify-send >/dev/null && notify-send -a Logbook -i "$PWD/frontend/public/logbook.svg" "Logbook" "$1" || true; }
    if ! { [ -x "$PY" ] && "$PY" -c "import fastapi, uvicorn, openpyxl, multipart" 2>/dev/null; }; then
      notify "Setting up - this takes a minute the first time..."
    fi
    ensure_python || { notify "Could not set up Python - see $LOG_DIR/app.log"; exit 1; }
    ensure_screens || { notify "Could not build the screens - see $LOG_DIR/app.log"; exit 1; }
    cd backend && exec "$PY" -m logbook app "$@"
    ;;
  install-app)
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"; mkdir -p "$APPS"
    cat > "$APPS/logbook.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Logbook
GenericName=Pilot logbook
Comment=Your pilot logbook
Exec="$PWD/logbook.sh" app
Icon=$PWD/frontend/public/logbook.svg
Terminal=false
Categories=Office;Utility;
StartupWMClass=LogbookApp
StartupNotify=true
DESKTOP
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" || true
    echo "Logbook added to your app menu. Search for \"Logbook\", or right-click it to pin it to the dock."
    echo "(If you move the Logbook folder, run ./logbook.sh install-app again.)"
    ;;
  uninstall-app)
    rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/logbook.desktop"
    echo "Logbook removed from your app menu. Your logbook data is untouched."
    ;;
  import)
    shift
    ensure_python || exit 1
    args=()
    for a in "$@"; do [ -e "$a" ] && a="$(realpath "$a")"; args+=("$a"); done
    cd backend && exec "$PY" -m logbook import "${args[@]}"
    ;;
  test)
    ensure_python || exit 1
    (cd backend && "$PY" -m pytest -q)
    (cd frontend && npm run --silent typecheck)
    ;;
  *)
    echo "Usage: ./logbook.sh [setup|serve|app|install-app|uninstall-app|import|test]"; exit 1 ;;
esac
