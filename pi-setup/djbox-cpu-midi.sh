#!/bin/bash
# Sends overall CPU usage (0-100) once a second as MIDI CC 0x10 on the first
# VirMIDI port. The Time-Clamp mapping picks it up and the skin displays it.
#
# The device is opened ONCE and kept open: reopening it every second (the old
# amidi -S approach) cycles the ALSA rawmidi substream, which can drop or
# garble concurrent traffic on the port -- the djbox-osk-midi daemon reads
# Mixxx's output from the same device node.
set -u

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
while true; do
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
