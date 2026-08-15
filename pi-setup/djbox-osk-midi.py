#!/usr/bin/env python3
"""On-screen keyboard toggle driven by Mixxx via VirMIDI.

Reads the VirMIDI rawmidi device directly (unbuffered). The Time-Clamp
script broadcasts the DESIRED keyboard state once a second as
0xB0 0x20 0x7F (shown) / 0x00 (hidden). This daemon reacts to level
changes: 00->7F shows the overlay, 7F->00 hides it. Level + heartbeat makes
the chain self-healing against dropped or late MIDI events.
The ALSA seq->rawmidi bridge uses running status and keeps that state across
reader reconnects, so the first message after attach may arrive without its
0xB0 status byte -- the parser assumes running 0xB0 from the start.
"""
import glob
import os
import subprocess
import syslog
import time

SHOW = "/usr/local/bin/djbox-osk-show.sh"
HIDE = "/usr/local/bin/djbox-osk-hide.sh"


def find_dev():
    while True:
        devs = sorted(glob.glob("/dev/snd/midiC*D0"))
        if devs:
            return devs[0]
        time.sleep(2)


def show():
    syslog.syslog("show")
    subprocess.Popen([SHOW])


def hide():
    syslog.syslog("hide")
    subprocess.Popen([HIDE])


def main():
    dev = find_dev()
    fd = os.open(dev, os.O_RDONLY)
    syslog.openlog("djbox-osk")
    state = 1          # 0: want status, 1: want data1, 2: want data2
    d1 = None
    level = None       # last seen 0x20 level (0x7F shown / 0x00 hidden)
    while True:
        chunk = os.read(fd, 64)
        if not chunk:
            time.sleep(0.05)
            continue
        for byte in chunk:
            if byte >= 0x80:
                state = 1 if byte == 0xB0 else 0
                continue
            if state == 1:
                d1 = byte
                state = 2
            elif state == 2:
                if d1 == 0x20:
                    if byte == 0x7F and level != 0x7F:
                        show()
                    elif byte != 0x7F and level == 0x7F:
                        hide()
                    level = byte
                elif d1 == 0x25 and byte == 0x7F:
                    # Mixxx version badge pressed: toggle Preferences. No
                    # ControlObject exists for the dialog, so type the
                    # shortcut -- Ctrl+P to open, Escape to close if the
                    # window is already up.
                    syslog.syslog("prefs")
                    subprocess.Popen(["bash", "-c",
                        "if xdotool search --name '^Preferences$' >/dev/null 2>&1; "
                        "then xdotool search --name '^Preferences$' "
                        "windowactivate --sync key Escape; "
                        "else xdotool key ctrl+p; fi"])
                state = 1  # running status: next pair reuses 0xB0
            # state == 0: inside a foreign message, swallow data bytes


if __name__ == "__main__":
    main()
