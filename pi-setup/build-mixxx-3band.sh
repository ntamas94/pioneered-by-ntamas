#!/bin/bash
# Rebuild Mixxx so the three-band waveform is coloured the way rekordbox's
# 3Band mode colours it, and so the numbers that decide that live in the skin
# instead of in the binary.
#
# Both programs work the same way in outline. At analysis time each one splits
# the track into a low, a mid and a high band and stores one level per band per
# waveform column; at draw time each one mixes three colours by those levels.
# Picking three skin colours therefore gets the hues right and the character
# wrong, because the character is not in the colours. It is in three other
# things: where the bands are split, what curve each band's level goes through
# before it becomes colour, and what happens to brightness and saturation when
# the level is low or when all three bands are strong at once.
#
# What Mixxx 2.5.6 does, read out of the source:
#
#   The split is at 600 Hz and 4000 Hz -- kLowMidFreqHz and kMidHighFreqHz in
#   src/analyzer/analyzerwaveform.cpp -- with fourth-order Bessel filters, a
#   low-pass, a band-pass and a high-pass, settled on silence before the track
#   starts. Per column the analyzer keeps the maximum absolute sample in each
#   band, per channel, and stores it as one byte. Low and mid are stored
#   linearly; high and the overall level are stored as x^0.632, which lifts
#   quiet detail (scaleSignal, src/analyzer/analyzerwaveform.h).
#
#   The drawing is in two places. The scrolling waveform is
#   allshader::WaveformRendererRGB::paintGL in
#   src/waveform/renderers/allshader/waveformrendererrgb.cpp; the overview
#   under the deck card is WOverview::drawNextPixmapPartRGB in
#   src/widget/woverview.cpp. Both do the same arithmetic: multiply each band
#   level by its base colour, add the three, then divide all three components
#   by the largest of them. That last step is the whole difference in
#   character. Dividing by the largest component throws the level away and
#   keeps only the ratio, so a column ten decibels down is drawn at exactly the
#   same brightness as the loudest column in the track, and no column is ever
#   white, because white needs all three components at once and only the
#   largest survives. Column height comes from a fourth stored value, the
#   overall level, not from the three bands.
#
# So the mix Mixxx ships is "additive, then normalised to full brightness".
# rekordbox's is additive without that normalisation, which is why quiet
# passages there stay dark and dense ones go white. This patch does not hard
# code the alternative. It puts the mix behind three named choices, gives every
# band a gain and a curve, and reads all of it out of the skin's signal-colour
# block, with defaults that reproduce today's Mixxx exactly. Nothing changes
# until the skin says so. When the measurement of rekordbox's own function is
# finished, the numbers go into skin XML and nothing has to be rebuilt.
#
# What the skin may now set inside <Waveform>, alongside SignalColor and the
# rest -- every one of them optional:
#
#   Signal3BandLowColor / MidColor / HighColor   base colours; default to
#                                                SignalRGBLow/Mid/HighColor
#   Signal3BandLowGain / MidGain / HighGain      per-band gain, default 1
#   Signal3BandLowGamma / MidGamma / HighGamma   per-band curve, default 1
#   Signal3BandMix                               normalized (default, what
#                                                Mixxx does today) | additive |
#                                                preserve
#   Signal3BandBrightnessGamma                   curve on the mixed colour,
#                                                default 1
#   Signal3BandFloor                             lowest brightness a non-silent
#                                                column is drawn at, default 0
#   Signal3BandHeight                            all (default) | max | sum | rms
#   Signal3BandHeightGain / HeightGamma          default 1
#
# The mix modes, exactly: normalized divides the three components by the
# largest, additive clips each at 1, preserve divides by the largest only when
# it exceeds 1. Additive is the one that behaves like rekordbox -- brightness
# follows level and a column with all three bands strong comes out white.
#
# Band levels arrive here as the bytes the analyzer stored, so gain and curve
# are 256-entry lookup tables built once at skin load, not pow() in the
# per-pixel loop. Four decks of scrolling waveform at 60 Hz on a Pi 4 cannot
# afford the pow().
#
# The crossovers are left alone by default. rekordbox's are not known yet, and
# changing them means every track in the library is re-analysed, which also
# changes what the DDJ-1000 jog screens draw. When they are measured, set
# BAND3_LOW_HZ and BAND3_HIGH_HZ and this script will move them and bump the
# stored-waveform version string so Mixxx re-analyses instead of drawing stale
# data with the new colours. The filter shape is a separate question again:
# fourth-order Bessel is what Mixxx uses, upstream leaves eighth-order
# Butterworth in place commented out one line above, and which of the two is
# closer to rekordbox is unmeasured.
#
# This stacks on the tree in ~/build/mixxx-2.5.6, which already carries the
# minute ruler, the drop hover, the marquee, the staggered GL resize, the
# per-deck REMAIN/TIME, the OSK hook, the sound-device reopen control and the
# USB sidebar entry. It does not replace any of them. Built with -nc so the
# objects from the last run are kept; a clean build of Mixxx on this box is
# hours.
#
# When Mixxx is next upgraded this has to be redone, and it is worth knowing
# in advance how much. The patch hangs on five anchors: the block of nine
# m_rgbLowColor_r-style locals at the top of WaveformRendererRGB::paintGL, the
# three casts of u8maxLow/Mid/High to float in its loop, the normalise-by-
# largest-component block after them, the pair of matrix multiplications in
# WOverview::drawNextPixmapPartRGB, and the "// filtered colors" comment in
# WaveformSignalColors::setup. Everything else it adds is a new file. Upstream
# has been moving these two renderers around -- 2.5 split the all-shader path
# out of the old GL one -- so expect the anchors to need re-cutting rather than
# the idea to need rethinking. BAND3_PATCH_ONLY=1 patches and stops, which is
# how to find out whether they still match without spending an hour of CPU on
# a build that was going to fail.
#
# Log: ~/build/3band.log
set -euo pipefail

