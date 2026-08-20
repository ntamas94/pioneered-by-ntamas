#!/bin/bash
# One-shot health check for the DJ box: controller, audio, MIDI, display unlock.
card=$(awk '/\[DDJ/ {print $1}' /proc/asound/cards | head -1)
dev=$(lsusb | sed -nE 's/.*Device 0*([0-9]+): ID 2b73:0020.*/\1/p' | head -1)

echo "DDJ-1000 USB      : ${dev:-nincs}"
echo "ALSA card         : ${card:-nincs}"
[ -n "$card" ] && echo "audio playback    : $(head -1 /proc/asound/card$card/pcm0p/sub0/status)"
echo "bridge service    : $(systemctl is-active djbox-ddj-bridge)"
echo "Mixxx             : $(pgrep -f 'mixxx --fullScreen' >/dev/null && echo fut || echo all)"
echo "handshake         : $(journalctl -t djbox-ddj -b --no-pager | grep -c 'authenticated') alkalom"

if [ -n "$dev" ] && [ -r /sys/kernel/debug/usb/usbmon/1u ]; then
    timeout 4 cat /sys/kernel/debug/usb/usbmon/1u > /tmp/djbox-status.usbmon 2>/dev/null
    iso=$(grep -c ":1:00$dev:1" /tmp/djbox-status.usbmon)
    midi=$(grep -c ":1:00$dev:4" /tmp/djbox-status.usbmon)
    hid=$(grep -c ":1:00$dev:7" /tmp/djbox-status.usbmon)
    echo "4 mp alatt        : audio $iso, MIDI ki $midi, HID poll $hid"
fi
