#!/usr/bin/env bash
# Prepare a freshly flashed Raspberry Pi OS card for headless first boot.
#
# Run this on Windows in Git Bash, with the flashed card plugged in.
#
# Writes two files to the card's FAT boot partition:
#   ssh           empty file; switches the SSH server on at first boot
#   userconf.txt  username:password-hash; Bookworm has no default user, so
#                 without this there is no account to log into
#
# Your password is typed here and hashed locally with openssl. It is never
# echoed, never stored in shell history, and never leaves this machine.
#
# Wi-Fi cannot be set up this way. Bookworm dropped wpa_supplicant.conf and
# NetworkManager's config lives on the ext4 partition, which Windows cannot
# write. Use an Ethernet cable for the first boot.

set -euo pipefail

BOLD=$(tput bold 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)

say()  { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  ERROR %s\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------- find card

say "Looking for the boot partition"

boot=""
for letter in {d..z}; do
    candidate="/$letter"
    # config.txt plus a kernel image is a Pi boot partition and nothing else.
    if [ -f "$candidate/config.txt" ] && ls "$candidate"/*.elf >/dev/null 2>&1; then
        boot="$candidate"
        break
    fi
done

if [ -z "$boot" ]; then
    cat >&2 <<'EOF'
  ERROR no Raspberry Pi boot partition found.

  Checked every drive letter for config.txt plus firmware .elf files.

  If Etcher has finished, unplug the card reader and plug it back in --
  Etcher dismounts the card after flashing, so Windows will not have
  assigned it a drive letter yet.

  If Etcher is still flashing or verifying, wait for it to finish.
EOF
    exit 1
fi

ok "found $boot"
if [ -r "$boot/issue.txt" ]; then
    printf '        %s\n' "$(head -n1 "$boot/issue.txt")"
fi

# ---------------------------------------------------------------- ssh

say "Enabling SSH"
if [ -f "$boot/ssh" ]; then
    ok "ssh file already present"
else
    : > "$boot/ssh"
    ok "created $boot/ssh"
fi

# ---------------------------------------------------------------- user

say "Creating the first-boot user"

if [ -f "$boot/userconf.txt" ]; then
    printf '  userconf.txt already exists for user: %s\n' \
        "$(cut -d: -f1 "$boot/userconf.txt")"
    read -r -p "  Overwrite it? [y/N] " reply
    case "$reply" in
        [yY]*) ;;
        *) ok "keeping the existing userconf.txt"; exit 0 ;;
    esac
fi

read -r -p "  Username: " username
[ -n "$username" ] || fail "username cannot be empty"

# Pi OS requires a lowercase Linux-valid name.
if ! printf '%s' "$username" | grep -Eq '^[a-z_][a-z0-9_-]*$'; then
    fail "invalid username: use lowercase letters, digits, underscore, hyphen"
fi
if [ "$username" = "root" ]; then
    fail "do not use root as the first-boot user"
fi

command -v openssl >/dev/null 2>&1 || fail "openssl not found in PATH"

echo "  Now the password. It is not shown as you type."
hash=$(openssl passwd -6)
[ -n "$hash" ] || fail "openssl produced no hash"

printf '%s:%s\n' "$username" "$hash" > "$boot/userconf.txt"
ok "wrote $boot/userconf.txt for user '$username'"

# ---------------------------------------------------------------- verify

say "Verifying"
[ -f "$boot/ssh" ] || fail "ssh file missing"
ok "ssh present"

lines=$(wc -l < "$boot/userconf.txt")
[ "$lines" -eq 1 ] || fail "userconf.txt must be exactly one line, got $lines"
grep -q '^[a-z_][a-z0-9_-]*:\$6\$' "$boot/userconf.txt" ||
    fail "userconf.txt is not in username:\$6\$hash form"
ok "userconf.txt looks correct"

say "Next"
cat <<EOF
        Eject the card safely, put it in the Pi, and connect an Ethernet
        cable to your router before powering it on.

        First boot resizes the filesystem and reboots once, so give it a
        couple of minutes before expecting a response.

        Then from Git Bash:

            ssh $username@raspberrypi.local

        If that name does not resolve, find the Pi's address in your
        router's client list and use the IP instead.
EOF
