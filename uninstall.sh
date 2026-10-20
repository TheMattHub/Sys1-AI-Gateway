#!/usr/bin/env sh
# Remove the System-1 gateway for the current user. Keeps the config unless --purge is given.
set -eu

INSTALL_DIR="${SYSTEM1_INSTALL_DIR:-$HOME/.system1-gateway}"
PURGE=0
if [ "${1:-}" = "--purge" ]; then PURGE=1; fi

if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user system1 || true  # fine if it was never registered
fi

if [ -d "$INSTALL_DIR/venv" ]; then
  rm -rf "$INSTALL_DIR/venv"
  echo "Removed $INSTALL_DIR/venv"
fi

# Engines (Laya's venv and checkpoint are several GB) and logs: only with --purge.
for dir in engines logs; do
  [ -d "$INSTALL_DIR/$dir" ] || continue
  if [ "$PURGE" = 1 ]; then rm -rf "${INSTALL_DIR:?}/$dir"; echo "Removed $INSTALL_DIR/$dir"
  else echo "Kept $INSTALL_DIR/$dir (re-run with --purge to remove it)"; fi
done
echo "If you set Laya to start at login, remove it: systemctl --user disable --now system1-laya (Linux)"
echo "or rm ~/Library/LaunchAgents/*system1-laya*.plist (macOS)."
rmdir "$INSTALL_DIR" 2>/dev/null || true  # only if empty

# A custom SYSTEM1_CONFIG may live in a shared folder: purge only that file, never its directory.
CONFIG_PATH="${SYSTEM1_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/system1}"
if [ "$PURGE" = 1 ]; then
  rm -rf "$CONFIG_PATH"
  echo "Removed $CONFIG_PATH"
else
  echo "Kept config: $CONFIG_PATH (re-run with --purge to remove it)"
fi
