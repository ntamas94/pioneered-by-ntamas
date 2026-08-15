#!/usr/bin/env python3
"""Push the Pioneered skin towards the XDJ-XZ WAVEFORM screen.

Runs against a copy of Pioneered_4_deck. Every step is idempotent: steps that
inject a block replace their own previous output rather than skipping it, so
later refinements always land and this script stays the single source of truth.

    python3 patch-skin-xz.py [SKIN_DIR]

SKIN_DIR defaults to ~/.mixxx/skins/Pioneered_by_ntamas
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SKIN = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path.home() / ".mixxx" / "skins" / "Pioneered_by_ntamas"
)

NL = "\n"


# ---------------------------------------------------------------- helpers


def replace_block(text: str, marker: str, opener: str, closer: str) -> str:
    """Cut a previously injected block out, located by a marker inside it."""
    idx = text.index(marker)
    start = text.rindex(opener, 0, idx)
    end = text.index(closer, idx) + len(closer)
    return text[:start] + text[end:]


def extract_block(text: str, marker: str, opener: str, closer: str) -> tuple[str, str]:
    """Return (block, text-without-block), located by a marker inside it."""
    idx = text.index(marker)
    start = text.rindex(opener, 0, idx)
    end = text.index(closer, idx) + len(closer)
    return text[start:end], text[:start] + text[end:]


def extract_group(text: str, marker: str) -> tuple[str, str]:
    """Return (block, text-without-block) for the WidgetGroup holding marker.

    extract_block() takes the first closing tag after the marker, which is wrong
    for a group that nests further WidgetGroups. This counts depth instead.
    """
    idx = text.index(marker)
    start = text.rindex("<WidgetGroup>", 0, idx)
    depth = 0
    pos = start
    while True:
        nxt_open = text.find("<WidgetGroup>", pos)
        nxt_close = text.index("</WidgetGroup>", pos)
        if nxt_open != -1 and nxt_open < nxt_close:
            depth += 1
            pos = nxt_open + len("<WidgetGroup>")
            continue
        depth -= 1
        pos = nxt_close + len("</WidgetGroup>")
        if depth == 0:
            break
    return text[start:pos], text[:start] + text[pos:]


def swap_qss(section: str, block: str) -> None:
    """Replace one named block in place, or append it if it is new.

    Replace must stop at the next section header. Truncating everything after
    the header instead would delete every later step's styling whenever an
    earlier step is re-run.
    """
    path = SKIN / "style.qss"
    text = path.read_text(encoding="utf-8")
    head = f"/* ---- {section} ---- */"
    if head in text:
        before, rest = text.split(head, 1)
        nxt = rest.find("/* ---- ")
        tail = rest[nxt:] if nxt != -1 else ""
        text = before.rstrip() + NL + NL + head + block.rstrip() + NL + NL + tail
        print(f"  style.qss: {section} replaced")
    else:
        text = text.rstrip() + NL + NL + head + block
        print(f"  style.qss: {section} appended")
    path.write_text(text, encoding="utf-8")


def check_xml(*names: str) -> bool:
    for name in names:
        path = SKIN / name
        if not path.is_file():
            continue
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            print(f"  XML ERROR in {name}: {exc}", file=sys.stderr)
            return False
    return True


# ---------------------------------------------------------------- step 1-2

# The XZ lights ON AIR only while a deck is actually feeding the master.
# Binding `visible` reproduces that: the badge is absent rather than dimmed.
ON_AIR = """          <WidgetGroup>
            <ObjectName>DeckOnAir</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckOnAirLabel</ObjectName>
                <Text>ON AIR</Text>
              </Label>
            </Children>
            <Connection>
              <ConfigKey>[Channel<Variable name="channel"/>],play_indicator</ConfigKey>
              <BindProperty>visible</BindProperty>
            </Connection>
          </WidgetGroup>
"""

ON_AIR_ANCHOR = """          <TrackProperty>
            <ObjectName>DeckTitle</ObjectName>"""

QSS_12 = """

#DeckOnAir {
  background-color: #d32020;
  border: 1px solid #ff5a5a;
  border-radius: 2px;
  margin: 2px 6px 2px 2px;
  max-height: 16px;
}

#DeckOnAirLabel {
  color: #ffffff;
  font-size: 10px;
  font-weight: bold;
  letter-spacing: 1px;
  padding: 1px 6px;
  qproperty-alignment: 'AlignCenter';
}

/* Remaining time is the number a DJ reads most, so give it XZ weight — but
   the widget sits in a SizeAwareStack, and a font wide enough to overflow the
   column makes the stack render nothing at all. 30px fits six digits here. */
#DeckTrackTime {
  font-size: 30px;
  font-weight: bold;
  color: #ffffff;
}

#DeckTrackTimeMini {
  font-size: 20px;
  font-weight: bold;
  color: #ffffff;
}

/* The skin hides one of the two stacked readouts by making it transparent.
   Keep that behaviour, but never let it blank both. */
#DeckTrackTimeWrapper {
  min-width: 150px;
}

#DeckTrackTimeTitle {
  color: #8fa4b8;
  font-size: 10px;
  letter-spacing: 1px;
}
"""


def step12() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckOnAir" in text:
        text = replace_block(
            text, "<ObjectName>DeckOnAir</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )
    if ON_AIR_ANCHOR in text:
        text = text.replace(ON_AIR_ANCHOR, ON_AIR + ON_AIR_ANCHOR, 1)
        print("  deck.xml: ON AIR badge")
    else:
        print("  ! ON AIR anchor missing")

    text = text.replace("<Text>Time</Text>", "<Text>REMAIN / TIME</Text>", 1)

    # Mixxx renamed this control: the skin still binds to the 2.3-era name,
    # which no longer exists, so the elapsed/remaining toggle never resolves.
    renamed = text.count("[Controls],ShowDurationRemaining")
    if renamed:
        text = text.replace("[Controls],ShowDurationRemaining", "[Controls],PositionDisplay")
        print(f"  deck.xml: ShowDurationRemaining -> PositionDisplay ({renamed} bindings)")

    path.write_text(text, encoding="utf-8")
    print("  deck.xml: REMAIN / TIME label")

    swap_qss("step 1-2: ON AIR and time", QSS_12)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 3-4

# BeatSpinBox is the widget stock skins use to show and edit a beat count.
BEATJUMP = """              <WidgetGroup>
                <ObjectName>DeckBeatJumpContainer</ObjectName>
                <Layout>vertical</Layout>
                <SizePolicy>max,max</SizePolicy>
                <Children>
                  <Label>
                    <ObjectName>DeckBeatJumpTitle</ObjectName>
                    <Text>BEAT JUMP</Text>
                  </Label>
                  <BeatSpinBox>
                    <ObjectName>DeckBeatJumpValue</ObjectName>
                    <TooltipId>beatjump_size</TooltipId>
                    <SizePolicy>max,max</SizePolicy>
                    <MinimumSize>52,20</MinimumSize>
                    <MaximumSize>72,20</MaximumSize>
                    <Alignment>center</Alignment>
                    <Value>[Channel<Variable name="channel"/>],beatjump_size</Value>
                  </BeatSpinBox>
                </Children>
              </WidgetGroup>
"""

BEATJUMP_ANCHOR = """          <WidgetGroup>
            <ObjectName>TrackTimeContainer</ObjectName>"""

# The XZ's X-PAD sweeps a filter; Mixxx's equivalent is the QuickEffect super
# knob, so the legends mark its ends and centre and the readout tracks it.
XPAD = """<WidgetGroup>
    <ObjectName>XPadStrip</ObjectName>
    <Layout>vertical</Layout>
    <Size>0me,60max</Size>
    <Children>
      <Label>
        <ObjectName>XPadTitle</ObjectName>
        <Text>X-PAD PARAMETER</Text>
      </Label>
      <WidgetGroup>
        <ObjectName>XPadRow</ObjectName>
        <Layout>horizontal</Layout>
        <Children>
          <Label>
            <ObjectName>XPadLpf</ObjectName>
            <SizePolicy>me,min</SizePolicy>
            <Text>LPF</Text>
          </Label>
          <Label>
            <ObjectName>XPadMid</ObjectName>
            <SizePolicy>me,min</SizePolicy>
            <Text>FILTER</Text>
          </Label>
          <Label>
            <ObjectName>XPadHpf</ObjectName>
            <SizePolicy>me,min</SizePolicy>
            <Text>HPF</Text>
          </Label>
        </Children>
      </WidgetGroup>
      <Number>
        <ObjectName>XPadValue</ObjectName>
        <TooltipId>super1</TooltipId>
        <Connection>
          <ConfigKey>[QuickEffectRack1_[Channel1]],super1</ConfigKey>
        </Connection>
      </Number>
    </Children>
  </WidgetGroup>
"""

XPAD_ANCHOR = """<WidgetGroup>
    <Layout>horizontal</Layout>
     <Children>
<PushButton>
        <ObjectName>LOW</ObjectName>"""

QSS_34 = """

#DeckBeatJumpContainer {
  margin: 0 10px 0 4px;
  min-width: 60px;
}

#DeckBeatJumpTitle {
  color: #8fa4b8;
  font-size: 9px;
  letter-spacing: 1px;
  qproperty-alignment: 'AlignCenter';
}

#DeckBeatJumpValue {
  background-color: #10141a;
  border: 1px solid #2b3948;
  color: #ffffff;
  font-size: 13px;
  font-weight: bold;
}

#XPadRow {
  margin: 1px 4px;
}

#XPadStrip {
  background-color: #0d1116;
  border-top: 1px solid #2b3948;
  margin-top: 4px;
  padding: 2px;
}

#XPadTitle {
  color: #8fa4b8;
  font-size: 9px;
  letter-spacing: 1px;
  qproperty-alignment: 'AlignCenter';
}

/* Warm at the low end, cool at the high end, mirroring the XZ strip. */
#XPadLpf { color: #ffb340; font-size: 10px; font-weight: bold; qproperty-alignment: 'AlignLeft | AlignVCenter'; }
#XPadMid { color: #ffffff; font-size: 10px; font-weight: bold; qproperty-alignment: 'AlignCenter'; }
#XPadHpf { color: #4fc3f7; font-size: 10px; font-weight: bold; qproperty-alignment: 'AlignRight | AlignVCenter'; }

#XPadValue {
  color: #ffffff;
  font-size: 12px;
  qproperty-alignment: 'AlignCenter';
}
"""


def step34() -> int:
    deck = SKIN / "deck.xml"
    text = deck.read_text(encoding="utf-8")
    if "DeckBeatJumpContainer" in text:
        text = replace_block(
            text,
            "<ObjectName>DeckBeatJumpContainer</ObjectName>",
            "<WidgetGroup>",
            "</WidgetGroup>",
        )
    if BEATJUMP_ANCHOR in text:
        text = text.replace(BEATJUMP_ANCHOR, BEATJUMP + BEATJUMP_ANCHOR, 1)
        deck.write_text(text, encoding="utf-8")
        print("  deck.xml: BEAT JUMP")
    else:
        print("  ! BEAT JUMP anchor missing")

    be = SKIN / "beffect.xml"
    b = be.read_text(encoding="utf-8")
    if "XPadStrip" in b:
        b = replace_block(
            b, "<ObjectName>XPadStrip</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )
    if XPAD_ANCHOR in b:
        b = b.replace(XPAD_ANCHOR, XPAD + XPAD_ANCHOR, 1)
        be.write_text(b, encoding="utf-8")
        print("  beffect.xml: X-PAD")
    else:
        print("  ! X-PAD anchor missing")

    swap_qss("step 3-4: beat jump and X-PAD", QSS_34)
    return 0 if check_xml("deck.xml", "beffect.xml") else 1


# ---------------------------------------------------------------- step 5

QSS_5 = """

/* Deep navy ground instead of flat black, as on the XZ. */
#Mixxx, WMainMenuBar, #Deck, #Decks {
  background-color: #050b16;
}

#DeckHeader {
  background-color: #0d2444;
  border-bottom: 1px solid #1f4c85;
  padding: 1px 4px;
}

