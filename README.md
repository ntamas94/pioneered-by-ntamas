# Pioneered by ntamas

Mixxx 2.5 skin and Raspberry Pi 4 DJ-box toolkit that recreates the Pioneer
XDJ-XZ / XDJ-AZ WAVEFORM screen — built for the DDJ-1000 controller.

The skin is based on the 4-deck variant of
[Pioneered](https://github.com/timewasternl/Pioneered) /
[Pioneered-Plus](https://github.com/bencejuhaasz/Pioneered-Plus) (GPL-3.0).

![](docs/screenshot.png)

## Features

- XZ-style deck cards: DECK badge in channel colour, REMAIN/TIME (two-state,
  tap to toggle), one-sided blue/yellow/white overview waveform, BPM box with
  MASTER chip, Q / range / tempo% panel, TRACK number with QUANTIZE lamp
- `2 DECK | 2/4 DECK | 4 DECK` view selector — pressing the active button
  again flips between deck pairs (1-2 ↔ 3-4)
- Waveform sidebar: USB1 + eject, KEY, ON AIR column with large deck number
- Pioneer-style cyclic ZOOM (zooms in, wraps back to widest) on all four
  decks at once
- CPU readout in the top bar (systemd daemon → VirMIDI → mapping → skin)
- SINGLE/CONTINUE (AutoDJ), X-PAD strip, ZOOM/GRID, LOW/MID/HI kills
- Minute ruler under the card waveform (`-4:00 -3:00 …`) — requires the
  patched Mixxx built by `pi-setup/build-mixxx-ruler.sh`
- Whole deck card is a track drop target; with the patched build the card
  lights up while a drag hovers over it, and long titles scroll (marquee)
  instead of pushing the layout apart

## Layout

| Path | What it is |
|---|---|
| `skin/Pioneered_by_ntamas/` | the finished skin — copy into `~/.mixxx/skins/` |
| `patch-skin-xz.py` | idempotent builder: produces the skin from the `Pioneered_4_deck` base, step by step |
| `controllers/Time-Clamp.midi.xml` + `-scripts.js` | mapping attached to a VirMIDI port: two-state time, view-selector radio, cyclic zoom, CPU input — loads without any hardware controller |
| `controllers/pioneer-ddj1000.midi.xml` + JS | custom 4-deck DDJ-1000 mapping (351 controls, 56 outputs), generated from the official AlphaTheta MIDI list |
| `controllers/gen_mapping.py` | the DDJ-1000 XML generator |
| `pi-setup/` | Pi 4 provisioning: headless boot, audit, CPU→MIDI daemon, conky overlay, patched Mixxx source build |

## Quick install on the Pi

```bash
# on the Pi:
echo 'options snd-virmidi index=5' | sudo tee /etc/modprobe.d/virmidi.conf
echo snd-virmidi | sudo tee /etc/modules-load.d/virmidi.conf
sudo modprobe snd-virmidi
cp -r skin/Pioneered_by_ntamas ~/.mixxx/skins/
cp controllers/Time-Clamp* ~/.mixxx/controllers/
sudo install -m755 pi-setup/djbox-cpu-midi.sh /usr/local/bin/
# mixxx.cfg: [Controller] VirMIDI_5-0 1, [ControllerPreset] VirMIDI_5-0 Time-Clamp.midi.xml
```

Recommended `mixxx.cfg` values: `WaveformType 19` (all-shader Filtered, uses
the skin colours), `WaveformOverviewType 0`, `TimeFormat 1`,
`PositionDisplay 1`.

## Patched Mixxx (minute ruler + drop hover + marquee titles)

The `.deb` packages attached to the Release (arm64, Debian Trixie /
Raspberry Pi OS) add three things on top of stock 2.5.0:

- minute ruler under the card overview waveform (`-4:00 -3:00 …`)
- `dropHover` property on `TrackWidgetGroup` — the skin highlights the card
  a track is about to be dropped onto
- `<Elide>scroll</Elide>` in WLabel: long titles bounce left-right instead
  of stretching the layout

Install: `sudo dpkg -i mixxx-data_*.deb mixxx_*.deb`. Rebuild from source:
`pi-setup/build-mixxx-ruler.sh`. The version string sorts above the distro
package, so `apt upgrade` will not replace it.

## Why it is built this way

- `[Controls],PositionDisplay` is only a config-file key; the live control is
  `ShowDurationRemaining` — and the 3-state cycle is hard-coded in
  `WNumberPos`, which is why the two-state time needs a controller script.
- `WPushButton` only toggles on a `ControlPushButton`; on a plain
  `ControlObject` it falls back to PUSH — hence the view-selector buttons use
  momentary triggers plus separate display controls.
- Qt applies `min-width` to the content box, padding/border comes on top —
  the column sizes the boxes instead of fixed widths.

GPL-3.0, inherited from the base skin.
