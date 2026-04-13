#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ensure_supported_platform
require_root
require_cmd tar
require_cmd python3

ARCHIVE="${1:-}"
[[ -n "$ARCHIVE" ]] || die "usage: ./import.sh /path/to/archive.tar.gz"
[[ -f "$ARCHIVE" ]] || die "archive not found: $ARCHIVE"

TARGET_HOME="$(target_home)"
STATE_DIR="$(state_dir)"
WORKSPACE_PATH="${OVERLAY_WORKSPACE:-$(detect_workspace)}"
BACKUP_DIR="$(backup_dir)"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$BACKUP_DIR"
if [[ -d "$STATE_DIR" ]]; then
  cp -R "$STATE_DIR" "$BACKUP_DIR/state-pre-import"
fi
if [[ -d "$WORKSPACE_PATH" ]]; then
  cp -R "$WORKSPACE_PATH" "$BACKUP_DIR/workspace-pre-import"
fi

tar -C "$TMP_DIR" -xzf "$ARCHIVE"

mkdir -p "$STATE_DIR" "$WORKSPACE_PATH"

if [[ -f "$TMP_DIR/state/openclaw.json" ]]; then
  python3 "$SCRIPT_DIR/lib/merge_import_config.py" \
    --current "$STATE_DIR/openclaw.json" \
    --imported "$TMP_DIR/state/openclaw.json" \
    --output "$STATE_DIR/openclaw.json"
fi

if [[ -d "$TMP_DIR/state/agents" ]]; then
  mkdir -p "$STATE_DIR/agents"
  cp -R "$TMP_DIR/state/agents/." "$STATE_DIR/agents/"
fi

if [[ -d "$TMP_DIR/workspace" ]]; then
  cp -R "$TMP_DIR/workspace/." "$WORKSPACE_PATH/"
fi

chown -R "$(openclaw_user):$(openclaw_user)" "$WORKSPACE_PATH" 2>/dev/null || true

log "import completed"
log "backup: $BACKUP_DIR"
log "re-applying overlay runtime and config patch"
"$SCRIPT_DIR/install.sh"
