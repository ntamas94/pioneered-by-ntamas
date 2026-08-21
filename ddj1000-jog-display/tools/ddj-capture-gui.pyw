"""A window for capturing what rekordbox sends the DDJ-1000, and reading it.

The capture itself is USBPcap, which is fine at its job and awkward around it:
its interfaces are renumbered whenever the root hubs are restarted, it forgets
a device across a power cycle, it needs administrator rights to open even to
be asked what it can see, and it fails by writing an empty file rather than by
saying anything. All of that is handled here so a capture is three clicks
rather than an evening.

The analysis knows the one thing the raw traffic will not tell you: which byte
of the jog display's state record changed while you moved something. Every
field that never moves is filtered out, so what is left is what you touched.
"""
import collections
import ctypes
import os
import re
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

USBPCAP = r"C:\Program Files\USBPcap\USBPcapCMD.exe"
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
DECKS = {"deck 1": 0x10, "deck 2": 0x20, "deck 3": 0x30, "deck 4": 0x40}

# The clock and the playhead move on their own and drown everything else out.
ALWAYS_MOVING = {11, 12, 13, 14, 31, 32, 33, 55, 56, 57}


def run(args, timeout=30):
    """A command's output, without a console window flashing up."""
    try:
        done = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, creationflags=NO_WINDOW)
        return (done.stdout or "") + (done.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return "error: %s" % exc


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate():
    """Ask for administrator rights and hand over, or carry on without.

    USBPcap will not even answer what devices it can see unelevated, so the
    unelevated window is only good for reading a capture someone else made.
    """
    if is_admin():
        return True
    params = " ".join('"%s"' % arg for arg in sys.argv)
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1)
    except Exception:
        return False
    if result > 32:
        sys.exit(0)
    return False


def find_controller():
    """(interface, device number, note) for the DDJ-1000.

    Every interface is asked, not just the first: restarting the root hubs
    renumbers them, so the one that worked an hour ago may not exist now.
    """
    listing = run([USBPCAP, "--extcap-interfaces"])
    interfaces = re.findall(r"\{value=(\\\\\.\\USBPcap\d+)\}", listing)
    if not interfaces:
        return None, None, "USBPcap lists no interfaces at all"
    refused = 0
    for interface in interfaces:
        config = run([USBPCAP, "--extcap-interface", interface, "--extcap-config"])
        if "Couldn't open device" in config:
            refused += 1
            continue
        for line in config.splitlines():
            if "PIONEER DJ DDJ-1000" in line:
                parent = re.search(r"parent=(\d+)", line)
                if parent:
                    return interface, parent.group(1), ""
    if refused == len(interfaces):
        return None, None, "USBPcap refused every interface (administrator?)"
    return None, None, "the filter is attached but the controller is not on it"


def device_present():
    """Whether Windows itself can see the controller, filter or no filter."""
    out = run(["powershell", "-NoProfile", "-Command",
               "Get-PnpDevice -ErrorAction SilentlyContinue | "
               "Where-Object { $_.InstanceId -like '*VID_2B73*' -and "
               "$_.Status -eq 'OK' } | Select-Object -First 1 "
               "-ExpandProperty FriendlyName"])
    return "DDJ-1000" in out


# --- reading a capture ------------------------------------------------------

def read_packets(path):
    """USB packets from a pcap, as (seconds, endpoint, payload)."""
    with open(path, "rb") as fh:
        header = fh.read(24)
        if len(header) < 24:
            return
        magic, = struct.unpack("<I", header[:4])
        if magic not in (0xA1B2C3D4, 0xA1B23C4D):
            return
        nano = magic == 0xA1B23C4D
        while True:
            record = fh.read(16)
            if len(record) < 16:
                return
            sec, frac, caplen, _ = struct.unpack("<IIII", record)
            body = fh.read(caplen)
            if len(body) < caplen:
                return
            if caplen < 27:
                continue
            # The USBPcap header is longer for control and isochronous
            # transfers, so the payload starts where the header says.
            header_length = body[0] | (body[1] << 8)
            stamp = sec + frac / (1e9 if nano else 1e6)
            endpoint = body[21]
            length, = struct.unpack("<I", body[23:27])
            payload = body[header_length:header_length + length] if length else b""
            yield stamp, endpoint, payload


