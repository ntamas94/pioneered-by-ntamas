#!/bin/bash
# Konzol allapotkijelzo, amig a Mixxx le van allitva (pl. build alatt).
export TERM=linux
setfont /usr/share/consolefonts/Lat2-TerminusBold32x16.psf.gz 2>/dev/null
setterm --cursor off --blank 0 </dev/tty1 >/dev/tty1 2>/dev/null
while true; do
    t=$(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))
    l=$(cut -d' ' -f1 /proc/loadavg)
    mhz=$(( $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq) / 1000 ))
    b=$(grep -c 'Building CXX' /tmp/build-256.log 2>/dev/null || echo -)
    clear >/dev/tty1
    {
        printf '\n'
        figlet -w 100 "  MIXXX ALL"
        printf '\n'
        figlet -w 100 "  $t C   $b db"
        printf '\n'
        printf '      Load: %s   Orajel: %s MHz   Ido: %s\n\n' "$l" "$mhz" "$(date +%H:%M)"
        printf '      2.5.6 BUILD FUT -- ne kapcsold ki!\n'
    } >/dev/tty1
    sleep 5
done
