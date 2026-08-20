#!/usr/bin/env python3
"""Drive the DDJ-1000 jog wheel screens over HID.

The screens live on the controller's vendor HID interface (interface 3, usage
page 0xFFA0, 64-byte reports, no report IDs). Two things are needed to get
anything on screen:

1. A **state record**, command 0x21, pushed at 125 Hz per screen. Without it the
   unit shows its idle logo and ignores uploaded content, however correct the
   upload is. Layout (decoded from USBPcap captures of rekordbox):

       byte 0      screen: 0x10 left, 0x20 right
       byte 1      0x21
       bytes 2-5   bring-up flags; byte 5 bit 0x80 = this deck is sync master
       byte 9      0x00 screen off, 0x10 no track, 0xB4 track loaded
       bytes 11-12 playhead seconds, big-endian pair
       bytes 13-14 playhead milliseconds, u16 LE, 0..999
       bytes 15-18 track id, u32 LE
       byte 21     BPM, integer      (byte 38 repeats it)
       byte 31     first beat, ms    (byte 55 repeats it)
       byte 58     0x01 = track loaded
       byte 61     0x0D while the screen is up

2. **Content transfers**, chunked as

       <deck> <cmd> <index u16 LE> <total u16 LE> + 58 payload bytes

   one report per millisecond, preceded by a lone copy of the last chunk:

       0x2B  artwork    u16 LE length, then a JFIF JPEG (80x80, colour)
       0x2C  waveform   0x80, then 600 records of <4-byte colour><h1><h2>00,
                        heights 1..40, colours from a fixed 7-entry palette
       0x2D  cue points
       0x2F  beat grid  u16 LE beat count, then the beats

Usage:
    djbox-ddj-jogdisplay.py show <deck> <artwork.jpg> [waveform.bin]
    djbox-ddj-jogdisplay.py idle <deck>
"""
import glob
import os
import struct
import sys
import threading
import time

CHUNK = 58
DECKS = {1: 0x10, 2: 0x20, 3: 0x30, 4: 0x40}
STATE_INTERVAL = 0.008        # the unit expects the state record at 125 Hz
REPORT_INTERVAL = 0.0012      # the endpoint services one report per millisecond

# Colour tokens the unit accepts in a waveform record. Only these seven ever
# appear, byte-identical across every captured track, so they are an enumerated
# palette rather than computed colour.
WAVE_COLOURS = [
    bytes.fromhex("4e0a1313"), bytes.fromhex("110b1714"), bytes.fromhex("77039f0c"),
    bytes.fromhex("550cdd15"), bytes.fromhex("955c1c7e"), bytes.fromhex("976c1f96"),
    bytes.fromhex("779d5fd7"),                             # near silence
]


def hidraw_node():
    for node in sorted(glob.glob("/dev/hidraw*")):
        name = os.path.basename(node)
        try:
            with open("/sys/class/hidraw/%s/device/uevent" % name) as fh:
                info = fh.read().upper()
        except OSError:
            continue
        if "2B73" in info and "0020" in info:
            return node
    return None


def write_report(fd, body):
    os.write(fd, b"\x00" + bytes(body).ljust(64, b"\x00"))


def send_transfer(fd, deck, cmd, payload, lock):
    chunks = [payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK)] or [b""]
    total = len(chunks)

    def report(index, data):
        with lock:
            write_report(fd, struct.pack("<BBHH", deck, cmd, index, total) + data)
        time.sleep(REPORT_INTERVAL)

    report(total, chunks[-1])                    # the priming copy rekordbox sends
    for i, data in enumerate(chunks, start=1):
        report(i, data)
    return total


class ScreenState:
    """The 0x21 record for one screen, pushed continuously by a background thread."""

    def __init__(self, fd, deck, lock):
        self.fd = fd
        self.deck = deck
        self.lock = lock
        self.loaded = False
        self.track_id = 0
        self.bpm = 0
        self.first_beat = 0
        self.position_ms = 0
        self.master = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=1)

    def record(self):
        b = bytearray(64)
        b[0] = self.deck
        b[1] = 0x21
        b[2] = 0x18                      # bring-up flags, as rekordbox leaves them
        b[3] = 0x0A
        b[4] = 0x11
        b[5] = 0x81 | (0x80 if self.master else 0x00)
        b[9] = 0xB4 if self.loaded else 0x10
        seconds, ms = divmod(int(self.position_ms), 1000)
        b[11] = (seconds >> 8) & 0xFF
        b[12] = seconds & 0xFF
        struct.pack_into("<H", b, 13, ms)
        struct.pack_into("<I", b, 15, self.track_id & 0xFFFFFFFF)
        b[21] = b[38] = min(255, int(self.bpm))
        b[27] = 0x80
        b[31] = b[55] = min(255, int(self.first_beat))
        b[58] = 0x01 if self.loaded else 0x00
        b[61] = 0x0D
        return b

    def _run(self):
        while not self._stop.is_set():
            with self.lock:
                write_report(self.fd, self.record())
            time.sleep(STATE_INTERVAL)


def artwork_payload(path):
    """Scale any picture to what the screen takes: an 80x80 JPEG, length-prefixed."""
    import io
    from PIL import Image

    image = Image.open(path).convert("RGB").resize((80, 80), Image.LANCZOS)
    for quality in (90, 80, 70, 60, 50, 40, 30):
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=quality)
        data = buf.getvalue()
        if len(data) <= 4000:
            break
    return struct.pack("<H", len(data)) + data


def flat_waveform(height=20, colour=1):
    """A placeholder overview: 600 columns of the same height and colour."""
    body = bytearray([0x80])
    record = WAVE_COLOURS[colour % len(WAVE_COLOURS)] + bytes([height, max(1, height // 2), 0])
    body += record * 600
    return bytes(body)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mode = sys.argv[1]
    deck = DECKS.get(int(sys.argv[2]))
    if deck is None:
        sys.exit("deck must be 1-4")

    node = hidraw_node()
    if not node:
        sys.exit("no DDJ-1000 HID node")
    fd = os.open(node, os.O_RDWR)
    lock = threading.Lock()
    state = ScreenState(fd, deck, lock)

    try:
        if mode == "idle":
            state.loaded = False
            state.start()
            time.sleep(3)
            return

        # Announce a loaded track first: the unit ignores content uploads while
        # it thinks the deck is empty.
        state.loaded = True
        state.track_id = 0x03250305
        state.bpm = 140
        state.first_beat = 32
        state.start()
        time.sleep(0.3)

        art = sys.argv[3]
        if art.endswith(".bin"):
            with open(art, "rb") as fh:
                payload = fh.read()
        else:
            payload = artwork_payload(art)

        if len(sys.argv) > 4:
            with open(sys.argv[4], "rb") as fh:
                wave = fh.read()
        else:
            wave = flat_waveform()

        print("waveform: %d chunks" % send_transfer(fd, deck, 0x2C, wave, lock))
        print("artwork:  %d chunks" % send_transfer(fd, deck, 0x2B, payload, lock))

        print("holding the screen up, ctrl-c to stop")
        start = time.monotonic()
        while True:
            state.position_ms = int((time.monotonic() - start) * 1000)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        state.stop()
        os.close(fd)


if __name__ == "__main__":
    main()
