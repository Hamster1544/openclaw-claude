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

home_for_user() {
  local user="$1"
  getent passwd "$user" 2>/dev/null | cut -d: -f6
}

detect_target_home() {
  local guessed_home
  if [[ -n "${OVERLAY_TARGET_HOME:-}" ]]; then
    printf '%s\n' "$OVERLAY_TARGET_HOME"
    return
  fi
  if [[ -n "${OVERLAY_CONFIG_PATH:-}" ]]; then
    dirname "$(dirname "$OVERLAY_CONFIG_PATH")"
    return
  fi
  if [[ -f /root/.openclaw/openclaw.json ]]; then
    printf '%s\n' "/root"
    return
  fi
  if [[ -n "${SUDO_USER:-}" ]]; then
    guessed_home="$(home_for_user "$SUDO_USER")"
    if [[ -n "$guessed_home" && -f "$guessed_home/.openclaw/openclaw.json" ]]; then
      printf '%s\n' "$guessed_home"
      return
    fi
  fi
  if [[ -f "$HOME/.openclaw/openclaw.json" ]]; then
    printf '%s\n' "$HOME"
    return
  fi
  if [[ -n "${SUDO_USER:-}" ]]; then
    guessed_home="$(home_for_user "$SUDO_USER")"
    if [[ -n "$guessed_home" ]]; then
      printf '%s\n' "$guessed_home"
      return
    fi
  fi
  printf '%s\n' "$HOME"
}

target_home() {
  detect_target_home
}

state_dir() {
  if [[ -n "${OVERLAY_STATE_DIR:-}" ]]; then
    printf '%s\n' "$OVERLAY_STATE_DIR"
  else
    printf '%s/.openclaw\n' "$(target_home)"
  fi
}

config_path() {
  if [[ -n "${OVERLAY_CONFIG_PATH:-}" ]]; then
    printf '%s\n' "$OVERLAY_CONFIG_PATH"
  else
    printf '%s/openclaw.json\n' "$(state_dir)"
  fi
}

target_user() {
  local cfg
  if [[ -n "${OVERLAY_TARGET_USER:-}" ]]; then
    printf '%s\n' "$OVERLAY_TARGET_USER"
    return
  fi
  cfg="$(config_path)"
  if [[ -f "$cfg" ]]; then
    stat -c '%U' "$cfg"
    return
  fi
  if [[ "$(target_home)" == "/root" ]]; then
    printf '%s\n' "root"
    return
  fi
  basename "$(target_home)"
}

overlay_home() {
  printf '%s\n' "${OVERLAY_HOME:-/opt/openclaw-bridge}"
}

relay_target_path() {
  printf '%s\n' "${OVERLAY_RELAY_PATH:-/usr/local/bin/claude-openclaw-relay}"
}

openclaw_user() {
  printf '%s\n' "${OVERLAY_OPENCLAW_USER:-openclaw}"
}

openclaw_home() {
  local user home
  if [[ -n "${OVERLAY_OPENCLAW_HOME:-}" ]]; then
    printf '%s\n' "$OVERLAY_OPENCLAW_HOME"
    return
  fi
  user="$(openclaw_user)"
  home="$(home_for_user "$user")"
  if [[ -n "$home" ]]; then
    printf '%s\n' "$home"
  else
    printf '%s\n' "/home/$user"
  fi
}

claude_source_home() {
  if [[ -n "${OVERLAY_CLAUDE_SOURCE_HOME:-}" ]]; then
    printf '%s\n' "$OVERLAY_CLAUDE_SOURCE_HOME"
  else
    printf '%s\n' "$(target_home)"
  fi
}

backup_dir() {
  printf '%s/backups/overlay-%s\n' "$(state_dir)" "$(date +%Y%m%d-%H%M%S)"
}

detect_workspace() {
  local cfg
  cfg="$(config_path)"
  python3 - "$cfg" "$(target_home)" <<'PY'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
target_home = Path(sys.argv[2])
default = str(target_home / "openclaw-workspace")
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
if workspace:
    print(workspace)
    raise SystemExit(0)

for entry in agents.get("list") or []:
    if isinstance(entry, dict) and entry.get("default") is True:
        value = str(entry.get("workspace") or "").strip()
        if value:
            print(value)
            raise SystemExit(0)

print(default)
PY
}

