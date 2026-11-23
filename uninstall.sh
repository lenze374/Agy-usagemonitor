#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PY_BIN=""

for cand in "${PYTHON3:-}" python3 python; do
  [ -n "$cand" ] || continue
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
      PY_BIN="$(command -v "$cand")"
      break
    fi
  fi
done

if [ -z "$PY_BIN" ]; then
  echo "Error: Python 3.9+ is required to uninstall Antigravity Usage Monitor." >&2
  exit 1
fi

exec "$PY_BIN" "$SCRIPT_DIR/scripts/manage.py" uninstall "$@"
