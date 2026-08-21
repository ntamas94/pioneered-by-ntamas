# Pioneer DDJ-1000 on Linux

Sound, controls, and the colour screens in the jog wheels — the screens
included, which no DJ software on Linux drives.

```sh
./install.sh
```

Three parts, each usable on its own:

```sh
./install.sh audio      # just the sound card quirk
./install.sh bridge     # just the jog screen daemon
./install.sh mixxx      # just the mapping
```

## What each part is

**audio** — a DKMS build of `snd-usb-audio` with a quirk for this unit. Its
descriptor claims 1024-byte packets every 250 µs. The hardware delivers 432
bytes every 500 µs, and taking the descriptor at its word makes the host
overrun the device: everything plays at double speed. The quirk also asks for
the sample rate on the input endpoint the way the DJM mixers need, without
which capture is silent.

Built against the running kernel and rebuilt automatically on kernel updates.
Needs `dkms`, `build-essential` and the kernel headers.

**bridge** — a daemon sitting between the controller and the DJ software. It:

- answers the challenge that takes the jog screens off `NO AUDIO DRIVER`
- holds the HID interface open, which is what the unit reads as "a driver is
  present" — without it the screens lock again within seconds
- draws each deck: artwork with the track's name over it, a waveform coloured
  by density, the beat grid, hot cues and saved loops on the beat scale, key,
  tempo, and the playhead
- carries the controls between the unit and the software, and replays the
  panel's knob and fader positions to it, which the unit reports exactly once

**mixxx** — a four-deck mapping. The jog screens are driven from it: it sends
the deck's position, tempo, grid, cues and time readout to the bridge over a
private SysEx.

## How it sits on the system

The controller presents four USB interfaces, and only one of them needs
anything written for it:

| interface | class | endpoints | handled by |
|---|---|---|---|
| 0 | vendor specific | `0x01` out, `0x82` in | the DKMS quirk |
| 1 | audio control | none | — |
| 2 | MIDI streaming | `0x85` in, `0x04` out | stock `snd-usb-audio` |
| 3 | HID | `0x06` out, `0x87` in | the bridge |

The MIDI side is class compliant and has always worked; nothing here touches
it. The audio side is not: interface 0 is vendor specific and carries no audio
descriptors at all — no channel count, no sample rate, no bit depth — so the
host has to know the format, which is what the quirk supplies. Six channels
each way at 24-bit 44.1 kHz.

The screens live on the HID interface. Authentication, decoding artwork and
talking to the DJ software are all user-space work, so they stay in the
bridge; there is nothing a kernel driver would do for them except make them
harder to debug.

The bridge also holds the capture stream open. The unit reads an idle audio
interface as "no driver present" and locks its screens — which is what happens
every time the DJ software closes. Capture is the side nothing else wants, so
holding it keeps the screens awake while leaving playback free.

## Requirements

    sudo apt install dkms build-essential linux-headers-$(uname -r) \
                     python3 python3-pil ffmpeg

On Raspberry Pi OS the headers package is `raspberrypi-kernel-headers`.

## After installing

Plug the controller in and start Mixxx. In **Preferences → Controllers**, pick
the DDJ-1000's MIDI port, choose **Pioneer DDJ-1000 (4 deck)** and enable it.
Set the sound output to the DDJ-1000 in **Preferences → Sound Hardware**.

The screens come up a few seconds after the audio does. The first load of a
track decodes it to build the picture; the library is built ahead of time in
the background, so this is only ever a wait once.

## If the screens stay on NO AUDIO DRIVER

The unit accepts the authentication once per USB session. If the bridge was not
running when it was plugged in, unplug and replug it — or:

    sudo systemctl restart djbox-ddj-bridge
    journalctl -u djbox-ddj-bridge -f

`authenticated -- jog displays unlocked` means it worked.

## How this was worked out

Captured traffic from rekordbox on Windows (USBPcap) and from this bridge on
Linux (usbmon), compared byte for byte, plus a reading of the screens' own
firmware where the traffic did not say enough. `tools/sh2.py` is the SH-2A
disassembler that took — capstone mis-decodes the very instructions the
firmware reads its reports with.

The last piece to fall was the track id: it is the track's *length*, written
as minutes, seconds and a 16-bit millisecond figure. A plain millisecond count
is not a track the screens recognise, and until that was right the playhead
would not move across the waveform, whatever else was correct.
