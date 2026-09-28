#!/bin/bash
set -euo pipefail

APP_ID="${1:-}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [[ -z "$APP_ID" || -z "${APP_TOKEN:-}" ]]; then
  exit 2
fi

exec python3 "$SCRIPT_DIR/bridge.py" "$APP_ID"
