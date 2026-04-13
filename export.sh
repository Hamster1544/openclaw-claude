#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ensure_supported_platform
require_root
require_cmd python3
require_cmd tar

OUT_PATH="${1:-openclaw-claude-export-$(date +%Y%m%d-%H%M%S).tar.gz}"
TARGET_HOME="$(target_home)"
STATE_DIR="$(state_dir)"
CONFIG_PATH="$(config_path)"
WORKSPACE_PATH="${OVERLAY_WORKSPACE:-$(detect_workspace)}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$TMP_DIR/state" "$TMP_DIR/workspace"

if [[ -f "$CONFIG_PATH" ]]; then
  cp "$CONFIG_PATH" "$TMP_DIR/state/openclaw.json"
fi

if [[ -d "$STATE_DIR/agents" ]]; then
  cp -R "$STATE_DIR/agents" "$TMP_DIR/state/agents"
fi

if [[ -d "$WORKSPACE_PATH" ]]; then
  cp -R "$WORKSPACE_PATH/." "$TMP_DIR/workspace/"
fi

python3 - <<PY
import json
from pathlib import Path

meta = {
    "target_home": ${TARGET_HOME@Q},
    "workspace": ${WORKSPACE_PATH@Q},
    "state_dir": ${STATE_DIR@Q},
    "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
}
Path(${TMP_DIR@Q}, "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\\n")
PY

tar -C "$TMP_DIR" -czf "$OUT_PATH" .
log "export written to $OUT_PATH"