#DeckTitle { color: #cfe4ff; font-weight: bold; }
#DeckTitleNote { color: #2d85cd; }

#TabButtonOverview, #TabButtonBrowse, #TabButtonSampler {
  background-color: #0d1a2e;
  border: 1px solid #1f4c85;
  color: #8fb4e0;
  font-weight: bold;
  padding: 4px 10px;
  margin: 0 1px;
}

#TabButtonOverview[value="1"],
#TabButtonBrowse[value="1"],
#TabButtonSampler[value="1"] {
  background-color: #12518f;
  color: #ffffff;
  border: 1px solid #2d85cd;
}

#BeatFX_Header, #BeatFX_Title {
  background-color: #0d2444;
  color: #cfe4ff;
}

/* Tempo readouts in XZ amber so they separate from the blue chrome. */
#DeckBPM, #RateDisplay1, #RateDisplay2, #RateDisplay3, #RateDisplay4 {
  color: #f5a623;
}
"""


def step5() -> int:
    swap_qss("step 5: XZ colour scheme", QSS_5)
    return 0


# ---------------------------------------------------------------- step 6

TOPBAR_STATUS = """          <WidgetGroup>
            <ObjectName>TopStatus</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,me</SizePolicy>
            <Children>
              <Label>
                <ObjectName>TopStatusLoadLabel</ObjectName>
                <Text>LOAD</Text>
              </Label>
              <Number>
                <ObjectName>TopStatusLoad</ObjectName>
                <TooltipId>audio_latency_usage</TooltipId>
                <Connection>
                  <ConfigKey>[App],audio_latency_usage</ConfigKey>
                </Connection>
              </Number>
              <Time>
                <ObjectName>TopStatusClock</ObjectName>
                <TooltipId>time</TooltipId>
              </Time>
            </Children>
          </WidgetGroup>
"""

# Anchored on the last tab rather than on closing tags: closing-tag indentation
# shifts as the file is edited, tab blocks do not.
TOPBAR_ANCHOR = """          <Template src="skin:tab.xml">
            <SetVariable name="tab_name">Sampler</SetVariable>
            <SetVariable name="config_key">samplers</SetVariable>
          </Template>"""

QSS_6 = """

#TopStatus {
  background-color: #0d1a2e;
  border: 1px solid #1f4c85;
  margin: 4px 6px;
  padding: 2px 8px;
}

#TopStatusLoadLabel {
  color: #8fb4e0;
  font-size: 9px;
  letter-spacing: 1px;
  padding-right: 4px;
  qproperty-alignment: 'AlignVCenter';
}

#TopStatusLoad {
  color: #f5a623;
  font-size: 11px;
  font-weight: bold;
  padding-right: 10px;
  qproperty-alignment: 'AlignVCenter';
}

#TopStatusClock {
  color: #cfe4ff;
  font-size: 13px;
  font-weight: bold;
  qproperty-alignment: 'AlignVCenter';
}
"""


def step6() -> int:
    path = SKIN / "topbar.xml"
    text = path.read_text(encoding="utf-8")
    if "TopStatus" in text:
        text = replace_block(
            text, "<ObjectName>TopStatus</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )
    if TOPBAR_ANCHOR in text:
        # The Topbar is a fixed-height vertical box, so the status block has to
        # sit beside the tabs, not below them.
        text = text.replace(TOPBAR_ANCHOR, TOPBAR_ANCHOR + NL + TOPBAR_STATUS, 1)
        path.write_text(text, encoding="utf-8")
        print("  topbar.xml: status block")
    else:
        print("  ! topbar anchor missing")

    swap_qss("step 6: top bar status", QSS_6)
    return 0 if check_xml("topbar.xml") else 1


# ---------------------------------------------------------------- step 7

# Both Overview and Browse carry their own deck row, differing only in height.
DECKS_ROW_RE = re.compile(
    r"      <WidgetGroup>\s*"
    r"<ObjectName>Decks</ObjectName>\s*"
    r"<Layout>horizontal</Layout>\s*"
    r"<Size>0me,(\d+)max</Size>\s*"
    r"<Children>.*?</Children>\s*"
    r"</WidgetGroup>",
    re.S,
)

QSS_7 = """

#DeckRowTop {
  border-bottom: 1px solid #1f4c85;
}

/* A visible seam between the two cards in each row, as on the XZ. */
#DeckRowTop > #Deck, #DeckRowBottom > #Deck {
  border-right: 1px solid #14304f;
}
"""


def decks_grid(height: int) -> str:
    """Two horizontal rows of two decks inside a vertical box."""

    def tpl(channel: int) -> str:
        return (
            '              <Template src="skin:deck.xml">'
            + NL
            + f'                <SetVariable name="channel">{channel}</SetVariable>'
            + NL
            + "              </Template>"
            + NL
        )

    def row(name: str, left: int, right: int) -> str:
        return (
            "          <WidgetGroup>"
            + NL
            + f"            <ObjectName>{name}</ObjectName>"
            + NL
            + "            <Layout>horizontal</Layout>"
            + NL
            + f"            <Size>0me,{height}max</Size>"
            + NL
            + "            <Children>"
            + NL
            + tpl(left)
            + tpl(right)
            + "            </Children>"
            + NL
            + "          </WidgetGroup>"
            + NL
        )

    return (
        "      <WidgetGroup>"
        + NL
        + "        <ObjectName>Decks</ObjectName>"
        + NL
        + "        <Layout>vertical</Layout>"
        + NL
        + f"        <Size>0me,{height * 2}max</Size>"
        + NL
        + "        <Children>"
        + NL
        + row("DeckRowTop", 1, 2)
        + row("DeckRowBottom", 3, 4)
        + "        </Children>"
        + NL
        + "      </WidgetGroup>"
    )


def step7() -> int:
    for name in ("overview.xml", "library.xml"):
        path = SKIN / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "DeckRowTop" in text:
            print(f"  {name}: 2x2 grid already present")
            continue
        match = DECKS_ROW_RE.search(text)
        if not match:
            print(f"  ! {name}: deck row not matched")
            continue
        height = int(match.group(1))
        text = text[: match.start()] + decks_grid(height) + text[match.end() :]
        path.write_text(text, encoding="utf-8")
        print(f"  {name}: deck strips regrouped 2x2 (rows {height}px)")

    swap_qss("step 7: 2x2 deck grid", QSS_7)
    return 0 if check_xml("overview.xml", "library.xml") else 1


# ---------------------------------------------------------------- step 8

# Q and MASTER are state badges on the XZ track card. Both are plain Mixxx
# controls, so `visible` bindings give the same appear-when-true behaviour the
# ON AIR badge uses.
DECK_BADGES = """              <WidgetGroup>
                <ObjectName>DeckBadges</ObjectName>
                <Layout>horizontal</Layout>
                <SizePolicy>max,max</SizePolicy>
                <Children>
                  <WidgetGroup>
                    <ObjectName>DeckQuantize</ObjectName>
                    <Layout>horizontal</Layout>
                    <SizePolicy>max,max</SizePolicy>
                    <Children>
                      <Label>
                        <ObjectName>DeckQuantizeLabel</ObjectName>
                        <Text>Q</Text>
                      </Label>
                    </Children>
                    <Connection>
                      <ConfigKey>[Channel<Variable name="channel"/>],quantize</ConfigKey>
                      <BindProperty>visible</BindProperty>
                    </Connection>
                  </WidgetGroup>
                  <WidgetGroup>
                    <ObjectName>DeckMaster</ObjectName>
                    <Layout>horizontal</Layout>
                    <SizePolicy>max,max</SizePolicy>
                    <Children>
                      <Label>
                        <ObjectName>DeckMasterLabel</ObjectName>
                        <Text>MASTER</Text>
                      </Label>
                    </Children>
                    <Connection>
                      <ConfigKey>[Channel<Variable name="channel"/>],sync_master</ConfigKey>
                      <BindProperty>visible</BindProperty>
                    </Connection>
                  </WidgetGroup>
                </Children>
              </WidgetGroup>
"""

# ZOOM and GRID sit under the XZ's X-PAD. Mixxx has zoom controls per deck;
# deck 1 stands in for the pair the way the XZ's global buttons do.
ZOOM_GRID = """<WidgetGroup>
    <ObjectName>ZoomGridRow</ObjectName>
    <Layout>horizontal</Layout>
    <Size>0me,26max</Size>
    <Children>
      <PushButton>
        <ObjectName>ZoomButton</ObjectName>
        <Size>0me,24max</Size>
        <NumberStates>2</NumberStates>
        <State>
          <Number>0</Number>
          <Text>ZOOM</Text>
        </State>
        <State>
          <Number>1</Number>
          <Text>ZOOM</Text>
        </State>
        <Connection>
          <ConfigKey>[Pioneered],zoomcycle</ConfigKey>
          <ConnectValueToWidget>false</ConnectValueToWidget>
        </Connection>
      </PushButton>
      <PushButton>
        <ObjectName>GridButton</ObjectName>
        <Size>0me,24max</Size>
        <NumberStates>2</NumberStates>
        <State>
          <Number>0</Number>
          <Text>GRID</Text>
        </State>
        <State>
          <Number>1</Number>
          <Text>GRID</Text>
        </State>
        <Connection>
          <ConfigKey>[Channel1],waveform_zoom_set_default</ConfigKey>
          <ConnectValueToWidget>false</ConnectValueToWidget>
        </Connection>
      </PushButton>
    </Children>
  </WidgetGroup>
"""

QSS_8 = """

#DeckBadges {
  margin: 0 4px;
}

/* Q and MASTER only render when their control is on, like ON AIR. */
#DeckQuantize {
  background-color: #12518f;
  border: 1px solid #2d85cd;
  border-radius: 2px;
  margin-right: 3px;
  max-height: 15px;
}

#DeckQuantizeLabel {
  color: #ffffff;
  font-size: 9px;
  font-weight: bold;
  padding: 1px 5px;
  qproperty-alignment: 'AlignCenter';
}

#DeckMaster {
  background-color: #f5a623;
  border: 1px solid #ffc766;
  border-radius: 2px;
  max-height: 15px;
}

#DeckMasterLabel {
  color: #12202f;
  font-size: 9px;
  font-weight: bold;
  letter-spacing: 1px;
  padding: 1px 5px;
  qproperty-alignment: 'AlignCenter';
}

#ZoomGridRow {
  margin: 4px 2px 2px 2px;
}

#ZoomButton, #GridButton {
  background-color: #0d1a2e;
  border: 1px solid #1f4c85;
  color: #8fb4e0;
  font-size: 10px;
  font-weight: bold;
  margin: 0 2px;
  padding: 3px 0;
}
"""


def step8() -> int:
    deck = SKIN / "deck.xml"
    text = deck.read_text(encoding="utf-8")
    if "DeckBadges" in text:
        text = replace_block(
            text, "<ObjectName>DeckBadges</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )
    # Sit the badges next to the beat-jump box, in the same info row.
    if BEATJUMP_ANCHOR in text:
        text = text.replace(BEATJUMP_ANCHOR, DECK_BADGES + BEATJUMP_ANCHOR, 1)
        deck.write_text(text, encoding="utf-8")
        print("  deck.xml: Q and MASTER badges")
    else:
        print("  ! badge anchor missing")

    be = SKIN / "beffect.xml"
    b = be.read_text(encoding="utf-8")
    if "ZoomGridRow" in b:
        b = replace_block(
            b, "<ObjectName>ZoomGridRow</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )
    if XPAD_ANCHOR in b:
        b = b.replace(XPAD_ANCHOR, ZOOM_GRID + XPAD_ANCHOR, 1)
        be.write_text(b, encoding="utf-8")
        print("  beffect.xml: ZOOM and GRID")
    else:
        print("  ! zoom/grid anchor missing")

    swap_qss("step 8: Q, MASTER, zoom and grid", QSS_8)
    return 0 if check_xml("deck.xml", "beffect.xml") else 1


# ---------------------------------------------------------------- step 9

# The XZ puts the deck badge, title, ON AIR and a large BPM on one row, and
# shows only the remaining time below it. Ours split those across two rows and
# showed elapsed *and* remaining, which is what still read as "not like it".

# Deck badge, boxed, before the title.
DECK_BADGE = """          <WidgetGroup>
            <ObjectName>DeckNumBadge</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckNumBadgeLabel</ObjectName>
                <Text>DECK <Variable name="channel"/></Text>
              </Label>
            </Children>
          </WidgetGroup>
