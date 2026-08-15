#!/bin/bash
# Build a distributable SD-card image of the Pioneered DJ box.
# Run as root ON the Pi, with a big exFAT USB drive mounted (default
# /media/dj/Music). Produces pioneered-djbox-<date>.img.xz + .sha256.
#
# Steps: raw-copy the SD card to the USB drive, then loop-mount the copy and
# scrub everything owner-specific (WiFi credentials, SSH keys and host keys,
# shell history, Mixxx library DB, music files, the 9 GB build tree), drop in
# a generic cloud-init config (user dj / password pioneered, SSH enabled, no
# WiFi -- the buyer adds their own), shrink with PiShrink and compress.
set -euo pipefail

OUT_DIR=${1:-/media/dj/Music}
STAMP=$(date +%Y%m%d)
IMG="$OUT_DIR/pioneered-djbox-$STAMP.img"

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ -d "$OUT_DIR" ] || { echo "$OUT_DIR missing" >&2; exit 1; }

echo "== 1/6 quiesce =="
systemctl stop getty@tty1 || true
pkill -f 'mixxx --[f]ullScreen' || true
sleep 3
sync

echo "== 2/6 raw copy (about 30-40 min) =="
dd if=/dev/mmcblk0 of="$IMG" bs=4M conv=fsync status=progress

systemctl start getty@tty1 || true

echo "== 3/6 sanitize =="
LOOP=$(losetup -P --show -f "$IMG")
trap 'umount /mnt/imgroot/boot/firmware 2>/dev/null; umount /mnt/imgroot 2>/dev/null; losetup -d "$LOOP"' EXIT
mkdir -p /mnt/imgroot
mount "${LOOP}p2" /mnt/imgroot
mount "${LOOP}p1" /mnt/imgroot/boot/firmware
R=/mnt/imgroot

# owner-specific data
rm -rf "$R"/home/dj/.ssh "$R"/home/dj/.cache "$R"/home/dj/build
rm -f  "$R"/home/dj/.bash_history "$R"/home/dj/.python_history \
       "$R"/home/dj/.lesshst "$R"/home/dj/.wget-hsts
rm -f  "$R"/home/dj/.mixxx/mixxxdb.sqlite*
rm -rf "$R"/home/dj/Music/*
# credentials
rm -f  "$R"/etc/netplan/*.yaml
rm -f  "$R"/etc/NetworkManager/system-connections/* 2>/dev/null || true
rm -rf "$R"/var/lib/cloud
rm -f  "$R"/etc/ssh/ssh_host_*
ln -sf /usr/lib/systemd/system/regenerate_ssh_host_keys.service \
       "$R"/etc/systemd/system/multi-user.target.wants/regenerate_ssh_host_keys.service 2>/dev/null || true
# logs, apt leftovers, identity
rm -rf "$R"/var/log/journal/*
find "$R"/var/log -type f -delete 2>/dev/null || true
rm -f  "$R"/var/cache/apt/archives/*.deb
: > "$R"/etc/machine-id

# generic cloud-init: dj / pioneered, SSH on, WiFi left to the owner
B=$R/boot/firmware
cat > "$B/user-data" <<'EOF'
#cloud-config
hostname: pidj
manage_etc_hosts: true
users:
  - name: dj
    groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
    shell: /bin/bash
    lock_passwd: false
    sudo: ALL=(ALL) NOPASSWD:ALL
chpasswd:
  expire: false
  users:
    - name: dj
      password: pioneered
      type: text
ssh_pwauth: true
EOF
cat > "$B/network-config" <<'EOF'
# Add your WiFi here (Raspberry Pi Imager format), or just use ethernet.
version: 2
wifis:
  renderer: networkd
  wlan0:
    dhcp4: true
    optional: true
    access-points: {}
EOF

umount "$R/boot/firmware"
umount "$R"
losetup -d "$LOOP"
trap - EXIT

echo "== 4/6 pishrink =="
if [ ! -x /usr/local/bin/pishrink.sh ]; then
    curl -fsSL -o /usr/local/bin/pishrink.sh \
        https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
    chmod +x /usr/local/bin/pishrink.sh
fi
/usr/local/bin/pishrink.sh "$IMG"

echo "== 5/6 compress =="
xz -T0 -6 -v "$IMG"

echo "== 6/6 checksum =="
sha256sum "$IMG.xz" > "$IMG.xz.sha256"
ls -lh "$IMG.xz"
echo DONE
