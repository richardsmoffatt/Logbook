#!/usr/bin/env bash
# Logbook - run from anywhere:  ./logbook.sh setup | serve | import <export.xlsx> [--corrections file.json] [--replace] | test
set -euo pipefail
cd "$(dirname "$0")"
PY="$PWD/.venv/bin/python"   # absolute: newer Python warns about "backend/../.venv"

# Build the app screens if they are missing, or older than their sources (e.g. after a git pull)
ensure_screens() {
  if [ -f frontend/dist/index.html ] && \
     [ -z "$(find frontend/src frontend/index.html frontend/package.json -newer frontend/dist/index.html 2>/dev/null | head -1)" ]; then
    return
  fi
  command -v npm >/dev/null || { echo "Install Node.js 20+ (e.g. sudo dnf install nodejs npm) first"; exit 1; }
  echo "Updating the app screens..."
  (cd frontend && { [ -d node_modules ] || npm install --silent; } && npm run build --silent >/dev/null) \
    || { echo "Could not build the screens - run ./logbook.sh setup and send me the output"; exit 1; }
}

# Make sure .venv exists and has the app's packages. It can go missing or break after a Python
# upgrade (e.g. a Fedora update) or when .venv isn't synced; it only holds packages, never data.
ensure_python() {
  if [ -x "$PY" ] && "$PY" -c "import fastapi, uvicorn, openpyxl, multipart" 2>/dev/null; then return; fi
  command -v python3 >/dev/null || { echo "Install Python 3.10+ first"; exit 1; }
  echo "Setting up the app's Python packages (one-off, takes a minute)..."
  if ! { [ -x "$PY" ] && "$PY" -c "" 2>/dev/null; }; then python3 -m venv --clear .venv; fi
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r backend/requirements-dev.txt
}

case "${1:-serve}" in
  setup)
    command -v python3 >/dev/null || { echo "Install Python 3.10+ first"; exit 1; }
    command -v npm >/dev/null || { echo "Install Node.js 20+ (e.g. sudo dnf install nodejs npm) first"; exit 1; }
    ensure_python
    (cd frontend && npm install --silent && npm run build --silent)
    echo "Setup complete. Start the app with: ./logbook.sh"
    ;;
  serve)
    shift || true
    ensure_python
    ensure_screens
    cd backend && exec "$PY" -m logbook serve "$@"
    ;;
  import)
    shift
    ensure_python
    args=()
    for a in "$@"; do [ -e "$a" ] && a="$(realpath "$a")"; args+=("$a"); done
    cd backend && exec "$PY" -m logbook import "${args[@]}"
    ;;
  test)
    ensure_python
    (cd backend && "$PY" -m pytest -q)
    (cd frontend && npm run --silent typecheck)
    ;;
  *)
    echo "Usage: ./logbook.sh [setup|serve|import|test]"; exit 1 ;;
esac
