#!/bin/bash
# Show onboard (dark Droid theme, full keyboard layout) as an
# override-redirect overlay over the deck cards. Started with --xid so the
# window is never mapped as a normal/dock window -- the WM never sees it and
# Mixxx is NOT resized (avoids v3d GL resize hangs). Focus stays on Mixxx;
# the keyboard types via XTEST into the focused widget.
export DISPLAY=${DISPLAY:-:0}

if pgrep -f '[o]nboard' >/dev/null; then
    exit 0
fi

rm -f /tmp/osk.xid
onboard --xid --theme=Droid --layout="Full Keyboard" >/tmp/osk.xid 2>/dev/null &
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

python3 - "$XID" <<'PYEOF'
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
