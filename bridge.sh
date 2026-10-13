#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[[ -n "${1:-}" && -n "${APP_TOKEN:-}" ]] || exit 2
exec python3 "$SCRIPT_DIR/bridge.py" "$1"
