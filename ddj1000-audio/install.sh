#!/bin/bash
# Build and install the patched snd-usb-audio module with DDJ-1000 support
# as a DKMS package, so it survives kernel updates. Raspberry Pi OS / Debian.
#
# What it does:
#   1. fetches sound/usb from the running kernel's source tree (rpi-<ver>.y)
#   2. applies ddj1000-usb-audio.patch (quirks-table.h + quirks.c)
#   3. registers it with DKMS and builds/installs the module
#   4. reloads snd-usb-audio -> the DDJ-1000 shows up as an ALSA card
set -euo pipefail

KVER=$(uname -r)                         # e.g. 6.18.39+rpt-rpi-v8
BRANCH="rpi-$(echo "$KVER" | cut -d. -f1,2).y"
PKG=snd-usb-audio-ddj1000
VER=1.0
SRC=/usr/src/$PKG-$VER
HERE=$(cd "$(dirname "$0")" && pwd)

[ "$(id -u)" = 0 ] || { echo "run as root (sudo $0)"; exit 1; }
apt-get install -y dkms "linux-headers-$KVER" curl patch >/dev/null

echo "== fetching sound/usb from raspberrypi/linux $BRANCH =="
TMP=$(mktemp -d)
curl -fsSL "https://github.com/raspberrypi/linux/archive/refs/heads/$BRANCH.tar.gz" \
    | tar -xz -C "$TMP" --strip-components=1 --wildcards "linux-$BRANCH/sound/usb/*"

echo "== applying DDJ-1000 patch =="
( cd "$TMP" && patch -p1 < "$HERE/ddj1000-usb-audio.patch" )

echo "== installing DKMS source =="
rm -rf "$SRC"; mkdir -p "$SRC"
cp "$TMP"/sound/usb/*.c "$TMP"/sound/usb/*.h "$SRC/"
cat > "$SRC/Kbuild" <<'EOF'
obj-m := snd-usb-audio.o
snd-usb-audio-y := card.o clock.o endpoint.o fcp.o format.o helper.o implicit.o mixer.o mixer_quirks.o mixer_scarlett.o mixer_scarlett2.o mixer_us16x08.o mixer_s1810c.o pcm.o power.o proc.o quirks.o stream.o validate.o
snd-usb-audio-$(CONFIG_SND_USB_AUDIO_MIDI_V2) += midi2.o
snd-usb-audio-$(CONFIG_SND_USB_AUDIO_USE_MEDIA_CONTROLLER) += media.o
ccflags-y += -I$(src)
EOF
cp "$HERE/dkms.conf" "$SRC/"
rm -rf "$TMP"

dkms remove -m "$PKG" -v "$VER" --all >/dev/null 2>&1 || true
dkms add -m "$PKG" -v "$VER"
dkms install -m "$PKG" -v "$VER"

echo "== reloading module =="
modprobe -r snd_usb_audio || true
modprobe snd_usb_audio
sleep 2
aplay -l | grep -i ddj && echo "DDJ-1000 audio: OK" || echo "DDJ-1000 not detected (is it plugged in and powered?)"
