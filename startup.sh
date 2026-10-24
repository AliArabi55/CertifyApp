#!/bin/bash
APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_FILE="$(find "$APP_ROOT" -maxdepth 8 -type f -path '*/app/main.py' -print -quit 2>/dev/null)"
if [ -n "$APP_FILE" ]; then
  APP_DIR="${APP_FILE%/app/main.py}"
fi
if [ -z "${APP_DIR:-}" ] && [ -f "$APP_ROOT/main.py" ] && [ -f "$APP_ROOT/__init__.py" ]; then
  APP_DIR="$(dirname -- "$APP_ROOT")"
fi
if [ -z "${APP_DIR:-}" ]; then
  echo "Could not locate app/main.py from $APP_ROOT" >&2
  exit 1
fi

echo "Starting Certify from $APP_DIR"
exec gunicorn -k uvicorn.workers.UvicornWorker \
  --chdir "$APP_DIR" app.main:app \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 1 --timeout 600 --access-logfile -
