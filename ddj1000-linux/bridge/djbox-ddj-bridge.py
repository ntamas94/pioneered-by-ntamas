#!/usr/bin/env python3
"""DDJ-1000 MIDI bridge that keeps the jog displays unlocked.

The controller locks its jog screens to "NO AUDIO DRIVER" until the DJ software
authenticates itself over SysEx and keeps a heartbeat running, and it re-runs
that challenge whenever it is power-cycled or replugged. The 66-byte response
only works if it reaches the device in a single USB transfer, which means
writing it to the raw MIDI device -- and raw MIDI is exclusive, so the DJ
software cannot hold the port at the same time.

So this owns the controller's raw MIDI port and bridges it to a virtual port
that Mixxx opens instead:

    Mixxx  <->  VirMIDI 5-1  <->  this daemon  <->  DDJ-1000 raw MIDI

Handshake traffic is answered here and never forwarded; everything else passes
through in both directions, one write() per complete MIDI message.

Protocol -- header F0 00 40 05 00 00 02 00 00 ... F7, arguments are TLV
<tag> <len> <payload> where len counts the two header bytes and payload bytes
are "spread" into 4-bit nibbles:

    HOST -> UNIT  50 01                  keep-alive, at least every second
    UNIT -> HOST  11 02                  "who are you?"
    HOST -> UNIT  12 2A ... 03 <SeedA>   identity (SeedA is not validated)
    UNIT -> HOST  13 2A ... 03 <SeedE>   challenge
    HOST -> UNIT  14 38 ... 04 <HashE>   response
    UNIT -> HOST  15 02                  ACK

    HashE = FNV-1a-32( SeedE || (SeedE XOR 0x680131FB) ), big-endian.

Handshake research: Nikolaus Einhauser (Swiftb0y), CDJHidProtocol.
"""
import ctypes
import ctypes.util
import errno
import fcntl
import glob
import math
import os
import shutil
import sqlite3
import struct
import subprocess
import threading
import select
import signal
import zlib
import sys
import syslog
import time

import faulthandler

asound = ctypes.CDLL(ctypes.util.find_library("asound"))
SND_RAWMIDI_NONBLOCK = 2

# Without explicit signatures ctypes assumes every argument and return value is
# a C int, which truncates the 64-bit handles and buffer pointers on arm64 and
# eventually segfaults the daemon -- which looks, from the outside, like the jog
# displays freezing and re-locking a few seconds after they come up.
asound.snd_rawmidi_open.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.c_char_p, ctypes.c_int]
asound.snd_rawmidi_open.restype = ctypes.c_int
asound.snd_rawmidi_close.argtypes = [ctypes.c_void_p]
asound.snd_rawmidi_close.restype = ctypes.c_int
asound.snd_rawmidi_write.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
asound.snd_rawmidi_write.restype = ctypes.c_ssize_t
asound.snd_rawmidi_read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
asound.snd_rawmidi_read.restype = ctypes.c_ssize_t
asound.snd_rawmidi_drain.argtypes = [ctypes.c_void_p]
asound.snd_rawmidi_drain.restype = ctypes.c_int
DEBUG = bool(os.environ.get("DDJ_DEBUG"))
DEBUG_STATE = bool(os.environ.get("DDJ_DEBUG_STATE"))
DEBUG_HID = bool(os.environ.get("DDJ_DEBUG_HID"))
# Diagnostic switch: skip uploading artwork to the jog screens. The upload
# sits between the cue table and the waveform in the load, and whether its
# presence is what keeps the playhead from moving is exactly the question.
NO_ARTWORK = bool(os.environ.get("DDJ_NO_ARTWORK"))
# Diagnostic switch: only push state for decks that hold a track.
LOADED_ONLY = bool(os.environ.get("DDJ_LOADED_ONLY"))
# Diagnostic tape: append every outgoing screen report here, so the exact
# byte stream the bridge produced can be replayed at the unit by itself.
TAPE = os.environ.get("DDJ_TAPE")


HDR = bytes([0xF0, 0x00, 0x40, 0x05, 0x00, 0x00, 0x02, 0x00, 0x00])

# The unit keys the authentication secret off the manufacturer name we announce,
# and it also decides from it how the jog displays are meant to be driven:
# rekordbox draws them over the vendor HID interface, while the Traktor and
# Serato style mappings drive them with plain MIDI CCs. Announcing the identity
# that matches how we actually drive the screens is what DDJ_IDENTITY selects.
IDENTITIES = {
    "rekordbox": (b"PioneerDJ", b"rekordbox", 0x680131FB),
    "traktor": (b"NativeInstruments", b"Traktor", 0x8C5B3F5D),
    "serato": (b"Serato", b"Serato DJ", 0x0D6F55AB),
    "virtualdj": (b"Atomix", b"VirtualDJ", 0x97779123),
}
MANUFACTURER, PRODUCT, PIONEER_SECRET = IDENTITIES[
    os.environ.get("DDJ_IDENTITY", "rekordbox")]
KEEPALIVE = bytes([0x50, 0x01])
KEEPALIVE_INTERVAL = 0.2
SESSION_TIMEOUT = 10.0      # no ACK within this -> re-enumerate and try again
RECONNECT_CHECK = 0.3       # how often to notice the controller re-enumerating
# Re-asserting "screens on" used to be needed every couple of seconds, the way
# the community mappings do it, because nothing else kept the unit awake. The
# 0x21 state record at 125 Hz does that now, and re-sending the display and
# time-mode notes on top of it makes the picture twitch. Set a number of
# seconds here to bring the old behaviour back.
SCREENS_REFRESH = 0
# How long after the DJ software goes quiet the screens are handed back to
# the unit's own start-up picture.
MIXXX_QUIET = 6.0
DEVICE_POLL = 0.02          # how often to look for the controller coming back

DEVICE_ID = bytes([0x08, 0x07, 0x0A, 0x00, 0x08, 0x0E, 0x0E, 0x0A, 0x0C, 0x00,
                   0x09, 0x00, 0x03, 0x04, 0x07, 0x06, 0x00, 0x0B, 0x09, 0x00])
SEED_A = bytes([0x06, 0x08, 0x07, 0x02, 0x0B, 0x0A, 0x03, 0x02,
                0x0D, 0x04, 0x00, 0x07, 0x0C, 0x00, 0x0E, 0x01])

# Sent once before the handshake: the unit expects the display state to be
# initialised before it will accept an authentication response.
# The order is the capture's: 0B, then 0C, then 0A, sent only after the unit
# has accepted the authentication -- rekordbox never sends these cold.
PRELUDE = [
    bytes.fromhex("000b2b68000000"),
    bytes.fromhex("000c0000020e0e000000"),
    bytes.fromhex("000a00280026000a394a742853202014152205" + "00" * 21),
]
JOGSCREEN_ENABLE = [
    bytes.fromhex("000a002800260024153255481421" + "00" * 26),
    bytes.fromhex("000b3560140100"),
    bytes.fromhex("000c0000020e0e000000"),
]
JOGSCREEN_ENABLE_6 = [
    bytes.fromhex("000b310000000000"),
    bytes.fromhex("000a002800260028490a64691400" + "00" * 26),
    bytes.fromhex("000b310000000000"),
    bytes.fromhex("000c0000020e0e000000"),
]
BROWSER_STARTUP = [bytes.fromhex(h) for h in
                   ("9f407f", "9f4100", "9f427f", "bf4630", "bf4100", "bf4200",
                    "bf4300", "bf4430", "bf4720", "bf4840", "bf4910", "bf4a20")]
DECK_STARTUP_NOTES = (0x0B, 0x47, 0x0C, 0x50)

# --- jog screen state -------------------------------------------------------
# The screens only show anything while a 0x21 state record arrives at 125 Hz per
# deck. Everything in it can be read out of the MIDI the controller mapping is
# already sending: minutes and seconds on notes 0x42/0x43, BPM as a 14-bit CC on
# 0x15/0x35. So the bridge watches that traffic on its way through and keeps the
# screens fed with Mixxx's real state.
SCREEN_DECKS = (0x10, 0x20, 0x30, 0x40)
STATE_INTERVAL = 0.008
MIXXX_DB = "/home/dj/.mixxx/mixxxdb.sqlite"
TRACKART = "/usr/local/bin/djbox-ddj-trackart.py"
# Built artwork and waveforms, kept between loads: building one means
# decoding the whole track, which takes seconds.
ART_CACHE = "/var/cache/djbox-art"
CMD_ARTWORK = 0x2B
CMD_WAVEFORM = 0x2C
# One lead byte and 600 columns of seven: the size every waveform this
# builds comes out at, and the size of the empty one that clears it.
WAVEFORM_BYTES = 1 + 600 * 7
# Pause between screen reports. The endpoint runs at 1 kHz and paces the
# writes on its own; asking sleep() for a millisecond gets two or three
# from the scheduler, and across the couple of hundred reports a load
# takes that was most of the second it spent.
REPORT_GAP = float(os.environ.get("DDJ_REPORT_GAP", "0"))
# Holding the unit's capture stream open keeps its screens awake, but the two
# directions cannot run at once here: the quirk names the input endpoint as
# playback's implicit feedback source, so capture takes the clock playback
# needs and the output stalls with its hardware pointer at zero. Off by
# default; DDJ_HOLD_AUDIO=1 for a box that never plays anything.
HOLD_AUDIO = os.environ.get("DDJ_HOLD_AUDIO", "0") != "0"

