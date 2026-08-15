#!/bin/bash
# Sends overall CPU usage (0-100) once a second as MIDI CC 0x10 on the first
# VirMIDI port. The Time-Clamp mapping picks it up and the skin displays it.
#
# Also watches which DJ controller is plugged in (ALSA client names) and
# broadcasts a deck-profile level on CC 0x23 every few seconds:
#   0x7F  a known 2-channel controller is connected (DDJ-FLX4, DDJ-400, ...)
#         -> the skin collapses to the 2 DECK view
#   0x00  4-deck controller, unknown device or nothing -> full 4-deck UI
#
# The device is opened ONCE and kept open: reopening it every second (the old
# amidi -S approach) cycles the ALSA rawmidi substream, which can drop or
# garble concurrent traffic on the port -- the djbox-osk-midi daemon reads
# Mixxx's output from the same device node.
set -u

TWODECK_RE='DDJ-200|DDJ-250|DDJ-400|DDJ-FLX4|DDJ-SB3|DDJ-SB2|DDJ-WeGO|DDJ-REV1|DDJ-RB|DDJ-800'

DEV=""
until [ -n "$DEV" ]; do
    for d in /dev/snd/midiC*D0; do
        [ -e "$d" ] && DEV="$d" && break
    done
    [ -n "$DEV" ] || sleep 2
done

exec 3>"$DEV"

prev_idle=0
prev_total=0
tick=0
while true; do
    # Deck profile: check every 5 s, resend the level every 10 s (heartbeat).
    # /etc/djbox-profile can pin it: "2deck", "full", or "auto"/absent.
    if [ $((tick % 5)) -eq 0 ]; then
        force=$(cat /etc/djbox-profile 2>/dev/null || echo auto)
        case "$force" in
            2deck) profile_hex='7f' ;;
            full)  profile_hex='00' ;;
            *)
                if aconnect -l 2>/dev/null | grep -v -i 'virtual raw midi\|virmidi' \
                        | grep -qE "$TWODECK_RE"; then
                    profile_hex='7f'
                else
                    profile_hex='00'
                fi
                ;;
        esac
        if [ "$profile_hex" != "${profile_sent:-}" ] || [ $((tick % 10)) -eq 0 ]; then
            printf "\xB0\x23\x${profile_hex}" >&3
            profile_sent=$profile_hex
        fi
    fi
    # SoC temperature in whole degrees C on 0xB0 0x24, every 2 s.
    if [ $((tick % 2)) -eq 0 ] && [ -r /sys/class/thermal/thermal_zone0/temp ]; then
        t=$(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))
        [ "$t" -gt 127 ] && t=127
        [ "$t" -lt 0 ] && t=0
        printf -v thex '%02x' "$t"
        printf "\xB0\x24\x${thex}" >&3
    fi
    tick=$((tick + 1))
    read -r _ user nice system idle iowait irq softirq steal _ < /proc/stat
    idle_all=$((idle + iowait))
    total=$((user + nice + system + idle_all + irq + softirq + steal))
    diff_total=$((total - prev_total))
    diff_idle=$((idle_all - prev_idle))
    if [ "$diff_total" -gt 0 ] && [ "$prev_total" -gt 0 ]; then
        usage=$(( (100 * (diff_total - diff_idle) + diff_total / 2) / diff_total ))
        [ "$usage" -gt 100 ] && usage=100
        printf -v hex '%02x' "$usage"
        printf "\xB0\x10\x${hex}" >&3
    fi
    prev_idle=$idle_all
    prev_total=$total
    sleep 1
done