"""

# Large BPM at the right of the title row.
HEADER_BPM = """          <WidgetGroup>
            <ObjectName>DeckHeaderBpm</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckHeaderBpmTitle</ObjectName>
                <Text>BPM</Text>
              </Label>
              <NumberBpm>
                <ObjectName>DeckHeaderBpmValue</ObjectName>
                <TooltipId>visual_bpm</TooltipId>
                <Channel><Variable name="channel"/></Channel>
                <NumberOfDigits>1</NumberOfDigits>
                <!-- Without an explicit Connection the widget renders 0.0:
                     Channel alone does not bind it to a value. -->
                <Connection>
                  <ConfigKey>[Channel<Variable name="channel"/>],visual_bpm</ConfigKey>
                </Connection>
              </NumberBpm>
            </Children>
          </WidgetGroup>
"""

# The header closes right after the title; append the BPM block there.
HEADER_CLOSE = """          </TrackProperty>
        </Children>
      </WidgetGroup>"""

QSS_9 = """

#DeckNumBadge {
  background-color: #1f4c85;
  border: 1px solid #2d85cd;
  border-radius: 2px;
  margin: 2px 6px 2px 2px;
  max-height: 17px;
}

#DeckNumBadgeLabel {
  color: #ffffff;
  font-size: 10px;
  font-weight: bold;
  letter-spacing: 1px;
  padding: 1px 6px;
  qproperty-alignment: 'AlignCenter';
}

#DeckHeaderBpm {
  margin: 0 6px 0 10px;
}

#DeckHeaderBpmTitle {
  color: #8fb4e0;
  font-size: 9px;
  letter-spacing: 1px;
  padding-right: 4px;
  qproperty-alignment: 'AlignBottom | AlignRight';
}

#DeckHeaderBpmValue {
  color: #ffffff;
  font-size: 22px;
  font-weight: bold;
  qproperty-alignment: 'AlignVCenter | AlignRight';
}
"""


def step9() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckNumBadge" in text:
        text = replace_block(
            text, "<ObjectName>DeckNumBadge</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )
    if "DeckHeaderBpm" in text:
        text = replace_block(
            text, "<ObjectName>DeckHeaderBpm</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
        )

    # Badge goes first in the header row, before the note glyph.
    badge_anchor = """          <Label>
            <ObjectName>DeckTitleNote</ObjectName>"""
    if badge_anchor in text:
        text = text.replace(badge_anchor, DECK_BADGE + badge_anchor, 1)
        print("  deck.xml: deck number badge")
    else:
        print("  ! badge anchor missing")

    if HEADER_CLOSE in text:
        text = text.replace(HEADER_CLOSE, "          </TrackProperty>" + NL + HEADER_BPM + "        </Children>" + NL + "      </WidgetGroup>", 1)
        print("  deck.xml: BPM in the title row")
    else:
        print("  ! header close anchor missing")

    path.write_text(text, encoding="utf-8")

    # Show remaining time only, the way the XZ does — clicking the readout then
    # toggles to elapsed. PositionDisplay is a preference value, not a
    # ControlObject, so a skin manifest attribute cannot set it; it has to go
    # into mixxx.cfg, and only while Mixxx is stopped or it gets written back.
    skin_xml = SKIN / "skin.xml"
    s = skin_xml.read_text(encoding="utf-8")
    stale = '\t\t\t<attribute config_key="[Controls],PositionDisplay">1</attribute>' + NL
    if stale in s:
        skin_xml.write_text(s.replace(stale, "", 1), encoding="utf-8")
        print("  skin.xml: removed ineffective PositionDisplay attribute")

    cfg = Path.home() / ".mixxx" / "mixxx.cfg"
    if cfg.is_file():
        c = cfg.read_text(encoding="utf-8")
        if re.search(r"^PositionDisplay ", c, re.M):
            c = re.sub(r"^PositionDisplay .*$", "PositionDisplay 1", c, flags=re.M)
        else:
            c = c.replace("[Controls]", "[Controls]" + NL + "PositionDisplay 1", 1)
        cfg.write_text(c, encoding="utf-8")
        print("  mixxx.cfg: PositionDisplay -> 1 (remaining only)")

    # The old channel/track labels in the info row now duplicate the header
    # badge, so hide them rather than deleting widgets other rules may target.
    swap_qss("step 9: header badge and BPM", QSS_9 + """
/* Superseded by the header badge. */
#DeckChannelTitle, #DeckChannelTitleContainer, #DeckChannelTitleWrapper {
  max-width: 0px;
  max-height: 0px;
  margin: 0px;
  padding: 0px;
}
""")
    return 0 if check_xml("deck.xml", "skin.xml") else 1


# ---------------------------------------------------------------- step 10

# On the XZ the waveform overview sits to the RIGHT of the time readout, on the
# same horizontal band, not in a full-width row below it. Pioneered puts it in
# its own row under DeckInfo. Move it into DeckInfo, between the time and the
# tempo, and let it expand to fill the middle.
BPMRANGE_ANCHOR = """          <WidgetGroup>
            <ObjectName>TrackBPMRangeContainer</ObjectName>"""


def step10() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckOverviewContainer" not in text:
        print("  ! DeckOverviewContainer not found")
        return 0

    # If a previous run already relocated it, the container sits before the BPM
    # range block; nothing to do.
    ov_idx = text.index("DeckOverviewContainer")
    if ov_idx < text.index("TrackBPMRangeContainer"):
        print("  deck.xml: overview already beside the time")
        return 0

    block, text = extract_block(
        text, "<ObjectName>DeckOverviewContainer</ObjectName>", "<WidgetGroup>", "</WidgetGroup>"
    )

    # Make it expand horizontally and shrink to a band height, so it reads like
    # the XZ's inline waveform rather than a full-height panel.
    block = block.replace(
        "<ObjectName>DeckOverviewContainer</ObjectName>",
        "<ObjectName>DeckOverviewContainer</ObjectName>" + NL + "        <SizePolicy>me,me</SizePolicy>",
        1,
    ).replace("<Size>0me,50f</Size>", "<Size>0me,0me</Size>", 1)

    # Re-indent from the Deck-child level (6 spaces) to the DeckInfo-child level
    # (10 spaces) so it nests correctly inside the info row.
    block = NL.join(("    " + ln if ln.strip() else ln) for ln in block.split(NL))

    if BPMRANGE_ANCHOR in text:
        text = text.replace(BPMRANGE_ANCHOR, block + NL + BPMRANGE_ANCHOR, 1)
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: waveform moved beside the time")
    else:
        print("  ! BPM range anchor missing; overview left in place")
        return 1

    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 11

# The XZ labels the time with two words, REMAIN and TIME, and lights whichever
# mode is active. Replace the single static label with two toggle buttons on
# [Controls],PositionDisplay (1 = remaining, 0 = elapsed): clicking either
# flips the mode, and each lights when its mode is showing.
TIME_TITLE_OLD = """                <ObjectName>DeckTrackTimeTitle</ObjectName>
                <Text>REMAIN / TIME</Text>
                <Size>200me,25f</Size>"""

# One button for the whole label: clicking it flips PositionDisplay between
# remaining (1) and elapsed (0). NumberStates 2 makes a press toggle.
TIME_TITLE_NEW = """                <ObjectName>DeckTrackTimeTitle</ObjectName>
                <Size>200me,25f</Size>
                <Layout>horizontal</Layout>
                <Children>
                  <PushButton>
                    <ObjectName>TimeModeToggle</ObjectName>
                    <Size>180f,18f</Size>
                    <NumberStates>2</NumberStates>
                    <State><Number>0</Number><Text>REMAIN / TIME</Text></State>
                    <State><Number>1</Number><Text>REMAIN / TIME</Text></State>
                    <Connection>
                      <ConfigKey>[Controls],PositionDisplay</ConfigKey>
                      <ConnectValueToWidget>false</ConnectValueToWidget>
                    </Connection>
                  </PushButton>
                </Children>"""

QSS_11 = """

/* The whole label is one toggle button; clicking it flips remain/elapsed. */
#DeckTrackTimeTitle { qproperty-layoutAlignment: 'AlignLeft | AlignVCenter'; }

#TimeModeToggle {
  background-color: transparent;
  border: 0;
  color: #8fa4b8;
  font-size: 10px;
  font-weight: bold;
  letter-spacing: 1px;
  padding: 0 2px;
  qproperty-alignment: 'AlignLeft | AlignVCenter';
}

/* Let the waveform take the middle without shoving the tempo column off the
   card: cap the time column, and let the overview simply fill what remains
   rather than demand a fixed minimum that overflows a half-width deck. */
#TrackTimeContainer { max-width: 210px; }
#DeckOverviewContainer { margin: 0 4px; }
"""


def step11() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "TimeModeToggle" in text:
        print("  deck.xml: time toggle button already present")
    elif TIME_TITLE_OLD in text:
        text = text.replace(TIME_TITLE_OLD, TIME_TITLE_NEW, 1)
        # The title element is a <Label>, which ignores <Children>; the button
        # only renders once the wrapper becomes a <WidgetGroup>. Retag just this
        # element by rewriting the opening/closing tags around our marker.
        marker = "<ObjectName>DeckTrackTimeTitle</ObjectName>"
        open_at = text.rindex("<Label>", 0, text.index(marker))
        text = text[:open_at] + "<WidgetGroup>" + text[open_at + len("<Label>"):]
        close_at = text.index("</Label>", text.index(marker))
        text = text[:close_at] + "</WidgetGroup>" + text[close_at + len("</Label>"):]
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: REMAIN / TIME is one toggle button")
    else:
        print("  ! time title block not matched")

    # Drop sub-second precision: the XZ shows mm:ss, not tenths. TimeFormat 1
    # is "Traditional (Coarse)" in Mixxx 2.5. Preference value, so it goes in
    # mixxx.cfg, not the skin.
    cfg = Path.home() / ".mixxx" / "mixxx.cfg"
    if cfg.is_file():
        c = cfg.read_text(encoding="utf-8")
        if re.search(r"^TimeFormat ", c, re.M):
            c = re.sub(r"^TimeFormat .*$", "TimeFormat 1", c, flags=re.M)
        else:
            c = c.replace("[Controls]", "[Controls]" + NL + "TimeFormat 1", 1)
        cfg.write_text(c, encoding="utf-8")
        print("  mixxx.cfg: TimeFormat -> 1 (mm:ss, no tenths)")

    swap_qss("step 11: time toggle and wide waveform", QSS_11)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 12

# On the XZ the time is the leftmost thing on the info row: REMAIN / TIME and
# the big mm:ss sit flush against the card edge, with the waveform starting
# immediately to their right. Pioneered puts the deck-name / track-number
# column, the beat jump box and the Q/MASTER badges in front of them. Move the
# time block to the head of DeckInfo and push that trio to the right of the
# waveform, so time and waveform end up adjacent and hard left.
TIME_LEFT_QSS = """

/* Time hugs the card edge like the XZ: no leading column, no left inset, and
   a column only as wide as six digits so the waveform starts right after it.
   Do not go below ~170px: DeckTrackTime carries MinimumSize 150 and the
   SizeAwareStack renders nothing at all once neither child fits. */
#TrackTimeContainer {
  max-width: 152px;
  margin-left: 0;
  padding-left: 0;
}

/* WPushButton is a QAbstractButton, which has no alignment property, so the
   qproperty-alignment from step 11 is silently dropped and the label centres
   itself in the button. text-align is the QPushButton way that works. */
#TimeModeToggle {
  text-align: left;
  padding-left: 0;
}

#DeckInfo { padding-left: 0; }

