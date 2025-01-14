#!/bin/bash
nohup /usr/bin/env python pipeline nuke >> "${TMPDIR}/pipe-launch.log" 2>&1 &
sleep 1
exit 0