SOURCE=${BAND3_SOURCE:-$HOME/build/mixxx-2.5.6}
VERSION=${BAND3_VERSION:-2.5.6-0pioneered4}

if [ ! -d "$SOURCE" ]; then
    echo "no source tree at $SOURCE" >&2
    echo "That tree is upstream Mixxx 2.5.6 with Debian's debian/ directory" >&2
    echo "from mixxx 2.5.0+dfsg-3 copied in, BUILD_BENCH and ENGINEPRIME" >&2
    echo "turned off in debian/rules, and pioneered-mixxx.patch applied." >&2
    exit 1
fi

cd "$SOURCE"

python3 - <<'PYEOF'
import os
import pathlib

root = pathlib.Path(".")


def read(rel):
    return (root / rel).read_text(encoding="utf-8")


def write(rel, text):
    (root / rel).write_text(text, encoding="utf-8")


def replace_once(text, old, new, what):
    assert old in text, "anchor gone: " + what
    assert text.count(old) == 1, "anchor is not unique: " + what
    return text.replace(old, new, 1)


# ---------------------------------------------------------------- the mixer

band3_header = r'''#pragma once

// Three-band waveform colouring.
//
// The scrolling waveform and the overview both turn one low, one mid and one
// high level into one colour, and they used to do it with two copies of the
// same arithmetic. This is that arithmetic, once, with the numbers that decide
// its character -- the base colours, the per-band gain and curve, the way the
// three colours are combined, and where the column height comes from -- read
// out of the skin rather than compiled in. The defaults reproduce what Mixxx
// has always done: additive mix, normalised to full brightness, height from
// the separately stored overall level.
//
// Band levels arrive as the bytes the analyzer stored, so gain and curve are
// 256-entry tables built at skin load. There is no pow() in the per-pixel
// loop; four decks at 60 Hz on a Pi 4 would notice.

#include <QColor>
#include <QDomNode>
#include <algorithm>
#include <array>
#include <cmath>

#include "skin/legacy/skincontext.h"
#include "util/colorcomponents.h"
#include "util/math.h"

class WaveformBand3 {
  public:
    // How the three weighted colours become one.
    enum class Mix {
        // Divide by the largest component. Hue only: every column is drawn at
        // full brightness however quiet it is, and nothing is ever white.
        Normalized,
        // Add and clip at 1. Brightness follows level, and a column with all
        // three bands strong comes out white.
        Additive,
        // Add, and divide by the largest component only when it exceeds 1.
        // Brightness follows level, hue is never bent by clipping.
        Preserve,
    };

    // Where the column height comes from.
    enum class Height {
        All,      // the separately stored overall level, as Mixxx does
        MaxBand,  // the loudest of the three bands
        SumBands, // the three added
        Rms,      // root of the sum of squares
    };

    WaveformBand3()
            : m_lowColor(Qt::red),
              m_midColor(Qt::green),
              m_highColor(Qt::blue) {
        rebuild();
    }

    // The three base colours are read and colour-corrected by
    // WaveformSignalColors, which owns this; everything else is read here.
    void setup(const QDomNode& node,
            const SkinContext& context,
            const QColor& lowColor,
            const QColor& midColor,
            const QColor& highColor) {
        m_lowColor = lowColor;
        m_midColor = midColor;
        m_highColor = highColor;

        m_gain[0] = context.selectFloat(node, QStringLiteral("Signal3BandLowGain"), 1.0f);
        m_gain[1] = context.selectFloat(node, QStringLiteral("Signal3BandMidGain"), 1.0f);
        m_gain[2] = context.selectFloat(node, QStringLiteral("Signal3BandHighGain"), 1.0f);

        m_gamma[0] = context.selectFloat(node, QStringLiteral("Signal3BandLowGamma"), 1.0f);
        m_gamma[1] = context.selectFloat(node, QStringLiteral("Signal3BandMidGamma"), 1.0f);
        m_gamma[2] = context.selectFloat(node, QStringLiteral("Signal3BandHighGamma"), 1.0f);

        const QString mix =
                context.selectString(node, QStringLiteral("Signal3BandMix")).toLower();
        if (mix == QLatin1String("additive")) {
            m_mix = Mix::Additive;
        } else if (mix == QLatin1String("preserve")) {
            m_mix = Mix::Preserve;
        } else {
            m_mix = Mix::Normalized;
        }

        m_brightnessGamma =
                context.selectFloat(node, QStringLiteral("Signal3BandBrightnessGamma"), 1.0f);
        m_floor = context.selectFloat(node, QStringLiteral("Signal3BandFloor"), 0.0f);

        const QString height =
                context.selectString(node, QStringLiteral("Signal3BandHeight")).toLower();
        if (height == QLatin1String("max")) {
            m_height = Height::MaxBand;
        } else if (height == QLatin1String("sum")) {
            m_height = Height::SumBands;
        } else if (height == QLatin1String("rms")) {
            m_height = Height::Rms;
        } else {
            m_height = Height::All;
        }
        m_heightGain = context.selectFloat(node, QStringLiteral("Signal3BandHeightGain"), 1.0f);
        m_heightGamma = context.selectFloat(node, QStringLiteral("Signal3BandHeightGamma"), 1.0f);

        rebuild();
    }

    // A stored byte becomes a level in 0..1 (or above, if the band is gained).
    float low(unsigned char value) const {
        return m_band[0][value];
    }
    float mid(unsigned char value) const {
        return m_band[1][value];
    }
    float high(unsigned char value) const {
        return m_band[2][value];
    }

    // True when the column height is to come from the three bands rather than
    // from the separately stored overall level.
    bool heightFromBands() const {
        return m_height != Height::All;
    }

    void color(float lowLevel,
            float midLevel,
            float highLevel,
            float* pR,
            float* pG,
            float* pB) const {
        float r = lowLevel * m_lowR + midLevel * m_midR + highLevel * m_highR;
        float g = lowLevel * m_lowG + midLevel * m_midG + highLevel * m_highG;
        float b = lowLevel * m_lowB + midLevel * m_midB + highLevel * m_highB;

        const float largest = std::max({r, g, b});
        if (largest <= 0.0f) {
            *pR = 0.0f;
            *pG = 0.0f;
            *pB = 0.0f;
            return;
        }

        switch (m_mix) {
        case Mix::Normalized: {
            const float f = 1.0f / largest;
            r *= f;
            g *= f;
            b *= f;
            break;
        }
        case Mix::Preserve:
            if (largest > 1.0f) {
                const float f = 1.0f / largest;
                r *= f;
                g *= f;
                b *= f;
            }
            break;
        case Mix::Additive:
            r = std::min(r, 1.0f);
            g = std::min(g, 1.0f);
            b = std::min(b, 1.0f);
            break;
        }

        if (m_shapeBrightness) {
            r = curve(m_brightness, r);
            g = curve(m_brightness, g);
            b = curve(m_brightness, b);
        }

        *pR = r;
        *pG = g;
        *pB = b;
    }

    // Column height in 0..1, for the modes that take it from the bands.
    float bandHeight(float lowLevel, float midLevel, float highLevel) const {
        float value;
        switch (m_height) {
        case Height::MaxBand:
            value = std::max({lowLevel, midLevel, highLevel});
            break;
        case Height::SumBands:
            value = lowLevel + midLevel + highLevel;
            break;
        case Height::Rms:
            value = std::sqrt(lowLevel * lowLevel + midLevel * midLevel +
                    highLevel * highLevel);
            break;
        case Height::All:
        default:
            return 0.0f;
        }
        return curve(m_heightCurve, value * m_heightGain);
    }

  private:
    static float curve(const std::array<float, 256>& table, float value) {
        const float clamped = math_clamp(value, 0.0f, 1.0f);
        return table[static_cast<int>(clamped * 255.0f + 0.5f)];
    }

    void rebuild() {
        getRgbF(m_lowColor, &m_lowR, &m_lowG, &m_lowB);
        getRgbF(m_midColor, &m_midR, &m_midG, &m_midB);
        getRgbF(m_highColor, &m_highR, &m_highG, &m_highB);

        for (int band = 0; band < 3; ++band) {
            for (int i = 0; i < 256; ++i) {
                const float x = static_cast<float>(i) / 255.0f;
                m_band[band][i] = m_gain[band] *
                        (m_gamma[band] == 1.0f ? x : std::pow(x, m_gamma[band]));
            }
        }
        for (int i = 0; i < 256; ++i) {
            const float x = static_cast<float>(i) / 255.0f;
            m_brightness[i] = m_floor +
                    (1.0f - m_floor) *
                            (m_brightnessGamma == 1.0f ? x
                                                       : std::pow(x, m_brightnessGamma));
            m_heightCurve[i] = m_heightGamma == 1.0f ? x : std::pow(x, m_heightGamma);
        }
        m_shapeBrightness = m_brightnessGamma != 1.0f || m_floor != 0.0f;
    }

    QColor m_lowColor;
    QColor m_midColor;
    QColor m_highColor;
    float m_lowR{}, m_lowG{}, m_lowB{};
    float m_midR{}, m_midG{}, m_midB{};
    float m_highR{}, m_highG{}, m_highB{};

    float m_gain[3]{1.0f, 1.0f, 1.0f};
    float m_gamma[3]{1.0f, 1.0f, 1.0f};
    Mix m_mix{Mix::Normalized};
    float m_brightnessGamma{1.0f};
    float m_floor{0.0f};
    bool m_shapeBrightness{false};
    Height m_height{Height::All};
    float m_heightGain{1.0f};
    float m_heightGamma{1.0f};

    std::array<std::array<float, 256>, 3> m_band{};
    std::array<float, 256> m_brightness{};
    std::array<float, 256> m_heightCurve{};
};
'''

