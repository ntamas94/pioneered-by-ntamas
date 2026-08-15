#!/bin/bash
# Show the on-screen keyboard overlay. onboard is started ONCE (--xid, so the
# WM never sees it and Mixxx is not resized) and then kept alive; showing and
# hiding is just mapping/unmapping its override-redirect window, which makes
# the keyboard appear instantly instead of paying the ~3 s process start.
export DISPLAY=${DISPLAY:-:0}

STATE=/tmp/osk.state    # "<pid> <xid>"

map_win() {
    python3 - "$1" <<'PYEOF'
import sys
from Xlib import display, X

xid = int(sys.argv[1])
d = display.Display()
win = d.create_resource_object('window', xid)
sw = d.screen().width_in_pixels
sh = d.screen().height_in_pixels
kh = int(sh * 0.40)          # keyboard covers the deck-card strip
win.change_attributes(override_redirect=1)
win.configure(x=0, y=sh - kh, width=sw, height=kh)
win.map()
win.configure(stack_mode=X.Above)
d.sync()
PYEOF
}

# Fast path: onboard already running, just map its window again.
if [ -f "$STATE" ]; then
    read -r PID XID < "$STATE"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        map_win "$XID" && exit 0
    fi
    rm -f "$STATE"
fi

pkill -f '[o]nboard' 2>/dev/null
rm -f /tmp/osk.xid
onboard --xid --theme=Droid --layout="Full Keyboard" >/tmp/osk.xid 2>/dev/null &
PID=$!
XID=""
for _ in $(seq 1 100); do
    XID=$(head -1 /tmp/osk.xid 2>/dev/null)
    [ -n "$XID" ] && break
    sleep 0.1
done
if [ -z "$XID" ]; then
    pkill -f '[o]nboard'
    exit 1
fi
echo "$PID $XID" > "$STATE"
map_win "$XID"