# Byte 3 of the state record, bit 0x08: set counts the time down, clear counts
# it up. The Time Mode preference is not a MIDI setting at all -- capturing
# rekordbox while it was switched shows nothing on the MIDI side and this bit
# flipping -- so a fixed 0x0A here is what left every screen on remaining, with
# no track length behind it to count down from.
TIME_REMAINING_BIT = 0x08
# How long before the end the screen starts flashing, and where it speeds up.
# rekordbox drops bit 0 of byte 4 every 0.9 s from thirty seconds left and
# every 0.2 s from fifteen.
END_WARNING_MS = 30000
END_HURRY_MS = 15000
DISPLAY_FLAGS = int(os.environ.get("DDJ_DISPLAY_FLAGS", "0x18"), 16)
# Where rekordbox's library row numbers sat in every capture.
# rekordbox's own values here always begin with 3 in the top seven-bit group
# -- 03 08 0a 04, 03 06 0b 00, 03 0a 09 08 across every capture -- which puts
# them between 6.29 and 8.38 million. A number outside that band starts with a
# different group, and the group looks like what says which kind of id this is.
LIBRARY_ROW_BASE = 6400000
FORCED_ID = int(os.environ.get("DDJ_FORCE_ID", "0"), 16)


def track_by_duration(seconds):
    """Find the loaded track in Mixxx's library by its duration.

    Mixxx's scripting API does not expose a path, so the mapping announces the
    duration and this matches it. Duration to the millisecond is effectively
    unique in a library of any size.
    """
    try:
        db = sqlite3.connect("file:%s?mode=ro" % MIXXX_DB, uri=True)
    except sqlite3.Error:
        return None
    try:
        row = db.execute(
            "SELECT tl.location FROM library l JOIN track_locations tl"
            " ON l.location = tl.id"
            " WHERE l.mixxx_deleted = 0 AND abs(l.duration - ?) < 0.05"
            " ORDER BY abs(l.duration - ?) LIMIT 1", (seconds, seconds)).fetchone()
    except sqlite3.Error:
        return None
    finally:
        db.close()
    return row[0] if row else None


def library_tracks():
    """Every track Mixxx knows about, longest first."""
    try:
        db = sqlite3.connect("file:%s?mode=ro" % MIXXX_DB, uri=True)
    except sqlite3.Error:
        return []
    try:
        rows = db.execute(
            "SELECT tl.location FROM library l JOIN track_locations tl"
            " ON l.location = tl.id WHERE l.mixxx_deleted = 0").fetchall()
    except sqlite3.Error:
        return []
    finally:
        db.close()
    return [r[0] for r in rows]


def u24(value):
    """The screen's millisecond figures: 24 bits, little end first."""
    value = max(0, min(0xFFFFFF, int(value)))
    return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF


