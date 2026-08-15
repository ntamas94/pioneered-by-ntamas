#!/bin/bash
# Build a distributable SD-card image of the Pioneered DJ box.
# Run as root ON the Pi, output goes to a mounted USB drive (default
# /media/dj/Music). Produces pioneered-djbox-<date>.img.xz + .sha256.
#
# rsync-based: a fresh 10 GB image file is partitioned, formatted and filled
# from the live system with owner-specific data excluded (WiFi credentials,
# SSH keys and host keys, shell history, Mixxx library DB, music, the build
# tree). Much smaller and gentler on the target drive than a raw card copy,
# and the sanitizing is inherent in the exclude list. A generic cloud-init
# config is dropped in (user dj / password pioneered, SSH on, no WiFi -- the
# new owner adds their own); cloud-init also grows the partition to fill the
# card on first boot.
set -euo pipefail

OUT_DIR=${1:-/media/dj/Music}
WORK_DIR=${2:-$OUT_DIR}   # scratch for the raw .img (FAT32 targets cap files at 4 GiB)
PROFILE=${3:-full}        # full | 2deck -- baked into /etc/djbox-profile
STAMP=$(date +%Y%m%d)
SUFFIX=""
[ "$PROFILE" = "2deck" ] && SUFFIX="-2deck"
IMG="$WORK_DIR/pioneered-djbox$SUFFIX-$STAMP.img"
SIZE_GB=10

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
ls "$OUT_DIR" >/dev/null 2>&1   # poke the automount
sleep 2
mountpoint -q "$OUT_DIR" || { echo "$OUT_DIR is not a mounted drive" >&2; exit 1; }

cleanup() {
    umount /mnt/newroot/boot/firmware 2>/dev/null || true
    umount /mnt/newroot 2>/dev/null || true
    [ -n "${LOOP:-}" ] && losetup -d "$LOOP" 2>/dev/null || true
    systemctl start getty@tty1 2>/dev/null || true
}
trap cleanup EXIT

echo "== 1/7 quiesce =="
systemctl stop getty@tty1 || true
pkill -f 'mixxx --[f]ullScreen' || true
sleep 3
sync

echo "== 2/7 create and format image =="
rm -f "$IMG"
truncate -s ${SIZE_GB}G "$IMG"
parted -s "$IMG" mklabel msdos \
    mkpart primary fat32 4MiB 516MiB \
    mkpart primary ext4 516MiB 100%
LOOP=$(losetup -P --show -f "$IMG")
mkfs.vfat -F32 -n bootfs "${LOOP}p1" >/dev/null
mkfs.ext4 -q -L rootfs "${LOOP}p2"
mkdir -p /mnt/newroot
mount "${LOOP}p2" /mnt/newroot
mkdir -p /mnt/newroot/boot/firmware
mount "${LOOP}p1" /mnt/newroot/boot/firmware

echo "== 3/7 rsync root filesystem =="
rsync -aHAXx --numeric-ids \
    --exclude='/home/dj/pioneered-djbox-*' \
    --exclude=/proc/ --exclude=/sys/ --exclude=/dev/ --exclude=/run/ \
    --exclude=/tmp/ --exclude=/mnt/ --exclude=/media/ --exclude=/lost+found \
    --exclude=/boot/firmware/ \
    --exclude=/home/dj/build \
    --exclude=/home/dj/.cache \
    --exclude=/home/dj/.ssh \
    --exclude=/home/dj/.bash_history --exclude=/home/dj/.python_history \
    --exclude=/home/dj/.lesshst --exclude=/home/dj/.wget-hsts \
    --exclude='/home/dj/.mixxx/mixxxdb.sqlite*' \
    --exclude=/home/dj/Music \
    --exclude=/var/log/ \
    --exclude=/var/cache/apt/archives \
    --exclude=/var/lib/cloud \
    --exclude=/var/tmp/ \
    --exclude=/etc/netplan \
    --exclude=/etc/NetworkManager/system-connections \
    --exclude='/etc/ssh/ssh_host_*' \
    / /mnt/newroot/

echo "== 4/7 skeleton + sanitize =="
mkdir -p /mnt/newroot/proc /mnt/newroot/sys /mnt/newroot/dev \
         /mnt/newroot/run /mnt/newroot/tmp /mnt/newroot/mnt \
         /mnt/newroot/media/dj/Music /mnt/newroot/var/log/journal \
         /mnt/newroot/var/cache/apt/archives/partial /mnt/newroot/var/tmp \
         /mnt/newroot/etc/netplan \
         /mnt/newroot/etc/NetworkManager/system-connections \
         /mnt/newroot/home/dj/Music /mnt/newroot/home/dj/.cache
chmod 1777 /mnt/newroot/tmp /mnt/newroot/var/tmp
chown 1000:1000 /mnt/newroot/home/dj/Music /mnt/newroot/home/dj/.cache
: > /mnt/newroot/etc/machine-id
echo "$PROFILE" > /mnt/newroot/etc/djbox-profile
if [ -f /mnt/newroot/usr/lib/systemd/system/regenerate_ssh_host_keys.service ]; then
    ln -sf /usr/lib/systemd/system/regenerate_ssh_host_keys.service \
       /mnt/newroot/etc/systemd/system/multi-user.target.wants/regenerate_ssh_host_keys.service
fi

echo "== 5/7 boot partition + identity =="
rsync -a --exclude=user-data --exclude=network-config --exclude=meta-data \
    /boot/firmware/ /mnt/newroot/boot/firmware/
DISKID=$(blkid -s PTUUID -o value "$LOOP")
sed -i "s|root=PARTUUID=[^ ]*|root=PARTUUID=${DISKID}-02|" \
    /mnt/newroot/boot/firmware/cmdline.txt
sed -i 's/ usb-storage.quirks=[^ ]*//' /mnt/newroot/boot/firmware/cmdline.txt
sed -i -E "s|^PARTUUID=[^ \t]+([ \t]+/boot/firmware[ \t])|PARTUUID=${DISKID}-01\1|; s|^PARTUUID=[^ \t]+([ \t]+/[ \t])|PARTUUID=${DISKID}-02\1|" \
    /mnt/newroot/etc/fstab
touch /mnt/newroot/boot/firmware/meta-data
cat > /mnt/newroot/boot/firmware/user-data <<'EOF'
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
cat > /mnt/newroot/boot/firmware/network-config <<'EOF'
# Add your WiFi here (Raspberry Pi Imager writes the same format), or just
# use ethernet. Example:
# version: 2
# wifis:
#   wlan0:
#     dhcp4: true
#     access-points:
#       "your-ssid":
#         password: "your-password"
version: 2
EOF

umount /mnt/newroot/boot/firmware
umount /mnt/newroot
losetup -d "$LOOP"
LOOP=""
systemctl start getty@tty1 || true

echo "== 6/7 pishrink + compress =="
if [ ! -x /usr/local/bin/pishrink.sh ]; then
    curl -fsSL -o /usr/local/bin/pishrink.sh \
        https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
    chmod +x /usr/local/bin/pishrink.sh
fi
/usr/local/bin/pishrink.sh "$IMG" || echo "pishrink skipped/failed, continuing"
xz -T0 -6 -f "$IMG"

echo "== 7/7 checksum + move to target =="
sha256sum "$IMG.xz" > "$IMG.xz.sha256"
if [ "$WORK_DIR" != "$OUT_DIR" ]; then
    mv "$IMG.xz" "$IMG.xz.sha256" "$OUT_DIR/"
fi
ls -lh "$OUT_DIR"/pioneered-djbox-$STAMP.img.xz
echo DONE
