# The DDJ-1000 sound card

Interface 0 is vendor specific and carries no audio descriptors worth the name:
no channel count, no sample rate, no bit depth. The host has to know the format
already, which is what this quirk supplies. Everything else in the tree is stock
`snd-usb-audio`.

The fork touches exactly two files. `grep -ril ddj` over the whole tree returns
`dkms.conf`, `quirks-table.h` and `quirks.c`, and `2b73` appears only at
`quirks-table.h:3095` and `quirks.c:1873`.

## What the hardware actually does

Measured off a USBPcap capture of rekordbox driving the unit on Windows, not
read off the descriptors — the descriptors are part of the problem.

Interface 0 alt 1 declares two endpoints:

```
EP 0x01  attr 0x05 (isoc, async, usage DATA)  wMaxPacketSize 1024  bInterval 2
EP 0x82  attr 0x05 (isoc, async, usage DATA)  wMaxPacketSize 1024  bInterval 2
```

`bInterval 2` at high speed is 2 microframes — **250 µs**, both directions. The
declared usage is DATA on both; nothing in the descriptors says the input
endpoint is a feedback source.

On the wire, rekordbox's entire audio setup is two control transfers:

```
SET_INTERFACE  bmRequestType 0x00  bRequest 0x0b  wValue 0x0001  wIndex 0x0000
SET_CUR        bmRequestType 0x22  bRequest 0x01  wValue 0x0100  wIndex 0x0082
```

One `SET_INTERFACE` for the whole session. It never goes back to alt 0 while
streaming, and it never re-issues alt 1.

Then the streams, 56 064 packets out and 56 080 in over 35 seconds:

| endpoint | packet sizes | mean |
|---|---|---|
| `0x01` out | 198 B ×12 614, 216 B ×1 398 | 198.45 B per 250 µs |
| `0x82` in | 396 B ×54 663, 432 B ×1 410, 360 B ×7 | 396.9 B per 250 µs |

198.45 B / 18 B per frame = 11.025 frames per 250 µs = **44 100 Hz, six channels
of S24_3LE**. The playback side is what the quirk says it is.

## The capture endpoint is twelve channels, not six

396.9 / 11.025 = **36.0 bytes per frame**. Twelve channels, not six.

The proof does not depend on believing that arithmetic. Decode the same packets
both ways and look at where the energy is:

```
peak per channel, stride 36 (12 ch):  [0,0,0,0,128,107,0,0,0,0,0,0]
peak per channel, stride 18 (6 ch):   [0,0,0,0,128,107]
stride-18 energy:  even frames 1409039,  odd frames 0
```

At 36 bytes per frame, two channels carry a dither floor and the other ten are
silent — a unit with nothing plugged into it. At 18 bytes per frame the same
bytes read as every other frame being *exactly* zero, which no audio source
produces. The stride is 36.

This matches the in-tree DJM-900NXS2 entry, `quirks-table.h:3029-3031`, whose
comment reads "10 channels playback & 12 channels capture" — the DDJ-1000's
mixer section descends from that hardware. That entry needs no packet-size
overrides at all.

**`quirks-table.h:3119` declaring `.channels = 6` on the input audioformat is
wrong.** Every other override in the quirk exists to compensate for it, and the
compensations do not fully cancel.

## How the error propagates

Playback opens `0x82` as its implicit feedback source using the *capture*
audioformat (`pcm.c:507` → `implicit.c:456`, `pcm.c:550` → `endpoint.c:828`), so
the sync endpoint inherits `cur_channels = 6`, `cur_frame_bytes = 18`,
`stride = 18` (`endpoint.c:1117`).

The feedback conversion, `endpoint.c:1808-1816`:

```c
unsigned int frames = urb->iso_frame_desc[i].actual_length / sender->stride;
out_packet->packet_size[i] = min(frames, ep->maxframesize);
```

With `stride` 18 instead of 36 a 396-byte packet reads as 22 frames instead of
11. The `.maxpacksize = 0x00c6` at `quirks-table.h:3108` then caps the playback
endpoint at `198 / 18 = 11` frames (`endpoint.c:1403`), and `min(22, 11)` gives
11 — the right answer, arrived at by two errors cancelling, because 198 is
exactly half of 396.

They only cancel for the common packet:

| device sends | really | driver computes | after the clamp | |
|---|---|---|---|---|
| 396 B (97.5%) | 11 frames | 22 | 11 | correct |
| 432 B (2.5%) | 12 frames | 24 | 11 | one frame short |
| 360 B (rare) | 10 frames | 20 | 11 | one frame over |

The 432-byte input packets are the device asking for a 12-frame output packet,
and rekordbox obliges: 1 398 of its output URBs are 810 bytes — 198+198+198+**216**
— against 1 410 input packets of 432. This driver can never send 216 bytes,
because `maxframesize` is hard-capped at 11.

So the host feeds 11 frames every 250 µs — **44 000 Hz** — to a device clocked at
44 100. A standing **−2 268 ppm** error, starving the device's playback FIFO by
100 frames a second, for as long as it runs.

## `datainterval = 2` contradicts the descriptor

`quirks-table.h:3129` asks for 500 µs on an endpoint whose descriptor says 250.
It sets `ep->pps = 2000` and `urb->interval = 4` microframes (`endpoint.c:1368`,
`1257`).

That playback comes out at nearly the right pitch is only consistent with the
input endpoint still being serviced every 250 µs, which is what xHCI does: it
schedules from the endpoint context built out of `bInterval` and ignores
`urb->interval`. **Unproven, and worth checking before anyone ships this:** on a
host controller that does honour `urb->interval` — EHCI, or dwc2, which is the
Pi 4's USB-C port, a Pi 3, and a CM4 OTG port — the same module would poll at
500 µs and run at half speed. Nobody has measured that; it is a reading of the
schedulers, not an observation.

Even on xHCI the driver's time base is off by two, so URBs complete twice as
fast as it expects. That halves the real-time depth of the `MAX_URBS = 12` queue
(`card.h:8`) and makes the `next_packet` overflow check at `endpoint.c:1786`
easier to reach under load. `hw_check_valid_format()` also refuses period times
under 500 µs for no reason (`pcm.c:789`).

## The capture stream is unusable as it stands

`arecord -D hw:N,0 -f S24_3LE -c 6 -r 44100` — which is exactly what the bridge
used to run to hold the interface open — reads 396-byte packets as 22 frames at
4 000 packets a second, 88 200 frames into a 44 100 Hz stream, and hands back
twelve interleaved channels reinterpreted as six.

## The corrected quirk

```c
/* OUT, EP 0x01 */  .channels = 6,   /* drop .maxpacksize = 0x00c6 */
/* IN,  EP 0x82 */  .channels = 12,  /* drop .maxpacksize = 0x01b0, .datainterval = 2 */
```

The arithmetic that follows: output `maxsize = 17 × 18 = 306` ≥ 216 and
`maxframesize = 1024 / 18 = 56`, no clamp; input `maxsize = 17 × 36 = 612` ≥ 432
and `maxframesize = 1024 / 36 = 28`, so feedback passes 11 and 12 through
untouched. That is rekordbox's packet mix exactly.
`snd_usb_find_implicit_fb_sync_format()` still picks the capture format
(`implicit.c:430-434`, score 1 > 0), so the asymmetric channel count is fine.

**Applied and measured on hardware.** `/proc/asound/cardN/stream0` now reports
6 channels playback and 12 capture, both at a 250 µs packet interval, which is
what rekordbox negotiates. Two things confirm it on the wire:

The playback rate, taken from `hw_ptr` over 20 seconds:

```
frames 882025 in 20.000 s = 44100.41 Hz
error vs 44100: +9 ppm
```

Against −2 268 ppm before. And usbmon on the Pi now shows the output URBs
carrying the packet mix the device asks for:

```
OUT lengths: [(792, 2595), (810, 306)]
```

792 is four 198-byte packets; 810 is 198+198+198+**216**. The 216-byte packet —
the 12-frame one the old entry could never send — is 10.5% of URBs here against
rekordbox's 10.0%.

## Alternate-setting behaviour

rekordbox issues one `SET_INTERFACE(0,1)` and leaves it. This driver does not,
in four places. Ranked by how well each explains the jog screens dropping back
to `NO AUDIO DRIVER` while everything else looks right:

All four are now addressed. The first two by a guard and a flags entry, both
applied and running; the last two are left alone as upstream behaviour.

