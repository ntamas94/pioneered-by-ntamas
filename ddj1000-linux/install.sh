#!/bin/bash
# Make a Pioneer DDJ-1000 work properly on Linux: sound, controls and the
# colour screens in the jog wheels.
#
# Three parts, and each stands on its own:
#
#   audio   a DKMS build of snd-usb-audio carrying a quirk for this unit. The
#           descriptor claims 1024-byte packets every 250 us; the hardware
#           actually delivers 432 bytes every 500 us, and taking it at its word
#           makes the host overrun it and play everything at double speed.
#
#   bridge  a daemon between the controller and the DJ software. It answers the
#           challenge that takes the jog screens out of "NO AUDIO DRIVER",
#           keeps the HID poll alive, and draws each deck's artwork, waveform,
#           beat grid, cues and playhead the way rekordbox does.
#
#   mixxx   a four-deck mapping, with the jog screens driven from it.
#
# Run as an ordinary user with sudo rights:
#
#     ./install.sh                 everything
#     ./install.sh audio           just the sound quirk
#     ./install.sh bridge mixxx    the screens and the mapping
#
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
MODULE=snd-usb-audio-ddj1000
VERSION=1.0
BIN=/usr/local/bin
SHARE=/usr/local/share
UNITS=/etc/systemd/system
RULES=/etc/udev/rules.d

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
# dkms lives in /usr/sbin, which a non-login shell often leaves off the path.
PATH=$PATH:/usr/sbin:/sbin

warn() { printf '  ! %s\n' "$*" >&2; }

need() {
    local missing=()
    for tool in "$@"; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        warn "missing: ${missing[*]}"
        return 1
    fi
}

# Installed through a temporary file in the destination directory and renamed
# into place, so a half-written copy can never end up being what runs. A
# truncated bridge is a controller with no screens and no obvious reason why.
install_file() {
    local src=$1 dest=$2 mode=$3
    sudo install -D -m "$mode" "$src" "$dest.new"
    sudo mv -f "$dest.new" "$dest"
}

install_audio() {
    say "sound: building snd-usb-audio with the DDJ-1000 quirk"
    need dkms make gcc || {
        warn "install dkms and the build tools first:"
        warn "  sudo apt install dkms build-essential"
        return 1
    }
    if [ ! -d /lib/modules/"$(uname -r)"/build ]; then
        warn "no kernel headers for $(uname -r)"
        warn "  sudo apt install linux-headers-\$(uname -r)"
        warn "  (on Raspberry Pi OS: sudo apt install raspberrypi-kernel-headers)"
        return 1
    fi

    sudo dkms remove -m "$MODULE" -v "$VERSION" --all >/dev/null 2>&1 || true
    sudo rm -rf "/usr/src/$MODULE-$VERSION"
    sudo cp -a "$HERE/audio/$MODULE-$VERSION" /usr/src/
    sudo dkms add -m "$MODULE" -v "$VERSION"
    sudo dkms build -m "$MODULE" -v "$VERSION"
    sudo dkms install -m "$MODULE" -v "$VERSION" --force

    echo "  built for $(uname -r); it rebuilds itself on kernel updates"

    # Deliberately not reloaded here. Pulling snd_usb_audio out from under a
    # running system takes the controller's sound card with it, and anything
    # holding it -- the DJ software, most likely -- is left with no output and
    # no idea why. Replugging the controller is enough; a reboot certainly is.
    if lsmod | grep -q '^snd_usb_audio'; then
        echo "  the driver is already loaded: unplug and replug the controller"
        echo "  (or reboot) for the new one to take effect" 
    fi
}

