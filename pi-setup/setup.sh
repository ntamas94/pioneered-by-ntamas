#!/usr/bin/env bash
# First-boot provisioning for a Raspberry Pi DJ appliance (Pi OS Lite, arm64).
#
# Does the parts that are needed whatever DJ software ends up running: realtime
# audio permissions, a CPU governor that will not downclock mid-set, and the
# checks that catch a bad power supply before it shows up as an audible dropout.
#
# Deliberately does NOT install any DJ software or graphical stack — that
# decision is still open. Safe to re-run; every step is idempotent.
#
#   ./setup.sh            provision
#   ./setup.sh --audit    report only, change nothing
#   ./setup.sh --strip    also disable services an audio appliance does not need

set -euo pipefail

AUDIT_ONLY=0
STRIP=0
for arg in "$@"; do
    case "$arg" in
        --audit) AUDIT_ONLY=1 ;;
        --strip) STRIP=1 ;;
        -h|--help)
            sed -n '2,14p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

BOLD=$(tput bold 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)
warnings=0

say()  { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
ok()   { printf '  ok    %s\n' "$1"; }
warn() { printf '  WARN  %s\n' "$1"; warnings=$((warnings + 1)); }
info() { printf '        %s\n' "$1"; }

need_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "this step needs root; re-run with sudo" >&2
        exit 1
    fi
}

# ---------------------------------------------------------------- checks

current_user() {
    # SUDO_USER when invoked through sudo, otherwise the real login name.
    # `id -un` rather than $USER, which is not always set under `set -u`.
    echo "${SUDO_USER:-${USER:-$(id -un)}}"
}

check_arch() {
    say "Architecture"
    local arch
    arch=$(uname -m)
    case "$arch" in
        aarch64)
            ok "aarch64 (64-bit ARM)"
            ;;
        armv7l|armv6l)
            warn "$arch — this is the 32-bit ARM image. Reflash with arm64."
            ;;
        *)
            warn "$arch — not an ARM64 system. This script targets a Pi on Pi OS Lite arm64."
            ;;
    esac
    info "kernel $(uname -r)"
}