#DeckTrackTimeTitle,
#DeckTrackTimeWrapper {
  qproperty-layoutAlignment: 'AlignLeft | AlignVCenter';
  margin-left: 0;
  padding-left: 0;
}
"""


def step_time_left() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckTrackNumberContainer" not in text:
        # Step 17 removes that column; nothing left to reorder, but the styling
        # below still has to be written.
        swap_qss("step 12: time flush left", TIME_LEFT_QSS)
        return 0 if check_xml("deck.xml") else 1

    if text.index("TrackTimeContainer") < text.index("DeckTrackNumberContainer"):
        print("  deck.xml: time already at the left edge")
    else:
        time_block, text = extract_group(text, "<ObjectName>TrackTimeContainer</ObjectName>")
        anchor = text.rindex("<WidgetGroup>", 0, text.index("<ObjectName>DeckTrackNumberContainer</ObjectName>"))
        text = text[:anchor] + time_block + NL + "          " + text[anchor:]

        # Everything that used to sit left of the time goes right of the
        # waveform, in its original order.
        moved = []
        for name in ("DeckTrackNumberContainer", "DeckBeatJumpContainer", "DeckBadges"):
            block, text = extract_group(text, f"<ObjectName>{name}</ObjectName>")
            moved.append(block)

        # Find where the overview group ends, and drop the trio in after it.
        ov_block, _ = extract_group(text, "<ObjectName>DeckOverviewContainer</ObjectName>")
        ov_end = text.index(ov_block) + len(ov_block)
        indent = NL + "          "
        text = text[:ov_end] + indent + indent.join(moved) + text[ov_end:]

        path.write_text(text, encoding="utf-8")
        print("  deck.xml: time moved to the left edge, waveform beside it")

    swap_qss("step 12: time flush left", TIME_LEFT_QSS)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 13

# Two separate mistakes kept the time three-state.
#
# 1. [Controls],PositionDisplay is a *config file key*, written by the deck
#    preferences page (dlgprefdeck.cpp:625). The live ControlObject is
#    [Controls],ShowDurationRemaining (dlgprefdeck.cpp:34). Binding a skin
#    widget to PositionDisplay silently creates a dummy control that nothing
#    reads, so the REMAIN / TIME button did nothing at all.
#
# 2. The three-way cycle is not in the control, it is hard-coded in
#    WNumberPos::mousePressEvent (wnumberpos.cpp:33-49): elapsed -> remaining
#    -> both -> elapsed. Clicking the number always walks all three, whatever
#    the skin says. There is no skin attribute to change that.
#
# A skin widget cannot do the clamping either: WPushButton only toggles when
# its control is a ControlPushButton (wpushbutton.cpp:143). ShowDurationRemaining
# is a plain ControlObject, so the button falls back to PUSH mode and emits 1 on
# press and 0 on release, which lands on elapsed every time. So step 11's toggle
# button is dead weight; put the plain label back and let Time-Clamp.midi.xml do
# the work in script.
TIME_TITLE_BUTTON = """                <ObjectName>DeckTrackTimeTitle</ObjectName>
                <Size>200me,25f</Size>
                <Layout>horizontal</Layout>
                <Children>
                  <PushButton>
                    <ObjectName>TimeModeToggle</ObjectName>
                    <Size>180f,18f</Size>
                    <NumberStates>2</NumberStates>
                    <State><Number>0</Number><Text>REMAIN / TIME</Text></State>
                    <State><Number>1</Number><Text>REMAIN / TIME</Text></State>
                    <Connection>
                      <ConfigKey>[Controls],ShowDurationRemaining</ConfigKey>
                      <ConnectValueToWidget>false</ConnectValueToWidget>
                    </Connection>
                  </PushButton>
                </Children>"""

TIME_TITLE_PLAIN = """                <ObjectName>DeckTrackTimeTitle</ObjectName>
                <Text>REMAIN / TIME</Text>
                <Size>200me,25f</Size>"""


def step_time_two_state() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "[Controls],PositionDisplay" in text:
        text = text.replace("[Controls],PositionDisplay", "[Controls],ShowDurationRemaining")
        print("  deck.xml: connections repointed to the real control")

    if "TimeModeCover" in text:
        text = replace_block(text, "<ObjectName>TimeModeCover</ObjectName>", "<PushButton>", "</PushButton>")
        text = text.replace("<Layout>stacked</Layout>", "<Layout>horizontal</Layout>", 1)
        print("  deck.xml: dead cover button removed")

    if TIME_TITLE_BUTTON in text:
        text = text.replace(TIME_TITLE_BUTTON, TIME_TITLE_PLAIN, 1)
        marker = "<ObjectName>DeckTrackTimeTitle</ObjectName>"
        open_at = text.rindex("<WidgetGroup>", 0, text.index(marker))
        text = text[:open_at] + "<Label>" + text[open_at + len("<WidgetGroup>"):]
        close_at = text.index("</WidgetGroup>", text.index(marker))
        text = text[:close_at] + "</Label>" + text[close_at + len("</WidgetGroup>"):]
        print("  deck.xml: REMAIN / TIME back to a plain label")

    path.write_text(text, encoding="utf-8")
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 14

# Amber digits, and REMAIN / TIME split into two labels so the active one lights
# up. Reading a plain ControlObject into a widget property works fine; only
# writing to one from a WPushButton does not.
TIME_TITLE_SPLIT = """              <WidgetGroup>
                <ObjectName>DeckTrackTimeTitle</ObjectName>
                <Size>200me,19f</Size>
                <Layout>horizontal</Layout>
                <Children>
                  <Label>
                    <ObjectName>TimeLabelRemain</ObjectName>
                    <Text>REMAIN</Text>
                    <Connection>
                      <ConfigKey>[Controls],ShowDurationRemaining</ConfigKey>
                      <Transform><IsEqual>1</IsEqual></Transform>
                      <BindProperty>highlight</BindProperty>
                    </Connection>
                  </Label>
                  <Label>
                    <ObjectName>TimeLabelSlash</ObjectName>
                    <Text>/</Text>
                  </Label>
                  <Label>
                    <ObjectName>TimeLabelTime</ObjectName>
                    <Text>TIME</Text>
                    <Connection>
                      <ConfigKey>[Controls],ShowDurationRemaining</ConfigKey>
                      <Transform><IsEqual>0</IsEqual></Transform>
                      <BindProperty>highlight</BindProperty>
                    </Connection>
                  </Label>
                  <Label>
                    <ObjectName>TimeLabelFill</ObjectName>
                    <Size>0me,0me</Size>
                  </Label>
                </Children>
              </WidgetGroup>"""

QSS_14 = """

/* REMAIN and TIME are separate labels so the active mode can light up. */
#DeckTrackTimeTitle {
  qproperty-layoutAlignment: 'AlignLeft | AlignBottom';
  margin: 0;
  padding: 0;
}

#TimeLabelRemain,
#TimeLabelSlash,
#TimeLabelTime {
  background-color: transparent;
  color: #4f6b85;
  font-size: 16px;
  font-weight: bold;
  letter-spacing: 0px;
  padding: 0 1px 0 0;
  qproperty-alignment: 'AlignLeft | AlignBottom';
}

#TimeLabelRemain[highlight="1"],
#TimeLabelTime[highlight="1"] {
  color: #ffffff;
}

#DeckTrackTime {
  color: #ffffff;
  font-size: 45px;
}

#DeckTrackTimeMini {
  color: #ffffff;
  font-size: 26px;
}
"""


def step_time_amber() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "TimeLabelRemain" in text:
        print("  deck.xml: split time label already present")
    elif TIME_TITLE_PLAIN in text:
        marker = "<ObjectName>DeckTrackTimeTitle</ObjectName>"
        open_at = text.rindex("<Label>", 0, text.index(marker))
        close_at = text.index("</Label>", text.index(marker)) + len("</Label>")
        text = text[:open_at].rstrip(" ") + TIME_TITLE_SPLIT.lstrip() + text[close_at:]
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: REMAIN and TIME split into lit labels")
    else:
        print("  ! plain time title not matched")
        return 1

    swap_qss("step 14: amber time", QSS_14)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 15

# The XZ deck badge is a filled square in the channel colour, DECK in small caps
# over a large number, and the title sits on a grey band next to it. ObjectName
# takes the channel variable, which is what lets one QSS block colour each deck
# differently.
BADGE_OLD = """            <ObjectName>DeckNumBadge</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckNumBadgeLabel</ObjectName>
                <Text>DECK <Variable name="channel"/></Text>
              </Label>
            </Children>"""

BADGE_NEW = """            <ObjectName>DeckNumBadge<Variable name="channel"/></ObjectName>
            <Layout>vertical</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckNumBadgeWord</ObjectName>
                <Text>DECK</Text>
              </Label>
              <Label>
                <ObjectName>DeckNumBadgeNum</ObjectName>
                <Text><Variable name="channel"/></Text>
              </Label>
            </Children>"""

QSS_15 = """

/* Filled channel-colour badge, DECK over the number, XZ style. */
#DeckNumBadge1, #DeckNumBadge2, #DeckNumBadge3, #DeckNumBadge4 {
  border: 0;
  border-radius: 0;
  margin: 0 6px 0 0;
  min-width: 34px;
  padding: 1px 0 2px 0;
}

#DeckNumBadge1 { background-color: #2d85cd; }
#DeckNumBadge2 { background-color: #d73535; }
#DeckNumBadge3 { background-color: #e9e9e9; }
#DeckNumBadge4 { background-color: #3fa93f; }

#DeckNumBadgeWord {
  font-size: 8px;
  font-weight: bold;
  letter-spacing: 1px;
  qproperty-alignment: 'AlignCenter';
}

#DeckNumBadgeNum {
  font-size: 17px;
  font-weight: bold;
  qproperty-alignment: 'AlignCenter';
}

#DeckNumBadge1 #DeckNumBadgeWord, #DeckNumBadge1 #DeckNumBadgeNum,
#DeckNumBadge3 #DeckNumBadgeWord, #DeckNumBadge3 #DeckNumBadgeNum,
#DeckNumBadge4 #DeckNumBadgeWord, #DeckNumBadge4 #DeckNumBadgeNum {
  color: #10222f;
}

#DeckNumBadge2 #DeckNumBadgeWord, #DeckNumBadge2 #DeckNumBadgeNum {
  color: #ffffff;
}

/* Title band: neutral grey, bold white track name. */
#DeckHeader {
  background-color: #35383c;
  border-bottom: 0;
  padding: 0;
}

#DeckTitle {
  color: #ffffff;
  font-weight: bold;
  font-size: 17px;
}

