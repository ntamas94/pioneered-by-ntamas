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

# Deliberately not waiting for the bridge to authenticate first. It holds its
# answer until audio is streaming -- which is what the unit itself waits for
# before it will take the screens off NO AUDIO DRIVER -- and the audio is what
# this script is here to bring back. Waiting for the handshake before
# restarting Mixxx makes the two wait for each other and neither ever happens.

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
