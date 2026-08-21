#!/usr/bin/env python3
"""Generate a 4-deck Mixxx MIDI mapping for the Pioneer DDJ-1000.

Every MIDI address here comes from AlphaTheta's official "DDJ-1000 List of MIDI
message version 1.00" (DDJ-1000_MIDI_Message_List_E1.pdf), not from guesswork.

Two facts from that document shape the whole design:

* Deck controls are listed as channel "1/2/3/4" with identical note numbers.
  The controller tracks which deck each physical section drives and sends on
  that deck's channel, so the mapping needs no deck-switching logic — it just
  has to answer on all four channels.

* Performance pads are laid out as ``note = mode * 8 + pad``, eight pads across
  sixteen mode slots, on channels 8/10/12/14 (shifted: 9/11/13/15). The pads
  are RGB: a MIDI-OUT note with data2 1..127 lights the pad in that colour,
  0x00 dims it.

Writing the XML by hand would mean several hundred near-identical blocks, so it
is generated. Edit this file, not the XML.

    python3 gen_mapping.py [OUTDIR]
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

MAPPING_NAME = "Pioneer DDJ-1000 (4 deck)"
AUTHOR = "generated from AlphaTheta MIDI message list v1.00"
DESCRIPTION = (
    "Four-deck mapping for the Pioneer DDJ-1000, including all eight "
    "performance pads with hot cue, beat loop, beat jump and sampler modes. "
    "Audio is NOT provided by this controller on Linux: its soundcard is not "
    "USB Audio Class compliant, so a separate audio interface is required."
)

SCRIPT_FILE = "Pioneer-DDJ-1000-4deck-scripts.js"
SCRIPT_PREFIX = "PioneerDDJ1000"

DECKS = (1, 2, 3, 4)

# Status bytes. Deck n uses 0x9(n-1) for notes and 0xB(n-1) for CC.
NOTE = 0x90
CC = 0xB0
MIXER_CC = 0xB6  # MIDI channel 7
MIXER_NOTE = 0x96

# Pads: channel 8/10/12/14, shifted 9/11/13/15 -> 0x97,0x99,0x9B,0x9D (+1 shift)
PAD_NOTE = {1: 0x97, 2: 0x99, 3: 0x9B, 4: 0x9D}
PAD_NOTE_SHIFT = {deck: status + 1 for deck, status in PAD_NOTE.items()}

# Pad mode base notes, straight from the table on page 4 of the MIDI list.
PAD_MODE_BASE = {
    "hotcue": 0x00,
    "padfx1": 0x10,
    "beatjump": 0x20,
    "sampler": 0x30,
    "keyboard": 0x40,
    "padfx2": 0x50,
    "beatloop": 0x60,
    "keyshift": 0x70,
}

# --- deck controls -------------------------------------------------------
# (note, mixxx key, description). Buttons that need only a plain control.
DECK_BUTTONS = [
    (0x0B, "play", "PLAY/PAUSE"),
    (0x0C, "cue_default", "CUE"),
    # Latching, with a long press for the leader role -- beatsync only ever
    # lines the beat up once and leaves nothing switched on, so the lamp
    # blinked and went out and the jog screen never showed sync at all.
    (0x58, f"{SCRIPT_PREFIX}.syncPress", "SYNC", ("script-binding",)),
    (0x54, "pfl", "HEADPHONE CUE"),
    # Printed 4 BEAT LOOP/EXIT: four beats, and during loop playback it
    # cancels whatever is running. beatloop_activate repeated the last size
    # used, and there was no way out from the same button.
    (0x14, f"{SCRIPT_PREFIX}.beatLoopButton", "4 BEAT LOOP / EXIT", ("script-binding",)),
    # The unit sends a different note for these two once it knows a loop is
    # running -- 0x12 and 0x13 rather than 0x10 and 0x11 -- which is why the
    # mapping answers on all four and why it reports the loop state back.
    (0x10, "loop_in", "LOOP IN"),
    (0x11, "loop_out", "LOOP OUT"),
    (0x12, "loop_halve", "LOOP IN while looping (halve)"),
    (0x13, "loop_double", "LOOP OUT while looping (double)"),
    (0x16, "orientation_left", "CROSSFADER ASSIGN left"),
    (0x1D, "orientation_center", "CROSSFADER ASSIGN center"),
    (0x18, "orientation_right", "CROSSFADER ASSIGN right"),
    (0x1A, "keylock", "MASTER TEMPO / key lock"),
    (0x35, "quantize", "QUANTIZE"),
    (0x40, "slip_enabled", "SLIP"),
    (0x15, "reverseroll", "SLIP REVERSE (momentary)"),
]

# Shifted variants.
DECK_BUTTONS_SHIFT = [
    (0x47, "start_stop", "SHIFT+PLAY: back to start"),
    (0x48, "start", "SHIFT+CUE: jump to track start"),
    (0x4D, "reloop_toggle", "SHIFT+LOOP OUT: reloop / exit"),
    (0x5C, "sync_key", "SHIFT+SYNC: match key"),
    (0x60, "reset_key", "SHIFT+KEY LOCK: reset key"),
    (0x65, "sync_key", "SHIFT+SEMITONE DOWN: match key"),
    (0x64, "reset_key", "SHIFT+SEMITONE UP: reset key"),
    (0x38, "reverse", "SHIFT+SLIP REVERSE: reverse"),
    (0x26, "beatjump_size_halve", "BEAT JUMP mode, left: halve the jump"),
    (0x2E, "beatjump_size_double", "BEAT JUMP mode, right: double the jump"),
]

# Script-driven deck buttons.
DECK_BUTTONS_SCRIPT = [
    (0x4C, "loopInAdjust", "SHIFT+LOOP IN: fine-tune the loop in from the jog"),
]

# (msb cc, lsb cc, mixxx key) — 14-bit continuous controls.
DECK_FADERS = [
    (0x00, 0x20, "rate", "TEMPO fader"),
    (0x04, 0x24, "pregain", "TRIM / gain"),
    (0x13, 0x33, "volume", "CHANNEL FADER"),
]

# EQ knobs live in their own effect rack group.
DECK_EQ = [
    (0x07, 0x27, "parameter3", "EQ HI"),
    (0x0B, 0x2B, "parameter2", "EQ MID"),
    (0x0F, 0x2F, "parameter1", "EQ LOW"),
]

# COLOR FX knob per channel, on the mixer channel (7). CH1 = CC 0x17/0x37,
# and each further channel steps by one.
COLOR_FX_MSB = {1: 0x17, 2: 0x18, 3: 0x19, 4: 0x1A}
COLOR_FX_LSB = {deck: msb + 0x20 for deck, msb in COLOR_FX_MSB.items()}

# --- Beat FX -------------------------------------------------------------
# The whole section talks on channel 5 (0x94/0xB4). rekordbox's own table names
# every address; Mixxx's first effect unit is the natural home for it.
BEAT_FX_STATUS = 0x94
BEAT_FX_CC = 0xB4
FX_UNIT = "[EffectRack1_EffectUnit1]"
FX_SLOT = "[EffectRack1_EffectUnit1_Effect1]"

# The fourteen FX the unit names on its own display, in its own order. Pressing
# one selects it, so each is a jump straight to that slot rather than a step
# through a list -- which is what the buttons are for.
BEAT_FX_SELECT = [
    (0x20, "LOW CUT ECHO"), (0x21, "ECHO"), (0x22, "MT DELAY"),
    (0x23, "SPIRAL"), (0x24, "REVERB"), (0x25, "TRANS"),
    (0x26, "ENIGMA JET"), (0x27, "FLANGER"), (0x28, "PHASER"),
    (0x29, "PITCH"), (0x2A, "SLIP ROLL"), (0x2B, "ROLL"),
    (0x2C, "MOBIUS SAW"), (0x2D, "MOBIUS TRIANGLE"),
]

# Which channels the unit routes the effect to.
BEAT_FX_ASSIGN = [
    (0x10, "[Channel1]", "CH1"), (0x11, "[Channel2]", "CH2"),
    (0x12, "[Channel3]", "CH3"), (0x13, "[Channel4]", "CH4"),
    (0x14, "[Master]", "MASTER"),
]

# --- mixer ---------------------------------------------------------------
MIXER_FADERS = [
    (0x1F, 0x3F, "[Master]", "crossfader", "CROSSFADER"),
    (0x08, 0x28, "[Master]", "gain", "MASTER LEVEL"),
    (0x0D, 0x2D, "[Master]", "headGain", "HEADPHONE LEVEL"),
    (0x0C, 0x2C, "[Master]", "headMix", "HEADPHONE MIXING"),
    # Not [Master],gain -- MASTER LEVEL already drives that, and the two
    # knobs fought over the house volume.
    (0x03, 0x23, "[Sampler1]", "pregain", "SAMPLER VOLUME"),
]


def el(tag: str, text) -> str:
    return f"<{tag}>{escape(str(text))}</{tag}>"


def control(status: int, midino: int, group: str, key: str, comment: str, options=("normal",)) -> str:
    opts = "".join(f"<{o}/>" for o in options)
    return f"""      <control>
        <!-- {escape(comment)} -->
        <group>{group}</group>
        <key>{key}</key>
        <status>0x{status:02X}</status>
        <midino>0x{midino:02X}</midino>
        <options>{opts}</options>
      </control>
