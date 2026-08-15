#!/bin/bash
# Sends overall CPU usage (0-100) once a second as MIDI CC 0x10 on the first
# VirMIDI port. The Time-Clamp mapping picks it up and the skin displays it.
set -u

PORT=""
until [ -n "$PORT" ]; do
    PORT=$(amidi -l 2>/dev/null | awk '/VirMIDI \[hw:.*,0,0\]|Virtual Raw MIDI/ {print $2; exit}')
    [ -n "$PORT" ] || sleep 2
done

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
        printf -v hex '%02X' "$usage"
        amidi -p "$PORT" -S "B0 10 $hex" 2>/dev/null
    fi
    prev_idle=$idle_all
    prev_total=$total
    sleep 1
done
