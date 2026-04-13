#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ensure_supported_platform
require_root
require_cmd python3
require_cmd openclaw
require_cmd claude
require_cmd sudo
require_cmd setpriv

REPO_ROOT="$(repo_root)"
TARGET_HOME="$(target_home)"
STATE_DIR="$(state_dir)"
CONFIG_PATH="$(config_path)"
OVERLAY_HOME="$(overlay_home)"
RELAY_PATH="$(relay_target_path)"
BACKUP_DIR="$(backup_dir)"
WORKSPACE_PATH="${OVERLAY_WORKSPACE:-$(detect_workspace)}"
MODEL_REF="${OVERLAY_MODEL:-claude-cli/claude-opus-4-6}"
OPENCLAW_USER="$(openclaw_user)"
OPENCLAW_HOME="$(openclaw_home)"

sync_claude_credentials() {
  local pattern src target found
  mkdir -p "$OPENCLAW_HOME"
  found=0
  for src in /root/.claude /root/.claude.json /root/.claude.json.backup /root/.claude-config /root/.claude-config.json /root/.claude*; do
    [[ -e "$src" ]] || continue
    found=1
    target="$OPENCLAW_HOME/$(basename "$src")"
    rm -rf "$target"
    cp -R "$src" "$target"
  done
  chown -R "$OPENCLAW_USER:$OPENCLAW_USER" "$OPENCLAW_HOME"
  if [[ "$found" -eq 0 ]]; then
    log "no /root/.claude* credentials found to sync"
  else
    log "claude credentials synced into $OPENCLAW_HOME"
  fi
}

install_sudoers() {
  local sudoers_path=/etc/sudoers.d/openclaw-overlay
  printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$OPENCLAW_USER" >"$sudoers_path"
  chmod 440 "$sudoers_path"
}

render_runtime_paths() {
  local claude_bin openclaw_bin setpriv_bin sudo_bin python3_bin env_bin
  claude_bin="$(command -v claude)"
  openclaw_bin="$(command -v openclaw)"
  setpriv_bin="$(command -v setpriv)"
  sudo_bin="$(command -v sudo)"
  python3_bin="$(command -v python3)"
  env_bin="$(command -v env)"
  python3 - "$RELAY_PATH" "$OVERLAY_HOME/openclaw_bridge_server.py" \
    "$claude_bin" "$openclaw_bin" "$setpriv_bin" "$sudo_bin" "$python3_bin" "$env_bin" <<'PY'
from pathlib import Path
import sys

relay_path = Path(sys.argv[1])
bridge_path = Path(sys.argv[2])
claude_bin, openclaw_bin, setpriv_bin, sudo_bin, python3_bin, env_bin = sys.argv[3:]

relay = relay_path.read_text()
relay = relay.replace('CLAUDE_BIN="/usr/bin/claude"', f'CLAUDE_BIN="{claude_bin}"')
relay = relay.replace('SET_PRIV="/usr/bin/setpriv"', f'SET_PRIV="{setpriv_bin}"')
relay_path.write_text(relay)

bridge = bridge_path.read_text()
bridge = bridge.replace('BIN="/usr/bin/openclaw"', f'BIN="{openclaw_bin}"')
bridge = bridge.replace('"/usr/bin/sudo"', f'"{sudo_bin}"')
bridge = bridge.replace('"/usr/bin/python3"', f'"{python3_bin}"')
bridge = bridge.replace('"/usr/bin/env"', f'"{env_bin}"')
bridge_path.write_text(bridge)
PY
}

log "target home: $TARGET_HOME"
log "state dir: $STATE_DIR"
log "workspace: $WORKSPACE_PATH"
log "model: $MODEL_REF"

mkdir -p "$BACKUP_DIR" "$OVERLAY_HOME" "$OPENCLAW_HOME" "$WORKSPACE_PATH" "$STATE_DIR"

if [[ -f "$CONFIG_PATH" ]]; then
  cp "$CONFIG_PATH" "$BACKUP_DIR/openclaw.json.bak"
fi

if ! id -u "$OPENCLAW_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$OPENCLAW_USER"
fi

cp "$REPO_ROOT/runtime/claude-openclaw-relay" "$RELAY_PATH"
cp "$REPO_ROOT/runtime/openclaw_bridge_server.py" "$OVERLAY_HOME/openclaw_bridge_server.py"
chmod +x "$RELAY_PATH" "$OVERLAY_HOME/openclaw_bridge_server.py"
render_runtime_paths

if [[ -f "$REPO_ROOT/runtime/requirements.txt" ]]; then
  python3 -m venv "$OVERLAY_HOME/venv"
  "$OVERLAY_HOME/venv/bin/pip" install --upgrade pip >/dev/null
  "$OVERLAY_HOME/venv/bin/pip" install -r "$REPO_ROOT/runtime/requirements.txt" >/dev/null
fi

chown -R "$OPENCLAW_USER:$OPENCLAW_USER" "$OPENCLAW_HOME" "$WORKSPACE_PATH"
sync_claude_credentials
install_sudoers

python3 "$REPO_ROOT/lib/patch_openclaw_config.py" \
  --config "$CONFIG_PATH" \
  --relay-path "$RELAY_PATH" \
  --bridge-path "$OVERLAY_HOME/openclaw_bridge_server.py" \
  --workspace "$WORKSPACE_PATH" \
  --model "$MODEL_REF" \
  --write

restart_gateway

log "overlay installed"
log "backup: $BACKUP_DIR"
log "run ./doctor.sh next"
