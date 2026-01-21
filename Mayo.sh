#!/usr/bin/env bash
set -euo pipefail

log_dir="${TMPDIR:-/tmp}"
log_file="${log_dir%/}/pipe-launch.log"

uv_shared="/srv/tools/uv/current/uv"

cmd=(pipeline maya)

if command -v uv >/dev/null 2>&1; then
  cmd=(uv run "${cmd[@]}")
elif [[ -x "$uv_shared" ]]; then
  cmd=("$uv_shared" run "${cmd[@]}")
fi

nohup "${cmd[@]}" >>"$log_file" 2>&1 &
sleep 1
exit 0
