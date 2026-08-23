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
then the deck's three stem buttons, then the four-row stem strip that only a
Mixxx with a stem engine ever shows, then a narrow column carrying the ON AIR
badge above the large deck number, then the scrolling `<Visual>` waveform with
its cue, hot cue and loop marks.

`stems.xml` and `stem_channel.xml` are that strip: the first is one deck's worth
and carries the single connection that decides whether any of it is visible, the
second is one stem's row, instantiated four times. Both are described at length
below, because on the version the box runs they are built and never seen.

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
| `stem1_drums` … `stem4_inst`, twelve in all | the twelve stem buttons in the lanes | the mapping's `watchStemButtons`, which turns a press into the `0x71` SysEx that asks the bridge to load that stem's render on that deck |
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
setting in `mixxx.cfg` or the skin can move it.

That is what `2.5.6-0pioneered4` is for. `pi-setup/build-mixxx-3band.sh` routes
those three lines through the same per-band tables the three-band mixer already
builds, and the gains come from the skin as `Signal3BandLowGain`,
`Signal3BandMidGain` and `Signal3BandHighGain` in the `<Overview>` block of
`deck.xml` — the same `1.15 / 0.69 / 0.06` the lane uses. With gains of 1 the
patch is an arithmetic no-op, so the build changes nothing until the skin asks.
Measured on the same track before and after, off the screen: the deck card went
from 3.8 % blue, 7.0 amber, **89.2 cream** to 50.4 % blue, 43.8 amber, **5.9
cream**, against rekordbox's own 47.8 / 41.7 / 10.5.

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
its value.

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

What is behind them is the bridge, not Mixxx. The mapping's `watchStemButtons`
connects to all twelve and turns a press into `F0 7D 71 <deck> <stem> F7`; the
daemon finds the matching render on disk and puts it on that deck through
Mixxx's File menu. That path exists because 2.5.6 has no stem engine at all:
there is nothing per-deck to switch on, only a separately rendered file to load,
and loading a named file is not reachable from a controller script. The names
are rekordbox's three and mean what rekordbox means by them, including that INST
is the residual, the mix with drums and vocals taken out. `docs/stem-buttons.md`
in the DDJ-1000 repository is the bridge end of it, and `docs/three-stem-mode.md`
beside it is where the three came from.

## The stem strip, and how it stays invisible on 2.5.6

Mixxx 2.6 has stems for real. Loading a file with a manifest gives every deck

```
[ChannelN_Stem1..4]                   volume, mute, color
[QuickEffectRack1_[ChannelN_StemM]]   one QuickEffect chain per stem
[ChannelN],stem_count                 read-only, 0 unless a stem track is up
```

and the stock 2.6 skins build a row per stem out of exactly those. This skin now
does too, in `stems.xml` and `stem_channel.xml`, four rows per deck, in the lane
immediately right of the three buttons above.

**The three buttons were not re-pointed at it, and that is the whole design
decision.** Aiming them at `[ChannelN_StemM],mute` would trade working behaviour
on the version the box runs for behaviour it cannot use, and it would do it
silently: the parser invents any key a `<Connection>` names, so on 2.5.6
`[Channel1_Stem1],mute` would come into being as a control nobody writes, the
button would look normal and do nothing, and no log line would say so. That is
the failure written up as four dead buttons in `docs/system-integration.md` in
the DDJ-1000 repository. So the two live side by side and mean different things:
the three buttons **load** a stem render, the strip **mixes** the stems of a file
already loaded.

It is one skin and not two, and what keeps it honest on both versions is a
single connection in `stems.xml`:

```xml
<Connection>
  <ConfigKey>[Channel<Variable name="channel"/>],stem_count</ConfigKey>
  <BindProperty>visible</BindProperty>
</Connection>
```

On 2.6 that is the engine's own read-only count, so the strip appears for a stem
track and for nothing else, which is what the stock skins do with it. On 2.5.6
there is no such control, the parser invents it at zero, and nothing ever writes
it. `ControlWidgetPropertyConnection`'s constructor reads the control once, so
the group is hidden from the moment it is built rather than appearing and then
settling: it is never shown at all. The mechanism that makes a dead button is the
mechanism that makes a container which stays shut, and pointed this way round it
costs nothing.

A separate skin for 2.6 was the alternative and was rejected for the reason the
version badge below has to be argued about: a second copy of a hundred kilobytes
of XML, kept in step by hand, is a larger version of the problem, not a solution
to it.

That was tested rather than reasoned about. The same files were run under the
box's own `/usr/bin/mixxx` 2.5.6 and under `~/build/mixxx-2.6/build26/mixxx`,
each headless on an Xvfb of its own with a settings path of its own, neither
touching the running Mixxx. On 2.6, with `sin_AAC_256kbps_VBR.stem.mp4` on deck
1, the strip appeared on that deck and on no other, the names came out of the
manifest, MUTE lit its row red and a dragged fader moved. On 2.5.6 the window was
the skin as it was, the strip nowhere, and the log carried sixteen new lines and
nothing else:

```
Skin parsing failed at skin:stem_channel.xml:39 <StemLabel>: Invalid node name in skin
```

