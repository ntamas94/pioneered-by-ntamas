# The skin

`Pioneered_by_ntamas` is a legacy-format Mixxx skin: a tree of XML files that
Mixxx's own parser turns into widgets, and one stylesheet that colours them.
There is no code in it. Everything it does that looks like logic — a button
that changes the layout, a number that counts something, a waveform that
changes colour — is either a connection to a Mixxx control, a connection to a
control this skin invented, or a stylesheet rule keyed off a widget's value.

This document is what each file draws, what the invented controls are and who
is on the other end of each one, and why several things that used to be in the
panel on the right are not there any more.

Back to the [README](../README.md).

## The files, and how `skin.xml` puts them together

`skin.xml` is the only file Mixxx opens by name. It carries the manifest, the
list of attributes described in the next section, the launch-image style, and
an assembly that is deliberately thin: four singletons — the top bar, the
waveform page, the library page and the samplers page — and a `WidgetStack`
whose `currentpage` is `[Tab],current` and whose three pages are triggered by
`[Tab],overview`, `[Tab],library` and `[Tab],samplers`. The top bar sits above
the stack and is therefore on every page.

`topbar.xml` draws that bar: the Mixxx version badge on the left, which is also
the hit target for the Preferences control; the WAVEFORM and BROWSE tab
buttons, both built from `tab.xml`, which is nothing but a two-state
`PushButton` writing `[Tab],<name>`; the `2 DECK / 2/4 DECK / 4 DECK`
selector; SINGLE and CONTINUE for AutoDJ; and the status box with LOAD, CPU,
temperature, the clock and the OUT button.

`overview.xml` is the WAVEFORM page. It stacks four lanes from `waveform.xml`,
puts the side panel from `beffect.xml` to their right, and below them keeps
four alternative rows of deck cards — a small pair and a big pair, top and
bottom — each row shown or hidden by one of the `card_*` controls. Only the
rows the current deck mode asks for are visible; the others are still built,
which is why switching modes costs nothing but a visibility change.

`waveform.xml` is one lane, instantiated four times with `channel` set. Left to
right it is the 132-pixel information column (USB1 and eject, KEY, BEAT JUMP),
then the deck's three stem buttons, then a narrow column carrying the ON AIR
badge above the large deck number, then the scrolling `<Visual>` waveform with
its cue, hot cue and loop marks.

`deck.xml` is one deck card, instantiated with a channel and two heights so the
same file serves the small and the big rows. It holds the DECK badge in the
channel colour, the title, the two-state REMAIN/TIME readout, the BPM box, the
quantize and tempo panel, and the `<Overview>` of the whole track with the
minute ruler under it.

`library.xml` is the BROWSE page: search box, the KBD button, the sidebar
toggles, the table, and its own copies of the deck-card rows, gated on
`show_cardtop` and `show_cardbot` rather than on the `card_*` keys the waveform
page uses. `samplers.xml` and `sampler.xml` are the samplers page.

`beffect.xml` is the side panel on the right of the waveform page. It is named
for the Beat FX section it used to hold; what it holds now is a heading and
three view buttons, and the name is left alone because `overview.xml` and this
document both point at it.

Two files in the tree are not reachable. `effect.xml` came from the base skin
and no template instantiates it; `templates/toggle_button.xml` likewise. They
are left in place because removing them changes nothing and because
`style.qss` still carries `#EffectToggle` rules that `effect.xml` names.

`style.qss` is one stylesheet for all of it, written as a base section followed
by a long tail of dated refinements. Rules are keyed on `ObjectName`, so a
widget's name in the XML is its handle in the stylesheet, and a renamed object
silently loses its styling.

One warning about `patch-skin-xz.py` in the root of this repository. It
describes itself as the single source of truth and it was, once: it builds this
skin step by step out of the `Pioneered_4_deck` base. It has not been kept up.
The last several changes to the skin — this one included — were made in
`skin/Pioneered_by_ntamas/` directly, so running the builder over a current
tree would take features back out. Treat the tree as the truth and the builder
as history until somebody reconciles them.

## `[Pioneered]`, and why a typo there is silent

Mixxx's skin parser creates any `ConfigKey` a `<Connection>` names. It does not
check the name against a list of controls that exist, because for `[Channel1]`
and friends the control already exists and for anything else the parser is the
thing that brings it into being. That is what makes a private namespace
possible: `[Pioneered]` is not registered anywhere, has no header file and no
declaration, and exists entirely because widgets in this skin refer to it.

The same mechanism is the trap. A button connected to `[Pioneered],zoomni`
builds without complaint, creates the control `zoomni`, and does nothing for
ever. There is no error in the log, nothing in the widget's appearance to say
it is unattached, and the only way to find it is to read both ends. The
`<attributes>` block in `skin.xml` lists the keys with their starting values;
that list is not required — the connections would create them anyway — but it
puts the whole set in one place where it can be compared against the code that
reads them.

