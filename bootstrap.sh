#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${OVERLAY_REPO_OWNER:-Hamster1544}"
REPO_NAME="${OVERLAY_REPO_NAME:-openclaw-claude}"
REPO_REF="${OVERLAY_REPO_REF:-main}"
IMPORT_ARCHIVE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --import)
      [[ $# -ge 2 ]] || {
        echo "[bootstrap] ERROR: --import requires a path" >&2
        exit 1
      }
      IMPORT_ARCHIVE="$2"
      shift 2
      ;;
    *)
      echo "[bootstrap] ERROR: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

ARCHIVE_URL="https://codeload.github.com/${REPO_OWNER}/${REPO_NAME}/tar.gz/refs/heads/${REPO_REF}"
ARCHIVE_PATH="$TMP_DIR/repo.tar.gz"

curl -fsSL "$ARCHIVE_URL" -o "$ARCHIVE_PATH"
tar -C "$TMP_DIR" -xzf "$ARCHIVE_PATH"

REPO_DIR="$(find "$TMP_DIR" -maxdepth 1 -mindepth 1 -type d -name "${REPO_NAME}-*" | head -n 1)"
[[ -n "$REPO_DIR" ]] || {
  echo "[bootstrap] ERROR: failed to unpack repository" >&2
  exit 1
}

cd "$REPO_DIR"
chmod +x ./*.sh runtime/claude-openclaw-relay scripts/*.sh

if [[ -n "$IMPORT_ARCHIVE" ]]; then
  ./import.sh "$IMPORT_ARCHIVE"
else
  ./install.sh
fi
