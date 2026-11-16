#!/usr/bin/env bash
# SYSTEM MIND X — Local Development Setup Wrapper (macOS & Linux)
# Strictly unprivileged. Never run with sudo.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Safety check: prevent execution as root / sudo
if [ "$(id -u)" -eq 0 ]; then
    echo "[!] ERROR: Do not run setup_dev.sh as root or with sudo." >&2
    echo "    SYSTEM MIND X requires unprivileged user-space installation." >&2
    exit 1
fi

# Ensure Python 3 is available
if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] ERROR: python3 is not installed or not in PATH." >&2
    echo "    Please install Python 3.10+ (macOS: brew install python@3.12)" >&2
    exit 1
fi

# Default to 'bootstrap' command if no argument passed
CMD="${1:-bootstrap}"
shift || true

exec python3 "${ROOT_DIR}/tools/dev_setup.py" "${CMD}" "$@"