| Key | Written by | Read by |
|---|---|---|
| `mode2`, `mode24`, `mode4` | the three deck-mode buttons in `topbar.xml`; each button writes all three | the buttons themselves, for the white highlight on the active one |
| `show_wf1` … `show_wf4` | the deck-mode buttons | `waveform.xml`, as each lane's `visible` |
| `card_smalltop`, `card_smallbot`, `card_bigtop`, `card_bigbot` | the deck-mode buttons | `overview.xml`, as the four card rows' `visible` |
| `show_cardtop`, `show_cardbot` | the deck-mode buttons | `library.xml`, as the browse page's card rows |
| `timemode1` … `timemode4` (persisted) | the REMAIN/TIME toggle on each deck card | the same card's `NumberPos` through `<ModeConfigKey>`, which needs the patched build, and the DDJ-1000 mapping, which reads them to decide what the jog screen shows |
| `zoomin`, `zoomout` | the two ZOOM buttons in the side panel | the mapping's `watchZoomButtons`, which steps every deck's `waveform_zoom` |
| `prefs_btn` | the version badge in the top bar | the mapping, which turns it into the `0x7x` SysEx that asks the daemon to open Preferences |
| `cpu`, `temp` | the mapping, from MIDI the bridge sends it | the top bar's status box |
| `load` | the mapping, from Mixxx's own `[App],audio_latency_usage` | the top bar's status box |
| `stem1_drums` … `stem4_inst`, twelve in all | the twelve stem buttons in the lanes | nothing yet; see below |
| `profile2` | the 2/4 DECK and 4 DECK buttons | nothing. Measured: no other file in the skin names it and the mapping does not either |
| `osk` | the KBD button in `library.xml` | nothing. **Dead** |
| `osk_req` | the patched Mixxx build, when the search box takes focus | nothing. **Dead** |
| `audio_btn` | the OUT button in the top bar | nothing. **Dead** |

The three marked dead are recorded here rather than fixed. The keyboard pair is
the more interesting of them: the on-screen keyboard daemon is running and
listening on VirMIDI 5-0, but for a message the retired `Time-Clamp` mapping
used to send, and nothing sends it now, so the KBD button presses a control
that reaches nobody. `audio_btn` is the same shape of gap on the output
switch. `profile2` is written by two of the three deck-mode buttons and read by
none; that is measured, and what it was meant for is not recorded anywhere I
can find.

## The deck modes

The three buttons in the top bar do not set a mode. There is no mode: there are
ten independent flags, and each button writes all of the ones its layout needs,
because nothing in a legacy skin fans one value out to many controls. The
button is the fan-out. Connections that have to land at zero carry
`<Transform><Not/></Transform>`, and each button writes its own `modeN` flag
last, because the last connection is the one the widget reads back and the
white highlight in the stylesheet keys off that.

4 DECK raises `show_wf1` through `show_wf4`, so four lanes are drawn, and
`card_smalltop` with `card_smallbot`, so all four cards are shown at the
smaller of the two heights. 2/4 DECK drops `show_wf3` and `show_wf4` — two
lanes, which then take the full height between them — and keeps all four
cards. 2 DECK drops the same two lanes and moves the cards to `card_bigtop`
alone: one row, large, flush with the bottom. `show_cardtop` and
`show_cardbot` are the browse page's equivalents of the `card_*` pair, kept
separate because that page has a table to fit in and its own idea of how much
room the cards may have.

The defaults in `skin.xml` are one row of that table and have to stay one row.
A default that mixed two modes would show a layout no button can produce until
one is pressed.

## The time mode

`[Controls],PositionDisplay` is a config-file key rather than a live control,
and the live one, `ShowDurationRemaining`, is global and cycles through three
states in hard-coded `WNumberPos` code. Neither is what the deck cards want,
which is two states, per deck. The patched build adds `<ModeConfigKey>` to
`NumberPos` so the widget can follow a control named by the skin, and
`deck.xml` points it at `[Pioneered],timemode<channel>`.

Those four keys are persisted, so the choice survives a restart, and the
DDJ-1000 mapping reads them: the time on the jog screen is drawn by the daemon
from a `0x3x` SysEx the mapping sends, and the mapping decides remaining or
elapsed by asking the same control the deck card is displaying. Tap the card,
the jog wheel follows.

## LOAD, CPU and °C

The three figures in the top-right corner come from three different places, and
only one of them is Mixxx's own.