band3_path = "src/waveform/renderers/waveformband3.h"
assert not (root / band3_path).exists(), "already patched: " + band3_path
write(band3_path, band3_header)

# --------------------------------------------------- hang it off the colours

text = read("src/waveform/renderers/waveformsignalcolors.h")
assert "WaveformBand3" not in text, "already patched: waveformsignalcolors.h"
text = replace_once(text,
        '#include "skin/legacy/skincontext.h"',
        '#include "skin/legacy/skincontext.h"\n'
        '#include "waveform/renderers/waveformband3.h"',
        "waveformsignalcolors.h include")
text = replace_once(text,
        """    inline int getDimBrightThreshold() const {""",
        """    inline const WaveformBand3& getBand3() const {
        return m_band3;
    }
    inline int getDimBrightThreshold() const {""",
        "waveformsignalcolors.h getter")
text = replace_once(text,
        """    QColor m_bgColor;
    int m_dimBrightThreshold;""",
        """    QColor m_bgColor;
    WaveformBand3 m_band3;
    int m_dimBrightThreshold;""",
        "waveformsignalcolors.h member")
write("src/waveform/renderers/waveformsignalcolors.h", text)

text = read("src/waveform/renderers/waveformsignalcolors.cpp")
text = replace_once(text,
        """    // filtered colors
    m_rgbLowFilteredColor""",
        """    // The three-band mix has its own base colours, and falls back to the RGB
    // colours above when the skin does not name them.
    QColor band3Low = QColor(context.selectString(node, "Signal3BandLowColor"));
    band3Low = band3Low.isValid() ? WSkinColor::getCorrectColor(band3Low).toRgb()
                                  : m_rgbLowColor;
    QColor band3Mid = QColor(context.selectString(node, "Signal3BandMidColor"));
    band3Mid = band3Mid.isValid() ? WSkinColor::getCorrectColor(band3Mid).toRgb()
                                  : m_rgbMidColor;
    QColor band3High = QColor(context.selectString(node, "Signal3BandHighColor"));
    band3High = band3High.isValid() ? WSkinColor::getCorrectColor(band3High).toRgb()
                                    : m_rgbHighColor;
    m_band3.setup(node, context, band3Low, band3Mid, band3High);

    // filtered colors
    m_rgbLowFilteredColor""",
        "waveformsignalcolors.cpp setup call")
