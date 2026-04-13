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
require_cmd env

REPO_ROOT="$(repo_root)"
TARGET_HOME="$(target_home)"
TARGET_USER="$(target_user)"
STATE_DIR="$(state_dir)"
CONFIG_PATH="$(config_path)"
OVERLAY_HOME="$(overlay_home)"
RELAY_PATH="$(relay_target_path)"
BRIDGE_PATH="$OVERLAY_HOME/openclaw_bridge_server.py"
BRIDGE_PYTHON="$OVERLAY_HOME/venv/bin/python"
BACKUP_DIR="$(backup_dir)"
WORKSPACE_PATH="${OVERLAY_WORKSPACE:-$(detect_workspace)}"
MODEL_REF="${OVERLAY_MODEL:-claude-cli/claude-opus-4-6}"
MODEL_REWRITE_MODE="${OVERLAY_MODEL_REWRITE_MODE:-claude-only}"
FORCE_DEFAULT_MODEL="${OVERLAY_FORCE_DEFAULT_MODEL:-0}"
FORCE_AGENT_MODELS="${OVERLAY_FORCE_AGENT_MODELS:-0}"
ENSURE_NEWS_AGENT="${OVERLAY_ENSURE_NEWS_AGENT:-0}"
OPENCLAW_USER="$(openclaw_user)"
OPENCLAW_HOME="$(openclaw_home)"
CLAUDE_SOURCE_HOME="$(claude_source_home)"

sync_claude_credentials() {
  local src target found
  mkdir -p "$OPENCLAW_HOME"
  found=0
  for src in \
    "$CLAUDE_SOURCE_HOME/.claude" \
    "$CLAUDE_SOURCE_HOME/.claude.json" \
    "$CLAUDE_SOURCE_HOME/.claude.json.backup" \
    "$CLAUDE_SOURCE_HOME/.claude-config" \
    "$CLAUDE_SOURCE_HOME/.claude-config.json" \
    "$CLAUDE_SOURCE_HOME"/.claude*; do
    [[ -e "$src" ]] || continue
    found=1
    target="$OPENCLAW_HOME/$(basename "$src")"
    rm -rf "$target"
    cp -R "$src" "$target"
  done
  chown -R "$OPENCLAW_USER:$OPENCLAW_USER" "$OPENCLAW_HOME"
  if [[ "$found" -eq 0 ]]; then
    log "no Claude credentials found in $CLAUDE_SOURCE_HOME"
  else
    log "Claude credentials synced from $CLAUDE_SOURCE_HOME into $OPENCLAW_HOME"
  fi
}

install_sudoers() {
  local sudoers_path=/etc/sudoers.d/openclaw-overlay
  printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$OPENCLAW_USER" >"$sudoers_path"
  chmod 440 "$sudoers_path"
}

