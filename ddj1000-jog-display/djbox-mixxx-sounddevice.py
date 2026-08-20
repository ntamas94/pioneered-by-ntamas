#!/usr/bin/env python3
"""Point Mixxx's stored sound configuration at a device.

Usage: djbox-mixxx-sounddevice.py <alsaHwDevice> <name> <portAudioIndex>

Mixxx rewrites soundconfig.xml when it exits, and if it had no working output it
leaves behind an empty <SoundManagerConfig/> with no device in it at all -- after
which every later start comes up with "Mixxx was configured without any output
sound devices", however correct the hardware is. Patching an existing element is
therefore not enough: when there is nothing to patch the file has to be rebuilt.

The device name must be written the way Mixxx itself stores it: PortAudio calls
an ALSA device "DDJ-1000: USB Audio (hw:1,0)" but Mixxx matches on the name with
that suffix stripped.
"""
import re
import sys

PATH = "/home/dj/.mixxx/soundconfig.xml"

TEMPLATE = """<!DOCTYPE SoundManagerConfig>
<SoundManagerConfig api="ALSA" deck_count="4" force_network_clock="0" latency="5" samplerate="44100" sync_buffers="2">
 <SoundDevice alsaHwDevice="{hw}" name="{name}" portAudioIndex="{index}">
  <output channel="0" channel_count="2" index="0" type="Master"/>
 </SoundDevice>
</SoundManagerConfig>
"""

OUTPUT = '  <output channel="0" channel_count="2" index="0" type="Master"/>'


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    hw, name, index = sys.argv[1:4]
    element = '<SoundDevice alsaHwDevice="%s" name="%s" portAudioIndex="%s">' % (hw, name, index)

    try:
        with open(PATH) as fh:
            text = fh.read()
    except OSError:
        text = ""

    if "<SoundDevice" in text:
        text = re.sub(r"<SoundDevice\b[^>]*>", element, text, count=1)
        if "<output" not in text:
            text = text.replace(element, element + "\n" + OUTPUT, 1)
    else:
        text = TEMPLATE.format(hw=hw, name=name, index=index)

    with open(PATH, "w") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