**A duplicate `SET_INTERFACE(0,1)` on every prepare.** `quirks.c:1776`, inside
`pioneer_djm_set_format_quirk()`, issues a raw `usb_set_interface(dev, 0, 1)`.
By then `endpoint_set_interface()` has already selected alt 1
(`endpoint.c:1490-1494`), so the wire carries two where rekordbox carries one.
A device that reads `SET_INTERFACE` as a stream restart would drop and re-arm
its "driver present" state — landing after the SysEx handshake has completed,
which is the reported symptom exactly. The further claim that this also flushes
a concurrent stream's URBs could not be checked: `drivers/usb/core/message.c` is
not in this tree and no kernel source was available. Treat the URB flushing as
unverified.

**Nothing sets `QUIRK_FLAG_IFACE_SKIP_CLOSE`.** `endpoint.c:956-958` drops the
interface to alt 0 when the last PCM client closes — the driver telling the
device the driver is gone. There is no `DEVICE_FLG(0x2b73, ...)` anywhere in
`quirk_flags_table` (`quirks.c:2149`ff); this device runs with only
`QUIRK_FLAG_PLAYBACK_FIRST`, set at runtime by `implicit.c:344`.

**The cached altsetting can desync.** `endpoint.c:917` returns early when
`iface_ref->altset` already matches, so if the real setting changes behind the
driver's back — a device-side reset that does not re-enumerate, a port reset —
the cache says 1, the device sits at 0, and alt 1 is never issued again.
Mainline's mitigation is `QUIRK_FLAG_FORCE_IFACE_RESET` (`endpoint.c:1693`),
also not set here. Note this cannot explain a real power cycle, which
re-enumerates and rebuilds the whole `iface_ref` list.

**A failed re-select leaves alt 0.** `snd_usb_endpoint_prepare()` deselects
unconditionally at `endpoint.c:1481` and ignores the result; if the re-select at
`1491` fails, it returns the error and nothing restores alt 1. During every
normal re-prepare the interface visibly bounces 1 → 0 → 1, which rekordbox never
does.

### What was changed

In `pioneer_djm_set_format_quirk()`, the raw `usb_set_interface()` now runs only
when the interface is not already at alternate setting 1, read from the USB
core's own `cur_altsetting`. Skipping a redundant request is safe for the DJM
devices that share the function.

And an entry in `quirk_flags_table`:

```c
DEVICE_FLG(0x2b73, 0x0020, /* Pioneer DJ DDJ-1000 */
           QUIRK_FLAG_IFACE_SKIP_CLOSE | QUIRK_FLAG_DISABLE_AUTOSUSPEND),
```

Playback still clocks correctly afterwards — 44100.99 Hz, +22 ppm over fifteen
seconds.

`QUIRK_FLAG_FORCE_IFACE_RESET` was considered and left off: it re-arms the setup
on every playback stop, which is a bounce in the opposite direction, and the
desync it guards against cannot explain a power cycle anyway.

## Other notes

`.ep_attr`'s `USB_ENDPOINT_USAGE_IMPLICIT_FB` bit at `quirks-table.h:3127` is
decorative — only the SYNCTYPE bits of `fp->ep_attr` are ever read
(`implicit.c:264`, `298`; `pcm.c:116`, `360`). The implicit feedback link is
established from the descriptor by `is_pioneer_implicit_fb()`
(`implicit.c:202-234` → `343-348`), which is also what sets
`QUIRK_FLAG_PLAYBACK_FIRST`.

Because playback and capture share interface 0 alt 1 through implicit feedback,
a second opener must match the first exactly — same rate, format, period frames
and buffer periods (`endpoint_compatible()`, `endpoint.c:745-758`) — or
`snd_usb_hw_params()` returns `-EINVAL` (`pcm.c:554`). That is a consequence of
the design rather than a bug in the fork, but it is why holding the interface
open with a second stream is fragile.

`snd-usb-audio.mod.c` is a checked-in modpost artifact. Harmless — kbuild
regenerates it — but it does not belong in a source tree.

## Reproducing the measurements

The packet sizes and the stride proof come from `ddj-tempo.pcap`, a USBPcap
recording of rekordbox on Windows. Parse it with the helpers in
`ddj-capture-gui.pyw`: `read_packets(path)` yields `(timestamp, endpoint,
payload)`, and the input URBs on `0x82` are whole multiples of the packet size.
