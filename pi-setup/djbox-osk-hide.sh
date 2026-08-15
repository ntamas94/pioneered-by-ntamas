#!/bin/bash
# Hide the on-screen keyboard overlay: unmap the window but keep onboard
# running, so the next show is instant. Falls back to killing it.
export DISPLAY=${DISPLAY:-:0}

STATE=/tmp/osk.state

if [ -f "$STATE" ]; then
    read -r PID XID < "$STATE"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        python3 - "$XID" <<'PYEOF' && exit 0
import sys
from Xlib import display

xid = int(sys.argv[1])
d = display.Display()
win = d.create_resource_object('window', xid)
win.unmap()
d.sync()
PYEOF
    fi
    rm -f "$STATE"
fi
pkill -f '[o]nboard' 2>/dev/null
pkill -f '[m]atchbox-keyboard' 2>/dev/null
exit 0
