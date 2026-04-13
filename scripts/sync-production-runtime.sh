#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REMOTE_HOST="${OVERLAY_REMOTE_HOST:-}"
REMOTE_USER="${OVERLAY_REMOTE_USER:-root}"
REMOTE_RELAY="${OVERLAY_REMOTE_RELAY:-/usr/local/bin/claude-openclaw-relay}"
REMOTE_BRIDGE="${OVERLAY_REMOTE_BRIDGE:-/opt/openclaw-bridge/openclaw_bridge_server.py}"

[[ -n "$REMOTE_HOST" ]] || {
  echo "Set OVERLAY_REMOTE_HOST before running this script." >&2
  exit 1
}

scp "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_RELAY}" "$REPO_ROOT/runtime/claude-openclaw-relay"
scp "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BRIDGE}" "$REPO_ROOT/runtime/openclaw_bridge_server.py"
chmod +x "$REPO_ROOT/runtime/claude-openclaw-relay" "$REPO_ROOT/runtime/openclaw_bridge_server.py"
echo "runtime synced from ${REMOTE_USER}@${REMOTE_HOST}"