one per row, because `StemLabel` is a 2.6 element and 2.5.6's parser skips what
it does not know. Those sixteen lines are the price of the manifest's names and
they are worth paying: a warning that names the file and the line is the opposite
of the silent kind of wrong. Nothing else moved — the `track_number` tooltip
warnings in the same log predate this and come from `deck.xml`.

A row holds the name, MUTE, a volume fader and a colour fader, which is the
DDJ-1000's own hand on a stem: the channel fader, the CUE button and the COLOR
knob. The two faders are `SliderComposed` drawn entirely from `BarColor` and
`BarWidth`, with no images — a skin with one PNG in it can still have a fader —
and the colour one has `BarUnipolar` false so it fills from the centre out, the
way the knob it stands for works from its detent. The only pixmap is a hairline
handle, `images/stem_handle.svg`, added because a slider with no handle logs a
line per instance and thirty-two of those is worse than one small file.

Three things are deliberately absent.

**The chain preset.** Which effect a stem's COLOR knob runs is not selectable
from this skin. A combo box on a row this tall cannot be hit with a finger, and
the unit has no per-stem control that would pick one either. It is a gap, and it
is recorded here so the next reader does not think it was forgotten.

**The stem's colour.** `WStemLabel` writes the manifest's colour into the
widget's palette, and this skin's `WLabel { color: #e5e6ea; }` overrides it,
because a Qt type selector matches subclasses and a stylesheet colour beats a
palette. `color: palette(window-text)` looks like the escape and is not: the
stylesheet resolves that once, while the label still wears the default palette,
and reapplies what it resolved on every repolish. Measured on 2.6 with the test
file, whose manifest asks for `#fd4a4a`, `#ffff00`, `#00e8e8` and `#ad65ff`, all
four names rendered `#010203`. The only fix is narrowing the global rule to
`.WLabel`, which would take the colour off every Number, Key, Time and title in
the skin, so the names are grey and the words carry the meaning.

**`[Skin],show_stem_controls`.** The stock skins hang their strip off that
persisted key as well, and declare it in their own manifests. Binding it here
without declaring it would leave the strip hidden on 2.6 for ever, which is the
dead-button trap with the sign flipped, so it is not bound.

`<RequiresStem>true</RequiresStem>` on the group is 2.6's own gate and covers the
third case: a 2.6 built without `__STEM__` skips the group at parse time, so not
even the invented controls appear. 2.5.6 ignores the element, which is exactly
why it cannot be the version test on its own.

The four rows are in slot order, and that order is not this skin's to choose. The
renderer in the DDJ-1000 repository writes rekordbox's own four-stem
`PartLayout`, confirmed by ear on a rendered proof file:

| Slot | Name | Colour | Button beside it |
|---|---|---|---|
| `[ChannelN_Stem1]` | DRUMS | `#4655FF` | DRUMS |
| `[ChannelN_Stem2]` | VOCAL | `#02DA0C` | VOCAL |
| `[ChannelN_Stem3]` | INST | `#DA1B02` | INST |
| `[ChannelN_Stem4]` | BASS | `#D60094` | none |

Slots 1 to 3 line up with the unit's three ACTIVE PART buttons and with the three
load buttons to the left of the strip; BASS is the slot with no button and sits
at the bottom. The words on screen still come out of the file, so a stem file
from somewhere else shows its own names in its own order.

## The version number in the top bar

The badge in the top left says `Mixxx` over a number, and the number used to be
`2.5.6` typed into `topbar.xml`. That is a claim nobody checks, and it was going
to be wrong the first time this skin ran on 2.6.

A skin cannot ask. Nothing in `legacyskinparser.cpp` hands a skin the running
Mixxx's version; the `<version>` in `skin.xml` is this skin's own, and none of
the stock 2.6 skins display the application's at all. The one question a skin can
ask about the Mixxx running it is whether a control exists, because a
`<Connection>` to a control that does not exist creates it at zero. So the badge
holds two labels now, one reading `2.5.6` and one reading `2.6`, each with its
`visible` bound to

```
[QuickEffectRack1_[Channel1_Stem1]],num_effectslots
```

and a `<Not/>` on the first. 2.6 creates that control when it builds the
QuickEffect chain of deck 1's first stem, at startup rather than at track load,
and `EffectChain` marks it read-only, so nothing on the box can move it. 2.5.6
has no stem chains and the invented key stays zero. Measured: the badge reads
`2.6` under `build26/mixxx` and `2.5.6` under `/usr/bin/mixxx`, from the same
files.

Two limits belong next to the number rather than in somebody's memory. **The
strings are still hand-written and they live in `topbar.xml`, nowhere else.** And
the test has two answers, so a Mixxx newer than 2.6 that still has stem chains
will read `2.6` until somebody adds a third label. That is a badge one version
behind rather than a badge that never moves, and it is the reason the number was
not simply dropped in favour of the word `Mixxx` alone: the number is wanted, and
this is the only way a skin can make it true of both builds that exist here.

One more copy of the version is out of the skin's reach entirely.
`images/pioneered_logo.png`, the launch image, has `Mixxx 2.5.6` drawn into its
pixels, which is what the screen shows for the second or two before the skin
appears. Nothing conditional reaches an image, so that one stays wrong on 2.6
until somebody redraws it or takes the number out of the artwork.
