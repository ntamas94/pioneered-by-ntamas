#!/usr/bin/env python3
"""Build jog-screen artwork and waveform payloads for a track.

Called by the bridge when a deck loads something. Produces the two payloads the
DDJ-1000's screens take:

  artwork   u16 LE length + an 80x80 JFIF JPEG (command 0x2B)
  waveform  0x80 + 600 records of <4-byte colour><outer><inner><00> (command 0x2C)

The cover comes out of the file's own tags and the waveform from a decode, both
through ffmpeg, so no Python imaging or audio libraries are needed.
"""
import os
import struct
import subprocess
import sys

COLUMNS = 600
MAX_HEIGHT = 40

# The controller only accepts these seven colour tokens; they are the palette
# rekordbox uses, identical across every track it was captured with. Ordered
# here from quiet to loud so a column can pick one by amplitude.
WAVE_COLOURS = [
    bytes.fromhex("779d5fd7"),   # near silence
    bytes.fromhex("976c1f96"),
    bytes.fromhex("955c1c7e"),
    bytes.fromhex("550cdd15"),
    bytes.fromhex("77039f0c"),
    bytes.fromhex("4e0a1313"),
    bytes.fromhex("110b1714"),   # loudest
]


MAX_ARTWORK = 4300      # rekordbox's own covers run to about this


def artwork_payload(path):
    """Embedded cover art, as the exact flavour of JPEG the screen decodes.

    The unit's decoder is not a general one. Every cover rekordbox sends is a
    JFIF baseline file with 4:2:0 chroma, and ffmpeg's own MJPEG output --
    4:4:4, no JFIF header, a Lavc comment where the header should be -- is
    quietly ignored by the screen. So ffmpeg only unpacks the picture and the
    encoding is done here, where the flavour can be pinned down.
    """
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-y", "-i", path, "-an", "-vframes", "1",
             "-vf", "scale=80:80", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if len(raw) < 80 * 80 * 3:
        return None

    import io
    from PIL import Image

    image = Image.frombytes("RGB", (80, 80), raw[:80 * 80 * 3])
    for quality in (85, 75, 65, 55, 45, 35):
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=quality, subsampling=2, optimize=False)
        data = buf.getvalue()
        if len(data) <= MAX_ARTWORK:
            return struct.pack("<H", len(data)) + data
    return None


def waveform_payload(path):
    """A 600-column overview of the whole track."""
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", "4000",
             "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=180).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    samples = len(raw) // 2
    if samples < COLUMNS:
        return None

    per_column = samples // COLUMNS
    peaks = []
    rms_values = []
    for col in range(COLUMNS):
        start = col * per_column * 2
        chunk = raw[start:start + per_column * 2]
        peak = 0
        total = 0
        # step through the block rather than every sample: 600 columns of a long
        # track is millions of samples, and a peak envelope does not need them all
        step = max(2, (len(chunk) // 400) & ~1)
        count = 0
        for i in range(0, len(chunk) - 1, step):
            value = abs(struct.unpack_from("<h", chunk, i)[0])
            peak = max(peak, value)
            total += value
            count += 1
        peaks.append(peak)
        rms_values.append(total / max(count, 1))

    ceiling = max(peaks) or 1
    body = bytearray([0x80])
    for peak, mean in zip(peaks, rms_values):
        outer = max(1, min(MAX_HEIGHT, round(peak / ceiling * MAX_HEIGHT)))
        inner = max(1, min(outer, round(mean / ceiling * MAX_HEIGHT * 1.6)))
        colour = WAVE_COLOURS[min(len(WAVE_COLOURS) - 1,
                                  int(outer / MAX_HEIGHT * len(WAVE_COLOURS)))]
        body += colour + bytes([outer, inner, 0x00])
    return bytes(body)


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: djbox-ddj-trackart.py <track> <artwork.bin> <waveform.bin>")
    track, art_out, wave_out = sys.argv[1:4]
    if not os.path.exists(track):
        sys.exit("no such track: %s" % track)

    art = artwork_payload(track)
    if art:
        with open(art_out, "wb") as fh:
            fh.write(art)
        print("artwork %d bytes" % len(art))
    else:
        print("no usable cover art")

    wave = waveform_payload(track)
    if wave:
        with open(wave_out, "wb") as fh:
            fh.write(wave)
        print("waveform %d bytes" % len(wave))
    else:
        print("could not build a waveform")


if __name__ == "__main__":
    main()