class DeckScreen:
    def __init__(self):
        self.loaded = False
        self.suspend = False
        self.duration_ms = 0
        self.remaining = False
        self.on_air = True
        self.tempo_percent = 0.0
        self.cues = []
        self.cue_ms = 0
        self.ready = False
        self.bpm = 0
        # The track's own tempo, unpitched: the loop ends are measured
        # against it, while the BPM above is whatever the fader is asking for.
        self.file_bpm = 0
        self.track_id = 0
        self.first_beat_ms = 0
        self.key_code = 0
        self.loop_in = -1
        self.loop_out = -1
        self.last_seen = 0.0
        self.base_ms = -1
        self.base_time = 0.0
        self.rate = 0.0
        self.report_ms = 0
        self.report_time = 0.0

    def set_position(self, ms):
        """Take a millisecond figure from the mapping into a smoothed clock.

        The screen is fed at 125 Hz but the reports arrive at 20, and they
        arrive unevenly -- a timer in a busy application is not a metronome.
        Snapping the playhead onto each one hands that unevenness straight to
        the needle, which is the shiver. So the clock runs at its own
        estimated rate and each report only steers it, and the rate itself is
        measured rather than assumed, so scratching and the tempo fader come
        out right instead of fighting a hardcoded 1.0.
        """
        now = time.monotonic()
        dt = now - self.report_time
        if dt <= 0.0 or dt > 0.5:
            self.base_ms, self.base_time, self.rate = ms, now, 0.0
            self.report_ms, self.report_time = ms, now
            return

        predicted = self.base_ms + (now - self.base_time) * 1000.0 * self.rate
        measured = (ms - self.report_ms) / (dt * 1000.0)
        self.report_ms, self.report_time = ms, now

        if abs(measured) > 5.0 or abs(ms - predicted) > 400:
            # A seek or a hard scratch: nothing to smooth, just go there.
            self.base_ms, self.base_time, self.rate = ms, now, 0.0
            return
        self.rate += (measured - self.rate) * 0.35
        self.base_ms = predicted + (ms - predicted) * 0.25
        self.base_time = now

    def position_ms(self):
        # Run the clock on between reports so the needle turns at the 125 Hz
        # the screen is fed rather than stepping at the rate they arrive.
        elapsed = min(time.monotonic() - self.base_time, 0.5)
        position = max(0, int(self.base_ms + elapsed * 1000.0 * self.rate))
        if self.duration_ms:
            # Never past the end of the track: the screen reads anything
            # beyond it as "over" and counts negative time at the DJ.
            position = min(position, self.duration_ms)
        return position

    def loop_code(self):
        """The screen's own name for how long the loop is: 12 + log2(beats).

        One beat is 12 and 64 beats is 18, the whole auto-loop ladder in
        between, and 1 means a length that is not on it -- a hand-set loop,
        which the screen writes as two dashes. The beats have to be counted
        against the track's own tempo: the loop ends are original-time
        milliseconds while the BPM on the record is the pitched figure, and
        counting against that one puts every loop a few percent off its step.
        """
        bpm = self.file_bpm or self.bpm
        if bpm <= 0 or self.loop_out <= self.loop_in:
            return 0x01
        beats = (self.loop_out - self.loop_in) / (60000.0 / bpm)
        if beats <= 0:
            return 0x01
        steps = math.log2(beats)
        nearest = int(round(steps))
        if abs(steps - nearest) > 0.05 or not -5 <= nearest <= 6:
            return 0x01
        return 12 + nearest

    def record(self, deck):
        b = bytearray(64)
        b[0] = deck
        b[1] = 0x21
        # Display Artwork (0x08) and CUE SCOPE (0x10). Both are off in the one
        # capture where the playhead travels and on in the ones where it does
        # not, and CUE SCOPE is a waveform view in its own right -- switchable
        # here so the pair can be tried against the playhead.
        b[2] = DISPLAY_FLAGS
        # Bit 0x02 is on air: the screen greys the deck out without it. Every
        # capture of someone actually playing has it set from end to end,
        # which is why it read as a constant for so long -- it only drops when
        # the mixer shuts the channel out.
        b[3] = ((0x02 if self.on_air else 0x00)
                | (TIME_REMAINING_BIT if self.remaining else 0))
        # The track-end warning. The screen flashes for the last thirty
        # seconds and it is the host that flashes it, twice over: rekordbox
        # drops bit 0 of this byte and puts it back every 0.9 s from 30.0 s
        # left, then every 0.2 s from 15 s -- the same warning, hurrying.
        b[4] = 0x11
        if self.loaded and self.duration_ms:
            left = self.duration_ms - self.position_ms()
            if 0 < left <= END_WARNING_MS:
                period = 0.9 if left > END_HURRY_MS else 0.2
                if int(time.monotonic() / period) & 1:
                    b[4] = 0x10
        b[5] = 0x81
        if self.suspend:
            # The unloading frame of a load: no track at all, whatever the
            # rest of the state says. A flag rather than juggling the real
            # fields, because the playhead reports keep arriving while the
            # sequence runs and would put them straight back -- the unit then
            # never sees the empty frame and quietly drops the new upload.
            b[9] = 0x10
            b[61] = 0x0D
            return bytes(b)
        looping = self.loaded and self.loop_out > self.loop_in >= 0
        b[9] = (0xBC if looping else 0xB4) if self.loaded else 0x10
        b[10] = self.loop_code() if looping else 0x00
        # The playhead is minutes and seconds, not a 16-bit second count: the
        # second byte never goes past 59 in a capture, and feeding it 60 is
        # what made the screen call the track over a minute in. Always the
        # elapsed figure, even in remaining mode: the needle is drawn from
        # this same field, and counting it down runs the needle backwards.
        # The remaining readout is the unit's own, switched by the mode note.
        seconds, ms = divmod(self.position_ms(), 1000)
        # Bit 7 of the minute byte is the needle's direction, not a flag to
        # set: raising it runs the two pointers backwards against each other.
        b[11] = min(127, seconds // 60)
        b[12] = seconds % 60
        b[13] = ms & 0xFF
        b[14] = (ms >> 8) & 0xFF
        b[15] = self.track_id & 0xFF
        b[16] = (self.track_id >> 8) & 0xFF
        b[17] = (self.track_id >> 16) & 0xFF
        b[18] = (self.track_id >> 24) & 0xFF
        # BPM to one decimal, the way rekordbox reports it: the whole number,
        # then the tenth in the high nibble of the next byte -- 141.8 goes out
        # as 8D 80. Anything in the low nibble and the screen gives up and
        # shows 999.9.
        whole = min(255, int(self.bpm))
        # The playing speed, hundredths of a percent, signed 16-bit LE. It
        # reads zero in every capture taken before this one, because they were
        # all taken with the fader centred; sweeping it end to end in
        # rekordbox runs this pair from -1000 to 1000 over a +-10% range, and
        # the BPM alongside divides back to the track's own 145.000 at every
        # point along the way.
        speed = max(-32768, min(32767, int(round(self.tempo_percent * 100))))
        b[23] = speed & 0xFF
        b[24] = (speed >> 8) & 0xFF
        b[21] = b[38] = whole
        b[22] = b[39] = (int(round((self.bpm - whole) * 10)) % 10) << 4
        # The loop ends are 24-bit millisecond figures; with no loop the in
        # point reads 0x800000 and the out point zero. The marker the screen
        # draws is the first beat normally and the loop in while one is set.
        if looping:
            b[25], b[26], b[27] = u24(self.loop_in)
            b[28], b[29], b[30] = u24(self.loop_out)
            marker = self.loop_in
        else:
            b[27] = 0x80
            marker = self.cue_ms or self.first_beat_ms
        # The two marker fields hold the same value in every captured record
        # bar one: b55 is a copy of b31, not the playhead. Writing the live
        # position into b55 was a guess that never matched rekordbox, so the
        # marker sat at whatever the guess produced.
        b[31], b[32], b[33] = u24(marker)
        b[55], b[56], b[57] = u24(marker)
        # 1 while a track is being handed over, 3 once its waveform is up.
        # rekordbox holds 1 for the length of the upload and then sits on 3 for
        # the rest of the track -- and 3 is what moves the playhead along the
        # waveform. Stuck on 1, the screen draws everything and never marks
        # where the music is.
        b[58] = (0x03 if self.ready else 0x01) if self.loaded else 0x00
        # Set just before the 3 goes into the byte before it, and cleared just
        # after it goes back to 1. In every capture where the playhead travels
        # this pair reads 03 and non-zero together; where it stands still they
        # read 01 and 00 for the whole recording.
        b[59] = 0x16 if (self.loaded and self.ready) else 0x00
        b[60] = self.key_code                  # musical key, constant per track
        b[61] = 0x0D
        return bytes(b)



def beat_grid(bpm, first_beat_ms, duration_s):
    """The 0x2F payload: a beat count, then one record per beat.

    Each record is <position in the bar, 1..4> <time in ms, u24 LE>. The unit
    draws the bar markers on the waveform from this, and rejects a load that
    arrives without it.
    """
    if duration_s <= 0:
        return bytes(58)
    # The last beat is the only length the unit is ever told, so the grid has
    # to span the whole track even when the tempo is not known yet -- a short
    # grid, or the 58 zero bytes this used to send, and the screen decides the
    # track is over and puts up END.
    if bpm <= 0:
        bpm = 120.0
    interval = 60000.0 / bpm
    # Exactly the track and no further. The screen lays the waveform out
    # across the whole grid, so beats past the end of the music stretch the
    # picture: sixteen bars of overshoot at 87 BPM put the playhead a good
    # twenty seconds adrift of where the music actually was.
    count = min(int((duration_s * 1000 - first_beat_ms) / interval), 2000)
    if count < 1:
        return bytes(58)
    body = bytearray(struct.pack("<H", count))
    for i in range(count):
        ms = int(first_beat_ms + i * interval)
        body += bytes([i % 4 + 1, ms & 0xFF, (ms >> 8) & 0xFF, (ms >> 16) & 0xFF])
    return bytes(body)


POST_AUTH_FILE = "/usr/local/share/ddj1000-post-auth-midi.txt"


# One line of the cue table: minute, second, millisecond (16-bit), and a flag
# byte whose meaning is still unknown -- rekordbox writes zero for real cues.
# An empty slot is the out-of-range time 158:47.295, which is what rekordbox
# fills its unused slots with.
CUE_EMPTY_SLOT = bytes((0x9E, 0x2F, 0x27, 0x01, 0x00))


def track_record(key, cues):
    """The 0x30 transfer: the track id followed by its hot cues.

    Six bytes each -- a marker, a colour, a spare, then the position as a
    24-bit millisecond figure -- in the order they were set rather than in
    time order, which is how a capture of rekordbox has them. Sent once as
    the track is handed over and again once its waveform is up.
    """
    body = bytearray(key)
    for minute, second, milli, loop in cues[:16]:
        # A marker byte, a colour, then the position in the same shape as
        # every other time here: minutes, seconds, and a 16-bit millisecond
        # figure. Written as a 24-bit millisecond count instead, as this did,
        # the seconds land in the milliseconds and every cue sits wrong.
        #
        # Saved loops carry their own marker and colour: a capture of
        # rekordbox writing one alongside a plain hot cue has 02/24 against
        # the loop and 01/16 against the cue.
        body += bytes((0x02 if loop else 0x01, 0x24 if loop else 0x16,
                       minute & 0xFF, second % 60,
                       milli & 0xFF, (milli >> 8) & 0xFF))
    return bytes(body) + bytes(max(0, 116 - len(body)))


def cue_table(key, cues):
    """The 0x2D transfer: ten slots of cue markers for the beat scale.

    Starts at the track id. The two bytes in front of it in a capture belong
    to the transfer header -- every chunk repeats how many chunks there are --
    and copying them into the payload here shifts the whole table along by two,
    which is enough for the screen to file it under nothing at all.
    """
    body = bytearray()
    body += key
    body += bytes((0x0A, 0x00))
    for minute, second, ms, _loop in cues[:10]:
        body += bytes((minute & 0xFF, second % 60, ms & 0xFF, (ms >> 8) & 0xFF, 0x00))
    for _ in range(max(0, 10 - len(cues))):
        body += CUE_EMPTY_SLOT
    return bytes(body)


def load_post_auth():
    try:
        with open(POST_AUTH_FILE) as fh:
            return [bytes.fromhex(line.strip()) for line in fh if line.strip()]
    except OSError:
        return []


POST_AUTH = load_post_auth()


# ---- handshake maths -------------------------------------------------------

def fnv1a32(data):
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def pack_nibbles(spread):
    return bytes(((spread[2 * i] << 4) | spread[2 * i + 1]) for i in range(len(spread) // 2))


def spread_bytes(data):
    out = bytearray()
    for b in data:
        out.append((b >> 4) & 0x0F)
        out.append(b & 0x0F)
    return bytes(out)


def auth_response(seed_e):
    secret = int.from_bytes(seed_e, "big") ^ PIONEER_SECRET
    return fnv1a32(seed_e + secret.to_bytes(4, "big")).to_bytes(4, "big")


def tlv(tag, payload):
    return bytes([tag, len(payload) + 2]) + payload


def identity_msg():
    body = tlv(0x01, MANUFACTURER) + tlv(0x02, PRODUCT) + tlv(0x03, SEED_A)
    return bytes([0x12, len(body) + 2]) + body


def capabilities_msg(hash_e_spread):
    body = (tlv(0x01, MANUFACTURER) + tlv(0x02, PRODUCT)
            + tlv(0x04, hash_e_spread) + tlv(0x05, DEVICE_ID))
    return bytes([0x14, len(body) + 2]) + body


def find_arg(msg, tag):
    i = 11
    while i + 1 < len(msg) - 1:
        t, ln = msg[i], msg[i + 1]
        if ln < 2:
            return None
        if t == tag:
            return msg[i + 2:i + ln]
        i += ln
    return None


# ---- MIDI stream framing ---------------------------------------------------

DATA_BYTES = {0xC0: 1, 0xD0: 1}      # everything else in 0x80..0xEF takes two


class MidiSplitter:
    """Turn a raw MIDI byte stream into complete messages."""

    def __init__(self):
        self.buf = bytearray()
        self.status = 0

    def feed(self, data):
        out = []
        self.buf += data
        while self.buf:
            b = self.buf[0]
            if b == 0xF0:
                end = self.buf.find(0xF7)
                if end < 0:
                    break                       # wait for the rest
                out.append(bytes(self.buf[:end + 1]))
                del self.buf[:end + 1]
                self.status = 0
                continue
            if b >= 0xF8:                       # realtime, may interleave
                out.append(bytes([b]))
                del self.buf[0]
                continue
            if b >= 0x80:
                need = DATA_BYTES.get(b & 0xF0, 2)
                if len(self.buf) < 1 + need:
                    break
                out.append(bytes(self.buf[:1 + need]))
                self.status = b if b < 0xF0 else 0
                del self.buf[:1 + need]
                continue
            # running status
            if not self.status:
                del self.buf[0]
                continue
            need = DATA_BYTES.get(self.status & 0xF0, 2)
            if len(self.buf) < need:
                break
            out.append(bytes([self.status]) + bytes(self.buf[:need]))
            del self.buf[:need]
        return out


# ---- device discovery ------------------------------------------------------

def card_by_name(needle):
    try:
        with open("/proc/asound/cards") as fh:
            for line in fh:
                s = line.strip()
                if needle.upper() in s.upper() and s[:1].isdigit():
                    return int(s.split()[0])
    except OSError:
        pass
    return None


def ddj_node():
    card = card_by_name("DDJ")
    return "/dev/snd/midiC%dD0" % card if card is not None else None


def ddj_hidraw():
    """The controller's vendor HID node (interface 3)."""
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


def virmidi_node(sub):
    card = card_by_name("VirMIDI")
    return "/dev/snd/midiC%dD%d" % (card, sub) if card is not None else None


class _ctrltransfer(ctypes.Structure):
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8),
                ("wValue", ctypes.c_uint16), ("wIndex", ctypes.c_uint16),
                ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]


USBDEVFS_CONTROL = (3 << 30) | (ctypes.sizeof(_ctrltransfer) << 16) | (ord("U") << 8) | 0
USBDEVFS_RESET = (ord("U") << 8) | 20      # _IO('U', 20)


def usb_node():
    for path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        base = os.path.dirname(path)
        try:
            if open(path).read().strip() != "2b73":
                continue
            if open(os.path.join(base, "idProduct")).read().strip() != "0020":
                continue
            bus = int(open(os.path.join(base, "busnum")).read())
            dev = int(open(os.path.join(base, "devnum")).read())
        except OSError:
            continue
        return "/dev/bus/usb/%03d/%03d" % (bus, dev)
    return None


def audio_alt_setting():
    """Alternate setting of the controller's vendor audio interface, or None."""
    for path in glob.glob("/sys/bus/usb/devices/*:1.0/bAlternateSetting"):
        base = os.path.dirname(path).rsplit(":", 1)[0]
        try:
            if open(os.path.join(base, "idVendor")).read().strip() != "2b73":
                continue
            return int(open(path).read().strip())
        except (OSError, ValueError):
            continue
    return None


def vendor_probe():
    """The read the Pioneer driver issues right after selecting alt 1.

    This is what actually takes the jog displays off "NO AUDIO DRIVER". Capturing
    the moment the driver is enabled in Windows Device Manager shows the whole
    trigger: SET_INTERFACE(interface 0, alt 1) and then this two-byte vendor read
    -- with no audio streaming at all. Linux selects alt 1 when a PCM is opened
    but never issues the read, so the screens stayed locked.
    """
    node = usb_node()
    if not node:
        return False
    try:
        fd = os.open(node, os.O_RDWR)
    except OSError:
        return False
    try:
        buf = ctypes.create_string_buffer(2)
        xfer = _ctrltransfer(0xC0, 0x00, 0x0000, 0x8003, 2, 2000,
                             ctypes.cast(buf, ctypes.c_void_p))
        fcntl.ioctl(fd, USBDEVFS_CONTROL, xfer)
        return True
    except OSError as exc:
        syslog.syslog("vendor probe failed: %s" % exc)
        return False
    finally:
        os.close(fd)


def audio_streaming():
    """True while something has the controller's playback PCM open.

    The unit shows "NO AUDIO DRIVER" whenever the host is not holding the audio
    interface in its streaming alternate setting, so a reset that interrupts
    playback trades one problem for the other -- and the display state the user
    actually cares about depends on this, not on the handshake.
    """
    for status in glob.glob("/proc/asound/card*/pcm0p/sub0/status"):
        card_dir = status.split("/pcm0p")[0]
        try:
            with open(os.path.join(card_dir, "id")) as fh:
                if "DDJ" not in fh.read().upper():
                    continue
            with open(status) as fh:
                return "RUNNING" in fh.read()
        except OSError:
            continue
    return False


def usb_reset():
    """Re-enumerate the controller.

    The unit accepts an authentication response only once per USB session: if a
    handshake is started and then abandoned (the daemon restarts, the heartbeat
    stops), it keeps challenging forever but never acknowledges again. A reset
    gives it a fresh session, after which the handshake succeeds immediately.
    """
    import fcntl
    for path in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        base = os.path.dirname(path)
        try:
            if open(path).read().strip() != "2b73":
                continue
            if open(os.path.join(base, "idProduct")).read().strip() != "0020":
                continue
            bus = int(open(os.path.join(base, "busnum")).read())
            dev = int(open(os.path.join(base, "devnum")).read())
        except OSError:
            continue
        node = "/dev/bus/usb/%03d/%03d" % (bus, dev)
        try:
            fd = os.open(node, os.O_WRONLY)
            try:
                fcntl.ioctl(fd, USBDEVFS_RESET, 0)
            finally:
                os.close(fd)
            syslog.syslog("reset %s to get a fresh session" % node)
            return True
        except OSError as exc:
            syslog.syslog("cannot reset %s: %s" % (node, exc))
    return False


# ---- the bridge ------------------------------------------------------------

class SessionStale(Exception):
    """The unit keeps challenging but will not accept -- it needs a fresh session."""


class Bridge:
    def __init__(self, card, vir_path):
        # The controller side goes through the ALSA raw MIDI API rather than a
        # plain file descriptor: writing a message and then draining leaves the
        # output idle, so the next message becomes one USB transfer. Written
        # straight to the character device the driver packs it together with
        # whatever else is queued and the 66-byte response arrives split in two,
        # which the unit silently ignores.
        self.inp = ctypes.c_void_p()
        self.out = ctypes.c_void_p()
        name = ("hw:%d,0,0" % card).encode()
        rc = asound.snd_rawmidi_open(ctypes.byref(self.inp), ctypes.byref(self.out),
                                     name, SND_RAWMIDI_NONBLOCK)
        if rc < 0:
            raise OSError(errno.EBUSY, "snd_rawmidi_open(%s) failed: %d" % (name.decode(), rc))
        self.rbuf = ctypes.create_string_buffer(1024)
        self.vir = os.open(vir_path, os.O_RDWR | os.O_NONBLOCK)
        self.from_ddj = MidiSplitter()
        self.probe_at = 0.0
        self.burst_at = 0.0
        self.burst_seen = set()
        self.panel = {}
        # Seeded from the clock so ids differ across restarts too.
        self.load_seq = int(time.time()) % 5
        self.library_row = 0
        self.screens_woken = False
        self.mixxx_seen = 0.0
        # Whether the screens have already been handed back to the unit, so
        # the release goes out once rather than sixty times a second.
        self.released = False
        self.paused = False
        self.time_mode_reset = False
        self.state_logged = 0.0
        self.draw_locks = [threading.Lock() for _ in SCREEN_DECKS]
        self.from_vir = MidiSplitter()
        self.screens = [DeckScreen() for _ in range(4)]
        self.drawn = {}
        self.last_state = 0.0
        self.authenticated = False
        self.started = time.monotonic()
        # Hold the HID interface open for as long as we run. Linux only polls a
        # HID interrupt endpoint while some client has the device open, and this
        # unit takes that 1 kHz poll on EP 0x87 as "a driver is present": without
        # it the jog wheels show "NO AUDIO DRIVER" no matter what else the host
        # does. The Windows driver stack polls it from plug-in and never stops.
        self.hid = None
        self.card = card
        self.hid_node = ddj_hidraw()
        node = self.hid_node
        if node:
            try:
                self.hid = os.open(node, os.O_RDWR | os.O_NONBLOCK)
                syslog.syslog("holding %s open to keep the HID poll running" % node)
            except OSError as exc:
                syslog.syslog("cannot open %s: %s" % (node, exc))
        else:
            syslog.syslog("no HID node found -- the jog displays will stay locked")

    def close(self):
        # Idempotent on purpose: the error paths close the bridge and the
        # surrounding finally closes it again, and closing an ALSA raw MIDI
        # handle twice is a double free -- the daemon died of SIGSEGV every
        # time the controller hiccuped, which read as the jog displays
        # freezing and re-locking.
        for attr in ("inp", "out"):
            handle = getattr(self, attr, None)
            if handle is None:
                continue
            setattr(self, attr, None)
            try:
                asound.snd_rawmidi_close(handle)
            except Exception:
                pass
        for attr in ("vir", "hid"):
            fd = getattr(self, attr, None)
            if fd is None:
                continue
            setattr(self, attr, None)
            try:
                os.close(fd)
            except OSError:
                pass

    def to_ddj(self, data):
        """One write plus a drain per message, so each lands in its own transfer."""
        data = bytes(data)
        if DEBUG and len(data) > 3:
            syslog.syslog("tx %d: %s" % (len(data), data[:24].hex()))
        buf = ctypes.create_string_buffer(data, len(data))
        asound.snd_rawmidi_write(self.out, buf, len(data))
        asound.snd_rawmidi_drain(self.out)

    def read_ddj(self):
        n = asound.snd_rawmidi_read(self.inp, self.rbuf, 1024)
        if n > 0:
            return self.rbuf.raw[:n]
        # -EAGAIN just means nothing to read; anything else means the controller
        # is gone (unplugged or power-cycled) and we have to rebuild everything,
        # otherwise the daemon happily keeps writing to a dead device.
        if n < 0 and n != -errno.EAGAIN:
            raise OSError(-n, "raw MIDI read failed")
        return b""

    def device_changed(self):
        """True once the controller has re-enumerated under us."""
        return card_by_name("DDJ") != self.card or ddj_hidraw() != self.hid_node

    def to_mixxx(self, data):
        data = bytes(data)
        written = 0
        while written < len(data):
            try:
                written += os.write(self.vir, data[written:])
            except BlockingIOError:
                select.select([], [self.vir], [], 0.05)

    def sysex(self, payload):
        self.to_ddj(HDR + payload + bytes([0xF7]))

    @staticmethod
    def press_preferences():
        """Press Ctrl+P at whatever has the keyboard on the desktop.

        Mixxx exposes no way to open its preferences from a skin or a mapping;
        the dialog is bound to the shortcut and to the menu, and a skin button
        pointed at a made-up control key just creates a control nothing
        listens to. Reaching in from outside is the only route there is.
        """
        try:
            subprocess.Popen(
                ["xdotool", "key", "--clearmodifiers", "ctrl+p"],
                env=dict(os.environ, DISPLAY=os.environ.get("DISPLAY", ":0")),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            syslog.syslog("cannot open preferences: %s" % exc)

    def announce_track(self, msg):
        """Handle the mapping's private track announcement (F0 7D deck ms F7)."""
        if len(msg) < 5 or msg[1] != 0x7D:
            return False
        self.mixxx_seen = time.monotonic()
        deck_index = msg[2] & 0x0F
        if (msg[2] & 0x70) == 0x70:
            # Open Mixxx's preferences. It has no control for that -- the
            # window is on a keyboard shortcut and nothing else -- so a skin
            # button asking for it can only be answered from outside, by
            # pressing the key at it. Tested before every other branch
            # because 0x70 also satisfies the 0x30 and 0x60 tests below.
            self.press_preferences()
            return True
        if deck_index <= 3 and (msg[2] & 0x60) == 0x60:
            # The cue point. This is the marker the screen draws across the
            # waveform: left at zero it sits against the very start of the
            # track, which is where it stayed while nothing sent one.
            self.screens[deck_index].cue_ms = (
                (msg[3] << 21) | (msg[4] << 14) | (msg[5] << 7) | msg[6])
            return True
        if deck_index <= 3 and (msg[2] & 0x50) == 0x50:
            # The hot cue positions, for the markers on the beat scale.
            screen = self.screens[deck_index]
            count = msg[3]
            cues = []
            for i in range(count):
                base = 4 + i * 5
                if base + 5 > len(msg) - 1:
                    break
                minute, second = msg[base], msg[base + 1]
                milli = (msg[base + 2] << 7) | msg[base + 3]
                cues.append((minute, second, milli, bool(msg[base + 4])))
            if cues != screen.cues:
                screen.cues = cues
                if cues:
                    syslog.syslog("jog screen %d: cues at %s (track %.1f s)"
                                  % (deck_index + 1,
                                     ", ".join("%d:%02d.%03d" % c[:3] for c in cues),
                                     screen.duration_ms / 1000.0))
                if screen.loaded and self.authenticated:
                    # Already on a deck: update the record in place.
                    key = struct.pack("<I", screen.track_id)
                    threading.Thread(
                        target=self.send_hid_transfer,
                        args=(SCREEN_DECKS[deck_index], 0x30,
                              track_record(key, cues)),
                        daemon=True).start()
            return True
        if deck_index <= 3 and (msg[2] & 0x30) == 0x30:
            # Which time readout to show. Five bytes, so it has to be picked
            # off before the length check the longer messages need. Only the
            # state bit changes: the overlay's remaining-time note must never
            # be sent with the screens up -- it drags the unit into its
            # overlay picture, which reads as the whole display falling apart.
            self.screens[deck_index].remaining = bool(msg[3])
            return True
        if len(msg) < 8:
            return False
        ms = (msg[3] << 21) | (msg[4] << 14) | (msg[5] << 7) | msg[6]
        if deck_index > 3:
            return True
        if msg[2] & 0x40:                      # the loop, if one is running
            screen = self.screens[deck_index]
            if len(msg) < 13 or not msg[3]:
                screen.loop_in = screen.loop_out = -1
            else:
                screen.loop_in = (msg[4] << 21) | (msg[5] << 14) | (msg[6] << 7) | msg[7]
                screen.loop_out = (msg[8] << 21) | (msg[9] << 14) | (msg[10] << 7) | msg[11]
            return True
        if msg[2] & 0x20:                      # grid start, key, on air
            screen = self.screens[deck_index]
            screen.first_beat_ms = (msg[3] << 7) | msg[4]
            screen.key_code = msg[5]
            # Older mappings do not send it; a deck nothing says otherwise
            # about is on air, which is what every capture of a DJ actually
            # playing looks like.
            screen.on_air = bool(msg[7]) if len(msg) >= 9 else True
            return True
        if msg[2] & 0x10:                      # a playhead report, not a load
            screen = self.screens[deck_index]
            screen.set_position(ms)
            screen.last_seen = time.monotonic()
            # Only a deck that has actually been announced counts as loaded.
            # The mapping reports a playhead for every deck, empty ones
            # included, and taking that as "a track is here" left the screen
            # holding a loaded deck with a zero id -- nothing for it to hang
            # the waveform or the playhead on.
            screen.loaded = screen.track_id != 0
            if len(msg) >= 10:                 # the tempo rides along with it
                screen.bpm = ((msg[7] << 7) | msg[8]) / 10.0
            if len(msg) >= 12:                 # and the speed the fader asks for
                raw = (msg[9] << 7) | msg[10]
                screen.tempo_percent = (raw - 5000) / 100.0
            return True
        if ms <= 0:                            # the deck was emptied
            screen = self.screens[deck_index]
            self.drawn[deck_index] = None
            screen.track_id = 0
            screen.loaded = False
            screen.ready = False
            screen.duration_ms = 0
            screen.bpm = 0
            screen.file_bpm = 0
            screen.cue_ms = 0
            screen.cues = []
            return True
        # The id the unit files artwork, waveform and cues under. Shaped the
        # way rekordbox shapes it: the track's length in milliseconds in the
        # upper three bytes, a small counter in the low one. The length alone
        # is unique enough, but the counter is what makes reloading the same
        # track a different id, which is how the screen knows to redraw.
        screen = self.screens[deck_index]
        if len(msg) >= 10:                     # the tempo comes with it
            screen.bpm = screen.file_bpm = ((msg[7] << 7) | msg[8]) / 10.0
        if screen.duration_ms != ms or not screen.track_id:
            # The id is the track's length, written the way the screen
            # writes every other time: minutes, seconds, and a 16-bit
            # millisecond figure, in that order. Its own firmware turns these
            # four bytes back into a time -- (minutes * 60 + seconds) * 1000
            # plus the milliseconds -- which is why a plain 32-bit millisecond
            # count was never recognised as a track at all, and why the
            # playhead would not travel for anything this loaded.
            seconds, milli = divmod(int(ms), 1000)
            minutes, seconds = divmod(seconds, 60)
            # A new track starts with no cues: the mapping only sends the
            # list when it changes, so the previous track's markers would
            # otherwise sit on the scale until it did.
            screen.cues = []
            screen.cue_ms = 0
            screen.track_id = (min(255, minutes)
                               | (seconds << 8)
                               | ((milli & 0xFF) << 16)
                               | ((milli >> 8) << 24))
            if FORCED_ID:
                screen.track_id = FORCED_ID
        screen.duration_ms = ms
        # The mapping repeats the announcement so a restarted daemon can catch
        # up; only redraw when it is actually a different track.
        if self.drawn.get(deck_index) == ms:
            return True
        self.drawn[deck_index] = ms
        threading.Thread(target=self._load_artwork_guarded,
                         args=(deck_index, ms / 1000.0), daemon=True).start()
        return True

    def _load_artwork_guarded(self, deck_index, seconds):
        # One draw per deck at a time. A second unload arriving while the first
        # is still uploading leaves the screen half written, which looks like
        # the display flickering and dropping out.
        lock = self.draw_locks[deck_index]
        if not lock.acquire(blocking=False):
            syslog.syslog("jog screen %d: already drawing, skipped" % (deck_index + 1))
            return
        try:
            self._load_artwork_locked(deck_index, seconds)
        finally:
            lock.release()

    def _load_artwork_locked(self, deck_index, seconds):
        # A worker thread that dies silently would just leave the screen blank,
        # so say what went wrong.
        try:
            self.load_artwork(deck_index, seconds)
        except Exception as exc:
            syslog.syslog("jog artwork failed: %r" % (exc,))

    def prebuild_cache(self):
        """Build every library track's artwork and waveform ahead of time.

        Building one means decoding the whole file, which is seconds of work,
        and doing it while a deck waits is the whole of the delay between
        loading a track and seeing it. Done here in the background instead,
        at the bottom of the scheduler, so the box is quietly ready.
        """
        try:
            os.nice(19)
        except OSError:
            pass
        tracks = library_tracks()
        built = 0
        for path in tracks:
            if not os.path.exists(path):
                continue
            tag = self.cache_tag(path)
            if tag and os.path.exists(os.path.join(ART_CACHE, tag + ".wave")):
                continue
            self.build_track_payloads(0, path)
            built += 1
            time.sleep(0.5)                    # leave the decks the machine
        if built:
            syslog.syslog("jog artwork: built %d of %d library tracks ahead of time"
                          % (built, len(tracks)))

    def load_artwork(self, deck_index, seconds):
        path = track_by_duration(seconds)
        if not path or not os.path.exists(path):
            syslog.syslog("no library match for a %.3f s track" % seconds)
            return
        deck = SCREEN_DECKS[deck_index]
        screen = self.screens[deck_index]

        started = time.monotonic()

        # rekordbox's load, in the order a capture of it shows. The unloading
        # step matters as much as the upload: it clears the deck with an
        # all-zero 0x30, lets a few state records go out with no track at all,
        # and only then announces the new id. Uploading against a deck that
        # still holds the previous track is what made the screen show the
        # artwork for a moment and throw it away again.
        #
        # It runs before the artwork build, not after: decoding a track for
        # its waveform takes seconds, and the deck should read right the
        # moment something lands on it. The picture catches up when ready.
        # rekordbox's own order for a fresh track, from a capture of it
        # loading one. Half of this sequence is demolition: the deck, the
        # waveform, the grid and the cue table are each wiped with a transfer
        # of the right shape full of zeros before anything real is sent, and
        # the two Pioneer messages land in the middle of the wiping rather
        # than in front of it.
        #
        #   clear deck, clear waveform, announce, clear grid, grid,
        #   the id, clear cues, artwork, waveform
        #
        # Sending the real waveform where the empty one belongs, as this did,
        # leaves the screen with a picture it will not run a playhead across.
        self.send_hid_transfer(deck, 0x30, bytes(116), prime=False)
        self.to_ddj(bytes((0x9F, deck_index, 0x00)))
        screen.ready = False
        screen.suspend = True                  # a few frames of "no track"
        time.sleep(0.03)
        screen.suspend = False
        time.sleep(0.01)
        key = struct.pack("<I", screen.track_id)

        # The clearing half runs before the artwork is built, not after:
        # building means decoding the whole track, and rekordbox has its own
        # ready long before it starts sending. Waiting on ours first left the
        # deck sitting empty for seconds where rekordbox's lands at once.
        self.send_hid_transfer(deck, CMD_WAVEFORM, bytes(WAVEFORM_BYTES),
                               prime=False)
        self.announce_load(screen.track_id)

        grid = beat_grid(screen.bpm, screen.first_beat_ms, seconds)
        self.send_hid_transfer(deck, 0x2F, bytes(58), prime=False)
        self.send_hid_transfer(deck, 0x2F, grid, prime=False)
        self.send_hid_transfer(deck, 0x30, track_record(key, screen.cues))
        for _ in range(3):
            self.send_hid_transfer(deck, 0x2D, bytes(60), prime=False)
        self.to_ddj(bytes((0x9F, deck_index, 0x7F)))

        payloads = self.build_track_payloads(deck_index, path)
        waveform = payloads.get(CMD_WAVEFORM, b"")
        syslog.syslog("jog screen %d: id %08x, %.1f s, %.1f BPM, %d beats, art %d, wave %d"
                      % (deck_index + 1, screen.track_id, seconds, screen.bpm,
                         int.from_bytes(grid[:2], "little"),
                         len(payloads.get(CMD_ARTWORK, b"")), len(waveform)))
        if CMD_ARTWORK in payloads and not NO_ARTWORK:
            self.send_hid_transfer(deck, CMD_ARTWORK, payloads[CMD_ARTWORK],
                                   prime=False)
        time.sleep(0.05)                       # let the artwork land first
        if waveform:
            self.send_hid_transfer(deck, CMD_WAVEFORM, waveform, prime=False)
        # The hot cues ride in the track record; the 0x2D table is the memory
        # cue list, which is why hot cues put there came up on the scale
        # wearing the wrong marker. Mixxx has no memory cues, so that table
        # stays as its ten empty slots.
        if screen.cues:
            self.send_hid_transfer(deck, 0x30, track_record(key, screen.cues))
        screen.ready = True
        syslog.syslog("jog screen %d: drew %s in %.0f ms"
                      % (deck_index + 1, os.path.basename(path),
                         (time.monotonic() - started) * 1000))

    @staticmethod
    def cache_tag(path):
        """Cache name for a track: its path and how recently it changed."""
        try:
            stamp = int(os.stat(path).st_mtime)
        except OSError:
            return None
        return "%08x-%d" % (zlib.crc32(path.encode("utf-8", "replace")) & 0xFFFFFFFF,
                            stamp)

    def build_track_payloads(self, deck_index, path):
        """The artwork and waveform for a track, cached across loads.

        The build decodes the whole file, which takes seconds; the same track
        loaded again -- the usual case in practice -- comes straight from the
        cache and its picture is up almost at once.
        """
        tag = self.cache_tag(path)
        if not tag:
            return {}
        cache_art = os.path.join(ART_CACHE, tag + ".art")
        cache_wave = os.path.join(ART_CACHE, tag + ".wave")

        if not (os.path.exists(cache_art) or os.path.exists(cache_wave)):
            try:
                os.makedirs(ART_CACHE, exist_ok=True)
            except OSError:
                pass
            art = "/run/djbox-ddj-art-%d.bin" % deck_index
            wave = "/run/djbox-ddj-wave-%d.bin" % deck_index
            try:
                subprocess.run([TRACKART, path, art, wave], timeout=240,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError) as exc:
                syslog.syslog("could not build the jog artwork: %s" % exc)
                return {}
            for made, kept in ((art, cache_art), (wave, cache_wave)):
                # shutil, not os.replace: the build writes to /run, which is
                # tmpfs, and the cache is on disk -- a rename across two
                # filesystems fails, and this quietly cached nothing.
                try:
                    shutil.move(made, kept)
                except (OSError, shutil.Error) as exc:
                    syslog.syslog("could not cache %s: %s" % (kept, exc))

        payloads = {}
        for name, cmd in ((cache_art, CMD_ARTWORK), (cache_wave, CMD_WAVEFORM)):
            try:
                with open(name, "rb") as fh:
                    payloads[cmd] = fh.read()
            except OSError:
                pass
        return payloads

    def send_hid_transfer(self, deck, cmd, payload, prime=True):
        """Upload one chunked transfer to the screen, one report per ms."""
        chunks = [payload[i:i + 58] for i in range(0, len(payload), 58)] or [b""]
        total = len(chunks)

        def report(index, data):
            # Every report is a full 64 bytes, short final chunk padded out.
            # rekordbox never sends a short one, and the screen treats one as
            # an unfinished transfer: it will draw the waveform it was given
            # and still refuse to run the playhead across it.
            packet = struct.pack("<BBHH", deck, cmd, index, total) + data
            packet += bytes(64 - len(packet))
            if DEBUG_HID and index <= 2:
                syslog.syslog("hid %02x deck%02x chunk %d/%d: %s"
                              % (cmd, deck, index, total, packet.hex()))
            self.to_ddj_hid(packet)
            if REPORT_GAP:
                time.sleep(REPORT_GAP)

        # The short records are led by a copy of their last chunk; artwork
        # and the waveform are sent straight through. Lead only: a capture of
        # a working load shows the run simply ending on its natural last
        # chunk, and repeating it once more after the run is what a capture
        # of this bridge had -- with the screens taking the data and never
        # moving the playhead over it.
        if prime and cmd in (0x2D, 0x2F, 0x30):
            report(total, chunks[-1])
        for i, data in enumerate(chunks, start=1):
            report(i, data)

    def clear_all_decks(self):
        """Empty every deck, so nothing from before is left standing.

        The screens keep whatever they were last given across a restart of
        this daemon and across the DJ software closing, which means a stale
        track sits on the wheels looking current. Nothing should show until
        something announces a track.
        """
        for index, deck in enumerate(SCREEN_DECKS):
            screen = self.screens[index]
            screen.loaded = False
            screen.ready = False
            screen.track_id = 0
            screen.duration_ms = 0
            screen.bpm = 0
            screen.cues = []
            screen.cue_ms = 0
            self.drawn[index] = None
            self.send_hid_transfer(deck, 0x30, bytes(116), prime=False)
            self.send_hid_transfer(deck, CMD_WAVEFORM, bytes(WAVEFORM_BYTES),
                                   prime=False)
            self.send_hid_transfer(deck, 0x2F, bytes(58), prime=False)
            self.to_ddj(bytes((0x9F, index, 0x00)))

    def hold_audio_open(self):
        """Keep the screens awake while the DJ software is not using the card.

        They go dark the moment nothing is streaming: the unit reads the audio
        interface sitting at its idle alternate setting as "no driver here".
        Opening the capture side holds it awake.

        Only while the card is otherwise idle, though. Sharing it with the DJ
        software costs that software its engine -- Mixxx opens its output, the
        callback never settles, and every track it is asked to load sits at
        "loading" for ever, which is a far worse fault than a dark screen.
        """
        recorder = None
        while True:
            card = card_by_name("DDJ")
            if card is None:
                recorder = self.stop_recorder(recorder)
                time.sleep(DEVICE_POLL)
                continue

            # Once the screens are up the interface has done its job here, and
            # holding it any longer only risks the stream the DJ software is
            # about to open. Unlocking happens against our own stream, before
            # anyone else's exists.
            if self.playback_in_use(card) or self.authenticated:
                recorder = self.stop_recorder(recorder)
            elif recorder is None or recorder.poll() is not None:
                try:
                    recorder = subprocess.Popen(
                        ["arecord", "-D", "hw:%d,0" % card, "-f", "S24_3LE",
                         "-c", "6", "-r", "44100", "-q"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError as exc:
                    syslog.syslog("cannot hold the audio interface open: %s" % exc)
                    return
            time.sleep(2.0)

    @staticmethod
    def stop_recorder(recorder):
        if recorder is not None and recorder.poll() is None:
            recorder.terminate()
            try:
                recorder.wait(timeout=2)
            except subprocess.TimeoutExpired:
                recorder.kill()
        return None

    @staticmethod
    def playback_in_use(card):
        """Whether anything has the controller's playback stream open."""
        for status in glob.glob("/proc/asound/card%d/pcm*p/sub*/status" % card):
            try:
                with open(status) as fh:
                    if "closed" not in fh.read():
                        return True
            except OSError:
                continue
        return False

    def pause(self, _signum=None, _frame=None):
        """Stop driving the screens without letting go of the controller.

        The unit only keeps its screens alive while something polls its HID
        interrupt endpoint, so simply stopping the daemon blanks them -- which
        makes it impossible to hand the screens to anything else, a capture
        replay included, and see what they do. SIGUSR1 toggles this: the poll
        and the session stay up, the state records stop.
        """
        self.paused = not self.paused
        syslog.syslog("state records %s" % ("paused" if self.paused else "resumed"))

    def push_state(self):
        if self.paused:
            return
        now = time.monotonic()
        # Nothing at all until the DJ software is there. Left alone the unit
        # shows its own start-up screen -- Pioneer DJ on one wheel, rekordbox
        # on the other -- and taking that over before anything can fill it in
        # replaces it with an empty deck. Once the software is talking the
        # decks are its to draw, track or no track.
        if now - self.mixxx_seen > MIXXX_QUIET:
            # Handing them back rather than just falling silent, which is what
            # rekordbox does when it lets go: an all-zero record and an empty
            # artwork per deck, after which the unit puts its own screen back
            # up. Going quiet alone leaves whatever was last drawn frozen
            # there, so a track sits on the wheel long after Mixxx has gone.
            # Only ever after Mixxx has actually been here: at start-up this
            # branch is reached before the unit is authenticated, and rekordbox
            # never writes HID to a locked unit -- doing so is what left the
            # screens on NO AUDIO DRIVER with every other condition met.
            if not self.released and self.authenticated and self.mixxx_seen:
                self.released = True
                syslog.syslog("no word from Mixxx -- handing the screens back")
                for deck in SCREEN_DECKS:
                    self.to_ddj_hid(bytes((deck, 0x21)) + bytes(62))
                    self.send_hid_transfer(deck, 0x2B, bytes(58), prime=False)
            return
        self.released = False

        for i, deck in enumerate(SCREEN_DECKS):
            screen = self.screens[i]
            if screen.loaded and now - screen.last_seen > 5.0:
                # The mapping went quiet, so the deck is empty -- or Mixxx
                # stopped talking for a moment, which looks the same from here
                # and blanks the screen for as long as it lasts.
                screen.loaded = False
                syslog.syslog("jog screen %d: no word from Mixxx for %.1f s, "
                              "blanking" % (i + 1, now - screen.last_seen))
            record = screen.record(deck)
            if DEBUG_STATE and screen.loaded and now - self.state_logged > 3.0:
                self.state_logged = now
                syslog.syslog("state deck%d: %s" % (i + 1, record.hex()))
            self.to_ddj_hid(record)

    def to_ddj_hid(self, report):
        if TAPE:
            try:
                with open(TAPE, "a") as fh:
                    fh.write("%.4f %s\n" % (time.monotonic(), bytes(report).hex()))
            except OSError:
                pass
        if self.hid is None:
            return
        # Not one byte before the unit has said yes. rekordbox's first HID
        # write comes over a second after the authentication answer, and
        # writing earlier is what kept the screens on NO AUDIO DRIVER with
        # every other condition met. Every write funnels through here -- the
        # state loop, the uploads, the hand-back -- so this is the one gate.
        # A restarted bridge is not locked out: the unit answers the opening
        # exchange with its "accepted" message again even mid-session, so
        # this flag comes back on its own.
        if not self.authenticated:
            return
        try:
            os.write(self.hid, bytes([0x00]) + bytes(report).ljust(64, bytes([0x00])))
        except OSError:
            pass

    def announce_load(self, track_id):
        """Tell the unit a track is being put on a deck.

        Two Pioneer messages rekordbox sends at every load and this never did.
        The first is fixed; the second carries the track's id as a 28-bit
        figure in seven-bit pieces. Without them the uploads still draw --
        artwork and waveform appear -- but the screen never turns them into a
        track it can follow, which is why the playhead stayed parked whatever
        the state record said.
        """
        # Written whole rather than through sysex(), which adds the header
        # and terminator these already carry.
        self.to_ddj(bytes.fromhex("f00040050000020000000b2b6800000000f7"))
        time.sleep(0.002)
        # Not the display id: rekordbox puts its own library row number
        # here. Kept inside the band its own values sit in and stepped once
        # per load, so the top seven-bit group reads 3 the way theirs does.
        self.library_row += 1
        value = (LIBRARY_ROW_BASE + self.library_row) & 0x0FFFFFFF
        self.to_ddj(bytes((0xF0, 0x00, 0x40, 0x05, 0x00, 0x00, 0x02,
                           0x00, 0x00, 0x00, 0x0C, 0x00, 0x00,
                           (value >> 21) & 0x7F, (value >> 14) & 0x7F,
                           (value >> 7) & 0x7F, value & 0x7F,
                           0x00, 0x00, 0xF7)))
        time.sleep(0.002)

    def reset_time_mode(self):
        """Put the time readout back to elapsed.

        The unit remembers this across power cycles, and in remaining mode it
        counts down from a track length it works out for itself -- which it
        never gets from us, so it sits at -99:59. rekordbox never touches the
        setting at all; it was an earlier version of this bridge, sending the
        overlay's remaining-time marker on every display update, that latched
        it on.

        Sent once the screens are actually released, not during bring-up: a
        locked screen takes the message and does nothing with it.
        """
        if self.time_mode_reset:
            return
        self.time_mode_reset = True
        for ch in range(4):
            self.to_ddj(bytes((0x90 | ch, 0x44, 0x00)))
            time.sleep(0.002)

    def screens_on(self):
        """Wake the jog screens: ring light and display on, once per session.

        Note 0x5D is inverted -- 0x00 turns the screen on, 0x7F turns it off.

        Kept deliberately short. These notes belong to the MIDI overlay the
        Traktor and Serato style mappings draw with, and anything from that set
        pulls the unit back to its own picture for a moment -- which, sent
        again on every audio-interface transition, is a screen that keeps
        flashing. The remaining-time marker in particular is part of that
        overlay and is not sent at all. Once is enough: the HID state record
        keeps the screens up from then on.
        """
        if self.screens_woken:
            return
        self.screens_woken = True
        for ch in range(4):
            self.to_ddj(bytes((0x90 | ch, 0x5B, 0x01)))
            self.to_ddj(bytes((0x90 | ch, 0x5D, 0x00)))


    def unit_settings(self):
        """Settings the DJ software applies on the unit itself.

        Addresses from rekordbox's own MidiMappings/DDJ-1000.midi.csv:
        BF 44 demo mode / screen saver, BF 48 jog LCD brightness, BF 46 jog ring
        brightness. Turning the demo off stops the unit taking over its own
        screens after ten idle minutes.
        """
        # 9F 09 7F is what the Traktor/Bome mapping calls "send PC app connect",
        # and it is the entire content of its screen-reset action.
        for msg in ((0x9F, 0x09, 0x7F), (0xBF, 0x44, 0x00),
                    (0xBF, 0x48, 0x40), (0xBF, 0x46, 0x30)):
            self.to_ddj(bytes(msg))

    def display_bringup(self):
        """Replay what the DJ software sends after the unit accepts the auth.

        Captured from rekordbox on Windows (keep-alives removed, this daemon
        sends its own). Faithfully reproducing the whole burst is what takes the
        decks out of the locked screen; a hand-picked subset did not.
        """
        # The 0B/0A/0C block, exactly where the capture has it: first thing
        # after the acceptance, 0B then 0C then 0A.
        for payload in PRELUDE:
            self.sysex(payload)
        self.unit_settings()
        if POST_AUTH:
            for msg in POST_AUTH:
                self.to_ddj(msg)
                time.sleep(0.002)
            return
        self._display_bringup_fallback()

    def request_panel_state(self):
        """Make the unit report where its knobs and faders are sitting.

        It does this once, unprompted, as the host brings it up -- which is
        long before Mixxx has opened its port, so Mixxx never sees it and
        starts out disagreeing with the panel. Replaying that same opening
        burst asks for it again. The mapping's own note on a deck channel is
        the signal that Mixxx is ready for the answer.
        """
        now = time.monotonic()
        if now - self.probe_at < 2.0:          # the mapping sends one per deck
            return
        self.probe_at = now

        # Ask again first, in case this is a session where the unit still has
        # something to say, then hand over what it said last time. Sorting puts
        # each 14-bit control's high byte before its low one, which is the
        # order Mixxx expects to assemble them in.
        for ch in range(4):
            self.to_ddj(bytes((0x90 | ch, 0x21, 0x20)))
            time.sleep(0.002)
        for address in sorted(self.panel):
            self.to_mixxx(bytes(address) + bytes([self.panel[address]]))
            time.sleep(0.001)
        if self.panel:
            syslog.syslog("replayed %d control positions to Mixxx" % len(self.panel))

    def _display_bringup_fallback(self):
        for payload in JOGSCREEN_ENABLE:
            self.sysex(payload)
        for msg in BROWSER_STARTUP:
            self.to_ddj(msg)
        for ch in range(4):
            for note in DECK_STARTUP_NOTES:
                self.to_ddj(bytes((0x90 | ch, note, 0x00)))
        for payload in JOGSCREEN_ENABLE_6:
            self.sysex(payload)
        for ch in range(4):
            self.to_ddj(bytes((0x90 | ch, 0x5B, 0x01)))   # ring light
            self.to_ddj(bytes((0x90 | ch, 0x5D, 0x00)))   # screen on (0x7F = off)

    def handle_unit_message(self, msg):
        """Return True if this was handshake traffic and must not be forwarded."""
        if not msg.startswith(HDR) or len(msg) < 11:
            return False
        cmd, sub = msg[9], msg[10]
        if cmd == 0x11 and sub == 0x02:
            self.sysex(identity_msg())
            return True
        if cmd == 0x13:
            seed_spread = find_arg(msg, 0x03)
            if seed_spread and len(seed_spread) >= 8:
                seed_e = pack_nibbles(seed_spread[:8])
                self.sysex(capabilities_msg(spread_bytes(auth_response(seed_e))))
            return True
        if cmd == 0x15 and sub == 0x02:
            if not self.authenticated:
                syslog.syslog("authenticated -- jog displays unlocked")
                threading.Thread(target=self.prebuild_cache, daemon=True).start()
                # Tell Mixxx to reopen the sound device: the controller is the
                # sound card, so a replug leaves Mixxx holding a stream that no
                # longer exists, and it has no way of noticing on its own. The
                # mapping turns this note into [SoundManager],reopen_devices.
                # The note-off matters: the control only signals on a change,
                # so left at 7F it fires once in Mixxx's lifetime and every
                # later reconnect is ignored.
                self.to_mixxx(bytes((0x9F, 0x7F, 0x7F)))
                self.to_mixxx(bytes((0x9F, 0x7F, 0x00)))
                self.authenticated = True
            self.display_bringup()
            return True
        return False

    def run(self):
        # Nothing but the keepalive until the unit has answered. A capture of
        # rekordbox meeting a freshly powered unit opens with the 50 01 ping
        # alone, every 0.2 s, and the whole 0B/0A/0C block goes out only after
        # the unit's acceptance -- sending it cold, before the handshake, is a
        # sequence rekordbox never produces. The keepalive loop below is the
        # ping; the block moved to display_bringup, behind the acceptance.
        last_ka = 0.0
        last_check = 0.0
        # None, not the current value: if the interface is already in alt 1 when
        # we start, the probe still has to go out once, because whoever selected
        # it (Mixxx, aplay, a reconnect) did not issue it.
        last_alt = None
        last_screens = 0.0
        self.started = time.monotonic()
        while True:
            now = time.monotonic()
            if now - last_ka >= KEEPALIVE_INTERVAL:
                self.sysex(KEEPALIVE)
                last_ka = now
            # Poll the controller with snd_rawmidi_read rather than select():
            # the poll descriptor of a duplex raw MIDI handle does not reliably
            # signal readable here, and a missed challenge means the jog
            # displays stay locked.
            # A unit that has already given up challenging stays silent and
            # locked, so the timeout runs from the start of the session rather
            # than from the first challenge.
            if now - self.last_state >= STATE_INTERVAL:
                self.last_state = now
                self.push_state()
            if SCREENS_REFRESH and now - last_screens > SCREENS_REFRESH                     and audio_alt_setting() == 1:
                self.screens_on()
                last_screens = now
            if now - last_check > RECONNECT_CHECK:
                last_check = now
                alt = audio_alt_setting()
                if alt is None:
                    # A failed read is not a change. Treating it as one made
                    # the release fire again on the next good read, and every
                    # one of those repaints the screens -- which under load,
                    # when sysfs is slow, showed up as the picture flashing.
                    alt = last_alt
                # Only while the screens still need releasing. The probe is a
                # vendor control read on the audio interface, and issuing it
                # against a stream someone has just opened stops that stream
                # dead: the device stays RUNNING with its hardware pointer at
                # zero, no samples move, and the DJ software's engine never
                # settles -- which shows up as every track sitting for ever at
                # "loading" rather than as anything to do with audio.
                if alt == 1 and last_alt != 1 and not self.authenticated:
                    if vendor_probe():
                        syslog.syslog("audio interface went to alt 1 -- jog displays released")
                        self.reset_time_mode()
                        # The screens only accept "display on" once they are
                        # released, and the mapping sends its own copy when Mixxx
                        # starts, which is usually too early.
                        self.screens_on()
                last_alt = alt
                if self.device_changed():
                    raise OSError(errno.ENODEV, "controller re-enumerated")
            if not self.authenticated and now - self.started > SESSION_TIMEOUT:
                raise SessionStale()
            chunk = self.read_ddj()
            if chunk:
                if DEBUG:
                    syslog.syslog("rx %d: %s" % (len(chunk), chunk[:32].hex()))
                for msg in self.from_ddj.feed(chunk):
                    if len(msg) == 3 and msg[0] & 0xF0 == 0xB0:
                        # Remember where every knob and fader is. The unit
                        # reports its whole panel once, just after it
                        # authenticates, and never again -- which is before
                        # Mixxx has opened its port, so Mixxx would otherwise
                        # never learn any of it.
                        self.panel[msg[:2]] = msg[2]
                        # The unit reports its whole panel in one burst; say so
                        # when it happens, since when it happens is the whole
                        # question -- Mixxx only picks the values up if its
                        # port is open at the time. Count distinct addresses,
                        # not messages: turning the jog wheel produces hundreds
                        # of messages from a single one.
                        if now - self.burst_at > 0.3:
                            self.burst_seen = set()
                        self.burst_at = now
                        self.burst_seen.add(msg[:2])
                    if not self.handle_unit_message(msg):
                        self.to_mixxx(msg)

            if len(self.burst_seen) >= 20 and now - self.burst_at > 0.3:
                syslog.syslog("panel state: %d control positions from the unit"
                              % len(self.burst_seen))
                self.burst_seen = set()

            if self.hid is not None:
                # Draining the reports keeps the poll running; their content is
                # controller state we do not need here. Read a bounded number of
                # them: the unit produces about a thousand a second, and an
                # unbounded loop here starves the MIDI side, which shows up as
                # the jog displays freezing a few seconds after they come up.
                try:
                    for _ in range(32):
                        if not os.read(self.hid, 64):
                            break
                except BlockingIOError:
                    pass
                except OSError:
                    self.hid = None

            ready, _, _ = select.select([self.vir], [], [], 0.002)
            if ready:
                try:
                    data = os.read(self.vir, 4096)
                except BlockingIOError:
                    data = b""
                for msg in self.from_vir.feed(data):
                    if msg[:1] == bytes([0xF0]):
                        if self.announce_track(msg):
                            continue           # ours, never goes to the controller
                        syslog.syslog("sysex from Mixxx: %s" % msg[:10].hex())
                    if len(msg) == 3 and msg[0] in (0x90, 0x91, 0x92, 0x93) \
                            and msg[1] == 0x21:
                        self.request_panel_state()
                        continue
                    self.to_ddj(msg)


BRIDGE = [None]


def main():
    syslog.openlog("djbox-ddj")
    faulthandler.enable()
    signal.signal(signal.SIGUSR1, lambda *a: BRIDGE[0] and BRIDGE[0].pause())
    sub = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    while True:
        card = card_by_name("DDJ")
        vir_path = virmidi_node(sub)
        if card is None or not vir_path:
            time.sleep(DEVICE_POLL)
            continue
        try:
            bridge = Bridge(card, vir_path)
            BRIDGE[0] = bridge
        except OSError as exc:
            if exc.errno == errno.EBUSY:
                syslog.syslog("raw MIDI busy -- another client holds the controller")
            time.sleep(2)
            continue
        syslog.syslog("bridging DDJ-1000 (card %d) <-> %s" % (card, vir_path))
        if HOLD_AUDIO:
            threading.Thread(target=bridge.hold_audio_open, daemon=True).start()
        try:
            bridge.run()
        except SessionStale:
            bridge.close()
            if audio_streaming():
                # Resetting now would drop the audio stream, which is what keeps
                # the jog displays alive in the first place. Leave it alone.
                syslog.syslog("not acknowledged, but audio is streaming -- leaving the device alone")
                time.sleep(30)
                continue
            syslog.syslog("challenged but never acknowledged -- resetting the controller")
            usb_reset()
            time.sleep(6)
            continue
        except OSError as exc:
            syslog.syslog("controller went away (%s); waiting for it to come back" % exc)
        finally:
            try:
                bridge.close()
            except Exception:
                pass
        time.sleep(2)


if __name__ == "__main__":
    main()