write("src/waveform/renderers/waveformsignalcolors.cpp", text)

# ------------------------------------------------- the scrolling waveform

rel = "src/waveform/renderers/allshader/waveformrendererrgb.cpp"
text = read(rel)
assert "getBand3" not in text, "already patched: " + rel

text = replace_once(text,
        """    const float low_r = static_cast<float>(m_rgbLowColor_r);
    const float mid_r = static_cast<float>(m_rgbMidColor_r);
    const float high_r = static_cast<float>(m_rgbHighColor_r);
    const float low_g = static_cast<float>(m_rgbLowColor_g);
    const float mid_g = static_cast<float>(m_rgbMidColor_g);
    const float high_g = static_cast<float>(m_rgbHighColor_g);
    const float low_b = static_cast<float>(m_rgbLowColor_b);
    const float mid_b = static_cast<float>(m_rgbMidColor_b);
    const float high_b = static_cast<float>(m_rgbHighColor_b);""",
        """    // Colours, per-band gain and curve, mix mode and height rule all come
    // from the skin's signal-colour block. Its defaults are what this renderer
    // did before: additive mix normalised to full brightness, height from
    // filtered.all.
    if (!m_pColors) {
        return;
    }
    const WaveformBand3& band3 = m_pColors->getBand3();""",
        "rgb renderer colour locals")