def state_records(path, deck=0x10):
    """The jog display's state records for one deck."""
    for stamp, endpoint, payload in read_packets(path):
        if endpoint == 0x06 and len(payload) >= 64 \
                and payload[0] == deck and payload[1] == 0x21:
            yield stamp, bytes(payload)


def survey(path, deck=0x10, loaded_only=True):
    """What moved in the state record, and how far.

    Returns the record count, the per-byte values seen, and for every run of
    neighbouring changed bytes the range they cover read as a little-endian
    number -- which is the shape a tempo percentage would have.
    """
    seen = {}
    previous = None
    count = 0
    records = []
    for _stamp, record in state_records(path, deck):
        if loaded_only and record[9] in (0x00, 0x10):
            continue
        count += 1
        records.append(record)
        if previous is not None:
            for index in range(64):
                if index in ALWAYS_MOVING or record[index] == previous[index]:
                    continue
                seen.setdefault(index, set()).add(record[index])
        previous = record

    pairs = []
    for index in sorted(seen):
        if index + 1 > 62:
            continue
        values = set()
        for record in records:
            values.add(record[index] | (record[index + 1] << 8))
        if len(values) > 2:
            low, high = min(values), max(values)
            signed = [v - 0x10000 if v > 0x7FFF else v for v in values]
            pairs.append((index, low, high, min(signed), max(signed), len(values)))
    return count, seen, pairs


def timeline(path):
    """What happened, for a capture with no track in it.

    A recording of the unit being switched on has nothing loaded and nothing
    to compare, so the byte survey has nothing to say about it. What is worth
    reading there is the order of events: when the device answered, what the
    host sent it, and how long each step took.
    """
    start = None
    when = 0.0
    lines = []
    hid = collections.Counter()
    first_hid = {}
    midi = []
    pending = {"host": bytearray(), "unit": bytearray()}
    control = 0
    state = []
    for stamp, endpoint, payload in read_packets(path):
        if start is None:
            start = stamp
        when = stamp - start
        if endpoint == 0x00:
            control += 1
        elif endpoint == 0x06 and len(payload) >= 2:
            command = (payload[0], payload[1])
            hid[command] += 1
            first_hid.setdefault(command, when)
            if payload[1] == 0x21:
                state.append((when, payload[9] if len(payload) > 9 else 0))
        elif endpoint in (0x04, 0x85) and payload:
            who = "host" if endpoint == 0x04 else "unit"
            for i in range(0, len(payload) - 3, 4):
                packet = payload[i:i + 4]
                code = packet[0] & 0x0F
                if not packet[0]:
                    continue
                # SysEx is carried a few bytes at a time: 4 means more is
                # coming, 5 to 7 end it with that many bytes in the packet.
                # Printing the fragments instead of the message is how the
                # authentication challenge reads as gibberish.
                if code == 4:
                    pending[who] += packet[1:4]
                elif code in (5, 6, 7):
                    pending[who] += packet[1:code - 3]
                    midi.append((when, who, bytes(pending[who])))
                    pending[who] = bytearray()
                else:
                    midi.append((when, who, bytes(packet[1:4])))
    lines.append("%.1f s of traffic, %d control transfers (enumeration)"
                 % (when, control))
    if hid:
        lines.append("screen commands, first seen at:")
        for command, count in sorted(hid.items(), key=lambda kv: first_hid[kv[0]]):
            lines.append("  deck %d  %02x   %6.2f s   x%d"
                         % (command[0] >> 4, command[1], first_hid[command], count))
    if state:
        loaded = [w for w, nine in state if nine not in (0x00, 0x10)]
        lines.append("state records: %d, first at %.2f s, %d with a track"
                     % (len(state), state[0][0], len(loaded)))
    if midi:
        lines.append("MIDI, first %d of %d:" % (min(20, len(midi)), len(midi)))
        for when, who, data in midi[:20]:
            lines.append("  %6.2f s  %-4s %s" % (when, who, data.hex()))
    return lines


