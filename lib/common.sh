#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[overlay] %s\n' "$*"
}

die() {
  printf '[overlay] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

ensure_supported_platform() {
  local os
  os="$(uname -s)"
  case "$os" in
    Linux) ;;
    *) die "unsupported platform: $os (Linux only in the current overlay build)" ;;
  esac
}

require_root() {
  [[ "$(id -u)" -eq 0 ]] || die "run this script as root"
}

repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

target_home() {
  printf '%s\n' "/root"
}

state_dir() {
  printf '%s\n' "/root/.openclaw"
}

config_path() {
  printf '%s\n' "/root/.openclaw/openclaw.json"
}

overlay_home() {
  printf '%s\n' "/opt/openclaw-bridge"
}

relay_target_path() {
  printf '%s\n' "/usr/local/bin/claude-openclaw-relay"
}

openclaw_user() {
  printf '%s\n' "${OVERLAY_OPENCLAW_USER:-openclaw}"
}

openclaw_home() {
  printf '%s\n' "/home/$(openclaw_user)"
}

backup_dir() {
  printf '%s/backups/overlay-%s\n' "$(state_dir)" "$(date +%Y%m%d-%H%M%S)"
}

detect_workspace() {
  local cfg
  cfg="$(config_path)"
  python3 - "$cfg" <<'PY'
import json, sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
default = "/home/openclaw/workspace"
if not cfg_path.exists():
    print(default)
    raise SystemExit(0)

try:
    data = json.loads(cfg_path.read_text())
except Exception:
    print(default)
    raise SystemExit(0)

agents = data.get("agents") or {}
defaults = agents.get("defaults") or {}
workspace = str(defaults.get("workspace") or "").strip()
print(workspace or default)
PY
}

restart_gateway() {
  if command -v openclaw >/dev/null 2>&1; then
    openclaw gateway restart >/dev/null 2>&1 || true
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart openclaw-gateway.service >/dev/null 2>&1 || true
    systemctl --user restart openclaw-gateway.service >/dev/null 2>&1 || true
  fi
}