ensure_runtime_user() {
  local user home
  user="$(openclaw_user)"
  home="$(openclaw_home)"
  if ! id -u "$user" >/dev/null 2>&1; then
    useradd -m -d "$home" -s /bin/bash "$user"
  fi
}

ensure_acl_tool() {
  if command -v setfacl >/dev/null 2>&1; then
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y >/dev/null 2>&1 || true
    apt-get install -y acl >/dev/null 2>&1 || true
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y acl >/dev/null 2>&1 || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y acl >/dev/null 2>&1 || true
  elif command -v zypper >/dev/null 2>&1; then
    zypper --non-interactive install acl >/dev/null 2>&1 || true
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm acl >/dev/null 2>&1 || true
  fi
}

list_configured_workspaces() {
  local cfg
  cfg="$(config_path)"
  python3 - "$cfg" "$(target_home)" <<'PY'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
target_home = Path(sys.argv[2])
default_fallback = str(target_home / "openclaw-workspace")
if not cfg_path.exists():
    print(default_fallback)
    raise SystemExit(0)

try:
    data = json.loads(cfg_path.read_text())
except Exception:
    print(default_fallback)
    raise SystemExit(0)

agents = data.get("agents") or {}
defaults = agents.get("defaults") or {}
default_workspace = str(defaults.get("workspace") or "").strip() or default_fallback

seen = set()
if default_workspace and default_workspace not in seen:
    print(default_workspace)
    seen.add(default_workspace)

for entry in agents.get("list") or []:
    if not isinstance(entry, dict):
        continue
    value = str(entry.get("workspace") or default_workspace).strip()
    if value and value not in seen:
        print(value)
        seen.add(value)
PY
}

grant_parent_traversal() {
  local path="$1" user current
  user="$(openclaw_user)"
  current="$(dirname "$path")"
  while [[ -n "$current" && "$current" != "/" && "$current" != "." ]]; do
    if command -v setfacl >/dev/null 2>&1; then
      setfacl -m "u:${user}:x" "$current" >/dev/null 2>&1 || true
    fi
    current="$(dirname "$current")"
  done
  if command -v setfacl >/dev/null 2>&1; then
    setfacl -m "u:${user}:x" "/" >/dev/null 2>&1 || true
  fi
}

grant_workspace_access() {
  local workspace user
  workspace="$1"
  user="$(openclaw_user)"

  [[ -d "$workspace" ]] || return 0

  ensure_acl_tool

  if command -v setfacl >/dev/null 2>&1; then
    grant_parent_traversal "$workspace"
    setfacl -R -m "u:${user}:rwx" "$workspace" >/dev/null 2>&1 || true
    setfacl -d -m "u:${user}:rwx" "$workspace" >/dev/null 2>&1 || true
    return 0
  fi

  if [[ "${OVERLAY_TAKE_WORKSPACE_OWNERSHIP:-1}" == "1" ]]; then
    chown -R "$user:$user" "$workspace"
    return 0
  fi

  log "workspace access was not changed for $workspace; set OVERLAY_TAKE_WORKSPACE_OWNERSHIP=1 if Claude cannot read/write it"
}

grant_all_workspace_access() {
  local workspace
  while IFS= read -r workspace; do
    [[ -n "$workspace" ]] || continue
    grant_workspace_access "$workspace"
  done < <(list_configured_workspaces)
}

restart_gateway() {
  local target_user_value target_home_value
  target_user_value="$(target_user)"
  target_home_value="$(target_home)"

  if command -v openclaw >/dev/null 2>&1; then
    openclaw gateway restart >/dev/null 2>&1 || true
    if [[ "$target_user_value" != "root" ]]; then
      sudo -u "$target_user_value" HOME="$target_home_value" openclaw gateway restart >/dev/null 2>&1 || true
    fi
  fi
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart openclaw-gateway.service >/dev/null 2>&1 || true
    if [[ "$target_user_value" != "root" ]]; then
      sudo -u "$target_user_value" systemctl --user restart openclaw-gateway.service >/dev/null 2>&1 || true
    else
      systemctl --user restart openclaw-gateway.service >/dev/null 2>&1 || true
    fi
  fi
}
