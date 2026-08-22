# What is left to wire

Written after reading Pioneer's own documents end to end — the List of MIDI
Messages ver 1.00, the Operating Instructions, the quick start and the
troubleshooting addendum — and auditing both halves of the mapping against
them. Every address below comes from the MIDI list unless it says otherwise.

Two things worth knowing before reading further.

**The XML is generated.** `mixxx/gen_mapping.py` produces
`Pioneer-DDJ-1000-4deck.midi.xml`. A fix made in the XML survives until the
next run of the generator and no longer. Everything here belongs in the
generator or in the script half.

**The channel map is not the obvious one.** Decks are 1-4 on `0x90`-`0x93`,
the effect section is 5 on `0x94`, browse and the global mixer are 7 on `0x96`
and `0xB6` — and the performance pads are two channels per deck, plain and
shifted: deck 1 on `0x97`/`0x98`, deck 2 on `0x99`/`0x9A`, deck 3 on
`0x9B`/`0x9C`, deck 4 on `0x9D`/`0x9E`. That last one settled a mystery: four
notes blinking on `0x9B`-`0x9E` that nothing here sent turned out to be
rekordbox lighting pad 5 of KEY SHIFT mode on decks 3 and 4.

## Bugs, in the order they should be fixed

**`selectEffectByIndex` cannot select an index.** It writes `effect_selector`
= 0 and then = 1, *index* times. `effect_selector` is a relative stepper, so
writing 0 does nothing at all and the loop simply steps forward from wherever
the chain already sits. The first of the fourteen effect buttons therefore does
nothing and the other thirteen drift further out of step with every press. They
need an absolute selection — load the effect by name into the slot, or step
from a known position.

**The hot cue pad lamps have two writers.** Thirty-two `<output>` entries send
`0x7F`/`0x00` on the pad notes, and `connectHotcueLed` sends `0x2A`/`0x00` on
the same notes from the same control. Every hot cue change emits two
conflicting messages and the colour that sticks depends on callback order. The
script should own it — it is the half that can send a colour rather than a
brightness. While there, read `hotcue_N_color` instead of the fixed blue.

**Four buttons, two functions.** SHIFT+SYNC (`0x5C`) and SHIFT+SEMITONE DOWN
(`0x65`) both fire `sync_key`; SHIFT+KEY LOCK (`0x60`) and SHIFT+SEMITONE UP
(`0x64`) both fire `reset_key`. The semitone buttons should be `pitch_up` and
`pitch_down`, and they have no unshifted binding at all.

**`orientation_center` sits on note `0x1D`.** Left is `0x16` and right is
`0x18`, which makes `0x17` the obvious place for centre and `0x1D` a
transcription slip worth checking against the hardware.

**Six `<output>` blocks are inside `<controls>`.** The generator appends the
five BEAT FX assign lamps and the BEAT FX ON/OFF lamp while it is building the
controls list, so they land in the wrong element and Mixxx never reads them.
That is the whole of why the effect section is dark, and it is a three-line
move in `build_controls` rather than anything that needs new addresses. The
count gives it away: the XML holds 102 `<output>` blocks but only 96 of them
are where an output belongs.

## Worth wiring, most useful first

**Instant doubles on SHIFT+LOAD** — `0x96` notes `0x5D`, `0x5E`, `0x6D`, `0x6F`
for decks 1-4 → `CloneFromDeck`. The manual's press-the-encoder-twice feature,
and a thing DJs actually use.

**KEY SHIFT pad mode** — pad notes `0x70`-`0x7F`, transposing the running track
by semitones, pad 5 being ±0. An entire pad mode currently dead, and the one
whose lamps rekordbox was blinking at us.

**PAD FX 1 and 2** — pad notes `0x10`-`0x1F` and `0x50`-`0x5F`. The pads'
flashiest mode: hold for a loop roll or an effect stab, release to drop it.
Wants scripting around `beatlooproll_*_activate` and the effect units.

**SOUND COLOR FX SELECT** — `0x96` notes `0x00`-`0x03` with SHIFT on
`0x08`-`0x0B`, plus their lamps. Makes the four COLOR knobs switch between
effects the way they do under rekordbox, instead of being stuck on one.

**MEMORY and SHIFT+SEARCH** — `0x3D`/`0x3E` to store and delete, `0x51`/`0x53`
to call the stored points back. Completes the cue-management story the hardware
is laid out for.

**BOOTH LEVEL** — `0xB6` CC `0x09`/`0x29` → `[Master] booth_gain`. One line.

