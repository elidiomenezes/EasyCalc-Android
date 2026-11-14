#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/server.py" \
  --spec "$SCRIPT_DIR/specs/nibss-v1.16.json" \
  --rules "$SCRIPT_DIR/rules/nibss-rules.json" \
  --framing binary-2 \
  "$@"
