#!/bin/bash
nohup "$(dirname "$0")/.venv/bin/python" pipeline houdini >> "${TMPDIR:-/tmp}/pipe-launch.log" 2>&1 &
sleep 1
exit 0
