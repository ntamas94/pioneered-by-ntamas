#!/usr/bin/env bash
# Dump everything needed to decide whether a Linux ALSA quirk can be written
# for the Pioneer DDJ-1000, and to write it.
#
# Run on the Pi with the DDJ-1000 connected and powered from its own 12V
# adapter. Put the unit in forced MIDI mode first: hold SHIFT + PLAY/PAUSE on
# the left deck while switching it on (SLIP REVERSE lights up).
#
#   ./ddj1000-probe.sh            print the report
#   ./ddj1000-probe.sh -o FILE    also save it
#
# Background: the DDJ-1000 is USB 2b73:0020 — confirmed from AlphaTheta's own
# signed Windows driver INF (DDJ-1000Audio64.inf, DriverVer 10/11/2021),
# which binds "PIONEER DJ DDJ-1000" to USB\VID_2B73&PID_0020&MI_00 through the
# Windows USBAudio class service. That the vendor driver rides on the class
# framework, and is only ~50 KB, suggests the hardware is close to USB Audio
# Class but advertises something that blocks generic enumeration — the same
# situation the existing Pioneer entries in sound/usb/quirks-table.h fix.
#
# This script gathers the evidence. It changes nothing.

set -uo pipefail

VID_PID="2b73:0020"
VENDOR="2b73"
OUT=""

while [ $# -gt 0 ]; do
    case "$1" in
        -o|--output) OUT="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,26p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

report() {
    section() { printf '\n========== %s ==========\n' "$1"; }

    section "PROBE CONTEXT"
    echo "date:    $(date -Is)"
    echo "host:    $(uname -a)"
    echo "expected device: $VID_PID (from AlphaTheta's Windows driver INF)"

    section "IS THE DEVICE THERE"
    if lsusb -d "$VID_PID" >/dev/null 2>&1; then
        lsusb -d "$VID_PID"
        echo "-> found at the expected ID"
    elif lsusb | grep -qi "$VENDOR"; then
        echo "expected ID absent, but another $VENDOR device is present:"
        lsusb | grep -i "$VENDOR"
        echo "-> the published 0020 ID may be wrong for this unit; note the real one"
    else
        echo "NO $VENDOR DEVICE FOUND."
        echo
        echo "Check, in order:"
        echo "  1. the 12V adapter is connected and the rear power switch is on"
        echo "     (the DDJ-1000 is not bus powered; without it nothing enumerates)"
        echo "  2. the USB cable carries data, not just power"
        echo "  3. it is plugged into the Pi directly, not through an unpowered hub"
        echo
        echo "Full USB tree for reference:"
        lsusb
        return 1
    fi

    section "FULL DESCRIPTORS  (the part that matters)"
    # Everything the quirk entry needs: interface classes, altsettings,
    # endpoint addresses and attributes, channel counts, sample rates.
    sudo lsusb -v -d "$VID_PID" 2>/dev/null || lsusb -v -d "$VID_PID"

    section "INTERFACE SUMMARY"
    # A vendor-specific class (0xff) on the audio interface is the signature
    # that a quirk is needed rather than plain class-compliant support.
    sudo lsusb -v -d "$VID_PID" 2>/dev/null |
        grep -E 'bInterfaceNumber|bAlternateSetting|bInterfaceClass|bInterfaceSubClass|bNumEndpoints|bEndpointAddress|bmAttributes|wMaxPacketSize|bNrChannels|tSamFreq|bBitResolution|bSubframeSize' |
        sed 's/^ */  /'

    section "DID ALSA BIND ANYTHING"
    echo "--- /proc/asound/cards"
    cat /proc/asound/cards
    echo
    echo "--- aplay -l (playback)"
    aplay -l 2>&1
    echo
    echo "--- arecord -l (capture)"
    arecord -l 2>&1
    echo
    echo "If no Pioneer card appears above, snd-usb-audio declined the device."
    echo "That is the expected result, and the reason to write a quirk."

    section "MIDI"
    echo "--- amidi -l"
    amidi -l 2>&1
    echo
    echo "--- aconnect -l"
    aconnect -l 2>&1
    echo
    echo "MIDI is expected to work with no driver at all."

    section "KERNEL MESSAGES"
    sudo dmesg -T 2>/dev/null | grep -iE "usb|snd|audio" | tail -30

    section "SYSFS VIEW"
    for d in /sys/bus/usb/devices/*/; do
        [ -f "$d/idVendor" ] || continue
        [ "$(cat "$d/idVendor" 2>/dev/null)" = "$VENDOR" ] || continue
        echo "device: $(basename "$d")"
        for f in idVendor idProduct manufacturer product serial bNumInterfaces bMaxPower speed version; do
            [ -f "$d/$f" ] && printf '  %-16s %s\n' "$f" "$(cat "$d/$f" 2>/dev/null)"
        done
        echo "  interfaces:"
        for i in "$d"*:*/; do
            [ -d "$i" ] || continue
            printf '    %-28s class=%s subclass=%s proto=%s driver=%s\n' \
                "$(basename "$i")" \
                "$(cat "$i/bInterfaceClass" 2>/dev/null)" \
                "$(cat "$i/bInterfaceSubClass" 2>/dev/null)" \
                "$(cat "$i/bInterfaceProtocol" 2>/dev/null)" \
                "$(basename "$(readlink "$i/driver" 2>/dev/null)" 2>/dev/null || echo none)"
        done
    done

    section "WHAT TO DO WITH THIS"
    cat <<'EOF'
Compare the interface summary against the Pioneer entries already in the
kernel, in sound/usb/quirks-table.h — DDJ-SX3 (2b73:0023), DDJ-RB (000e),
DDJ-RR (000d), DDJ-SR2 (001e), DDJ-800 (0029) and six DJM mixers.

Those entries are ~46 lines each and carry exactly the fields printed above:
channels, iface, altsetting, endpoint, ep_attr, rates. If the DDJ-1000 has the
same shape — one interface with a vendor-specific class, isochronous IN and OUT
endpoints, fixed 44100 — then the entry can be written directly from this dump
and the device will work with no new driver code at all.

Send the output to alsa-devel, or build it as an out-of-tree module first.

Note this fixes AUDIO only. rekordbox still will not run: it identifies
controllers over HID, which Wine cannot provide, and that is independent of
whether the soundcard works.
EOF
}

if [ -n "$OUT" ]; then
    report 2>&1 | tee "$OUT"
    echo
    echo "saved to $OUT"
else
    report
fi