LOAD is `[App],audio_latency_usage`, the fraction of each audio callback the
engine spent working, which the mapping multiplies by a hundred and copies into
`[Pioneered],load`. CPU and the temperature cannot be read from inside Mixxx at
all — nothing in a controller script can open `/proc` — so they arrive as MIDI
from the bridge, which reads them on the Pi and sends them in; the mapping's
`systemCpu` and `systemTemp` copy them into `[Pioneered],cpu` and
`[Pioneered],temp`. The skin creates all three by naming them, which is why the
box read three zeroes for as long as it did rather than showing an error: a
control nobody writes reads zero and says nothing.

## The waveform colours

This is the part with the most measurement behind it and the most room left to
get wrong, so it is worth being precise about which renderer reads what.

`WaveformSignalColors::setup` reads **two** independent triples out of the same
`<Visual>` or `<Overview>` block. `SignalLowColor` / `SignalMidColor` /
`SignalHighColor` are read by the **filtered** renderers.
`SignalRGBLowColor` / `SignalRGBMidColor` / `SignalRGBHighColor` are read by
the **RGB** renderers, and when they are absent the fallback is not the other
triple — it is `Qt::red`, `Qt::green` and `Qt::blue`, which is how this skin
once managed to draw a rainbow while holding a perfectly good blue palette.
Which of the two is live is decided outside the skin, by `WaveformType` in
`~/.mixxx/mixxx.cfg`: `19` is `AllShaderFilteredWaveform`, `17` is
`AllShaderRGBWaveform`, and the card overviews have their own switch,
`WaveformOverviewType`, where `0` is filtered and `2` is RGB.

The two renderers differ in kind, not in tuning. The filtered one draws one
filled bar per band, all centred on the lane, in the fixed order low, mid,
high, with no blending, so the last one drawn owns the middle and each colour
survives as itself. The RGB one draws a single bar per column and mixes:
`red = maxLow*low_r + maxMid*mid_r + maxHigh*high_r`, and the same for green
and blue, and then divides all three by the largest of them. That last step is
the whole story of what follows. It keeps the ratio and throws the level away,
so a column ten decibels down is drawn as bright as the loudest one, and no
column is ever white, because white needs all three components at full and only
the largest survives the division.

rekordbox's 3Band mode is structurally the RGB one — three band levels per
column, one colour computed from them — so `WaveformType 17` with rekordbox's
hues is the obvious thing to try, and it was tried here across six palettes:
blue with white highs, blue with a dimmed cream, a dimmed blue with a saturated
orange, and three balances in between. Every one of them washed out on dense
material, and the reason is arithmetic rather than taste. A blue low and a warm
mid are near-complementary; their sum is neutral, so any column containing both
bass and mids — which in dance music is nearly every column — normalises to
something pale, and whatever the high band adds on top only desaturates it
further. Screenshots of all six are in the working notes; the effect is
identical in the lane and in the card overview.

So the palette that is actually shipped is on the **filtered** renderer, with
the three colours ordered by draw order rather than by frequency:

```xml
<SignalLowColor>#f2e8d5</SignalLowColor>   <!-- cream: the rim and the tips -->
<SignalMidColor>#c8741c</SignalMidColor>   <!-- burnt orange: the ring       -->
<SignalHighColor>#1d6fe0</SignalHighColor> <!-- blue: the body               -->
<SignalRGBLowColor>#1d6fe0</SignalRGBLowColor>
<SignalRGBMidColor>#c8741c</SignalRGBMidColor>
<SignalRGBHighColor>#f2e8d5</SignalRGBHighColor>
```

The two triples look contradictory and are not. Each carries the assignment
that produces a blue body with orange accents and cream tips *in the renderer
that reads it*: the filtered triple ordered by who paints over whom, the RGB
triple ordered by frequency. Both blocks appear twice, once in `waveform.xml`
for the lanes and once in `deck.xml` for the card overviews, and they are not
interchangeable between the two files by accident — they happen to be the same
now, but the tags mean the same thing in both, so keep them in step by hand.

Which colour is visible where is not settled by the colours alone. In the
filtered renderer a band is only seen where its bar reaches past the bands
drawn after it, so the mid band is invisible unless it out-reaches the high
band, and the per-band gains in `mixxx.cfg` are what decide that. Measured on
the box with a dense drum-and-bass track: at `VisualGain_2 0.9` the orange was
absent, at `1.3` it appeared as flecks along the top of the blue, and at `1.6`
it reads as a proper band of transients. The values now on the box are

| Key | Value |
|---|---|
| `WaveformType` | `19` |
| `WaveformOverviewType` | `0` |
| `OverviewNormalized` | `1` |
| `VisualGain_0` | `1` |
| `VisualGain_1` (low, the cream tips) | `1` |
| `VisualGain_2` (mid, the orange) | `1.6` |
| `VisualGain_3` (high, the blue body) | `1.1` |

and `mixxx.cfg` is rewritten by Mixxx when it exits, so it can only be edited
while Mixxx is not running.