# --- the window -------------------------------------------------------------

class Window(tk.Tk):
    def __init__(self, elevated):
        super().__init__()
        self.title("DDJ-1000 capture")
        self.geometry("780x600")
        self.minsize(660, 480)
        self.elevated = elevated
        self.capture = None
        self.capture_path = None
        self.started = None
        self.interface = None
        self.device = None
        self.watch = 0
        self.watching = False
        self.capturing = False
        self.parts = []
        self.missing_said = False

        pad = {"padx": 10, "pady": 6}
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        self.status = ttk.Label(top, text="looking for the controller\u2026",
                                font=("Segoe UI", 10, "bold"))
        self.status.pack(side="left")
        ttk.Button(top, text="Rescan", command=self.rescan).pack(side="right")
        self.repair = ttk.Button(top, text="Repair filter", command=self.repair_filter)
        self.repair.pack(side="right", padx=(0, 6))

        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Save as").pack(side="left")
        self.name = ttk.Entry(row)
        self.name.insert(0, "ddj-tempo")
        self.name.pack(side="left", fill="x", expand=True, padx=8)
        self.deck = ttk.Combobox(row, values=list(DECKS), width=8, state="readonly")
        self.deck.current(0)
        self.deck.pack(side="left")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", **pad)
        self.start = ttk.Button(buttons, text="Start capture",
                                command=self.start_capture, state="disabled")
        self.start.pack(side="left")
        self.stop = ttk.Button(buttons, text="Stop", command=self.stop_capture,
                               state="disabled")
        self.stop.pack(side="left", padx=6)
        ttk.Button(buttons, text="Analyse a file\u2026",
                   command=self.analyse_file).pack(side="right")

        self.size = ttk.Label(self, text="")
        self.size.pack(anchor="w", padx=10)

        self.log = tk.Text(self, height=22, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        if not elevated:
            self.say("Running without administrator rights: capture is not")
            self.say("possible, only reading a file that already exists.")
            self.say("")
        self.rescan()
        self.tick()

    # --- talking back (always on the UI thread) ---------------------------

    def say(self, text):
        def write():
            self.log.insert("end", text + "\n")
            self.log.see("end")
        self.after(0, write)

    def set_status(self, text, can_start):
        def apply():
            self.status.config(text=text)
            self.start.config(state="normal" if can_start else "disabled")
        self.after(0, apply)

    def enable_repair(self, on):
        self.after(0, lambda: self.repair.config(state="normal" if on else "disabled"))

    # --- controller -------------------------------------------------------

    def rescan(self):
        self.status.config(text="looking for the controller\u2026")
        threading.Thread(target=self._rescan, daemon=True).start()

    def _rescan(self):
        interface, device, note = find_controller()
        self.interface, self.device = interface, device
        if device:
            self.set_status("ready: %s device %s"
                            % (interface.split("\\")[-1], device), True)
            return
        self.set_status(note or "no controller found", False)
        if device_present():
            self.say("Windows has the controller, USBPcap does not (%s)." % note)
            self.say("Repair the filter -- it lets go of every USB device for a")
            self.say("moment while it works, so close anything that is playing.")

    def repair_filter(self):
        """Restart the root hubs, which reattaches the filter to them."""
        if not self.elevated:
            self.say("")
            self.say("Repairing the filter needs administrator rights.")
            return
        self.say("")
        self.say("restarting the USB root hubs\u2026")
        self.enable_repair(False)
        threading.Thread(target=self._repair, daemon=True).start()

    def _repair(self):
        run(["powershell", "-NoProfile", "-Command",
             "Get-PnpDevice -Class USB | "
             "Where-Object { $_.InstanceId -match 'ROOT_HUB' } | "
             "ForEach-Object { pnputil /restart-device $_.InstanceId | Out-Null }"],
            timeout=180)
        time.sleep(6)
        self.say("done; rescanning")
        self.enable_repair(True)
        self._rescan()

    # --- capture ----------------------------------------------------------

    def start_capture(self):
        # Ask again rather than trusting what the last scan found: unplugging
        # the controller and plugging it back in gives it a new device number
        # on the filter, and starting a capture against the old one records a
        # perfectly valid file full of somebody else's traffic.
        interface, device, note = find_controller()
        if device:
            self.interface, self.device = interface, device
        if not self.device:
            self.say(note or "the controller is not there")
            return
        name = self.name.get().strip() or "ddj-capture"
        if not name.endswith(".pcap"):
            name += ".pcap"
        self.capture_path = os.path.join(DOWNLOADS, name)
        try:
            if os.path.exists(self.capture_path):
                os.remove(self.capture_path)
        except OSError as exc:
            self.say("cannot replace %s: %s" % (self.capture_path, exc))
            return
        self.parts = []
        self.capturing = True
        self.started = time.time()
        self.missing_said = False
        if not self._start_part():
            self.capturing = False
            return
        self.start.config(state="disabled")
        self.stop.config(state="normal")
        self.say("")
        self.say("capturing to %s" % self.capture_path)
        self.say("do the one thing you want to see, and nothing else.")

    def _start_part(self):
        """Begin recording the current device into a fresh piece of the file.

        USBPcap truncates whatever it is pointed at, so following the
        controller across a replug means a new file each time; the pieces are
        stitched back into one capture when recording stops.
        """
        part = "%s.part%d" % (self.capture_path, len(self.parts))
        try:
            self.capture = subprocess.Popen(
                [USBPCAP, "-d", self.interface, "--devices", self.device,
                 "--inject-descriptors", "-o", part],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        except OSError as exc:
            self.say("could not start USBPcap: %s" % exc)
            return False
        self.parts.append(part)
        return True

    def _follow(self):
        """Pick the controller up again after it moved, mid-capture."""
        interface, device, _note = find_controller()
        if not device:
            if not self.missing_said:
                self.missing_said = True
                self.say("controller gone -- still recording, waiting for it")
            return
        self.missing_said = False
        moved = (device != self.device or interface != self.interface)
        self.interface, self.device = interface, device
        if self.capture and self.capture.poll() is None:
            if not moved:
                return
            self.capture.terminate()
            try:
                self.capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.capture.kill()
        if self._start_part():
            self.say("switched to %s device %s, piece %d"
                     % (interface.split("\\")[-1], device, len(self.parts)))

    def _stitch(self):
        """One pcap out of the pieces: the first whole, the rest headerless."""
        parts = [p for p in self.parts if os.path.exists(p)]
        if not parts:
            return
        try:
            with open(self.capture_path, "wb") as out:
                for index, part in enumerate(parts):
                    with open(part, "rb") as fh:
                        if index:
                            fh.read(24)      # every piece carries its own header
                        while True:
                            block = fh.read(1 << 20)
                            if not block:
                                break
                            out.write(block)
        except OSError as exc:
            self.say("could not put the pieces together: %s" % exc)
            return
        for part in parts:
            try:
                os.remove(part)
            except OSError:
                pass
        if len(parts) > 1:
            self.say("%d pieces stitched into one capture" % len(parts))

    def stop_capture(self):
        self.capturing = False
        if self.capture and self.capture.poll() is None:
            self.capture.terminate()
            try:
                self.capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.capture.kill()
        self.capture = None
        self.stop.config(state="disabled")
        self.start.config(state="normal" if self.device else "disabled")
        path = self.capture_path
        self.after(1200, self._finish)

    def _finish(self):
        self._stitch()
        self.analyse(self.capture_path)

    def tick(self):
        if self.capturing:
            size = sum(os.path.getsize(p) for p in self.parts
                       if os.path.exists(p))
            self.size.config(text="%.1f MB captured, %d s%s"
                                  % (size / 1e6, time.time() - self.started,
                                     "" if len(self.parts) < 2
                                     else ", %d pieces" % len(self.parts)))
            # A replug kills the recording process and hands the controller a
            # new device number. Follow it rather than calling the capture
            # over: watching the unit come back up is usually the whole point.
            self.watch += 1
            if self.watch >= 4 and not self.watching:
                self.watch = 0
                threading.Thread(target=self._following, daemon=True).start()
        elif self.elevated:
            # Watch for the controller coming and going on its own, so a
            # replug does not need anyone to press Rescan and notice that the
            # device number moved.
            self.watch += 1
            if self.watch >= 6:
                self.watch = 0
                threading.Thread(target=self._watch, daemon=True).start()
        self.after(500, self.tick)

    def _following(self):
        if self.watching:
            return
        self.watching = True
        try:
            if not self.capturing:
                return
            dead = self.capture is None or self.capture.poll() is not None
            interface, device, _note = find_controller()
            if not dead and device == self.device and interface == self.interface:
                return
            self.after(0, self._follow)
        finally:
            self.watching = False

    def _watch(self):
        """A quiet rescan: only speaks when the answer changes."""
        if self.watching:
            return
        self.watching = True
        try:
            interface, device, note = find_controller()
        finally:
            self.watching = False
        if device == self.device and interface == self.interface:
            return
        self.interface, self.device = interface, device
        if device:
            self.set_status("ready: %s device %s"
                            % (interface.split("\\")[-1], device), True)
            self.say("")
            self.say("controller is back: %s device %s"
                     % (interface.split("\\")[-1], device))
        else:
            self.set_status(note or "no controller found", False)
            self.say("")
            self.say("controller went away (%s)" % (note or "gone"))

    # --- analysis ---------------------------------------------------------

    def analyse_file(self):
        path = filedialog.askopenfilename(
            initialdir=DOWNLOADS, filetypes=[("captures", "*.pcap"), ("all", "*.*")])
        if path:
            self.analyse(path)

    def analyse(self, path):
        if not path or not os.path.exists(path):
            self.say("no capture to read")
            return
        deck = DECKS[self.deck.get()]
        threading.Thread(target=self._analyse, args=(path, deck),
                         daemon=True).start()

    def _analyse(self, path, deck):
        size = os.path.getsize(path)
        self.say("")
        self.say("--- %s, %.1f MB, %s ---"
                 % (os.path.basename(path), size / 1e6, self.deck.get()))
        if size <= 24:
            self.say("empty. the filter was attached but caught nothing:")
            self.say("repair it and capture again.")
            return
        try:
            count, changed, pairs = survey(path, deck)
        except Exception as exc:
            self.say("could not read it: %s" % exc)
            return
        self.say("%d state records with a track loaded" % count)
        if not count:
            # Say where the track actually was before falling back: picking
            # the wrong deck looks exactly like a capture with nothing in it.
            elsewhere = []
            for label, code in DECKS.items():
                if code == deck:
                    continue
                other = sum(1 for _s, r in state_records(path, code)
                            if r[9] not in (0x00, 0x10))
                if other:
                    elsewhere.append("%s has %d" % (label, other))
            if elsewhere:
                self.say("but " + ", ".join(elsewhere)
                         + " -- change the deck and analyse again")
                return
            # Nothing loaded anywhere is what a recording of the unit being
            # switched on looks like, and there the order is the whole point.
            self.say("nothing loaded on any deck -- reading it as a sequence:")
            self.say("")
            for line in timeline(path):
                self.say(line)
            return
        if not changed:
            self.say("nothing moved but the clock and the playhead.")
            return
        self.say("bytes that moved:")
        for index in sorted(changed):
            values = sorted(changed[index])
            shown = " ".join("%02x" % v for v in values[:12])
            if len(values) > 12:
                shown += " \u2026 (%d values)" % len(values)
            self.say("  b%-3d %s" % (index, shown))
        if pairs:
            self.say("read as 16-bit little endian, in case one is the tempo:")
            for index, low, high, slow, shigh, n in pairs:
                self.say("  b%d-%d  %d..%d   signed %d..%d   (%d values)"
                         % (index, index + 1, low, high, slow, shigh, n))


if __name__ == "__main__":
    if not os.path.exists(USBPCAP):
        ctypes.windll.user32.MessageBoxW(
            None, "USBPcap is not installed at\n" + USBPCAP, "DDJ-1000 capture", 0)
        sys.exit(1)
    Window(elevate()).mainloop()
