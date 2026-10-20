#!/usr/bin/env sh
# Install or upgrade the System-1 gateway for the current user (Linux/macOS).
# Creates a venv under ~/.system1-gateway, copies the package into it (offline, no pip), creates
# the user config if missing, and prints the `claude mcp add` command. Re-run to upgrade.
# The installed copy does not depend on this repo, so the clone can be moved or deleted afterwards.
set -eu

REPO="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${SYSTEM1_INSTALL_DIR:-$HOME/.system1-gateway}"
VENV="$INSTALL_DIR/venv"
VPY="$VENV/bin/python"

# tomllib needs Python 3.11+.
PYTHON=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON="$c"; break
  fi
done
[ -n "$PYTHON" ] || { echo "Python 3.11+ not found. Install it and re-run." >&2; exit 1; }

# Reuse a working venv (same logic as install.ps1, where a running gateway locks the venv's python);
# rebuild only if it is missing or its base Python is gone.
# --without-pip also avoids needing the separate python3-venv/ensurepip package on Debian/Ubuntu.
if ! "$VPY" -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  "$PYTHON" -m venv --clear --without-pip "$VENV"
fi

PURELIB="$("$VPY" -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
: "${PURELIB:?could not locate the venv site-packages}"
rm -rf "$PURELIB/system1_gateway"
cp -R "$REPO/system1_gateway" "$PURELIB/system1_gateway"
find "$PURELIB/system1_gateway" -name __pycache__ -type d -prune -exec rm -rf {} +

# -I (isolated): ignore the caller's cwd and PYTHON* env vars, so no project can shadow our imports.
VERSION="$("$VPY" -I -c 'import system1_gateway; print(system1_gateway.__version__)')"
CONFIG="$("$VPY" -I -c 'from system1_gateway.config import config_path; print(config_path())')"

if [ -f "$CONFIG" ]; then
  echo "Kept existing config: $CONFIG"
else
  mkdir -p "$(dirname "$CONFIG")"
  cp "$REPO/config.example.toml" "$CONFIG"
  echo "Created config: $CONFIG"
fi

echo
echo "Installed system1-gateway $VERSION into $VENV"
echo
echo "Register it with Claude Code (user scope, all projects):"
echo "  claude mcp add --scope user --transport stdio system1 -- \"$VPY\" -I -m system1_gateway"
