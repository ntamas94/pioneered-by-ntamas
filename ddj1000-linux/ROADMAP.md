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

## Worth wiring, most useful first

**Hot cue page 2** — pad notes `0x08`-`0x0F` on both layers, hot cues 9 to 16.
Mixxx has them; the controller has the page; nothing joins the two. Doubles the
cue capacity for the cost of eight lines in the generator.

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
the sample, the pads want lamps from `track_loaded` and `play`, and page 2 and
the SHIFT+PAGE bank switch are both unwired.

**KEYBOARD mode** — pad notes `0x40`-`0x4F`, a hot cue played at pitches. The
hardest of the pad modes and the least missed; last.

**INPUT SELECT and the rear LINE/PHONO switch** — `0x55`-`0x57` per deck and
`0x46` on decks 3-4 → `passthrough`. Lets the hardware's own input switching
drive Mixxx's routing.

## Feedback the documents say the host must send

Channels `0x94` and `0x96` have no outputs at all — every effect button, every
browse button is dark. Specifically missing: BEAT FX ON/OFF now that its
address is right, the five FX assign lamps, the fourteen effect-select lamps,
the BEAT ◀/▶ lamps, the pad-mode buttons and PAGE buttons, and pad lamps for
every mode except hot cue.

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

SHIFT+SYNC is the key-match rather than the manual's sync-master, which lives
on a long press of SYNC instead. The tempo-range function of SHIFT+MASTER TEMPO
is not reproduced at all — the range lives in the unit's own settings.

## Still open

**The `0x74` blink.** The channel map identifies it as pad 5 of KEY SHIFT mode
on decks 3 and 4, and the inference that rekordbox blinks the pad for the
current key is only that — an inference. Wiring KEY SHIFT mode will settle it.

**Whether the pad-mode and PAGE buttons light themselves** without a host, or
need driving. The documents do not say; the bench will.

## How to settle a question here

One control, a few presses, nothing else, and capture it. Every field found in
this protocol came from a recording like that, and none came from a recording
with a dozen things happening in it — the SYNC and MASTER lamps had been moving
in three earlier captures and were invisible in all of them.
