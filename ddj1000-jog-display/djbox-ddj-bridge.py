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
import os
import sqlite3
import struct
import subprocess
import threading
import select
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
asound.snd_rawmidi_poll_descriptors_count.argtypes = [ctypes.c_void_p]
asound.snd_rawmidi_poll_descriptors_count.restype = ctypes.c_int
asound.snd_rawmidi_poll_descriptors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
asound.snd_rawmidi_poll_descriptors.restype = ctypes.c_int
DEBUG = bool(os.environ.get("DDJ_DEBUG"))


class pollfd_t(ctypes.Structure):
    _fields_ = [("fd", ctypes.c_int), ("events", ctypes.c_short), ("revents", ctypes.c_short)]


def rawmidi_poll_fd(handle):
    """File descriptor to select() on for a raw MIDI input handle."""
    count = asound.snd_rawmidi_poll_descriptors_count(handle)
    pfds = (pollfd_t * max(count, 1))()
    asound.snd_rawmidi_poll_descriptors(handle, pfds, count)
    return pfds[0].fd

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
SCREENS_REFRESH = 2.0       # how often to re-assert "screens on" on the unit
DEVICE_POLL = 0.02          # how often to look for the controller coming back

DEVICE_ID = bytes([0x08, 0x07, 0x0A, 0x00, 0x08, 0x0E, 0x0E, 0x0A, 0x0C, 0x00,
                   0x09, 0x00, 0x03, 0x04, 0x07, 0x06, 0x00, 0x0B, 0x09, 0x00])
SEED_A = bytes([0x06, 0x08, 0x07, 0x02, 0x0B, 0x0A, 0x03, 0x02,
                0x0D, 0x04, 0x00, 0x07, 0x0C, 0x00, 0x0E, 0x01])

