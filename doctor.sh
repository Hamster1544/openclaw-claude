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

CONFIG_PATH="$(config_path)"
OVERLAY_HOME="$(overlay_home)"
RELAY_PATH="$(relay_target_path)"
BRIDGE_PATH="$OVERLAY_HOME/openclaw_bridge_server.py"
OPENCLAW_USER="$(openclaw_user)"
OPENCLAW_HOME="$(openclaw_home)"
TARGET_USER="$(target_user)"

log "config: $CONFIG_PATH"
[[ -f "$CONFIG_PATH" ]] || die "missing config: $CONFIG_PATH"
[[ -f "$RELAY_PATH" ]] || die "missing relay: $RELAY_PATH"
[[ -f "$BRIDGE_PATH" ]] || die "missing bridge: $BRIDGE_PATH"
[[ -x "$OVERLAY_HOME/venv/bin/python" ]] || die "missing bridge venv: $OVERLAY_HOME/venv/bin/python"
id -u "$OPENCLAW_USER" >/dev/null 2>&1 || die "missing unix user: $OPENCLAW_USER"
[[ -d "$OPENCLAW_HOME" ]] || die "missing user home: $OPENCLAW_HOME"

python3 - "$CONFIG_PATH" <<'PY'
import json, sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text())
defaults = ((cfg.get("agents") or {}).get("defaults") or {})
cli = ((defaults.get("cliBackends") or {}).get("claude-cli") or {})
model = defaults.get("model")
if isinstance(model, dict):
    primary = model.get("primary")
else:
    primary = model
print("model.primary =", primary)
print("claude-cli.command =", cli.get("command"))
print("claude-cli.serialize =", cli.get("serialize"))
print("claude-cli.sessionMode =", cli.get("sessionMode"))
PY

sudo -n -u "$OPENCLAW_USER" claude --version >/dev/null 2>&1 || true
openclaw gateway status || true
if [[ "$TARGET_USER" != "root" ]]; then
  sudo -u "$TARGET_USER" HOME="$(target_home)" openclaw gateway status || true
fi
log "doctor finished"