#DeckTitleNote { color: #ffffff; }
"""


def step_deck_badge() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckNumBadgeWord" in text:
        print("  deck.xml: two-line deck badge already present")
    elif BADGE_OLD in text:
        text = text.replace(BADGE_OLD, BADGE_NEW, 1)
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: deck badge is DECK over the number")
    else:
        print("  ! deck badge block not matched")
        return 1

    swap_qss("step 15: channel-colour deck badge", QSS_15)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 16

# Right side of the XZ card: a white-outlined BPM box, and under it one panel
# holding Q on the left, the pitch range on the right and the rate percent
# below. The separate TEMPO column and the standalone badge row both fold into
# it, so the card ends at the same width it had before.
HEADER_BPM_OLD = """            <ObjectName>DeckHeaderBpm</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckHeaderBpmTitle</ObjectName>
                <Text>BPM</Text>
              </Label>"""

HEADER_BPM_NEW = """            <ObjectName>DeckHeaderBpm</ObjectName>
            <Layout>vertical</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <Label>
                <ObjectName>DeckHeaderBpmTitle</ObjectName>
                <Text>BPM</Text>
              </Label>"""

TEMPO_PANEL = """          <WidgetGroup>
            <ObjectName>DeckTempoPanel</ObjectName>
            <Layout>vertical</Layout>
            <Size>112max,0me</Size>
            <Children>
              <WidgetGroup>
                <ObjectName>DeckTempoRow</ObjectName>
                <Layout>horizontal</Layout>
                <Size>0me,30f</Size>
                <Children>
                  <Label>
                    <ObjectName>DeckQuantizeLabel</ObjectName>
                    <Text>Q</Text>
                    <Connection>
                      <ConfigKey>[Channel<Variable name="channel"/>],quantize</ConfigKey>
                      <BindProperty>visible</BindProperty>
                    </Connection>
                  </Label>
                  <Label>
                    <ObjectName>DeckTempoRowFill</ObjectName>
                    <Size>0me,0me</Size>
                  </Label>
                  <Label>
                    <ObjectName>BPMRangePlusMinus</ObjectName>
                    <Text>&#177;</Text>
                  </Label>
                  <RateRange>
                    <ObjectName>RateDisplay</ObjectName>
                    <TooltipId>rate_range_display</TooltipId>
                    <Channel><Variable name="channel"/></Channel>
                    <Display>range</Display>
                  </RateRange>
                </Children>
              </WidgetGroup>
              <WidgetGroup>
                <ObjectName>DeckTempoPercentRow</ObjectName>
                <Layout>horizontal</Layout>
                <Size>0me,32f</Size>
                <Children>
                  <Label>
                    <ObjectName>DeckTempoPercentFill</ObjectName>
                    <Size>0me,0me</Size>
                  </Label>
                  <NumberRate>
                    <ObjectName>DeckTempoPercent</ObjectName>
                    <TooltipId>rate_display</TooltipId>
                    <Channel><Variable name="channel"/></Channel>
                    <NumberOfDigits>2</NumberOfDigits>
                  </NumberRate>
                  <Label>
                    <ObjectName>BPMPercent</ObjectName>
                    <Text>%</Text>
                  </Label>
                </Children>
              </WidgetGroup>
              <WidgetGroup>
                <ObjectName>DeckMaster</ObjectName>
                <Layout>horizontal</Layout>
                <SizePolicy>max,max</SizePolicy>
                <Children>
                  <Label>
                    <ObjectName>DeckMasterLabel</ObjectName>
                    <Text>MASTER</Text>
                  </Label>
                </Children>
                <Connection>
                  <ConfigKey>[Channel<Variable name="channel"/>],sync_master</ConfigKey>
                  <BindProperty>visible</BindProperty>
                </Connection>
              </WidgetGroup>
            </Children>
          </WidgetGroup>"""

QSS_16 = """

/* BPM reads out of a white-outlined box, small BPM over big digits. */
#DeckHeaderBpm {
  background-color: #000000;
  border: 2px solid #ffffff;
  margin: 1px 2px;
  min-width: 108px;
  padding: 0 4px 2px 4px;
}

#DeckHeaderBpmTitle {
  color: #ffffff;
  font-size: 11px;
  font-weight: bold;
  letter-spacing: 1px;
  qproperty-alignment: 'AlignLeft | AlignTop';
}

#DeckHeaderBpmValue {
  color: #ffffff;
  font-size: 30px;
  font-weight: bold;
  qproperty-alignment: 'AlignRight | AlignBottom';
}

/* Q, pitch range and rate percent share one panel under the BPM box. */
#DeckTempoPanel {
  background-color: #2b2f33;
  margin: 0 2px;
  padding: 2px 5px;
}

#DeckQuantizeLabel {
  background-color: transparent;
  border: 0;
  color: #e08b2a;
  font-size: 23px;
  font-weight: bold;
  padding: 0;
  qproperty-alignment: 'AlignLeft | AlignVCenter';
}

#BPMRangePlusMinus, #RateDisplay {
  background-color: transparent;
  color: #6ee04a;
  font-size: 23px;
  font-weight: bold;
}

#DeckTempoPercent, #BPMPercent {
  background-color: transparent;
  color: #ffffff;
  font-size: 21px;
  font-weight: bold;
}

#DeckMasterLabel {
  color: #e08b2a;
  font-size: 9px;
  font-weight: bold;
  letter-spacing: 1px;
}
"""


def step_tempo_panel() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckTempoPanel" in text:
        print("  deck.xml: tempo panel already present")
    else:
        if HEADER_BPM_OLD not in text:
            print("  ! header BPM block not matched")
            return 1
        text = text.replace(HEADER_BPM_OLD, HEADER_BPM_NEW, 1)

        # The old badge row, range column and tempo column all fold into the
        # new panel, so drop them and put the panel where the range column was.
        for name in ("DeckBadges", "TrackBPMContainer"):
            if f"<ObjectName>{name}</ObjectName>" in text:
                _, text = extract_group(text, f"<ObjectName>{name}</ObjectName>")

        _, text = extract_group(text, "<ObjectName>TrackBPMRangeContainer</ObjectName>")

        # Insert the panel as the last child of DeckInfo.
        info_block, _ = extract_group(text, "<ObjectName>DeckInfo</ObjectName>")
        info_end = text.index(info_block) + info_block.rindex("</Children>")
        text = text[:info_end] + TEMPO_PANEL + NL + "        " + text[info_end:]
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: BPM box plus Q / range / percent panel")

    swap_qss("step 16: BPM box and tempo panel", QSS_16)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 17

# Match the sidebar next to each waveform row: source line, KEY caption with the
# key, BEAT JUMP with its size, and a channel-colour deck number under ON AIR.
# BEAT JUMP lives there on the XZ, not on the deck card, so drop the card copy
# along with the leftover Deck/Track column.
WAVE_HEADER_OLD = """          <WidgetGroup>
            <ObjectName>WaveformInfo_Header</ObjectName>
            <Layout>horizontal</Layout>
            <Size>0me,30max</Size>
            <Children>
              <Label>
                <ObjectName>WaveformInfo_Title</ObjectName>
                <Text>Deck&#160;<Variable name="channel"/></Text>
              </Label>
            </Children>
            <Connection>
              <ConfigKey>[Channel<Variable name="channel"/>],play</ConfigKey>
              <BindProperty>highlight</BindProperty>
            </Connection>
          </WidgetGroup>"""

WAVE_HEADER_NEW = """          <WidgetGroup>
            <ObjectName>WaveformInfo_Header</ObjectName>
            <Layout>horizontal</Layout>
            <Size>0me,30max</Size>
            <Children>
              <Label>
                <ObjectName>WaveformInfoSource</ObjectName>
                <Text>USB1</Text>
              </Label>
              <WidgetGroup>
                <ObjectName>WaveformOnAir</ObjectName>
                <Layout>horizontal</Layout>
                <SizePolicy>max,max</SizePolicy>
                <Children>
                  <Label>
                    <ObjectName>WaveformOnAirLabel</ObjectName>
                    <Text>ON AIR</Text>
                  </Label>
                </Children>
                <Connection>
                  <ConfigKey>[Channel<Variable name="channel"/>],play_indicator</ConfigKey>
                  <BindProperty>visible</BindProperty>
                </Connection>
              </WidgetGroup>
              <Label>
                <ObjectName>WaveformDeckNum<Variable name="channel"/></ObjectName>
                <Text><Variable name="channel"/></Text>
              </Label>
            </Children>
          </WidgetGroup>"""

WAVE_KEY_OLD = """                  <Label>
                    <ObjectName>WaveformInfo_Key_Icon</ObjectName>
                    <Text>&#9837;&#9839;</Text>
                    <Style>color: black;</Style>
                  </Label>"""

WAVE_KEY_NEW = """                  <Label>
                    <ObjectName>WaveformInfoCaption</ObjectName>
                    <Text>KEY</Text>
                  </Label>"""

QUANTIZE_VISIBLE = """                    <Connection>
                      <ConfigKey>[Channel<Variable name="channel"/>],quantize</ConfigKey>
                      <BindProperty>visible</BindProperty>
                    </Connection>"""

QUANTIZE_HIGHLIGHT = """                    <Connection>
                      <ConfigKey>[Channel<Variable name="channel"/>],quantize</ConfigKey>
                      <BindProperty>highlight</BindProperty>
                    </Connection>"""

QSS_17 = """

/* Waveform sidebar: source, KEY, BEAT JUMP, deck number in channel colour. */
#WaveformInfo { background-color: #0a0f1a; }

#WaveformInfoSource {
  color: #ffffff;
  font-size: 13px;
  font-weight: bold;
  padding-left: 3px;
  qproperty-alignment: 'AlignLeft | AlignVCenter';
}

#WaveformInfoCaption {
  color: #8fa4b8;
  font-size: 9px;
  font-weight: bold;
  letter-spacing: 1px;
  max-width: 46px;
  padding-left: 3px;
  qproperty-alignment: 'AlignLeft | AlignVCenter';
}

#WaveformOnAirLabel {
  background-color: #d32020;
  color: #ffffff;
  font-size: 8px;
  font-weight: bold;
  padding: 1px 3px;
}

#WaveformDeckNum1, #WaveformDeckNum2, #WaveformDeckNum3, #WaveformDeckNum4 {
  color: #10222f;
  font-size: 18px;
  font-weight: bold;
  margin: 0 0 0 4px;
  min-width: 22px;
  qproperty-alignment: 'AlignCenter';
}

#WaveformDeckNum1 { background-color: #2d85cd; }
#WaveformDeckNum2 { background-color: #d73535; color: #ffffff; }
#WaveformDeckNum3 { background-color: #e9e9e9; }
#WaveformDeckNum4 { background-color: #3fa93f; }

/* Q always sits in the panel and lights when quantize is on. */
#DeckQuantizeLabel { color: #4a5a68; }
#DeckQuantizeLabel[highlight="1"] { color: #e08b2a; }
"""


def step_waveform_sidebar() -> int:
    wave = SKIN / "waveform.xml"
    text = wave.read_text(encoding="utf-8")

    if "WaveformDeckNum" in text:
        print("  waveform.xml: sidebar already rebuilt")
    else:
        for old, new, what in (
            (WAVE_HEADER_OLD, WAVE_HEADER_NEW, "deck number and ON AIR"),
            (WAVE_KEY_OLD, WAVE_KEY_NEW, "KEY caption"),
        ):
            if old not in text:
                print(f"  ! waveform.xml: {what} anchor missing")
                return 1
            text = text.replace(old, new, 1)
        text = text.replace("<Size>100f,0me</Size>", "<Size>132f,0me</Size>", 1)
        wave.write_text(text, encoding="utf-8")
        print("  waveform.xml: sidebar rebuilt")

    deck = SKIN / "deck.xml"
    dtext = deck.read_text(encoding="utf-8")

    for name in ("DeckTrackNumberContainer", "DeckBeatJumpContainer"):
        if f"<ObjectName>{name}</ObjectName>" in dtext:
            _, dtext = extract_group(dtext, f"<ObjectName>{name}</ObjectName>")
            print(f"  deck.xml: {name} removed from the card")

    if QUANTIZE_VISIBLE in dtext:
        dtext = dtext.replace(QUANTIZE_VISIBLE, QUANTIZE_HIGHLIGHT, 1)
        print("  deck.xml: Q always shown, lit when quantize is on")

    deck.write_text(dtext, encoding="utf-8")
    swap_qss("step 17: waveform sidebar", QSS_17)
    return 0 if check_xml("deck.xml", "waveform.xml") else 1


# ---------------------------------------------------------------- step 18

# XZ card overview: blue body, yellow-to-white peaks. The overview is already in
# RGB mode (mixxx.cfg WaveformOverviewType 2), so the three signal colours are
# what draw it. Also lock the BPM box and the panel under it to one width so
# they read as a single block.
OVERVIEW_COLORS_OLD = """                <SignalColor>#222</SignalColor>
                <SignalLowColor>#007de1</SignalLowColor>
                <SignalMidColor>#007de1</SignalMidColor>
                <SignalHighColor>#007de1</SignalHighColor>"""

# Clipped to the upper lobe, the centre line sits at the bottom of the strip, so
# the inner band (highs) lands on the baseline and the outer band (lows) on top.
# The XZ stacks it the other way round, so swap the two colours: blue mass on the
# baseline, yellow and white peaks above it.
OVERVIEW_COLORS_NEW = """                <SignalColor>#1d6fe0</SignalColor>
                <SignalLowColor>#ffffff</SignalLowColor>
                <SignalMidColor>#f2d13c</SignalMidColor>
                <SignalHighColor>#1d6fe0</SignalHighColor>"""

