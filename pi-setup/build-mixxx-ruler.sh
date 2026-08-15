#!/bin/bash
# Build Mixxx 2.5 with an always-on minute ruler under the overview waveform.
# Runs unattended; log: ~/build/build.log
set -euo pipefail

mkdir -p ~/build
cd ~/build

# deb-src for the Debian repos (deb822 format on Trixie).
sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/*.sources
sudo apt-get update -qq

sudo apt-get install -y -qq dpkg-dev devscripts
sudo apt-get build-dep -y -qq mixxx

rm -rf mixxx-*
apt-get source mixxx
cd mixxx-*/

python3 - <<'PYEOF'
import re, pathlib

p = pathlib.Path("src/widget/woverview.cpp")
t = p.read_text(encoding="utf-8")

assert "drawMinuteRuler" not in t

# Call it right after the marks, inside the trackSamples > 0 branch.
old_call = """            drawRangeMarks(&painter, offset, gain);
            drawMarks(&painter, offset, gain);"""
new_call = """            drawRangeMarks(&painter, offset, gain);
            drawMarks(&painter, offset, gain);
            drawMinuteRuler(&painter, offset, gain);"""
assert old_call in t
t = t.replace(old_call, new_call, 1)

impl = """
void WOverview::drawMinuteRuler(QPainter* pPainter, float offset, float gain) {
    // XDJ-style minute scale: ticks and -M:00 labels measured from the end of
    // the track, drawn along the bottom edge.
    double trackSamples = getTrackSamples();
    double rate = m_trackSampleRateControl.get() * mixxx::kEngineChannelCount;
    if (trackSamples <= 0 || rate <= 0) {
        return;
    }
    double durationSeconds = trackSamples / rate;

    PainterScope painterScope(pPainter);
    QFont font = pPainter->font();
    font.setPixelSize(static_cast<int>(9 * m_scaleFactor));
    font.setBold(true);
    pPainter->setFont(font);

    // Thin out the labels when the minutes get closer than ~45 px.
    double minutePixels = gain * 60.0 * rate;
    int step = 1;
    while (step * minutePixels < 45.0 * m_scaleFactor && step < 16) {
        step *= 2;
    }

    int h = height();
    for (int minute = step; minute * 60.0 < durationSeconds; minute += step) {
        double posSample = (durationSeconds - minute * 60.0) * rate;
        float x = offset + static_cast<float>(gain * posSample);
        pPainter->setPen(QPen(QColor(255, 255, 255, 200), m_scaleFactor));
        pPainter->drawLine(QPointF(x, h - 8 * m_scaleFactor), QPointF(x, h));
        QString label = QStringLiteral("-%1:00").arg(minute);
        pPainter->setPen(QPen(QColor(255, 255, 255, 230), m_scaleFactor));
        pPainter->drawText(QPointF(x + 3 * m_scaleFactor, h - 2 * m_scaleFactor), label);
    }
}
"""

# Put the implementation before drawTimeRuler's definition.
anchor = "void WOverview::drawTimeRuler(QPainter* pPainter) {"
assert anchor in t
t = t.replace(anchor, impl + "\n" + anchor, 1)
p.write_text(t, encoding="utf-8")

h = pathlib.Path("src/widget/woverview.h")
th = h.read_text(encoding="utf-8")
old_decl = "    void drawTimeRuler(QPainter* pPainter);"
assert old_decl in th
th = th.replace(old_decl,
    "    void drawTimeRuler(QPainter* pPainter);\n"
    "    void drawMinuteRuler(QPainter* pPainter, float offset, float gain);", 1)
h.write_text(th, encoding="utf-8")
print("patch applied")
PYEOF

# Version bump so apt does not silently replace it on upgrade.
DEBEMAIL="dj@pidj" DEBFULLNAME="ntamas" debchange --local +ruler "overview minute ruler"

DEB_BUILD_OPTIONS="nocheck parallel=4" dpkg-buildpackage -b -uc -us
echo "BUILD DONE"
ls -l ../mixxx_*.deb
