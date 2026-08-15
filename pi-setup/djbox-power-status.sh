#!/bin/sh
# One line describing the Pi's power/throttle state, for the conky overlay.
#
# vcgencmd reports a bitmask: 0x1 under-voltage now, 0x2 ARM capped now,
# 0x4 throttled now, 0x8 soft temperature limit now, and the same four bits
# shifted 16 places to record that it happened at some point since boot.
# Latched bits only clear on reboot, so the live bits are what matter.

raw=$(vcgencmd get_throttled 2>/dev/null) || { echo "power unknown"; exit 0; }
value=${raw#*=}
n=$((value))

live=$((n & 0xF))
latched=$((n & 0xF0000))

if [ $((live & 0x1)) -ne 0 ]; then
    echo "UNDER-VOLTAGE - check PSU"
elif [ $((live & 0x4)) -ne 0 ]; then
    echo "THROTTLED NOW"
elif [ $((live & 0x8)) -ne 0 ]; then
    echo "TEMP LIMIT"
elif [ "$latched" -ne 0 ]; then
    echo "ok (throttled earlier)"
else
    echo "ok"
fi