install_bridge() {
    say "bridge: installing the jog screen daemon"
    need python3 ffmpeg ffprobe || {
        warn "install the decoders first: sudo apt install python3 ffmpeg"
        return 1
    }
    python3 -c 'import PIL' 2>/dev/null || {
        warn "install Pillow: sudo apt install python3-pil"
        return 1
    }

    install_file "$HERE/bridge/djbox-ddj-bridge.py"    "$BIN/djbox-ddj-bridge.py"    755
    install_file "$HERE/bridge/djbox-ddj-trackart.py"  "$BIN/djbox-ddj-trackart.py"  755
    install_file "$HERE/bridge/djbox-ddj-reconnect.sh" "$BIN/djbox-ddj-reconnect.sh" 755
    install_file "$HERE/bridge/ddj1000-post-auth-midi.txt"  "$SHARE/ddj1000-post-auth-midi.txt"  644
    install_file "$HERE/bridge/ddj1000-jog-hid-startup.txt" "$SHARE/ddj1000-jog-hid-startup.txt" 644

    install_file "$HERE/bridge/djbox-ddj-bridge.service"    "$UNITS/djbox-ddj-bridge.service"    644
    install_file "$HERE/bridge/djbox-ddj-reconnect.service" "$UNITS/djbox-ddj-reconnect.service" 644
    install_file "$HERE/bridge/99-ddj1000-reconnect.rules"  "$RULES/99-ddj1000-reconnect.rules"  644

    # The daemon needs a virtual MIDI port to meet the DJ software on, and one
    # ALSA sequencer client per port. Four of them, not one: the daemon uses
    # VirMIDI 5-1, so a single-port card leaves it with nowhere to go -- and a
    # one-port setting here does nothing until the next reboot reloads the
    # module, which makes it look like the reboot broke something else.
    if ! lsmod | grep -q '^snd_virmidi'; then
        sudo modprobe snd-virmidi midi_devs=4 2>/dev/null || true
    fi
    grep -q '^snd-virmidi' /etc/modules 2>/dev/null || \
        echo 'snd-virmidi' | sudo tee -a /etc/modules >/dev/null
    [ -f /etc/modprobe.d/djbox-virmidi.conf ] || \
        echo 'options snd-virmidi midi_devs=4' | \
            sudo tee /etc/modprobe.d/djbox-virmidi.conf >/dev/null
    sudo sed -i 's/midi_devs=1$/midi_devs=4/' /etc/modprobe.d/djbox-virmidi.conf

    sudo mkdir -p /var/cache/djbox-art
    sudo systemctl daemon-reload
    sudo udevadm control --reload-rules
    # Enabled against the controller's own device unit rather than against
    # boot: the udev rule names the USB device /dev/ddj1000, systemd turns
    # that into dev-ddj1000.device, and the service is bound to it. Plugging
    # the controller in starts it, pulling it out stops it, and there is
    # nothing for anyone to start by hand.
    sudo systemctl enable djbox-ddj-bridge.service
    sudo udevadm trigger --subsystem-match=usb --action=add
    echo "  bound to the controller as djbox-ddj-bridge.service"
}

install_mixxx() {
    say "mixxx: installing the four-deck mapping"
    local target=${MIXXX_CONTROLLERS:-$HOME/.mixxx/controllers}
    mkdir -p "$target"
    install -m 644 "$HERE/mixxx/Pioneer-DDJ-1000-4deck.midi.xml" "$target/"
    install -m 644 "$HERE/mixxx/Pioneer-DDJ-1000-4deck-scripts.js" "$target/"
    echo "  installed into $target"
    echo "  in Mixxx: Preferences -> Controllers -> the DDJ-1000's MIDI port"
    echo "  -> Pioneer DDJ-1000 (4 deck), and enable it"
}

main() {
    local parts=("$@")
    [ ${#parts[@]} -gt 0 ] || parts=(audio bridge mixxx)

    if [ "$(id -u)" -eq 0 ]; then
        warn "run this as your normal user; it calls sudo where it needs to"
        exit 1
    fi
    # Ask for the password now rather than partway through a build, but only
    # when there is a terminal to ask on -- `sudo -v` prompts even where the
    # commands themselves would not, which breaks running this over ssh.
    if ! sudo -n true 2>/dev/null; then
        if [ -t 0 ]; then
            sudo -v
        else
            warn "sudo needs a password and there is no terminal to ask on"
            exit 1
        fi
    fi

    local failed=()
    for part in "${parts[@]}"; do
        case $part in
            audio)  install_audio  || failed+=(audio) ;;
            bridge) install_bridge || failed+=(bridge) ;;
            mixxx)  install_mixxx  || failed+=(mixxx) ;;
            *) warn "unknown part: $part (audio, bridge, mixxx)"; exit 1 ;;
        esac
    done

    if [ ${#failed[@]} -gt 0 ]; then
        say "finished, but these did not install: ${failed[*]}"
        exit 1
    fi
    say "done"
    echo "  plug the controller in and start Mixxx."
    echo "  the jog screens come up a few seconds after the audio does."
}

main "$@"