QSS_18 = """

/* BPM box and tempo panel are one block: same width, same margins. */
#DeckHeaderBpm {
  margin: 1px 3px 0 3px;
  max-width: 126px;
  min-width: 126px;
}

#DeckTempoPanel {
  margin: 0 3px;
  max-width: 126px;
  min-width: 126px;
  padding: 4px 6px;
}

/* Thin black gutter between the four cards, as on the XZ. */
#Deck {
  border-bottom: 2px solid #000000;
  border-right: 2px solid #000000;
}
"""


VISUAL_COLORS_OLD = """        <SignalColor>#32323c</SignalColor>
        <SignalLowColor>#004ee4</SignalLowColor>
        <SignalMidColor>#c95a00</SignalMidColor>
        <SignalHighColor>#f6e9d3</SignalHighColor>"""

VISUAL_COLORS_NEW = """        <SignalColor>#1d6fe0</SignalColor>
        <SignalLowColor>#1d6fe0</SignalLowColor>
        <SignalMidColor>#f2d13c</SignalMidColor>
        <SignalHighColor>#ffffff</SignalHighColor>"""


def step_overview_colors() -> int:
    wave = SKIN / "waveform.xml"
    wtext = wave.read_text(encoding="utf-8")
    if VISUAL_COLORS_OLD in wtext:
        wave.write_text(wtext.replace(VISUAL_COLORS_OLD, VISUAL_COLORS_NEW, 1), encoding="utf-8")
        print("  waveform.xml: scrolling waveform matches the overview")

    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if OVERVIEW_COLORS_NEW in text:
        print("  deck.xml: overview colours already set")
    elif OVERVIEW_COLORS_OLD in text:
        text = text.replace(OVERVIEW_COLORS_OLD, OVERVIEW_COLORS_NEW, 1)
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: overview is blue with yellow peaks")
    else:
        print("  ! overview colour block not matched")
        return 1

    swap_qss("step 18: overview colours and equal block width", QSS_18)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 19

# ON AIR belongs at the right end of the title band, next to the BPM box, not
# in front of the track name.
def step_onair_right() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    onair = text.index("<ObjectName>DeckOnAir</ObjectName>")
    title = text.index("<ObjectName>DeckTitle</ObjectName>")
    if onair > title:
        print("  deck.xml: ON AIR already after the title")
        return 0

    block, text = extract_group(text, "<ObjectName>DeckOnAir</ObjectName>")
    # Land it between the title and the BPM box.
    anchor = text.rindex("<WidgetGroup>", 0, text.index("<ObjectName>DeckHeaderBpm</ObjectName>"))
    text = text[:anchor] + block + NL + "          " + text[anchor:]
    path.write_text(text, encoding="utf-8")
    print("  deck.xml: ON AIR moved next to the BPM box")
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 20

# WOverview always renders symmetrically around its centre line and has no
# one-sided mode. Clip it instead: make the widget twice the height of its
# container and cap the container, so the layout cannot shrink the child and Qt
# clips the lower lobe. What is left is a waveform standing on a baseline.
QSS_20 = """

/* Only the upper lobe of the overview is visible; the rest is clipped. */
#DeckOverviewContainer {
  max-height: 94px;
  min-height: 94px;
}
"""


def step_single_sided() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    marker = "<ObjectName>DeckOverview</ObjectName>"
    idx = text.index(marker)
    end = text.index("</Overview>", idx)
    block = text[idx:end]

    if "<Size>0me,188f</Size>" in block:
        print("  deck.xml: overview already clipped to one lobe")
    else:
        new = re.sub(r"<Size>[^<]*</Size>", "<Size>0me,188f</Size>", block, count=1)
        if new == block:
            print("  ! overview Size tag not found")
            return 1
        text = text[:idx] + new + text[end:]
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: overview twice the container height")

    swap_qss("step 20: one-sided overview", QSS_20)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 21

# Fill the leftovers: the EQ row at the bottom of the FX column stopped at a
# fixed height and left a gap, and the deck rows were shorter than the cards on
# the XZ, which pushed empty canvas into the waveform area.
EQ_ROW_OLD = """<WidgetGroup>
    <Layout>horizontal</Layout>
     <Children>
<PushButton>
        <ObjectName>LOW</ObjectName>"""

EQ_ROW_NEW = """<WidgetGroup>
    <Layout>horizontal</Layout>
    <Size>0me,0me</Size>
     <Children>
<PushButton>
        <ObjectName>LOW</ObjectName>"""


def step_fill_gaps() -> int:
    fx = SKIN / "beffect.xml"
    ftext = fx.read_text(encoding="utf-8")
    if EQ_ROW_NEW in ftext:
        print("  beffect.xml: EQ row already stretches")
    elif EQ_ROW_OLD in ftext:
        ftext = ftext.replace(EQ_ROW_OLD, EQ_ROW_NEW, 1)
        ftext = ftext.replace("""        <ObjectName>LOW</ObjectName>
        <Size>0me,50max</Size>""", """        <ObjectName>LOW</ObjectName>
        <Size>0me,0me</Size>""", 1)
        ftext = ftext.replace("""        <ObjectName>MID</ObjectName>
        <Size>0me,50max</Size>""", """        <ObjectName>MID</ObjectName>
        <Size>0me,0me</Size>""", 1)
        ftext = ftext.replace("""        <ObjectName>HI</ObjectName>
        <Size>0me,50max</Size>""", """        <ObjectName>HI</ObjectName>
        <Size>0me,0me</Size>""", 1)
        fx.write_text(ftext, encoding="utf-8")
        print("  beffect.xml: EQ row fills the bottom of the FX column")
    else:
        print("  ! EQ row anchor missing")

    # Only the overview page: on Browse the cards are header-only (DeckInfo is
    # bound to [Tab],overview), so a taller row there is just an empty band.
    path = SKIN / "overview.xml"
    text = path.read_text(encoding="utf-8")
    new_text = text.replace("<Size>0me,300max</Size>", "<Size>0me,280max</Size>")
    new_text = new_text.replace("<Size>0me,150max</Size>", "<Size>0me,140max</Size>")
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print("  overview.xml: deck rows raised to 180px")
    else:
        print("  overview.xml: deck rows already raised")

    return 0 if check_xml("beffect.xml", "overview.xml") else 1


# ---------------------------------------------------------------- step 22

# On Browse the card is header-only, so put a compact time next to the BPM box.
# Visible only off the overview page: bound to [Tab],overview through a Not
# transform, so it never doubles the big time on the overview cards.
HEADER_TIME = """          <WidgetGroup>
            <ObjectName>HeaderTime</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,max</SizePolicy>
            <Children>
              <NumberPos>
                <ObjectName>HeaderTimeValue</ObjectName>
                <TooltipId>track_time</TooltipId>
                <NumberOfDigits>6</NumberOfDigits>
                <Channel><Variable name="channel"/></Channel>
              </NumberPos>
            </Children>
            <Connection>
              <ConfigKey>[Tab],overview</ConfigKey>
              <Transform><Not/></Transform>
              <BindProperty>visible</BindProperty>
            </Connection>
          </WidgetGroup>
"""

QSS_22 = """

/* Compact time in the header, Browse and Sampler pages only. */
#HeaderTimeValue {
  background-color: transparent;
  color: #ffffff;
  font-size: 24px;
  font-weight: bold;
  padding: 0 8px;
  qproperty-alignment: 'AlignRight | AlignVCenter';
}
"""


def step_header_time() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "HeaderTime" in text:
        print("  deck.xml: header time already present")
    else:
        anchor = text.rindex("<WidgetGroup>", 0, text.index("<ObjectName>DeckHeaderBpm</ObjectName>"))
        text = text[:anchor] + HEADER_TIME + "          " + text[anchor:]
        path.write_text(text, encoding="utf-8")
        print("  deck.xml: time next to the BPM box on Browse")

    swap_qss("step 22: header time on Browse", QSS_22)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 23

# The XZ gives each waveform row its own ON AIR column: red badge on top, big
# deck number under it, sitting between the info column and the waveform. Move
# both out of the sidebar header into that column.
ONAIR_HEADER = """              <WidgetGroup>
                <ObjectName>WaveformOnAir</ObjectName>
                <Layout>horizontal</Layout>
                <SizePolicy>max,max</SizePolicy>
                <Children>
                  <Label>
                    <ObjectName>WaveformOnAirLabel</ObjectName>
                    <Text>ON AIR</Text>
                  </Label>
                </Children>
                <Connection>
                  <ConfigKey>[Channel<Variable name="channel"/>],play_indicator</ConfigKey>
                  <BindProperty>visible</BindProperty>
                </Connection>
              </WidgetGroup>
              <Label>
                <ObjectName>WaveformDeckNum<Variable name="channel"/></ObjectName>
                <Text><Variable name="channel"/></Text>
              </Label>
"""

ONAIR_COLUMN = """      <WidgetGroup>
        <ObjectName>WaveformOnAirColumn<Variable name="channel"/></ObjectName>
        <Layout>vertical</Layout>
        <Size>44f,0me</Size>
        <Children>
          <WidgetGroup>
            <ObjectName>WaveformOnAir</ObjectName>
            <Layout>horizontal</Layout>
            <Size>0me,16f</Size>
            <Children>
              <Label>
                <ObjectName>WaveformOnAirLabel</ObjectName>
                <Text>ON AIR</Text>
                <Size>0me,0me</Size>
              </Label>
            </Children>
            <Connection>
              <ConfigKey>[Channel<Variable name="channel"/>],play_indicator</ConfigKey>
              <BindProperty>visible</BindProperty>
            </Connection>
          </WidgetGroup>
          <Label>
            <ObjectName>WaveformDeckNum<Variable name="channel"/></ObjectName>
            <Text><Variable name="channel"/></Text>
            <Size>0me,0me</Size>
          </Label>
        </Children>
      </WidgetGroup>
"""

QSS_23 = """

/* ON AIR column between the sidebar and the waveform, XZ style. */
#WaveformOnAirColumn1, #WaveformOnAirColumn2,
#WaveformOnAirColumn3, #WaveformOnAirColumn4 {
  background-color: #14181d;
  border-left: 1px solid #000000;
  border-right: 1px solid #000000;
}

#WaveformOnAirLabel {
  background-color: #d32020;
  color: #ffffff;
  font-size: 8px;
  font-weight: bold;
  qproperty-alignment: 'AlignCenter';
}

#WaveformDeckNum1, #WaveformDeckNum2, #WaveformDeckNum3, #WaveformDeckNum4 {
  background-color: transparent;
  font-size: 26px;
  font-weight: bold;
  margin: 0;
  qproperty-alignment: 'AlignCenter';
}

#WaveformDeckNum1 { color: #2d85cd; }
#WaveformDeckNum2 { color: #d73535; }
#WaveformDeckNum3 { color: #e9e9e9; }
#WaveformDeckNum4 { color: #3fa93f; }
"""


def step_onair_column() -> int:
    path = SKIN / "waveform.xml"
    text = path.read_text(encoding="utf-8")

    if "WaveformOnAirColumn" in text:
        print("  waveform.xml: ON AIR column already present")
    else:
        if ONAIR_HEADER not in text:
            print("  ! sidebar header ON AIR block not matched")
            return 1
        text = text.replace(ONAIR_HEADER, "", 1)
        anchor = text.index("<Visual>")
        text = text[:anchor] + ONAIR_COLUMN + "      " + text[anchor:]
        path.write_text(text, encoding="utf-8")
        print("  waveform.xml: ON AIR and deck number in their own column")

    swap_qss("step 23: ON AIR column", QSS_23)
    return 0 if check_xml("waveform.xml") else 1


# ---------------------------------------------------------------- step 24

# Finishing touches from the photo: the X-PAD band is orange with black text,
# and the first tab is called WAVEFORM.
QSS_24 = """

/* Orange X-PAD band. */
#XPadRow { background-color: #e08b2a; }

#XPadLpf, #XPadMid, #XPadHpf {
  background-color: transparent;
  color: #10222f;
  font-size: 10px;
  font-weight: bold;
}
"""


