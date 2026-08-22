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

rekordbox's 3Band mode looks like the RGB one — three band levels per column,
one colour on screen — so `WaveformType 17` with rekordbox's hues is the
obvious thing to try, and it was tried here across six palettes: blue with
white highs, blue with a dimmed cream, a dimmed blue with a saturated orange,
and three balances in between. Every one washed out on dense material, for a
reason that is arithmetic rather than taste. A blue low and a warm mid are
near-complementary, so their sum is neutral; any column carrying both bass and
mids — which in dance music is nearly every column — normalises to something
pale, and whatever the high band adds only desaturates it further.

rekordbox does not mix at all. Static analysis of rekordbox 6.8.7, written up
in the DDJ-1000 repository as `docs/rekordbox-recon/waveform-3band-colour.md`,
found seven hand-written colours in the instruction stream and no arithmetic:
it draws one bar per band about the centre line, sorts the three by height and
paints them largest first, so the outer ring is the loudest band's own colour,
the middle ring belongs to whichever pair reaches it, and the core where all
three overlap is always the same pale cream. `#0055E1` low, `#FFA600` mid,
`#FFFFFF` high, `#B4690A` low and mid, `#D2DCFA` low and high, `#FFF0D7` mid
and high, `#F5EBD7` all three.

That is the filtered renderer's geometry, which is why the palette that ships
is on the filtered renderer and why its three slots hold *region* colours
rather than band colours. Mixxx paints low, mid, high in a fixed order and has
only one middle colour, so the rim gets the low-only blue, the ring gets the
low-and-mid `#B4690A`, and the core gets the all-three cream:

```xml
<SignalLowColor>#0055e1</SignalLowColor>    <!-- rim: bass alone      -->
<SignalMidColor>#b4690a</SignalMidColor>    <!-- ring: bass and mid   -->
<SignalHighColor>#f5ebd7</SignalHighColor>  <!-- core: all three      -->
<SignalRGBLowColor>#0055e1</SignalRGBLowColor>
<SignalRGBMidColor>#b4690a</SignalRGBMidColor>
<SignalRGBHighColor>#f5ebd7</SignalRGBHighColor>
<Signal3BandLowColor>#0055e1</Signal3BandLowColor>
<Signal3BandMidColor>#ffa600</Signal3BandMidColor>
<Signal3BandHighColor>#ffffff</Signal3BandHighColor>
<Signal3BandMix>additive</Signal3BandMix>
```

The three sets are not three opinions. The plain triple is regions, for the
filtered renderer that is live. The RGB triple is the same three, because the
stacked all-shaders renderer reads those tags and lays its bars out the same
way. The `Signal3Band*` set is per band rather than per region, because it
feeds a mixer that adds; those are rekordbox's own three band colours, and
`additive` asks for the sum without the divide. Nothing on the box reads that
last set today. All of it appears twice, in `waveform.xml` for the lanes and
`deck.xml` for the card overviews, and the two have to be kept in step by hand.

Colours alone do not decide which ring is visible. A band is only seen where
its bar reaches past the bands painted after it, and Mixxx's own high band is
far larger relative to low and mid than rekordbox's is. That was first set by
eye at `1.15 / 1.5 / 0.2`; it has since been measured, and the measurement
moved it.

Both programs' stored band levels can be read: rekordbox's out of the `PWV7`
tag of its 399 analysis files, Mixxx's out of the zlib'd protobuf under
`~/.mixxx/analysis`. Decoding rekordbox's reproduces the recon document's
ordering table exactly — 78.8 / 13.9 / 4.1 / 0.9 / 0.7 / 1.7 over 15 423 044
non-silent columns — which is a check on the decoder and on the recon at once.
Painting those columns the way each renderer paints them and counting what
colour each pixel of the lane ends up, rekordbox's lane is **47.8 % blue,
41.7 % amber and 10.5 % pale**. Mixxx's, over 32 tracks of the box's own
library, is 24.6 / 56.6 / 18.8 at `1.15 / 1.5 / 0.2`, and at equal gains the
cream covers **70 %** of the lane.

