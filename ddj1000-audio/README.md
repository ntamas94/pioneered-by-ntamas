# Pioneer DJ DDJ-1000 — Linux audio driver (kernel quirk)

The DDJ-1000's built-in sound card is not USB-audio-class compliant, so stock
Linux only sees it as a MIDI + HID device and the controller's display says
**"no audio driver"**. This is a small `snd-usb-audio` quirk that makes the
sound card work — 6 channels out (master / booth / headphones), 6 in, 24-bit
44.1 kHz — exactly like the in-tree DDJ-800 / DDJ-SX3 entries.

Tested on Raspberry Pi 4, Raspberry Pi OS Trixie, kernel 6.18: Mixxx plays
through the DDJ-1000 master out, the controller's display goes "audio OK".

## Install (Raspberry Pi OS / Debian)

```bash
sudo ./install.sh
```

Builds the patched module as a **DKMS** package (`snd-usb-audio-ddj1000`),
so it is rebuilt automatically on kernel updates. Then:

```bash
aplay -l            # card N: DDJ1000 [DDJ-1000], device 0: USB Audio
speaker-test -D plughw:N,0 -c 2 -t sine -f 440
```

In Mixxx pick `DDJ-1000: USB Audio (hw:N,0)` as Master, channels 1-2.
(On the DJ box: `djbox-audio.sh usb`.)

## What the quirk says (`ddj1000-usb-audio.patch`)

| | |
|---|---|
| USB ID | `2b73:0020` (AlphaTheta), vendor-specific interface 0, alt 1 |
| Format | S24_3LE, 6 ch, 44 100 Hz fixed |
| Playback | EP `0x01` OUT, isochronous async, **198 bytes / 250 µs** |
| Capture / feedback | EP `0x82` IN, implicit feedback for playback, **432 bytes / 500 µs** (`maxpacksize 0x1b0`, `datainterval 2`) |
| Init | DJM-style `SET_CUR` sample-rate (`bmRequestType 0x22, bRequest 1, wValue 0x0100, wIndex 0x0082, data 44 AC 00`) on the IN endpoint before streaming |

Why the packet sizes are spelled out: the descriptor claims 1024 bytes /
250 µs for both endpoints. Left to its own devices the host computes a
2× packet size, the device answers every IN packet with `-EOVERFLOW`, the
implicit feedback loop then runs the output at double speed — which is
exactly the "plays too fast, crackles" symptom. The real numbers came from a
Windows USBPcap capture of the official driver (Rekordbox playing): 198-byte
OUT packets at 250 µs, 396–432-byte IN packets at 500 µs, and the one
`SET_CUR 44100` control transfer after `SET_INTERFACE(0,1)` — no vendor
init sequence at all.

The input side mirrors the output (6 ch); channel mapping of the inputs
(line/phono/mic) has not been verified yet.

## Upstreaming

The patch is written against `sound/usb/quirks-table.h` and
`sound/usb/quirks.c` and applies to mainline as well as the Raspberry Pi
kernel. It follows the existing Pioneer entries (DDJ-800, DJM-450/900NXS2)
one to one, so it should be a straightforward addition for
`alsa-devel` / linux-sound. Not yet submitted.
