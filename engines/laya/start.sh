#!/usr/bin/env sh
# Start laya-serve on loopback for the System-1 gateway (Linux/macOS). No-op if the port already answers.
# /system1:choose-model copies this file to ~/.system1-gateway/engines/laya/start.sh, next to the Laya venv,
# so it keeps working when the plugin updates. Output goes to laya-serve.log in the same folder.
# LAYA_DEVICE is left unset: laya-serve picks CUDA/MPS when available, otherwise the CPU.
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${LAYA_PORT:-8765}"
EXE="$ROOT/venv/bin/laya-serve"
[ -x "$EXE" ] || { echo "laya-serve not found at $EXE; run /system1:choose-model" >&2; exit 1; }
if curl -s --noproxy '*' -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "Port $PORT already answers (Laya running?)"; exit 0
fi
export LAYA_MODELS="${LAYA_MODELS:-typed-decisions}" LAYA_HOST=127.0.0.1 LAYA_PORT="$PORT"
exec "$EXE" >>"$ROOT/laya-serve.log" 2>&1