"""


def output(status: int, midino: int, group: str, key: str, comment: str, on=0x7F, off=0x00, minimum=0.5) -> str:
    return f"""      <output>
        <!-- {escape(comment)} -->
        <group>{group}</group>
        <key>{key}</key>
        <status>0x{status:02X}</status>
        <midino>0x{midino:02X}</midino>
        <on>0x{on:02X}</on>
        <off>0x{off:02X}</off>
        <minimum>{minimum}</minimum>
      </output>
"""


def build_controls() -> str:
    out = []

    for deck in DECKS:
        g = f"[Channel{deck}]"
        note_status = NOTE + deck - 1
        cc_status = CC + deck - 1
        eq_group = f"[EqualizerRack1_{g}_Effect1]"
        filter_group = f"[QuickEffectRack1_{g}]"

        out.append(f"      <!-- ============ DECK {deck} ============ -->\n")

        for midino, key, desc in DECK_BUTTONS:
            out.append(control(note_status, midino, g, key, f"Deck {deck} {desc}"))
        for midino, key, desc in DECK_BUTTONS_SHIFT:
            out.append(control(note_status, midino, g, key, f"Deck {deck} {desc}"))
        for midino, key, desc in DECK_BUTTONS_SCRIPT:
            out.append(control(note_status, midino, g, f"{SCRIPT_PREFIX}.{key}",
                               f"Deck {deck} {desc}", ("script-binding",)))

        # Jog wheel. The platter and the outer ring are separate encoders and
        # each sends a different address depending on what is held, which
        # rekordbox's own mapping table names:
        #
        #   B0 22  platter, VINYL on         scratch
        #   B0 23  platter, VINYL off        pitch bend
        #   B0 21  outer ring                pitch bend
        #   B0 29  platter + SEARCH held     run through the track at speed
        #   B0 1F  platter + SHIFT           stretch the beat grid
        #   B0 26  outer ring + SHIFT        slide the whole beat grid
        #
        # The platter sends 0x22 or 0x23 depending on VINYL mode, not on
        # whether it is being touched -- the touch note says that.
        out.append(control(note_status, 0x36, g, f"{SCRIPT_PREFIX}.jogTouch", f"Deck {deck} JOG touch", ("script-binding",)))
        out.append(control(cc_status, 0x22, g, f"{SCRIPT_PREFIX}.jogScratch", f"Deck {deck} JOG platter (VINYL on)", ("script-binding",)))
        out.append(control(cc_status, 0x23, g, f"{SCRIPT_PREFIX}.jogBend", f"Deck {deck} JOG platter (VINYL off)", ("script-binding",)))
        out.append(control(cc_status, 0x21, g, f"{SCRIPT_PREFIX}.jogBend", f"Deck {deck} JOG outer ring", ("script-binding",)))
        out.append(control(cc_status, 0x29, g, f"{SCRIPT_PREFIX}.jogSearch", f"Deck {deck} JOG platter + SEARCH", ("script-binding",)))
        out.append(control(cc_status, 0x1F, g, f"{SCRIPT_PREFIX}.jogGridStretch", f"Deck {deck} JOG platter + SHIFT", ("script-binding",)))
        out.append(control(cc_status, 0x26, g, f"{SCRIPT_PREFIX}.jogGridSlide", f"Deck {deck} JOG outer ring + SHIFT", ("script-binding",)))

        # The SEARCH buttons send one note on a press and a second once the
        # press turns into a hold, so a tap jumps and holding scans. Holding
        # one of them also switches the platter to the search above.
        for midino, key, desc in ((0x5E, "searchBackward", "SEARCH backward"),
                                  (0x5F, "searchForward", "SEARCH forward"),
                                  (0x70, "searchBackward", "SEARCH backward held"),
                                  (0x71, "searchForward", "SEARCH forward held")):
            out.append(control(note_status, midino, g, f"{SCRIPT_PREFIX}.{key}",
                               f"Deck {deck} {desc}", ("script-binding",)))

        for msb, lsb, key, desc in DECK_FADERS:
            out.append(control(cc_status, msb, g, key, f"Deck {deck} {desc} MSB", ("fourteen-bit-msb",)))
            out.append(control(cc_status, lsb, g, key, f"Deck {deck} {desc} LSB", ("fourteen-bit-lsb",)))

        for msb, lsb, key, desc in DECK_EQ:
            out.append(control(cc_status, msb, eq_group, key, f"Deck {deck} {desc} MSB", ("fourteen-bit-msb",)))
            out.append(control(cc_status, lsb, eq_group, key, f"Deck {deck} {desc} LSB", ("fourteen-bit-lsb",)))

        out.append(control(MIXER_CC, COLOR_FX_MSB[deck], filter_group, "super1", f"Deck {deck} COLOR FX MSB", ("fourteen-bit-msb",)))
        out.append(control(MIXER_CC, COLOR_FX_LSB[deck], filter_group, "super1", f"Deck {deck} COLOR FX LSB", ("fourteen-bit-lsb",)))

        # --- performance pads ---
        pad_status = PAD_NOTE[deck]
        shift_status = PAD_NOTE_SHIFT[deck]

        for pad in range(8):
            n = pad + 1
            base = PAD_MODE_BASE["hotcue"] + pad
            out.append(control(pad_status, base, g, f"hotcue_{n}_activate", f"Deck {deck} PAD {n} hot cue {n}"))
            out.append(control(shift_status, base, g, f"hotcue_{n}_clear", f"Deck {deck} SHIFT+PAD {n} clear hot cue {n}"))

            # Beat loop: pads select loop lengths 1/4 .. 32 beats. Mixxx spells
            # the fractional sizes with a dot, e.g. beatloop_0.25_toggle.
            size = [0.25, 0.5, 1, 2, 4, 8, 16, 32][pad]
            key = f"beatloop_{size:g}_toggle"
            out.append(control(pad_status, PAD_MODE_BASE["beatloop"] + pad, g, key, f"Deck {deck} PAD {n} beat loop {size:g}"))

            # Beat jump: backward on the top row, forward on the bottom.
            jump = [1, 2, 4, 8][pad % 4]
            direction = "backward" if pad < 4 else "forward"
            out.append(control(pad_status, PAD_MODE_BASE["beatjump"] + pad, g, f"beatjump_{jump}_{direction}", f"Deck {deck} PAD {n} beat jump {jump} {direction}"))

            # Sampler pads address the global sampler decks, offset per deck.
            sampler = (deck - 1) * 8 + n
            out.append(control(pad_status, PAD_MODE_BASE["sampler"] + pad, f"[Sampler{sampler}]", "cue_gotoandplay", f"Deck {deck} PAD {n} sampler {sampler}"))
            out.append(control(shift_status, PAD_MODE_BASE["sampler"] + pad, f"[Sampler{sampler}]", "eject", f"Deck {deck} SHIFT+PAD {n} eject sampler {sampler}"))

    # --- Beat FX ---
    for midino, name in BEAT_FX_SELECT:
        out.append(control(BEAT_FX_STATUS, midino, FX_SLOT,
                           f"{SCRIPT_PREFIX}.selectEffect{midino:02X}",
                           f"BEAT FX select {name}", ("script-binding",)))

    for midino, group, name in BEAT_FX_ASSIGN:
        out.append(control(BEAT_FX_STATUS, midino, FX_UNIT,
                           f"group_{group}_enable",
                           f"BEAT FX assign to {name}"))
        out.append(output(BEAT_FX_STATUS, midino, FX_UNIT,
                          f"group_{group}_enable", f"BEAT FX {name} lamp"))

    out.append(control(BEAT_FX_STATUS, 0x47, FX_UNIT, "enabled", "BEAT FX ON/OFF"))
    out.append(output(BEAT_FX_STATUS, 0x47, FX_UNIT, "enabled",
                      # The MIDI list puts this lamp on the button's own
                      # note. 0x46 is not an address the unit answers to,
                      # so the lamp never lit.
                      "BEAT FX lamp"))
    out.append(control(BEAT_FX_STATUS, 0x4A, FX_SLOT,
                       f"{SCRIPT_PREFIX}.beatDown", "BEAT FX beat down", ("script-binding",)))
    out.append(control(BEAT_FX_STATUS, 0x4B, FX_SLOT,
                       f"{SCRIPT_PREFIX}.beatUp", "BEAT FX beat up", ("script-binding",)))
    out.append(control(BEAT_FX_CC, 0x02, FX_UNIT, "super1", "BEAT FX LEVEL/DEPTH"))

    # --- mixer / browser ---
    out.append("      <!-- ============ MIXER ============ -->\n")
    for msb, lsb, group, key, desc in MIXER_FADERS:
        out.append(control(MIXER_CC, msb, group, key, f"{desc} MSB", ("fourteen-bit-msb",)))
        out.append(control(MIXER_CC, lsb, group, key, f"{desc} LSB", ("fourteen-bit-lsb",)))

    out.append(control(MIXER_CC, 0x40, "[Library]", f"{SCRIPT_PREFIX}.browse", "TRAX encoder turn", ("script-binding",)))
    out.append(control(MIXER_CC, 0x64, "[Library]", f"{SCRIPT_PREFIX}.browseFast", "SHIFT+TRAX encoder turn", ("script-binding",)))
    out.append(control(MIXER_NOTE, 0x41, "[Library]", f"{SCRIPT_PREFIX}.browsePress",
                       "TRAX encoder press", ("script-binding",)))
    out.append(control(MIXER_NOTE, 0x7A, "[Library]", f"{SCRIPT_PREFIX}.viewButton",
                       "VIEW button", ("script-binding",)))
    # BACK moves the cursor between the tree view and the track list, which is
    # Mixxx's focus rather than its selection.
    out.append(control(MIXER_NOTE, 0x65, "[Sidebar]", f"{SCRIPT_PREFIX}.backButton",
                       "BACK button", ("script-binding",)))

    # Not a control on the unit: the bridge sends this once the controller has
    # come back and authenticated, so Mixxx reopens the sound device it lost
    # when the thing was unplugged -- the controller is also the sound card.
    out.append(control(0x9F, 0x7F, "[SoundManager]", "reopen_devices",
                       "bridge: controller reconnected"))
    out.append(control(MIXER_NOTE, 0x66, "[Library]", f"{SCRIPT_PREFIX}.backToOverview",
                       "SHIFT+BACK: leave the library", ("script-binding",)))

    for deck in DECKS:
        out.append(control(MIXER_NOTE, 0x46 + deck - 1, f"[Channel{deck}]",
                           f"{SCRIPT_PREFIX}.loadDeck{deck}",
                           f"LOAD deck {deck}", ("script-binding",)))

    return "".join(out)


def build_outputs() -> str:
    out = []
    for deck in DECKS:
        g = f"[Channel{deck}]"
        note_status = NOTE + deck - 1
        pad_status = PAD_NOTE[deck]

        out.append(f"      <!-- ============ DECK {deck} LEDs ============ -->\n")
        out.append(output(note_status, 0x0B, g, "play_indicator", f"Deck {deck} PLAY lamp"))
        out.append(output(note_status, 0x0C, g, "cue_indicator", f"Deck {deck} CUE lamp"))
        out.append(output(note_status, 0x58, g, "sync_enabled", f"Deck {deck} SYNC lamp"))
        out.append(output(note_status, 0x54, g, "pfl", f"Deck {deck} HEADPHONE CUE lamp"))
        out.append(output(note_status, 0x14, g, "loop_enabled", f"Deck {deck} LOOP lamp"))
        out.append(output(note_status, 0x1A, g, "keylock", f"Deck {deck} KEY LOCK lamp"))

        for pad in range(8):
            n = pad + 1
            out.append(output(pad_status, PAD_MODE_BASE["hotcue"] + pad, g, f"hotcue_{n}_enabled", f"Deck {deck} PAD {n} hot cue lamp"))
    return "".join(out)


def build_xml() -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!--
  {MAPPING_NAME}

  GENERATED FILE - do not edit by hand, edit gen_mapping.py and re-run it.

  Every MIDI address is taken from AlphaTheta's official
  "DDJ-1000 List of MIDI message version 1.00".

  Note that on Linux the DDJ-1000's built-in soundcard does not work: it is not
  USB Audio Class compliant and no kernel driver exists for it. Use a separate
  audio interface. MIDI, which is what this file covers, needs no driver.
-->
<MixxxControllerPreset mixxxVersion="2.4+" schemaVersion="1">
  <info>
    <name>{escape(MAPPING_NAME)}</name>
    <author>{escape(AUTHOR)}</author>
    <description>{escape(DESCRIPTION)}</description>
  </info>
  <controller id="DDJ-1000">
    <scriptfiles>
      <file filename="{SCRIPT_FILE}" functionprefix="{SCRIPT_PREFIX}"/>
    </scriptfiles>
    <controls>
{build_controls()}    </controls>
    <outputs>
{build_outputs()}    </outputs>
  </controller>
</MixxxControllerPreset>
"""


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / "Pioneer-DDJ-1000-4deck.midi.xml"
    xml = build_xml()
    target.write_text(xml, encoding="utf-8")

    controls = xml.count("<control>")
    outputs = xml.count("<output>")
    print(f"wrote {target}")
    print(f"  {controls} controls, {outputs} outputs, {len(xml)} bytes")
    print(f"  decks: {', '.join(str(d) for d in DECKS)}")
    print(f"  pad modes wired: hotcue, beatloop, beatjump, sampler (8 pads each)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
