#!/usr/bin/env python3
"""Replay a captured session -- HID and MIDI together -- at the controller.

The HID-only replays settled that the screens hold state per track id and only
animate ids they consider properly loaded; byte-perfect HID uploads under a
fresh id never register. This replays the whole context rekordbox's own load
sat in, both pipes with original timing, so whatever accompanies the upload on
the MIDI side goes out too. Run with djbox-ddj-bridge stopped: this holds the
raw MIDI port and the HID node itself.

Takes the JSON rows [seconds, "h"|"m", hex].
"""
import ctypes
import ctypes.util
import json
import os
import sys
import time

asound = ctypes.CDLL(ctypes.util.find_library("asound"))
asound.snd_rawmidi_open.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.c_char_p, ctypes.c_int]
asound.snd_rawmidi_write.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
asound.snd_rawmidi_drain.argtypes = [ctypes.c_void_p]


def card_by_name(needle):
    with open("/proc/asound/cards") as fh:
        for line in fh:
            if needle.lower() in line.lower() and "[" in line:
                return int(line.split("[")[0].strip().split()[0])
    return None


def hidraw_node():
    for name in sorted(os.listdir("/sys/class/hidraw")):
        try:
            with open("/sys/class/hidraw/%s/device/uevent" % name) as fh:
                if "2B73" in fh.read().upper():
                    return "/dev/" + name
        except OSError:
            continue
    return None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    events = json.load(open(sys.argv[1]))

    node = hidraw_node()
    card = card_by_name("DDJ")
    if not node or card is None:
        sys.exit("controller not found")
    hid = os.open(node, os.O_RDWR)

    inp = ctypes.c_void_p()
    out = ctypes.c_void_p()
    rc = asound.snd_rawmidi_open(ctypes.byref(inp), ctypes.byref(out),
                                 ("hw:%d,0,0" % card).encode(), 2)
    if rc < 0:
        sys.exit("cannot open raw MIDI (%d) -- stop djbox-ddj-bridge first" % rc)

    print("replaying %d events (HID+MIDI)" % len(events))
    started = time.monotonic()
    sent = 0
    try:
        for offset, kind, payload in events:
            wait = started + offset - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            data = bytes.fromhex(payload)
            if kind == "h":
                os.write(hid, data)
            else:
                buf = ctypes.create_string_buffer(data, len(data))
                asound.snd_rawmidi_write(out, buf, len(data))
                asound.snd_rawmidi_drain(out)
            sent += 1
    except OSError as exc:
        print("failed after %d events: %s" % (sent, exc))
    finally:
        os.close(hid)
    print("done, %d events" % sent)


if __name__ == "__main__":
    main()
