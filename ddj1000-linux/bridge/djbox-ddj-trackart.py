#!/usr/bin/env python3
"""Build jog-screen artwork and waveform payloads for a track.

Called by the bridge when a deck loads something. Produces the two payloads the
DDJ-1000's screens take:

  artwork   u16 LE length + an 80x80 JFIF JPEG (command 0x2B)
  waveform  0x80 + 600 records of <4-byte colour><outer><inner><00> (command 0x2C)

The cover comes out of the file's own tags and the waveform from a decode, both
through ffmpeg, so no Python imaging or audio libraries are needed.
"""
import math
import json
import os
import struct
import subprocess
import sys

COLUMNS = 600
MAX_HEIGHT = 40
MAX_ARTWORK = 4300      # rekordbox's own covers run to about this
CORE_GAIN = 1.8         # lifts RMS into the core height the screen expects

# A column's four colour bytes are not a token out of a fixed set of seven, as
# they look. They are TWO little-endian RGB565 colours -- bytes 0-1 the outer
# band, bytes 2-3 the inner core -- which the screen converts to its own
# ARGB1555 with (v >> 1) & 0x7FE0 | v & 0x1F. None of the seven values
# rekordbox uses appears anywhere in the unit's firmware; there is no table to
# be limited by. Any colour renders, per column, per band.
#
# Which of the seven rekordbox picks tracks the ratio between a column's core
# and its peak -- how dense the sound is rather than how loud -- with a
# separate set for quiet columns. A drum hit is a tall spike with a small core
# and takes the first; a bassline fills its column and takes the last.
QUIET_HEIGHT = 14        # columns shorter than this use the quiet set

# rekordbox's own blue ramp, as (outer, inner) RGB triples. A theme replaces
# these wholesale; see THEME below.
STOCK_LOUD = [
    (0.45, (8, 72, 115), (16, 97, 156)),     # spiky: transients, percussion
    (0.62, (8, 97, 139), (16, 129, 189)),
    (0.77, (0, 109, 189), (8, 145, 255)),
    (1.01, (8, 137, 172), (16, 186, 238)),   # dense: bass, sustained tone
]
STOCK_QUIET = [
    (0.70, (90, 145, 172), (123, 194, 230)),
    (0.85, (106, 145, 189), (148, 194, 255)),
    (1.01, (156, 174, 189), (213, 234, 255)),  # near silence
]


def rgb565(colour):
    r, g, b = (max(0, min(255, int(c))) for c in colour)
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def token(outer, inner):
    """The four bytes a column carries: two RGB565 colours, little endian."""
    o, i = rgb565(outer), rgb565(inner)
    return bytes((o & 0xFF, o >> 8, i & 0xFF, i >> 8))

# What goes on the 80x80 tile: the track's name over its cover ("both"),
# the cover alone, or the name alone. The unit's own layout has nowhere to
# put a track name, which is the thing people ask for it to show.
# What goes on the tile: "both" the name over the cover, "cover" the picture
# alone, "title" the name alone. A theme's "caption": false is the same as
# "cover" and is the friendlier place to say it.
#
# Worth knowing before asking for a caption: the screen does not show the whole
# tile. One of its four layouts draws it 80x80, the other three draw the top
# 80x45 and throw the rest away -- so text along the bottom, which is where it
# reads best over a picture, is invisible on three layouts out of four.
TILE_MODE = os.environ.get("DDJ_JOG_TILE", "both")

# A theme for the tile, since the tile is the only part of the jog screen that
# is ours -- the dial, the scale and the background are drawn by the unit's own
# firmware from its own resources and cannot be reached.
#
# Read from a file so it can be changed without touching code. Anything left
# out keeps the default below.
#
#   /etc/djbox-jog-theme.json
#   {
#     "background": [16, 18, 26],   the tile behind a track with no cover
#     "text":       [240, 242, 250],
#     "band":       0.75,           how hard the strip under the text darkens
#     "image":      "/home/dj/logo.png",   use this instead of every cover
#     "badge":      "/home/dj/badge.png",  corner mark over the cover, any size
#     "badge_size": 22
#   }
THEME_FILE = os.environ.get("DDJ_JOG_THEME", "/etc/djbox-jog-theme.json")
THEME = {
    "background": [16, 18, 26],
    "text": [240, 242, 250],
    "band": 0.75,
    "image": "",
    "badge": "",
    "badge_size": 22,
}
try:
    with open(THEME_FILE) as _fh:
        THEME.update(json.load(_fh))
except (OSError, ValueError):
    pass


WHITE = (255, 255, 255)