text = replace_once(text,
        """        // Cast to float
        float maxLow = static_cast<float>(u8maxLow);
        float maxMid = static_cast<float>(u8maxMid);
        float maxHigh = static_cast<float>(u8maxHigh);""",
        """        // Through the per-band gain and curve on the way out of the byte.
        // 1.0 is full scale from here on, where it used to be 255.
        float maxLow = band3.low(u8maxLow);
        float maxMid = band3.mid(u8maxMid);
        float maxHigh = band3.high(u8maxHigh);""",
        "rgb renderer band levels")

text = replace_once(text,
        """        if (sum != 0.f) {
            // magnitude = sqrt(sum) and magnitudeGained = sqrt(sumGained), and
            // factor = magnitudeGained / magnitude, but we can do with a single sqrt:
            const float factor = std::sqrt(sumGained / sum);
            maxAllChn[0] *= factor;
            maxAllChn[1] *= factor;
        }

        // Use the gained maxLow, maxMid and maxHigh values to calculate the color components
        float red = maxLow * low_r + maxMid * mid_r + maxHigh * high_r;
        float green = maxLow * low_g + maxMid * mid_g + maxHigh * high_g;
        float blue = maxLow * low_b + maxMid * mid_b + maxHigh * high_b;

        // Normalize the color components using the maximum of the three
        const float maxComponent = math_max3(red, green, blue);
        if (maxComponent == 0.f) {
            // Avoid division by 0
            red = 0.f;
            green = 0.f;
            blue = 0.f;
        } else {
            const float normFactor = 1.f / maxComponent;
            red *= normFactor;
            green *= normFactor;
            blue *= normFactor;
        }""",
        """        if (band3.heightFromBands()) {
            // The height comes from the bands themselves. They are already max
            // of left and right at this point, so both halves are the same.
            const float height =
                    band3.bandHeight(maxLow, maxMid, maxHigh) * m_maxValue;
            maxAllChn[0] = height;
            maxAllChn[1] = height;
        } else if (sum != 0.f) {
            // magnitude = sqrt(sum) and magnitudeGained = sqrt(sumGained), and
            // factor = magnitudeGained / magnitude, but we can do with a single sqrt:
            const float factor = std::sqrt(sumGained / sum);
            maxAllChn[0] *= factor;
            maxAllChn[1] *= factor;
        }

        float red, green, blue;
        band3.color(maxLow, maxMid, maxHigh, &red, &green, &blue);""",
        "rgb renderer mix")