def step_xz_touches() -> int:
    top = SKIN / "topbar.xml"
    text = top.read_text(encoding="utf-8")
    if ">Waveform<" in text:
        print("  topbar.xml: WAVEFORM tab already named")
    else:
        text = text.replace(
            '<SetVariable name="tab_name">Overview</SetVariable>',
            '<SetVariable name="tab_name">Waveform</SetVariable>',
            1,
        )
        top.write_text(text, encoding="utf-8")
        print("  topbar.xml: Overview tab renamed to Waveform")

    # The rename changes the button's ObjectName too; follow it in the QSS.
    qss = SKIN / "style.qss"
    qtext = qss.read_text(encoding="utf-8")
    if "#TabButtonOverview" in qtext:
        qss.write_text(qtext.replace("#TabButtonOverview", "#TabButtonWaveform"), encoding="utf-8")
        print("  style.qss: tab selector renamed")

    swap_qss("step 24: XZ touches", QSS_24)
    return 0 if check_xml("topbar.xml") else 1


# ---------------------------------------------------------------- step 25

# The XZ sidebar has no quantize/keylock buttons; drop the controls row.
def step_hide_sidebar_buttons() -> int:
    path = SKIN / "waveform.xml"
    text = path.read_text(encoding="utf-8")

    if "WaveformInfo_Controls" not in text:
        print("  waveform.xml: sidebar buttons already gone")
        return 0

    _, text = extract_group(text, "<ObjectName>WaveformInfo_Controls</ObjectName>")
    path.write_text(text, encoding="utf-8")
    print("  waveform.xml: quantize/keylock buttons removed")
    return 0 if check_xml("waveform.xml") else 1


# ---------------------------------------------------------------- step 26

# Title band a third flatter: every element in the header row scaled down so
# the row height, which follows the tallest child (the BPM box), drops ~1/3.
QSS_26 = """

/* Flatter title band. */
#DeckHeader { max-height: 40px; min-height: 40px; }

#DeckTitle { font-size: 30px; }
#DeckTitleNote { font-size: 30px; }

#DeckNumBadge1, #DeckNumBadge2, #DeckNumBadge3, #DeckNumBadge4 {
  min-width: 40px;
  padding: 0 0 1px 0;
}
#DeckNumBadgeWord { font-size: 12px; }
#DeckNumBadgeNum { font-size: 23px; }

#DeckOnAirLabel { font-size: 8px; }

#HeaderTimeValue { font-size: 18px; }

#DeckHeaderBpm {
  min-width: 96px;
  max-width: 96px;
  padding: 0 4px 1px 4px;
}
#DeckHeaderBpmTitle { font-size: 9px; }
#DeckHeaderBpmValue { font-size: 18px; }

/* The panel below keeps the same width as the shrunken BPM box. */
#DeckTempoPanel {
  min-width: 96px;
  max-width: 96px;
}
"""


def step_flat_header() -> int:
    swap_qss("step 26: flatter title band", QSS_26)
    return 0


# ---------------------------------------------------------------- step 27

# Double-height top bar with matching text.
QSS_27 = """

/* Double-height tab bar. */
#TabButtonWaveform, #TabButtonBrowse, #TabButtonSampler {
  font-size: 20px;
  padding: 8px 10px;
}

#TopStatusLoadLabel, #TopStatusLoad { font-size: 14px; }
#TopStatusClock { font-size: 20px; }
"""


def step_big_topbar() -> int:
    path = SKIN / "topbar.xml"
    text = path.read_text(encoding="utf-8")
    if "<Size>0me,100f</Size>" in text:
        print("  topbar.xml: already double height")
    elif "<Size>0me,50f</Size>" in text:
        text = text.replace("<Size>0me,50f</Size>", "<Size>0me,100f</Size>", 1)
        path.write_text(text, encoding="utf-8")
        print("  topbar.xml: height 50 -> 100")
    else:
        print("  ! topbar size tag not matched")
        return 1

    swap_qss("step 27: double top bar", QSS_27)
    return 0 if check_xml("topbar.xml") else 1


# ---------------------------------------------------------------- step 28

# On the XZ the BPM box is not part of the title band: box and Q panel form
# their own right-hand column spanning the full card height. Restructure the
# card into [main column | right column].
RIGHT_COL_OPEN = """    <WidgetGroup>
      <ObjectName>DeckMain</ObjectName>
      <Layout>vertical</Layout>
      <Size>0me,0me</Size>
      <Children>
"""

QSS_28 = """

/* BPM box and Q panel in their own right column, full card height. */
#DeckRightCol {
  background-color: #2b2f33;
}

#DeckHeaderBpm {
  margin: 0;
  padding: 0 4px 2px 4px;
  min-height: 55px;
  max-height: 55px;
}
#DeckHeaderBpmTitle { font-size: 10px; }
#DeckHeaderBpmValue { font-size: 36px; }

#DeckTempoPanel {
  margin: 0;
  min-width: 0;
  max-width: 116px;
}
"""


def step_right_column() -> int:
    path = SKIN / "deck.xml"
    text = path.read_text(encoding="utf-8")

    if "DeckRightCol" in text:
        print("  deck.xml: right column already present")
        swap_qss("step 28: BPM right column", QSS_28)
        return 0

    bpm_block, text = extract_group(text, "<ObjectName>DeckHeaderBpm</ObjectName>")
    panel_block, text = extract_group(text, "<ObjectName>DeckTempoPanel</ObjectName>")

    right_col = (
        "    <WidgetGroup>\n"
        "      <ObjectName>DeckRightCol</ObjectName>\n"
        "      <Layout>vertical</Layout>\n"
        "      <Size>116f,0me</Size>\n"
        "      <Children>\n"
        + bpm_block + NL + panel_block + NL +
        "      </Children>\n"
        "    </WidgetGroup>\n"
    )

    # The Deck root becomes a horizontal split: everything it had moves into a
    # DeckMain column, the new right column comes after it.
    deck_idx = text.index("<ObjectName>Deck</ObjectName>")
    lay_idx = text.index("<Layout>vertical</Layout>", deck_idx)
    text = text[:lay_idx] + "<Layout>horizontal</Layout>" + text[lay_idx + len("<Layout>vertical</Layout>"):]

    children_open = text.index("<Children>", deck_idx) + len("<Children>")
    text = text[:children_open] + NL + RIGHT_COL_OPEN + text[children_open:]

    children_close = text.rindex("</Children>")
    text = text[:children_close] + "      </Children>\n    </WidgetGroup>\n" + right_col + text[children_close:]

    path.write_text(text, encoding="utf-8")
    print("  deck.xml: BPM box and Q panel split into a right column")

    swap_qss("step 28: BPM right column", QSS_28)
    return 0 if check_xml("deck.xml") else 1


# ---------------------------------------------------------------- step 29

# Status block: LOAD row on top, clock under it, twice the size.
TOPSTATUS_OLD = """          <WidgetGroup>
            <ObjectName>TopStatus</ObjectName>
            <Layout>horizontal</Layout>
            <SizePolicy>max,me</SizePolicy>
            <Children>
              <Label>
                <ObjectName>TopStatusLoadLabel</ObjectName>
                <Text>LOAD</Text>
              </Label>
              <Number>
                <ObjectName>TopStatusLoad</ObjectName>
                <TooltipId>audio_latency_usage</TooltipId>
                <Connection>
                  <ConfigKey>[App],audio_latency_usage</ConfigKey>
                </Connection>
              </Number>
              <Time>
                <ObjectName>TopStatusClock</ObjectName>
                <TooltipId>time</TooltipId>
              </Time>
            </Children>
          </WidgetGroup>"""

TOPSTATUS_NEW = """          <WidgetGroup>
            <ObjectName>TopStatus</ObjectName>
            <Layout>vertical</Layout>
            <SizePolicy>max,me</SizePolicy>
            <Children>
              <WidgetGroup>
                <ObjectName>TopStatusLoadRow</ObjectName>
                <Layout>horizontal</Layout>
                <SizePolicy>max,max</SizePolicy>
                <Children>
                  <Label>
                    <ObjectName>TopStatusLoadLabel</ObjectName>
                    <Text>LOAD</Text>
                  </Label>
                  <Number>
                    <ObjectName>TopStatusLoad</ObjectName>
                    <TooltipId>audio_latency_usage</TooltipId>
                    <Connection>
                      <ConfigKey>[App],audio_latency_usage</ConfigKey>
                    </Connection>
                  </Number>
                </Children>
              </WidgetGroup>
              <Time>
                <ObjectName>TopStatusClock</ObjectName>
                <TooltipId>time</TooltipId>
              </Time>
            </Children>
          </WidgetGroup>"""

QSS_29 = """

/* LOAD over the clock, double size. */
#TopStatus { qproperty-layoutAlignment: 'AlignRight | AlignVCenter'; }
#TopStatusLoadLabel { font-size: 16px; }
#TopStatusLoad { font-size: 22px; }
#TopStatusClock {
  font-size: 40px;
  qproperty-alignment: 'AlignRight | AlignVCenter';
}
"""


def step_stacked_status() -> int:
    path = SKIN / "topbar.xml"
    text = path.read_text(encoding="utf-8")

    if "TopStatusLoadRow" in text:
        print("  topbar.xml: stacked status already present")
    elif TOPSTATUS_OLD in text:
        text = text.replace(TOPSTATUS_OLD, TOPSTATUS_NEW, 1)
        path.write_text(text, encoding="utf-8")
        print("  topbar.xml: LOAD over the clock")
    else:
        print("  ! TopStatus block not matched")
        return 1

    swap_qss("step 29: stacked status", QSS_29)
    return 0 if check_xml("topbar.xml") else 1


# ---------------------------------------------------------------- step 30

# CPU % in the status block and the XZ deck-view selector. The controls live
# in the [Pioneered] group: skin attributes create them, the Time-Clamp script
# owns the radio logic and the CPU value (fed over VirMIDI by a daemon).
SKIN_ATTRS = """			<attribute config_key="[Pioneered],cpu">0</attribute>
			<attribute config_key="[Pioneered],mode2">0</attribute>
			<attribute config_key="[Pioneered],mode24">0</attribute>
			<attribute config_key="[Pioneered],mode4">0</attribute>
			<attribute config_key="[Pioneered],disp2">0</attribute>
			<attribute config_key="[Pioneered],disp24">0</attribute>
			<attribute config_key="[Pioneered],disp4">1</attribute>
			<attribute config_key="[Pioneered],show_wf1">1</attribute>
			<attribute config_key="[Pioneered],show_wf2">1</attribute>
			<attribute config_key="[Pioneered],show_wf3">1</attribute>
			<attribute config_key="[Pioneered],show_wf4">1</attribute>
			<attribute config_key="[Pioneered],show_cardtop">1</attribute>
			<attribute config_key="[Pioneered],show_cardbot">1</attribute>
			<attribute config_key="[Pioneered],zoomcycle">0</attribute>
"""

DECKMODE_BUTTON = """          <PushButton>
            <ObjectName>DeckModeBtn{key}</ObjectName>
            <Size>{w}f,30f</Size>
            <NumberStates>1</NumberStates>
            <State><Number>0</Number><Text>{label}</Text></State>
            <Connection>
              <ConfigKey>[Pioneered],mode{key}</ConfigKey>
              <ConnectValueToWidget>false</ConnectValueToWidget>
            </Connection>
            <Connection>
              <ConfigKey>[Pioneered],disp{key}</ConfigKey>
            </Connection>
          </PushButton>
"""

CPU_ROW = """                  <Label>
                    <ObjectName>TopStatusCpuLabel</ObjectName>
                    <Text>CPU</Text>
                  </Label>
                  <Number>
                    <ObjectName>TopStatusCpu</ObjectName>
                    <NumberOfDigits>0</NumberOfDigits>
                    <Connection>
                      <ConfigKey>[Pioneered],cpu</ConfigKey>
                    </Connection>
                  </Number>
"""