There is a way out of the normalisation, and it is already written: the
`pi-setup/build-mixxx-3band.sh` build moves the mix out of the binary and into
the skin, where `Signal3BandMix` may be set to `additive` — adding without the
divide, which is what rekordbox does and what makes its quiet passages stay
dark and its dense ones go white. That build is `2.5.6-0pioneered4`; the box is
running `2.5.6-0pioneered3`, so nothing of it is live here. Both waveform
blocks in the skin already carry `<Signal3BandMix>additive</Signal3BandMix>`,
which the current binary ignores. When the patched build is installed, moving
`WaveformType` to `17` and `WaveformOverviewType` to `2` should be all that is
needed, and the RGB triple above is the palette it will use.

None of this touches the jog-wheel screens. Those are drawn by the bridge from
its own theme file and share nothing with the skin.

## What was taken out of the side panel, and why

The panel on the right of the waveform page used to be the effects section, and
none of it worked in a way that was worth the space.

**COLOR FX L and COLOR FX R** were two `EffectChainPresetSelector` combo boxes
over `[QuickEffectRack1_[Channel1]]` and `[Channel2]` — decks 1 and 2 only, on
a four-deck box, with no way to reach 3 and 4 and no indication that they were
missing. **BEAT FX** below them was a group of four: an `[InternalClock],bpm`
readout with an AUTO BPM chip that had nothing behind it, another chain
selector, an Off/Active button whose second connection named
`EffectRack1_EffectUnit1],group_[Master]_enable` — the leading bracket really
was missing, so that connection created a control with a bracket in its name
and enabled nothing — and a LENGTH readout of
`[EffectRack1_EffectUnit1_Effect2],parameter1`, the first parameter of whatever
effect happened to be in the second slot of the first unit, labelled as if it
were always a length. All of it is gone, with the two heading strips and the
now-unused `#Fx*`, `#Param`, `#text` and `#FxLenPct` rules in the stylesheet.
The `#EffectToggle` rules stayed, because `effect.xml` still names them.

Two earlier removals belong in the same paragraph, because they were the same
mistake. The **LOW/MID/HI** panel under ZOOM and GRID read the button
parameters of whatever effect sat in unit 1, slot 1 — button parameters that
most Mixxx effects do not declare at all, so the three labels usually stood
over nothing. The **X-PAD PARAMETER** strip was three fixed labels over a value
the stylesheet had already hidden with `max-height: 0px`; it had been copied
from a rekordbox band that belongs to a touch strip the DDJ-1000 does not have.

What is in the panel now is a heading and three buttons. Grid is a wide bar
that writes `waveform_zoom_set_default` on all four channels, not deck 1 alone,
because the lanes are read side by side and a reset that leaves three of them
zoomed is worse than none. Under it, ZOOM IN and ZOOM OUT are one-state
buttons, so a press sends 1 and the release sends 0, and each writes
`[Pioneered],zoomin` or `[Pioneered],zoomout`. The skin cannot step a number by
itself, so the stepping is in the mapping, which walks the ladder
`1, 2, 3, 4, 6, 8` on all four decks at once. It replaced a single cycling
ZOOM button that could only go one way round.

`waveform_zoom` counts samples across a pixel, so a larger number shows more of
the track: ZOOM IN steps *down* the ladder. That is the opposite of what the
name suggests and it was got wrong first time — four presses of ZOOM IN made
the lane denser, which is what the screenshot showed before the manual was
consulted.

## The stem buttons

Each deck's lane carries three buttons between the information column and the
deck number: **DRUMS**, **VOCAL**, **INST**, top to bottom, in rekordbox's own
colours — a royal blue, a bright green and a red. Twelve in all. They are
two-state toggles, so a press latches and the stylesheet lights the button from
its value; nothing else in the skin reads them.

The keys are

```
[Pioneered],stem1_drums   [Pioneered],stem1_vocal   [Pioneered],stem1_inst
[Pioneered],stem2_drums   [Pioneered],stem2_vocal   [Pioneered],stem2_inst
[Pioneered],stem3_drums   [Pioneered],stem3_vocal   [Pioneered],stem3_inst
[Pioneered],stem4_drums   [Pioneered],stem4_vocal   [Pioneered],stem4_inst
```

built in `waveform.xml` from the template's `channel` variable, and declared in
`skin.xml` so the set is visible in one place and reads zero before anything is
pressed.

Nothing is behind them yet. The names are rekordbox's three stems and mean what
rekordbox means by them, including that INST is the residual — the mix with
drums and vocals taken out — rather than something a separation network
predicts. The path from one of these presses to a file on a deck is being built
in the bridge and is written up in the DDJ-1000 repository, in
`docs/stem-buttons.md`; what the three stems are, read out of rekordbox's own
binaries, is in `docs/three-stem-mode.md` beside it.
