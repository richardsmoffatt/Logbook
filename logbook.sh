#!/usr/bin/env bash
# Logbook - run from anywhere:  ./logbook.sh setup | serve | import <export.xlsx> [--corrections file.json] [--replace] | test
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python

case "${1:-serve}" in
  setup)
    command -v python3 >/dev/null || { echo "Install Python 3.10+ first"; exit 1; }
    command -v npm >/dev/null || { echo "Install Node.js 20+ (e.g. sudo apt install nodejs npm) first"; exit 1; }
    [ -d .venv ] || python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
    .venv/bin/pip install -q -r backend/requirements-dev.txt
    (cd frontend && npm install --silent && npm run build --silent)
    echo "Setup complete. Start the app with: ./logbook.sh"
    ;;
  serve)
    shift || true
    [ -d frontend/dist ] || { echo "Run ./logbook.sh setup first"; exit 1; }
    cd backend && exec "../$PY" -m logbook serve "$@"
    ;;
  import)
    shift
    args=()
    for a in "$@"; do [ -e "$a" ] && a="$(realpath "$a")"; args+=("$a"); done
    cd backend && exec "../$PY" -m logbook import "${args[@]}"
    ;;
  test)
    (cd backend && "../$PY" -m pytest -q)
    (cd frontend && npm run --silent typecheck)
    ;;
  *)
    echo "Usage: ./logbook.sh [setup|serve|import|test]"; exit 1 ;;
esac