def hex_rgb(value, fallback):
    """#rrggbb or [r, g, b] to a triple; anything else keeps the fallback."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(c) for c in value)
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            pass
    return fallback


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def build_ramp():
    """The seven (threshold, outer, inner) rows, themed or stock.

    A theme names the two ends of the loud ramp and a colour for the quiet
    columns; the steps in between are interpolated and the inner band is the
    outer one lifted toward white, which is the relationship rekordbox's own
    seven have. Naming all seven rows outright is also allowed, for anyone who
    wants the exact colours rather than a gradient.
    """
    spec = THEME.get("waveform") or {}
    rows = spec.get("colours")
    if isinstance(rows, list) and len(rows) == 7:
        limits = [r[0] for r in STOCK_LOUD] + [r[0] for r in STOCK_QUIET]
        built = []
        for limit, row in zip(limits, rows):
            outer = hex_rgb(row[0] if isinstance(row, (list, tuple)) else row,
                            (0, 0, 0))
            inner = hex_rgb(row[1] if isinstance(row, (list, tuple))
                            and len(row) > 1 else None, mix(outer, WHITE, 0.35))
            built.append((limit, outer, inner))
        return built[:4], built[4:]

    low = hex_rgb(spec.get("from"), None)
    high = hex_rgb(spec.get("to"), None)
    if low is None or high is None:
        return STOCK_LOUD, STOCK_QUIET
    quiet = hex_rgb(spec.get("quiet"), mix(high, WHITE, 0.55))
    lift = float(spec.get("lift", 0.35))

    loud = []
    for i, (limit, _o, _i) in enumerate(STOCK_LOUD):
        outer = mix(low, high, i / (len(STOCK_LOUD) - 1.0))
        loud.append((limit, outer, mix(outer, WHITE, lift)))
    quiet_rows = []
    for i, (limit, _o, _i) in enumerate(STOCK_QUIET):
        outer = mix(mix(low, high, 0.5), quiet,
                    0.4 + 0.3 * i / (len(STOCK_QUIET) - 1.0))
        quiet_rows.append((limit, outer, mix(outer, WHITE, lift)))
    return loud, quiet_rows


LOUD_COLOURS, QUIET_COLOURS = build_ramp()


def colour_for(outer, ratio):
    table = QUIET_COLOURS if outer < QUIET_HEIGHT else LOUD_COLOURS
    for limit, band, core in table:
        if ratio < limit:
            return token(band, core)
    return token(table[-1][1], table[-1][2])


# Where to look when a file carries no cover of its own, in order: a picture
# sitting beside it; failing that the track's name is drawn as a tile.
FOLDER_COVERS = ("cover.jpg", "cover.png", "folder.jpg", "folder.png",
                 "front.jpg", "album.jpg")


def artwork_source(path):
    """The best picture available for a track: its own, or its folder's."""
    if embedded_cover(path):
        return path
    folder = os.path.dirname(path)
    for name in FOLDER_COVERS:
        candidate = os.path.join(folder, name)
        if os.path.exists(candidate):
            return candidate
    return None


def embedded_cover(path):
    """Whether the file has a picture stream of its own."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(out.strip())


def track_name(path):
    """Artist and title from the file's own tags, falling back to its name."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "format_tags=artist,title", "-of", "default=nw=1:nk=0", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=15).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        out = ""
    tags = {}
    for line in out.splitlines():
        key, _, value = line.partition("=")
        key = key.split(":")[-1].strip().lower()
        if value.strip():
            tags[key] = value.strip()

    if tags.get("title"):
        return tags.get("artist", ""), tags["title"]

    name = os.path.splitext(os.path.basename(path))[0]
    # Strip the leading track number rippers put there.
    words = name.split()
    if words and words[0].rstrip(".-").isdigit():
        words = words[1:]
    return "", " ".join(words) or name