render_runtime_files() {
  local claude_bin openclaw_bin setpriv_bin sudo_bin python3_bin env_bin
  claude_bin="$(command -v claude)"
  openclaw_bin="$(command -v openclaw)"
  setpriv_bin="$(command -v setpriv)"
  sudo_bin="$(command -v sudo)"
  python3_bin="$(command -v python3)"
  env_bin="$(command -v env)"

  python3 - "$RELAY_PATH" "$BRIDGE_PATH" \
    "$claude_bin" "$openclaw_bin" "$setpriv_bin" "$sudo_bin" "$python3_bin" "$env_bin" \
    "$CONFIG_PATH" "$STATE_DIR" "$BRIDGE_PATH" "$BRIDGE_PYTHON" "$OPENCLAW_USER" "$OPENCLAW_HOME" "$RELAY_PATH" "$WORKSPACE_PATH" <<'PY'
from pathlib import Path
import sys

relay_path = Path(sys.argv[1])
bridge_path = Path(sys.argv[2])
(
    claude_bin,
    openclaw_bin,
    setpriv_bin,
    sudo_bin,
    python3_bin,
    env_bin,
    config_path,
    state_dir,
    rendered_bridge_path,
    bridge_python,
    runtime_user,
    runtime_home,
    relay_target,
    default_workspace,
) = sys.argv[3:]

replacements = {
    "__OVERLAY_CLAUDE_BIN__": claude_bin,
    "__OVERLAY_SETPRIV_BIN__": setpriv_bin,
    "__OVERLAY_CONFIG_PATH__": config_path,
    "__OVERLAY_STATE_DIR__": state_dir,
    "__OVERLAY_BRIDGE_PATH__": rendered_bridge_path,
    "__OVERLAY_BRIDGE_PYTHON__": bridge_python,
    "__OVERLAY_RUNTIME_USER__": runtime_user,
    "__OVERLAY_RUNTIME_HOME__": runtime_home,
    "__OVERLAY_OPENCLAW_BIN__": openclaw_bin,
    "__OVERLAY_SUDO_BIN__": sudo_bin,
    "__OVERLAY_PYTHON3_BIN__": python3_bin,
    "__OVERLAY_ENV_BIN__": env_bin,
    "__OVERLAY_RELAY_PATH__": relay_target,
    "__OVERLAY_DEFAULT_WORKSPACE__": default_workspace,
}

for path in (relay_path, bridge_path):
    text = path.read_text()
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text)
PY
  chmod +x "$RELAY_PATH" "$BRIDGE_PATH"
}

log "target user: $TARGET_USER"
log "target home: $TARGET_HOME"
log "state dir: $STATE_DIR"
log "config: $CONFIG_PATH"
log "workspace: $WORKSPACE_PATH"
log "runtime user: $OPENCLAW_USER"
log "model default: $MODEL_REF"
log "rewrite mode: $MODEL_REWRITE_MODE"

mkdir -p "$BACKUP_DIR" "$OVERLAY_HOME" "$STATE_DIR"

if [[ -f "$CONFIG_PATH" ]]; then
  cp "$CONFIG_PATH" "$BACKUP_DIR/openclaw.json.bak"
fi

ensure_runtime_user
mkdir -p "$OPENCLAW_HOME" "$WORKSPACE_PATH"

cp "$REPO_ROOT/runtime/claude-openclaw-relay" "$RELAY_PATH"
cp "$REPO_ROOT/runtime/openclaw_bridge_server.py" "$BRIDGE_PATH"

if [[ -f "$REPO_ROOT/runtime/requirements.txt" ]]; then
  python3 -m venv "$OVERLAY_HOME/venv"
  "$OVERLAY_HOME/venv/bin/pip" install --upgrade pip >/dev/null
  "$OVERLAY_HOME/venv/bin/pip" install -r "$REPO_ROOT/runtime/requirements.txt" >/dev/null
fi

render_runtime_files
chown -R "$OPENCLAW_USER:$OPENCLAW_USER" "$OPENCLAW_HOME" "$OVERLAY_HOME"

sync_claude_credentials
install_sudoers
grant_workspace_access "$WORKSPACE_PATH"

python3 "$REPO_ROOT/lib/patch_openclaw_config.py" \
  --config "$CONFIG_PATH" \
  --relay-path "$RELAY_PATH" \
  --bridge-path "$BRIDGE_PATH" \
  --workspace "$WORKSPACE_PATH" \
  --model "$MODEL_REF" \
  --rewrite-mode "$MODEL_REWRITE_MODE" \
  --force-default-model "$FORCE_DEFAULT_MODEL" \
  --force-agent-models "$FORCE_AGENT_MODELS" \
  --ensure-news-agent "$ENSURE_NEWS_AGENT" \
  --runtime-user "$OPENCLAW_USER" \
  --runtime-home "$OPENCLAW_HOME" \
  --state-dir "$STATE_DIR" \
  --write

restart_gateway

log "overlay installed"
log "backup: $BACKUP_DIR"
log "run ./doctor.sh next"
