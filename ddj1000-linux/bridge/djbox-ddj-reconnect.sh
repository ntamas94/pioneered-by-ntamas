#!/bin/bash
# Re-point Mixxx at the controller after it is plugged in or power-cycled.
#
# The DDJ-1000 re-enumerates as a new ALSA card, and Mixxx keeps holding the old
# (now dead) device, so it silently ends up with no output at all -- which the
# controller reports on its jog wheels as "NO AUDIO DRIVER". Run from a udev
# rule on device add.
set -u
exec >>/var/log/djbox-ddj-reconnect.log 2>&1
echo "$(date '+%F %T') DDJ-1000 appeared, waiting for its ALSA card"

for _ in $(seq 1 60); do
    card=$(grep -oE '^ *[0-9]+ \[DDJ' /proc/asound/cards | grep -oE '[0-9]+' | head -1)
    [ -n "$card" ] && break
    sleep 0.5
done
[ -n "${card:-}" ] || { echo "no ALSA card appeared"; exit 0; }

# Wait for the bridge to have the controller again: it re-authenticates on every
# re-enumeration, and restarting Mixxx before that leaves the screens locked.
for _ in $(seq 1 40); do
    journalctl -u djbox-ddj-bridge --since '60 seconds ago' --no-pager -o cat         | grep -q 'jog displays unlocked' && break
    sleep 1
done

# Wait for the desktop session: djbox-audio.sh restarts Mixxx, and the kiosk has
# to be up for it to come back.
for _ in $(seq 1 60); do
    pgrep -f 'mixxx --[f]ullScreen' >/dev/null && break
    sleep 1
done

# aplay -l can still be catching up right after the card node appears, so retry
# until the script actually finds the controller rather than giving up on the
# first "no USB sound card" and leaving Mixxx with no output.
for attempt in $(seq 1 10); do
    if su - dj -c '/usr/local/bin/djbox-audio.sh usb'; then
        break
    fi
    sleep 2
done
echo "$(date '+%F %T') done (card $card, attempt $attempt)"