# Sent once before the handshake: the unit expects the display state to be
# initialised before it will accept an authentication response.
PRELUDE = [
    bytes.fromhex("000b2b68000000"),
    bytes.fromhex("000a00280026000a394a742853202014152205" + "00" * 21),
    bytes.fromhex("000b2b68000000"),
    bytes.fromhex("000c0000020e0e000000"),
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
CMD_ARTWORK = 0x2B
CMD_WAVEFORM = 0x2C


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


def u24(value):
    """The screen's millisecond figures: 24 bits, little end first."""
    value = max(0, min(0xFFFFFF, int(value)))
    return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF


class DeckScreen:
    def __init__(self):
        self.loaded = False
        self.minutes = 0
        self.seconds = 0
        self.bpm = 0
        self.bpm_msb = 0
        self.track_id = 0
        self.first_beat_ms = 0
        self.key_code = 0
        self.loop_in = -1
        self.loop_out = -1
        self.last_seen = 0.0
        self.base_ms = -1
        self.base_time = 0.0
        self.exact = False
        self.rate = 0.0
        self.report_ms = 0
        self.report_time = 0.0

    def resync(self):
        """Re-anchor the playhead from the whole-second display notes.

        Only used until the first millisecond report arrives: those notes
        repeat the same second many times over, and re-anchoring on every
        repeat drags the position back to the whole second each time, which
        shows up as a needle that shivers instead of turning.
        """
        if self.exact:
            return
        whole = (self.minutes * 60 + self.seconds) * 1000
        if whole == self.base_ms:
            return
        self.base_ms = whole
        self.base_time = time.monotonic()

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
        if not self.exact or dt <= 0.0 or dt > 0.5:
            self.exact = True
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
        if not self.exact:
            elapsed = min(time.monotonic() - self.base_time, 1.5)
            return max(0, int(self.base_ms + elapsed * 1000))
        elapsed = min(time.monotonic() - self.base_time, 0.5)
        return max(0, int(self.base_ms + elapsed * 1000.0 * self.rate))

    def record(self, deck):
        b = bytearray(64)
        b[0] = deck
        b[1] = 0x21
        b[2] = 0x18
        b[3] = 0x0A
        b[4] = 0x11
        b[5] = 0x81
        looping = self.loaded and self.loop_out > self.loop_in >= 0
        b[9] = (0xBC if looping else 0xB4) if self.loaded else 0x10
        b[10] = 0x01 if looping else 0x00
        # The playhead is minutes and seconds, not a 16-bit second count: the
        # second byte never goes past 59 in a capture, and feeding it 60 is
        # what made the screen call the track over a minute in.
        seconds, ms = divmod(self.position_ms(), 1000)
        b[11] = min(255, seconds // 60)
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
            marker = self.first_beat_ms
        b[31], b[32], b[33] = u24(marker)
        b[55], b[56], b[57] = u24(marker)
        b[58] = 0x01 if self.loaded else 0x00
        b[60] = self.key_code                  # musical key, constant per track
        b[61] = 0x0D
        return bytes(b)

# The cue table the unit gets when a track has no cue points: a count of ten
# and ten copies of the empty-slot marker, exactly as rekordbox sends it.
CUE_TABLE = struct.pack("<H", 10) + bytes.fromhex("9e2f270100") * 10 + bytes(2)


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
    count = min(int((duration_s * 1000 - first_beat_ms) / interval), 2000)
    if count < 1:
        return bytes(58)
    body = bytearray(struct.pack("<H", count))
    for i in range(count):
        ms = int(first_beat_ms + i * interval)
        body += bytes([i % 4 + 1, ms & 0xFF, (ms >> 8) & 0xFF, (ms >> 16) & 0xFF])
    return bytes(body)


POST_AUTH_FILE = "/usr/local/share/ddj1000-post-auth-midi.txt"


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
        self.ddj_fd = rawmidi_poll_fd(self.inp)
        self.rbuf = ctypes.create_string_buffer(1024)
        self.vir = os.open(vir_path, os.O_RDWR | os.O_NONBLOCK)
        self.from_ddj = MidiSplitter()
        self.probe_at = 0.0
        self.probe_seen = 0
        self.burst_at = 0.0
        self.burst_seen = set()
        self.panel = {}
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

    def announce_track(self, msg):
        """Handle the mapping's private track announcement (F0 7D deck ms F7)."""
        if len(msg) < 8 or msg[1] != 0x7D:
            return False
        deck_index = msg[2] & 0x0F
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
        if msg[2] & 0x20:                      # where the grid starts, and the key
            screen = self.screens[deck_index]
            screen.first_beat_ms = (msg[3] << 7) | msg[4]
            screen.key_code = msg[5]
            return True
        if msg[2] & 0x10:                      # a playhead report, not a load
            screen = self.screens[deck_index]
            screen.set_position(ms)
            screen.last_seen = time.monotonic()
            return True
        if ms <= 0:
            self.drawn[deck_index] = None
            self.screens[deck_index].track_id = 0
            return True
        # A stable non-zero id per track: the unit files artwork and waveform
        # under it, and with a zero id it throws them away again after a moment.
        self.screens[deck_index].track_id = ms & 0x7FFFFFFF
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

    def load_artwork(self, deck_index, seconds):
        path = track_by_duration(seconds)
        if not path or not os.path.exists(path):
            syslog.syslog("no library match for a %.3f s track" % seconds)
            return
        art = "/run/djbox-ddj-art-%d.bin" % deck_index
        wave = "/run/djbox-ddj-wave-%d.bin" % deck_index
        try:
            subprocess.run([TRACKART, path, art, wave], timeout=240,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            syslog.syslog("could not build the jog artwork: %s" % exc)
            return
        deck = SCREEN_DECKS[deck_index]
        key = struct.pack("<I", self.screens[deck_index].track_id)

        payloads = {}
        for name, cmd in ((art, CMD_ARTWORK), (wave, CMD_WAVEFORM)):
            try:
                with open(name, "rb") as fh:
                    payloads[cmd] = fh.read()
            except OSError:
                pass

        # rekordbox's load, in the order a capture of it shows. The unloading
        # step matters as much as the upload: it clears the deck with an
        # all-zero 0x30, lets a few state records go out with no track at all,
        # and only then announces the new id. Uploading against a deck that
        # still holds the previous track is what made the screen show the
        # artwork for a moment and throw it away again.
        screen = self.screens[deck_index]
        self.send_hid_transfer(deck, 0x30, bytes(116))

        held_bpm, held_loaded = screen.bpm, screen.loaded
        screen.track_id = 0
        screen.bpm = 0
        screen.loaded = False                  # one frame of "no track"
        time.sleep(0.02)
        screen.loaded = held_loaded
        screen.track_id = struct.unpack("<I", key)[0]
        screen.bpm = held_bpm
        time.sleep(0.01)

        grid = beat_grid(held_bpm, screen.first_beat_ms, seconds)
        syslog.syslog("jog screen %d: id %08x, %.1f s, %.1f BPM, %d beats, art %d, wave %d"
                      % (deck_index + 1, screen.track_id, seconds, held_bpm,
                         int.from_bytes(grid[:2], "little"),
                         len(payloads.get(CMD_ARTWORK, b"")),
                         len(payloads.get(CMD_WAVEFORM, b""))))
        self.send_hid_transfer(deck, 0x2F, grid)
        self.send_hid_transfer(deck, 0x30, key + bytes(112))
        self.send_hid_transfer(deck, 0x2D, key + CUE_TABLE)
        if CMD_ARTWORK in payloads:
            self.send_hid_transfer(deck, CMD_ARTWORK, payloads[CMD_ARTWORK])
        time.sleep(0.42)                       # rekordbox's pause before the waveform
        if CMD_WAVEFORM in payloads:
            self.send_hid_transfer(deck, CMD_WAVEFORM, payloads[CMD_WAVEFORM])
        syslog.syslog("jog screen %d: drew %s" % (deck_index + 1, os.path.basename(path)))

    def send_hid_transfer(self, deck, cmd, payload):
        """Upload one chunked transfer to the screen, one report per ms."""
        chunks = [payload[i:i + 58] for i in range(0, len(payload), 58)] or [b""]
        total = len(chunks)

        def report(index, data):
            self.to_ddj_hid(struct.pack("<BBHH", deck, cmd, index, total) + data)
            time.sleep(0.0012)

        # The short records get a lone copy of their last chunk first; artwork
        # and the waveform do not. Priming those two makes the unit see the
        # final index before the first one and drop the whole transfer.
        if cmd in (0x2D, 0x2F, 0x30):
            report(total, chunks[-1])
        for i, data in enumerate(chunks, start=1):
            report(i, data)

    def watch_display_midi(self, msg):
        """Learn the deck state from the display messages Mixxx sends."""
        if len(msg) != 3:
            return
        status, d1, d2 = msg
        channel = status & 0x0F
        if channel > 3:
            return
        screen = self.screens[channel]
        kind = status & 0xF0
        if kind == 0x90:                       # notes carry the time readout
            if d1 == 0x42:
                screen.minutes = d2
                screen.loaded = True
                screen.last_seen = time.monotonic()
                screen.resync()
            elif d1 == 0x43:
                screen.seconds = d2
                screen.loaded = True
                screen.last_seen = time.monotonic()
                screen.resync()
        elif kind == 0xB0:                     # BPM arrives as a 14-bit CC
            if d1 == 0x15:
                screen.bpm_msb = d2
            elif d1 == 0x35:
                screen.bpm = ((screen.bpm_msb << 7) | d2) / 10.0

    def push_state(self):
        now = time.monotonic()
        for i, deck in enumerate(SCREEN_DECKS):
            screen = self.screens[i]
            if screen.loaded and now - screen.last_seen > 5.0:
                screen.loaded = False          # the mapping went quiet: deck empty
            self.to_ddj_hid(screen.record(deck))

    def to_ddj_hid(self, report):
        if self.hid is None:
            return
        try:
            os.write(self.hid, bytes([0x00]) + bytes(report).ljust(64, bytes([0x00])))
        except OSError:
            pass

    def screens_on(self):
        """Wake the jog screens: ring light, display on, remaining-time dash.

        Note 0x5D is inverted -- 0x00 turns the screen on, 0x7F turns it off.
        """
        for ch in range(4):
            self.to_ddj(bytes((0x90 | ch, 0x5B, 0x01)))
            self.to_ddj(bytes((0x90 | ch, 0x5D, 0x00)))
            self.to_ddj(bytes((0x90 | ch, 0x44, 0x7F)))

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
                self.authenticated = True
            self.display_bringup()
            return True
        return False

    def run(self):
        for payload in PRELUDE:
            self.sysex(payload)
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
            if now - last_screens > SCREENS_REFRESH and audio_alt_setting() == 1:
                # The unit drops back to its idle logo unless the screens are
                # re-asserted; the community mappings re-send this with every
                # display update for the same reason.
                self.screens_on()
                last_screens = now
            if now - last_check > RECONNECT_CHECK:
                last_check = now
                alt = audio_alt_setting()
                if alt == 1 and last_alt != 1:
                    if vendor_probe():
                        syslog.syslog("audio interface went to alt 1 -- jog displays released")
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
                    if len(msg) == 3 and msg[0] == 0x96 and msg[2] == 0x7F:
                        syslog.syslog("browser button: %s" % msg.hex())
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
                    self.watch_display_midi(msg)
                    self.to_ddj(msg)


def main():
    syslog.openlog("djbox-ddj")
    faulthandler.enable()
    sub = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    while True:
        card = card_by_name("DDJ")
        vir_path = virmidi_node(sub)
        if card is None or not vir_path:
            time.sleep(DEVICE_POLL)
            continue
        try:
            bridge = Bridge(card, vir_path)
        except OSError as exc:
            if exc.errno == errno.EBUSY:
                syslog.syslog("raw MIDI busy -- another client holds the controller")
            time.sleep(2)
            continue
        syslog.syslog("bridging DDJ-1000 (card %d) <-> %s" % (card, vir_path))
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