QSS_30 = """

/* Deck view selector, XZ style. */
#DeckModeBtn2, #DeckModeBtn24, #DeckModeBtn4 {
  background-color: #0d1a2e;
  border: 1px solid #1f4c85;
  color: #8fb4e0;
  font-size: 13px;
  font-weight: bold;
  margin: 0 2px;
  min-height: 30px;
  max-height: 30px;
  padding: 0 10px;
  qproperty-alignment: 'AlignCenter';
}

#DeckModeBtn2[value="1"],
#DeckModeBtn24[value="1"],
#DeckModeBtn4[value="1"] {
  border: 1px solid #f2d13c;
  background-color: #1f4c85;
  color: #ffffff;
}

/* CPU next to LOAD. */
#TopStatusCpuLabel {
  color: #8fa4b8;
  font-size: 16px;
  font-weight: bold;
  padding: 0 2px 0 10px;
}

#TopStatusCpu {
  color: #e08b2a;
  font-size: 22px;
  font-weight: bold;
}
"""


def step_cpu_and_modes() -> int:
    skin = SKIN / "skin.xml"
    text = skin.read_text(encoding="utf-8")
    if "[Pioneered],cpu" in text:
        print("  skin.xml: [Pioneered] attributes already present")
    else:
        anchor = '			<attribute config_key="[Master],num_decks">4</attribute>\n'
        if anchor not in text:
            print("  ! skin.xml attribute anchor missing")
            return 1
        text = text.replace(anchor, anchor + SKIN_ATTRS, 1)
        skin.write_text(text, encoding="utf-8")
        print("  skin.xml: [Pioneered] controls declared")

    top = SKIN / "topbar.xml"
    text = top.read_text(encoding="utf-8")
    if "DeckModeBtn2" in text:
        print("  topbar.xml: deck mode buttons already present")
    else:
        buttons = (
            DECKMODE_BUTTON.format(key="2", label="2 DECK", w="80")
            + DECKMODE_BUTTON.format(key="24", label="2/4 DECK", w="90")
            + DECKMODE_BUTTON.format(key="4", label="4 DECK", w="80")
        )
        anchor = "          <WidgetGroup>\n            <ObjectName>TopStatus</ObjectName>"
        if anchor not in text:
            print("  ! topbar TopStatus anchor missing")
            return 1
        text = text.replace(anchor, buttons + anchor, 1)

    if "TopStatusCpu" in text:
        print("  topbar.xml: CPU display already present")
    else:
        # Anchor on the latency Number: the naive first </Number> is the
        # <State><Number>0</Number> inside the deck mode buttons.
        latency = text.index("audio_latency_usage")
        idx = text.index("</Number>", latency) + len("</Number>")
        text = text[:idx] + NL + CPU_ROW.rstrip() + text[idx:]
    top.write_text(text, encoding="utf-8")
    print("  topbar.xml: deck mode buttons and CPU display")

    wave = SKIN / "waveform.xml"
    text = wave.read_text(encoding="utf-8")
    if "[Pioneered],show_wf" in text:
        print("  waveform.xml: row visibility already bound")
    else:
        marker = '<ObjectName>Waveform_Channel<Variable name="channel"/></ObjectName>'
        idx = text.index(marker) + len(marker)
        conn = (NL + '    <Connection>'
                + NL + '      <ConfigKey>[Pioneered],show_wf<Variable name="channel"/></ConfigKey>'
                + NL + '      <BindProperty>visible</BindProperty>'
                + NL + '    </Connection>')
        text = text[:idx] + conn + text[idx:]
        wave.write_text(text, encoding="utf-8")
        print("  waveform.xml: rows follow the deck view selector")

    swap_qss("step 30: CPU and deck view selector", QSS_30)
    return 0 if check_xml("skin.xml", "topbar.xml", "waveform.xml") else 1


# ---------------------------------------------------------------- step 31

# The deck cards follow the view selector too: 2 DECK shows cards 1-2,
# 2/4 DECK cards 3-4, 4 DECK all. Rows already exist; bind their visibility
# to the same show_wf controls the waveform rows use.
def _bind_row(text: str, row: str, key: str) -> str:
    marker = f"<ObjectName>{row}</ObjectName>"
    if marker not in text or f"{key}</ConfigKey>" in text:
        return text
    idx = text.index(marker) + len(marker)
    conn = (NL + "            <Connection>"
            + NL + f"              <ConfigKey>[Pioneered],{key}</ConfigKey>"
            + NL + "              <BindProperty>visible</BindProperty>"
            + NL + "            </Connection>")
    return text[:idx] + conn + text[idx:]


def step_cards_follow_mode() -> int:
    for name in ("overview.xml", "library.xml"):
        path = SKIN / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new = _bind_row(text, "DeckRowTop", "show_cardtop")
        new = _bind_row(new, "DeckRowBottom", "show_cardbot")
        if new != text:
            path.write_text(new, encoding="utf-8")
            print(f"  {name}: card rows follow the deck view")
        else:
            print(f"  {name}: card rows already bound")
    return 0 if check_xml("overview.xml", "library.xml") else 1


# ---------------------------------------------------------------- step 32

# AZ main-display items that map onto Mixxx controls:
#   26-27: TRACK number with a QUANTIZE lamp under it, left of the time
#   29:    MASTER chip on the BPM box (sync leader)
#   1:     eject button in the waveform sidebar
#   5:     SINGLE/CONTINUE as the AutoDJ toggle
TRACK_COL = """          <WidgetGroup>
            <ObjectName>TrackNoCol</ObjectName>
            <Layout>vertical</Layout>
            <Size>64f,0me</Size>
            <Children>
              <Label>
                <ObjectName>TrackNoCaption</ObjectName>
                <Text>TRACK</Text>
              </Label>
              <TrackProperty>
                <ObjectName>TrackNoValue</ObjectName>
                <TooltipId>track_number</TooltipId>
                <Property>track_number</Property>
                <Channel><Variable name="channel"/></Channel>
              </TrackProperty>
              <Label>
                <ObjectName>TrackNoQuantize</ObjectName>
                <Text>QUANTIZE</Text>
                <Connection>
                  <ConfigKey>[Channel<Variable name="channel"/>],quantize</ConfigKey>
                  <BindProperty>highlight</BindProperty>
                </Connection>
              </Label>
              <Label>
                <ObjectName>TrackNoFill</ObjectName>
                <Size>0me,0me</Size>
              </Label>
            </Children>
          </WidgetGroup>
"""

BPM_TITLE_OLD = """              <Label>
                <ObjectName>DeckHeaderBpmTitle</ObjectName>
                <Text>BPM</Text>
              </Label>"""

BPM_TITLE_NEW = """              <WidgetGroup>
                <ObjectName>DeckHeaderBpmTitleRow</ObjectName>
                <Layout>horizontal</Layout>
                <Size>0me,14f</Size>
                <Children>
                  <Label>
                    <ObjectName>DeckHeaderBpmTitle</ObjectName>
                    <Text>BPM</Text>
                  </Label>
                  <Label>
                    <ObjectName>BpmFill</ObjectName>
                    <Size>0me,0me</Size>
                  </Label>
                  <Label>
                    <ObjectName>BpmMaster</ObjectName>
                    <Text>MASTER</Text>
                    <Connection>
                      <ConfigKey>[Channel<Variable name="channel"/>],sync_master</ConfigKey>
                      <BindProperty>visible</BindProperty>
                    </Connection>
                  </Label>
                </Children>
              </WidgetGroup>"""

EJECT_BUTTON = """              <PushButton>
                <ObjectName>SidebarEject</ObjectName>
                <Size>22f,18f</Size>
                <NumberStates>1</NumberStates>
                <State><Number>0</Number><Text>&#9167;</Text></State>
                <Connection>
                  <ConfigKey>[Channel<Variable name="channel"/>],eject</ConfigKey>
                  <ConnectValueToWidget>false</ConnectValueToWidget>
                </Connection>
              </PushButton>
"""

SINGLE_BUTTON = """          <PushButton>
            <ObjectName>SingleContinueBtn</ObjectName>
            <Size>110f,30f</Size>
            <NumberStates>2</NumberStates>
            <State><Number>0</Number><Text>SINGLE</Text></State>
            <State><Number>1</Number><Text>CONTINUE</Text></State>
            <Connection>
              <ConfigKey>[AutoDJ],enabled</ConfigKey>
            </Connection>
          </PushButton>
"""

QSS_32 = """

/* TRACK number and QUANTIZE lamp, AZ style. */
#TrackNoCol { padding: 2px 0 0 4px; }

#TrackNoCaption {
  color: #8fa4b8;
  font-size: 10px;
  font-weight: bold;
  letter-spacing: 1px;
}

#TrackNoValue {
  color: #ffffff;
  font-size: 24px;
  font-weight: bold;
}

#TrackNoQuantize {
  color: #4a5a68;
  font-size: 9px;
  font-weight: bold;
  letter-spacing: 1px;
}
#TrackNoQuantize[highlight="1"] { color: #d73535; }

/* MASTER chip on the BPM box. */
#BpmMaster {
  background-color: #e08b2a;
  color: #10222f;
  font-size: 9px;
  font-weight: bold;
  padding: 1px 4px;
}

/* Sidebar eject. */
#SidebarEject {
  background-color: transparent;
  border: 0;
  color: #8fa4b8;
  font-size: 14px;
}

/* SINGLE/CONTINUE follows the tab button look. */
#SingleContinueBtn {
  background-color: #0d1a2e;
  border: 1px solid #1f4c85;
  color: #8fb4e0;
  font-size: 13px;
  font-weight: bold;
  margin: 0 12px 0 2px;
  min-height: 30px;
  max-height: 30px;
  padding: 0 10px;
  qproperty-alignment: 'AlignCenter';
}
#SingleContinueBtn[value="1"] {
  border: 1px solid #f2d13c;
  background-color: #1f4c85;
  color: #ffffff;
}
"""


def step_az_details() -> int:
    deck = SKIN / "deck.xml"
    text = deck.read_text(encoding="utf-8")
    if "TrackNoCol" in text:
        print("  deck.xml: TRACK column already present")
    else:
        anchor = text.rindex("<WidgetGroup>", 0, text.index("<ObjectName>TrackTimeContainer</ObjectName>"))
        text = text[:anchor] + TRACK_COL + "          " + text[anchor:]
        print("  deck.xml: TRACK number and QUANTIZE lamp")

    if "BpmMaster" in text:
        print("  deck.xml: MASTER chip already present")
    elif BPM_TITLE_OLD in text:
        text = text.replace(BPM_TITLE_OLD, BPM_TITLE_NEW, 1)
        print("  deck.xml: MASTER chip on the BPM box")
    else:
        print("  ! BPM title block not matched")
    deck.write_text(text, encoding="utf-8")

    wave = SKIN / "waveform.xml"
    text = wave.read_text(encoding="utf-8")
    if "SidebarEject" in text:
        print("  waveform.xml: eject already present")
    else:
        marker = "<Text>USB1</Text>\n              </Label>"
        idx = text.index(marker) + len(marker)
        text = text[:idx] + NL + EJECT_BUTTON.rstrip() + text[idx:]
        wave.write_text(text, encoding="utf-8")
        print("  waveform.xml: eject button beside USB1")

    top = SKIN / "topbar.xml"
    text = top.read_text(encoding="utf-8")
    if "SingleContinueBtn" in text:
        print("  topbar.xml: SINGLE/CONTINUE already present")
    else:
        anchor = text.index("          <PushButton>\n            <ObjectName>DeckModeBtn2</ObjectName>")
        text = text[:anchor] + SINGLE_BUTTON + text[anchor:]
        top.write_text(text, encoding="utf-8")
        print("  topbar.xml: SINGLE/CONTINUE toggle")

    swap_qss("step 32: AZ details", QSS_32)
    return 0 if check_xml("deck.xml", "waveform.xml", "topbar.xml") else 1


# ---------------------------------------------------------------- main


def main() -> int:
    if not SKIN.is_dir():
        print(f"error: {SKIN} not found", file=sys.stderr)
        return 1
    print(f"patching {SKIN.name}")
    for step in (step12, step34, step5, step6, step7, step8, step9, step10, step11, step_time_left):
        rc = step()
        if rc != 0:
            return rc
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