def fit(draw, text, font, width):
    """One line, cut with an ellipsis rather than dropped words."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "\u2026", font=font) > width:
        text = text[:-1]
    return (text.rstrip() + "\u2026") if text else ""


def wrap(draw, text, font, width, limit):
    """Break text into lines that fit; the last one is cut with an ellipsis."""
    lines, current = [], ""
    for word in text.split():
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=font) <= width:
            current = trial
            continue
        if not current:
            current = fit(draw, trial, font, width)
            continue
        lines.append(current)
        if len(lines) == limit:
            return lines
        current = word
    if current and len(lines) < limit:
        lines.append(current)
    return lines[:limit]


def label_tile(path, cover):
    """The 80x80 tile: the track's name, over its cover when there is one.

    The name is what people actually want off the jog -- it is the one thing
    the unit's own layout has no room for -- so it goes on whether or not
    there is a picture behind it. Over a cover it sits in a darkened band
    across the bottom; with no cover it takes the whole tile.
    """
    from PIL import Image, ImageDraw, ImageFont

    artist, title = track_name(path)
    # A theme picture stands in for every cover, for a deck that should look
    # like itself rather than like whatever is loaded.
    if THEME["image"]:
        try:
            cover = Image.open(THEME["image"]).convert("RGB").resize(
                (80, 80), Image.LANCZOS)
        except (OSError, ValueError):
            pass
    over_cover = cover is not None
    image = cover if over_cover else Image.new(
        "RGB", (80, 80), tuple(THEME["background"]))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            11 if over_cover else 13)
        small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
    except OSError:
        font = small = ImageFont.load_default()

    rows = [(line, font) for line in
            wrap(draw, title, font, 76, 2 if over_cover else 4)]
    if artist:
        rows.append((fit(draw, artist, small, 76), small))

    step = 12 if over_cover else 14
    height = sum(step if face is font else 11 for _, face in rows) + 4

    if over_cover:
        # Darken the band the text sits in, hard enough to read over anything.
        band = image.crop((0, 80 - height, 80, 80))
        black = Image.new("RGB", band.size, (0, 0, 0))
        image.paste(Image.blend(band, black, float(THEME["band"])),
                    (0, 80 - height))
        y = 80 - height + 2
    else:
        y = (80 - height) // 2 + 2

    for line, face in rows:
        x = max(1, (80 - draw.textlength(line, font=face)) // 2)
        draw.text((x, y), line, fill=tuple(THEME["text"]), font=face)
        y += step if face is font else 11

    # A small mark in the top corner, over whatever is behind it. Transparency
    # is honoured, so a PNG with an alpha channel sits on the cover cleanly.
    if THEME["badge"]:
        try:
            size = max(8, min(40, int(THEME["badge_size"])))
            badge = Image.open(THEME["badge"]).convert("RGBA").resize(
                (size, size), Image.LANCZOS)
            image.paste(badge, (80 - size - 2, 2), badge)
        except (OSError, ValueError):
            pass
    return image


def artwork_payload(path):
    """Cover art, as the exact flavour of JPEG the screen decodes.

    The unit's decoder is not a general one. Every cover rekordbox sends is a
    JFIF baseline file with 4:2:0 chroma, and ffmpeg's own MJPEG output --
    4:4:4, no JFIF header, a Lavc comment where the header should be -- is
    quietly ignored by the screen. So ffmpeg only unpacks the picture and the
    encoding is done here, where the flavour can be pinned down.
    """
    import io
    from PIL import Image

    cover = None
    source = artwork_source(path)
    if source is not None:
        try:
            raw = subprocess.run(
                ["ffmpeg", "-v", "quiet", "-y", "-i", source, "-an", "-vframes", "1",
                 "-vf", "scale=80:80", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            raw = b""
        if len(raw) >= 80 * 80 * 3:
            cover = Image.frombytes("RGB", (80, 80), raw[:80 * 80 * 3])

    # A theme saying caption: false is the same as asking for the cover alone.
    plain = THEME.get("caption") is False
    if (plain or TILE_MODE == "cover") and cover is not None:
        image = cover
    else:
        image = label_tile(path, cover if TILE_MODE != "title" else None)
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
        squares = 0
        # step through the block rather than every sample: 600 columns of a long
        # track is millions of samples, and a peak envelope does not need them all
        step = max(2, (len(chunk) // 400) & ~1)
        count = 0
        for i in range(0, len(chunk) - 1, step):
            value = abs(struct.unpack_from("<h", chunk, i)[0])
            peak = max(peak, value)
            squares += value * value
            count += 1
        peaks.append(peak)
        rms_values.append(math.sqrt(squares / max(count, 1)))

    ceiling = max(peaks) or 1
    body = bytearray([0x80])
    for peak, rms in zip(peaks, rms_values):
        outer = max(1, min(MAX_HEIGHT, round(peak / ceiling * MAX_HEIGHT)))
        # The core is drawn from the RMS rather than the peak, and lifted so
        # the spread of core-to-peak ratios lands where rekordbox's does --
        # which is what picks the colour.
        inner = max(1, min(outer, round(rms / ceiling * MAX_HEIGHT * CORE_GAIN)))
        body += colour_for(outer, inner / outer) + bytes([outer, inner, 0x00])
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
