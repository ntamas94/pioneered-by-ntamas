#!/usr/bin/env python3
"""Replay a captured rekordbox jog-screen session onto the controller.

Every field the bridge sends now matches a capture of rekordbox byte for byte,
and the screens still will not move the playhead along the waveform. This
settles where the difference is: it plays rekordbox's own reports back at the
unit -- its track id, its beat grid, its waveform, its position stream -- with
the original timing. If the playhead moves under the replay then something in
what the bridge sends is still wrong; if it does not, the difference is not in
these reports at all.

Takes the JSON produced by the capture extractor: a list of [seconds, hex].
Stop djbox-ddj-bridge first -- both writing to the screens at once proves
nothing.
"""
import json
import os
import sys
import time


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
    with open(sys.argv[1]) as fh:
        events = json.load(fh)

    node = hidraw_node()
    if not node:
        sys.exit("no DDJ-1000 hidraw node")
    fd = os.open(node, os.O_RDWR)
    print("replaying %d reports through %s" % (len(events), node))

    started = time.monotonic()
    sent = 0
    try:
        for offset, payload in events:
            wait = started + offset - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            os.write(fd, bytes.fromhex(payload))
            sent += 1
    except OSError as exc:
        print("write failed after %d reports: %s" % (sent, exc))
    finally:
        os.close(fd)
    print("done, %d reports sent" % sent)


if __name__ == "__main__":
    main()