write(rel, text)

# ------------------------------------------------------------- the overview

rel = "src/widget/woverview.cpp"
text = read(rel)
assert "getBand3" not in text, "already patched: " + rel

text = replace_once(text,
        """    QColor color;

    float lowColor_r, lowColor_g, lowColor_b;
    getRgbF(m_signalColors.getRgbLowColor(), &lowColor_r, &lowColor_g, &lowColor_b);

    float midColor_r, midColor_g, midColor_b;
    getRgbF(m_signalColors.getRgbMidColor(), &midColor_r, &midColor_g, &midColor_b);

    float highColor_r, highColor_g, highColor_b;
    getRgbF(m_signalColors.getRgbHighColor(), &highColor_r, &highColor_g, &highColor_b);""",
        """    QColor color;

    // Same mixer as the scrolling waveform, same numbers out of the skin, so
    // the card overview and the big waveform cannot drift apart.
    const WaveformBand3& band3 = m_signalColors.getBand3();""",
        "overview colour locals")

text = replace_once(text,
        """        unsigned char left = pWaveform->getAll(currentCompletion);
        unsigned char right = pWaveform->getAll(currentCompletion + 1);

        // Retrieve "raw" LMH values from waveform
        float low = static_cast<float>(pWaveform->getLow(currentCompletion));
        float mid = static_cast<float>(pWaveform->getMid(currentCompletion));
        float high = static_cast<float>(pWaveform->getHigh(currentCompletion));

        // Do matrix multiplication
        float red = low * lowColor_r + mid * midColor_r + high * highColor_r;
        float green = low * lowColor_g + mid * midColor_g + high * highColor_g;
        float blue = low * lowColor_b + mid * midColor_b + high * highColor_b;

        // Normalize and draw
        float max = math_max3(red, green, blue);
        if (max > 0.0) {
            color.setRgbF(red / max, green / max, blue / max);
            pPainter->setPen(color);
            pPainter->drawLine(QPointF(currentCompletion / 2, -left),
                    QPointF(currentCompletion / 2, 0));
        }

        // Retrieve "raw" LMH values from waveform
        low = static_cast<float>(pWaveform->getLow(currentCompletion + 1));
        mid = static_cast<float>(pWaveform->getMid(currentCompletion + 1));
        high = static_cast<float>(pWaveform->getHigh(currentCompletion + 1));

        // Do matrix multiplication
        red = low * lowColor_r + mid * midColor_r + high * highColor_r;
        green = low * lowColor_g + mid * midColor_g + high * highColor_g;
        blue = low * lowColor_b + mid * midColor_b + high * highColor_b;

        // Normalize and draw
        max = math_max3(red, green, blue);
        if (max > 0.0) {
            color.setRgbF(red / max, green / max, blue / max);
            pPainter->setPen(color);
            pPainter->drawLine(QPointF(currentCompletion / 2, 0),
                    QPointF(currentCompletion / 2, right));
        }""",
        """        // One half-column per channel, each with its own colour.
        for (int chn = 0; chn < 2; ++chn) {
            const int index = currentCompletion + chn;
            const float low = band3.low(pWaveform->getLow(index));
            const float mid = band3.mid(pWaveform->getMid(index));
            const float high = band3.high(pWaveform->getHigh(index));

            float red, green, blue;
            band3.color(low, mid, high, &red, &green, &blue);
            if (red <= 0.0f && green <= 0.0f && blue <= 0.0f) {
                continue;
            }

            float length = band3.heightFromBands()
                    ? band3.bandHeight(low, mid, high) * 255.0f
                    : static_cast<float>(pWaveform->getAll(index));
            if (length <= 0.0f) {
                continue;
            }
            if (chn == 0) {
                length = -length;
            }

            color.setRgbF(red, green, blue);
            pPainter->setPen(color);
            pPainter->drawLine(QPointF(currentCompletion / 2, 0),
                    QPointF(currentCompletion / 2, length));
        }""",
        "overview mix")