check_power() {
    say "Power and thermals"
    if ! command -v vcgencmd >/dev/null 2>&1; then
        warn "vcgencmd not found, cannot read throttling state"
        return
    fi

    local raw value
    raw=$(vcgencmd get_throttled)          # throttled=0x0
    value=${raw#*=}
    if [ "$value" = "0x0" ]; then
        ok "no throttling recorded ($raw)"
    else
        warn "$raw — decoding:"
        local n=$((value))
        # Bits 0-3 are live; bits 16-19 latch that it happened at some point
        # since boot. Written as if-blocks because under `set -e` a false
        # arithmetic test would abort the script.
        if (( n & 0x1     )); then info "under-voltage RIGHT NOW — power supply is inadequate"; fi
        if (( n & 0x2     )); then info "ARM frequency capped right now"; fi
        if (( n & 0x4     )); then info "throttled right now"; fi
        if (( n & 0x8     )); then info "soft temperature limit reached right now"; fi
        if (( n & 0x10000 )); then info "under-voltage has occurred since boot"; fi
        if (( n & 0x40000 )); then info "throttling has occurred since boot — check cooling"; fi
        info "USB audio breaks up long before the Pi feels slow. Fix this first."
    fi

    if command -v vcgencmd >/dev/null 2>&1; then
        info "core temperature: $(vcgencmd measure_temp | cut -d= -f2)"
    fi
}

check_realtime() {
    say "Realtime audio permissions"
    local user
    user=$(current_user)

    if id -nG "$user" | tr ' ' '\n' | grep -qx audio; then
        ok "$user is in the audio group"
    else
        warn "$user is NOT in the audio group"
    fi

    if [ -f /etc/security/limits.d/audio.conf ]; then
        ok "/etc/security/limits.d/audio.conf present"
        sed 's/^/        /' /etc/security/limits.d/audio.conf
    else
        warn "no realtime limits configured"
    fi

    local rtprio memlock
    rtprio=$(ulimit -Hr 2>/dev/null || echo "?")
    memlock=$(ulimit -Hl 2>/dev/null || echo "?")
    info "current shell limits: rtprio=$rtprio memlock=$memlock"
    info "(these only change after a full logout and login)"
}

check_governor() {
    say "CPU governor"
    local gov=/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
    if [ ! -r "$gov" ]; then
        warn "cannot read the scaling governor"
        return
    fi
    local current
    current=$(cat "$gov")
    if [ "$current" = "performance" ]; then
        ok "performance"
    else
        warn "$current — will downclock mid-set and cause dropouts"
    fi
    if [ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq ]; then
        info "current: $(( $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq) / 1000 )) MHz"
    fi
}

check_audio_hardware() {
    say "Audio hardware seen by ALSA"
    if [ -r /proc/asound/cards ]; then
        sed 's/^/        /' /proc/asound/cards
    else
        warn "/proc/asound/cards missing — no ALSA?"
    fi

    say "USB devices"
    if command -v lsusb >/dev/null 2>&1; then
        lsusb | sed 's/^/        /'
        if lsusb | grep -qi 'pioneer\|alphatheta\|2b73'; then
            ok "a Pioneer/AlphaTheta device is attached"
        else
            info "no Pioneer/AlphaTheta device attached right now"
        fi
    else
        info "lsusb not installed (apt install usbutils)"
    fi

    say "MIDI ports"
    if command -v aconnect >/dev/null 2>&1; then
        aconnect -l 2>/dev/null | sed 's/^/        /' || info "no MIDI sequencer ports"
    else
        info "aconnect not installed (apt install alsa-utils)"
    fi
}

audit() {
    check_arch
    check_power
    check_realtime
    check_governor
    check_audio_hardware

    say "Summary"
    if [ "$warnings" -eq 0 ]; then
        ok "nothing to fix"
    else
        printf '  %d warning(s) above\n' "$warnings"
    fi
}

# ---------------------------------------------------------------- actions

do_update() {
    say "Updating packages"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade

    # One at a time: package names drift between Debian releases, and a single
    # missing candidate must not abort the whole provisioning run.
    for pkg in alsa-utils usbutils git curl; do
        if DEBIAN_FRONTEND=noninteractive apt-get -y install "$pkg" >/dev/null 2>&1; then
            ok "installed $pkg"
        else
            warn "could not install $pkg (skipped)"
        fi
    done
}

do_realtime() {
    say "Configuring realtime audio permissions"
    local user
    user=$(current_user)

    if ! id -nG "$user" | tr ' ' '\n' | grep -qx audio; then
        usermod -aG audio "$user"
        ok "added $user to the audio group"
    else
        ok "$user already in the audio group"
    fi

    # SCHED_FIFO is the single biggest factor in avoiding xruns; without it the
    # rest of the tuning barely matters.
    cat > /etc/security/limits.d/audio.conf <<'EOF'
# Realtime scheduling and locked memory for audio work.
@audio   -  rtprio      95
@audio   -  memlock     unlimited
EOF
    ok "wrote /etc/security/limits.d/audio.conf"
    info "takes effect after a full logout and login"
}

do_governor() {
    say "Setting the CPU governor to performance"

    if ! grep -qw performance \
        /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors 2>/dev/null; then
        warn "this kernel does not offer a performance governor"
        return
    fi

    # A systemd unit rather than cpufrequtils: that package was dropped after
    # Bookworm, and writing the sysfs node directly depends on nothing.
    cat > /etc/systemd/system/cpu-governor.service <<'EOF'
[Unit]
Description=Pin the CPU governor to performance for low-latency audio
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > "$g"; done'

[Install]
WantedBy=multi-user.target
EOF
    ok "wrote /etc/systemd/system/cpu-governor.service"

    systemctl daemon-reload
    if systemctl enable --now cpu-governor.service >/dev/null 2>&1; then
        ok "enabled and started"
    else
        warn "could not enable the unit"
    fi

    local current
    current=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "?")
    if [ "$current" = "performance" ]; then
        ok "governor is now performance on cpu0"
    else
        warn "governor is still $current"
    fi
}

do_strip() {
    say "Disabling services an audio appliance does not need"
    # Only touches services that exist; each is safe to leave running, so this
    # is opt-in rather than part of the default provisioning.
    for unit in bluetooth avahi-daemon triggerhappy ModemManager cups; do
        if systemctl list-unit-files 2>/dev/null | grep -q "^${unit}\."; then
            systemctl disable --now "$unit" >/dev/null 2>&1 &&
                ok "disabled $unit" ||
                warn "could not disable $unit"
        fi
    done
}

# ---------------------------------------------------------------- main

if [ "$AUDIT_ONLY" = 1 ]; then
    audit
    exit 0
fi

need_root
do_update
do_realtime
do_governor
if [ "$STRIP" = 1 ]; then do_strip; fi

warnings=0
audit

say "Next"
info "Log out and back in so the audio group and realtime limits apply."
info "Then plug in the controller and re-run: ./setup.sh --audit"
info "No DJ software installed yet — that decision is still open."