**Vinyl mode on SHIFT+SLIP** (`0x17`) — the jog top does pitch bend rather than
scratch with vinyl off, which the jog code already distinguishes by CC.

**Sampler polish** — SHIFT+pad should stop the playing slot rather than eject
the sample, and the pads want lamps from `track_loaded` and `play`. The lamps
matter more than they did: the bank now moves under the pads and nothing on
the unit says which of the four it is on.

**KEYBOARD mode** — pad notes `0x40`-`0x4F`, a hot cue played at pitches. The
hardest of the pad modes and the least missed; last.

**INPUT SELECT and the rear LINE/PHONO switch** — `0x55`-`0x57` per deck and
`0x46` on decks 3-4 → `passthrough`. Lets the hardware's own input switching
drive Mixxx's routing.

## Feedback the documents say the host must send

Channels `0x94` and `0x96` have no outputs at all — every effect button, every
browse button is dark. Specifically missing: BEAT FX ON/OFF and the five FX
assign lamps, both of which the generator does write but into the wrong
element (above); the fourteen effect-select lamps, the BEAT ◀/▶ lamps, the
pad-mode buttons, fourteen of the sixteen PAGE buttons, and pad lamps for
every mode except hot cue.

The two exceptions are the BEAT JUMP PAGE pair, `0x26` and `0x2E`, which the
script lights to show whether the jump range can still be halved or doubled.
Whether the unit would have lit them itself is still unmeasured, so if they
end up fighting something, that pair is where to look.

MASTER CUE is documented as lighting itself *or* by MIDI; it is currently left
to the hardware, which is probably right.

## Deliberate divergences, not gaps

The jog screens are drawn over HID by the daemon rather than by the MIDI
display messages — position ring, BPM, cue marker, time, key. rekordbox drives
them the same way, and sending both leaves the unit flipping between two
pictures. Only the tempo pair, the time mode, the ring LED, show/hide and the
two sync lamps still go out over MIDI.

Beat loop page 1 starts at 1/32 rather than the manual's 1/64, because 1/32 is
the smallest loop Mixxx has.

The sampler pads address one global bank rather than a private eighth of the
rack per deck. The manual says the sampler "has four banks and each bank has
sixteen slots", which is exactly Mixxx's sixty-four samplers, so the pads are
bank × 16 + page × 8 + pad and every slot is reachable from every deck
section. The cost is that all four sections now show the same sixteen slots,
where before deck 2 had its own eight. See
[docs/pad-pages-and-page-buttons.md](docs/pad-pages-and-page-buttons.md).

Beat jump pads carry a multiplier rather than a fixed number of beats, so the
PAGE pair can scale all eight at once the way the manual describes. A range of
1 leaves them on the manual's printed 1/2/4/8; the range is clamped to 1/8 …
64, which keeps the largest pad inside Mixxx's own 512-beat ceiling.

SHIFT+SYNC is the key-match rather than the manual's sync-master, which lives
on a long press of SYNC instead. The tempo-range function of SHIFT+MASTER TEMPO
is not reproduced at all — the range lives in the unit's own settings.

## Still open

**The `0x74` blink.** The channel map identifies it as pad 5 of KEY SHIFT mode
on decks 3 and 4, and the inference that rekordbox blinks the pad for the
current key is only that — an inference. Wiring KEY SHIFT mode will settle it.

**Whether the pad-mode and PAGE buttons light themselves** without a host, or
need driving. The documents do not say; the bench will. What the PAGE buttons
*do* is no longer open: footnote \*1 of the MIDI list says the unit switches
the notes its pads send, with a diagram of deck 1's hot cues moving from
`97 00`-`97 07` to `97 08`-`97 0F`, and it does not ask the host first.

**Whether rekordbox's page-change permission flags matter.** Its CSV carries
eight host→unit indicators named "Permission flag of PAGE change" — `0x21`,
`0x63`, `0x6A`, `0x6C`, `0x6E`, `0x74`, `0x75`, `0x76` — that the official
MIDI list does not list at all. Nothing here sends them deliberately, on the
reading that the footnote means what it says and the paging is the unit's own.
If a PAGE button turns out to do nothing on the bench, they are the first
thing to try — and note that one of them is already going out by accident:
`sendOpeningState` writes `0x20` to note `0x21` on every deck to ask for the
panel's knob positions, and `0x21` is rekordbox's hot cue permission flag. If
hot cue is the one mode that pages, that is why.

## How to settle a question here

One control, a few presses, nothing else, and capture it. Every field found in
this protocol came from a recording like that, and none came from a recording
with a dozen things happening in it — the SYNC and MASTER lamps had been moving
in three earlier captures and were invisible in all of them.