Searching the two free ratios for the closest match gives `1.15 / 0.69 / 0.06`,
which lands on 47.3 / 42.0 / 10.7 — within about a point of rekordbox on all
three. On the box, on one track, that reads 67.1 / 24.8 / 8.1; single tracks
vary widely and the library figure is the one to trust. Those are the gains
that ship.

Twelve tracks turn out to be in both libraries, confirmed by correlating the
low-band envelopes (r = 0.81 to 0.89), so the two analysers can be compared on
identical audio. Doing that, **Mixxx draws its high band ten times hotter,
relative to its own low band, than rekordbox draws its own**. Two causes
compound. The bands differ by 2.2× in energy. The rest is the curve, and the
curve is the part a gain cannot follow: Mixxx's analyser stores the high band
as `x^0.632`, which lifts quiet detail, where rekordbox draws
`0.5 - 0.5·cos(πx)`, which crushes it. The correction those two demand of each
other is 24× at a tenth of full scale, 2.8× at a quarter, and 1.0× at the top.
A single multiplier can sit at one point on that curve and nowhere else, which
is why the fitted `0.06` matches rekordbox's *average* cream and not its
behaviour: at the fitted gain Mixxx's core is 4.6 % of the lane in the median
column against rekordbox's 1.4 %, and 18 % at the 90th percentile against
rekordbox's 33 %. rekordbox keeps its cream for transients. Mixxx spreads it.

| Key | Value |
|---|---|
| `WaveformType` | `19`, `AllShaderFilteredWaveform` |
| `WaveformOverviewType` | `0`, filtered, reading the `<Overview>` block in `deck.xml` |
| `OverviewNormalized` | `1`, so the card overview crops to the track's own peak instead of fighting the master gain |
| `VisualGain_0` | `1` |
| `VisualGain_1` (low, the blue rim) | `1.15` |
| `VisualGain_2` (mid, the amber body) | `0.69` |
| `VisualGain_3` (high, the cream core) | `0.06` |
| `AxesColor` | `#00000000`, in both `waveform.xml` and `deck.xml` |

`mixxx.cfg` is rewritten by Mixxx when it exits, so it can only be edited while
Mixxx is not running: kill it, wait for the process to go, edit in the gap, and
let the autologin chain bring it back. The gap is short, because killing Mixxx
ends the X session and the autologin chain starts it again within a second, so
the edit has to be driven by polling for the process to disappear rather than
by sleeping.

Two things the gains do not reach.

**The card overview is not affected by them at all.** `WOverview` reads only
`getVisualGain(All)`; `drawNextPixmapPartLMH` takes the three stored bytes and
draws three lines with no per-band gain anywhere. So the card overviews are
drawn at the equal gains that put cream over 70 % of the lane, and measuring
the pixels of a card confirms it: **89 % to 99.8 % of the coloured pixels in a
deck card's overview are the cream**, before and after the lane gains changed.
That is a solid pale block where rekordbox shows a blue-rimmed waveform, and no
setting in `mixxx.cfg` or the skin can move it. It needs code.

**The centre line is Mixxx's, not rekordbox's.** The filtered renderer paints
an axis over the bands after all three, and with `AxesColor` unset it defaults
to `#f5f5f5` — hidden inside a cream core, a white seam across every quiet
passage. Setting it to `#00000000` removes it: measured, the centre row goes
from `#f5f5f5` to the band colour underneath at both a sparse and a dense
position. That works because GL blending happens to be enabled by the time this
renderer draws, which `WaveformRendererFiltered` does not set itself, so it is
worth rechecking after an upgrade.

There is a way out of the normalisation the RGB renderer imposes, and it is
already written. The `pi-setup/build-mixxx-3band.sh` build moves the mix out of
the binary and into the skin, where `Signal3BandMix` may be `additive` — adding
without the divide, which is what keeps rekordbox's quiet passages dark and
lets its loud ones reach white. That build is `2.5.6-0pioneered4`; the box runs
`2.5.6-0pioneered3`, so none of it is live here.
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