write(rel, text)

# ------------------------------------------------------- crossovers, if asked

low_hz = os.environ.get("BAND3_LOW_HZ", "").strip()
high_hz = os.environ.get("BAND3_HIGH_HZ", "").strip()
if low_hz or high_hz:
    low_hz = low_hz or "600.0"
    high_hz = high_hz or "4000.0"
    rel = "src/analyzer/analyzerwaveform.cpp"
    text = read(rel)
    text = replace_once(text,
            "constexpr double kLowMidFreqHz = 600.0;",
            "constexpr double kLowMidFreqHz = %s;" % low_hz,
            "low/mid crossover")
    text = replace_once(text,
            "constexpr double kMidHighFreqHz = 4000.0;",
            "constexpr double kMidHighFreqHz = %s;" % high_hz,
            "mid/high crossover")
    write(rel, text)

    # Stored waveforms from the old crossovers must not be drawn with the new
    # colours. An unknown version string is kept, not deleted, so nothing is
    # lost -- Mixxx simply re-analyses.
    tag = "3band-%s-%s" % (low_hz.replace(".0", ""), high_hz.replace(".0", ""))
    rel = "src/waveform/waveformfactory.h"
    text = read(rel)
    text = replace_once(text,
            '#define WAVEFORM_CURRENT_VERSION WAVEFORM_5_VERSION',
            '#define WAVEFORM_CURRENT_VERSION "Waveform-5.0-%s"' % tag,
            "waveform version")
    text = replace_once(text,
            '#define WAVEFORMSUMMARY_CURRENT_VERSION WAVEFORMSUMMARY_5_VERSION',
            '#define WAVEFORMSUMMARY_CURRENT_VERSION "WaveformSummary-5.0-%s"' % tag,
            "waveform summary version")
    print("crossovers moved to %s / %s Hz" % (low_hz, high_hz))
    write(rel, text)

print("patched")
PYEOF

if [ "${BAND3_PATCH_ONLY:-0}" = "1" ]; then
    echo "PATCH ONLY -- not building"
    exit 0
fi

dch --local "" --distribution unstable "Skin-driven three-band waveform mix" || true
sed -i "1s/^mixxx (.*)/mixxx ($VERSION)/" debian/changelog

dpkg-buildpackage -us -uc -b -nc -j4

cd ~/build
sudo apt-get install -y --allow-downgrades \
    ./mixxx_${VERSION}_arm64.deb ./mixxx-data_${VERSION}_all.deb
echo "installed $VERSION"
