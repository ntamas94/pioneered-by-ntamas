#!/bin/bash
# Rebuild Mixxx with the three-band waveform's gain, curve and mix read out of
# the skin instead of compiled into the binary.
#
# READ THIS FIRST: THE PREMISE THIS WAS WRITTEN ON IS WRONG
#
# This script was written to close what looked like the gap between Mixxx's
# three-band waveform and rekordbox's 3Band mode. The reasoning was that both
# programs store a low, a mid and a high level per column and mix three colours
# by those levels at draw time, so the difference in character had to be in the
# mix -- and Mixxx's mix ends by dividing the colour by its own largest
# component, which throws the level away. That reasoning was sound about Mixxx
# and wrong about rekordbox.
#
# rekordbox has no colour mix at all. Static analysis of rekordbox 6.8.7 --
# ntamas94/ddj1000-linux, docs/rekordbox-recon/waveform-3band-colour.md, commit
# c76237e -- found the detail waveform drawing each band as its own bar
# symmetric about the centre line, sorting the three by height, painting them
# largest first with no blending, and carrying a hand-written colour for each of
# the seven regions three overlapping bars can make:
#
#   low only #0055E1   mid only #FFA600   high only #FFFFFF
#   low+mid  #B4690A   low+high #D2DCFA   mid+high #FFF0D7
#   all three #F5EBD7
#
# Seven literals, seven mov instructions, no arithmetic. The pair colour depends
# only on which two bands overlap, never on which of the two is larger, and the
# core is a constant. So the divide-by-largest step is a fact about the renderer
# the box happened to be using, not the thing that separates Mixxx from
# rekordbox.
#
# THE CHEAP ROUTE COMES FIRST
#
# Mixxx already owns rekordbox's geometry. allshader::WaveformRendererFiltered
# draws one unblended bar per band, all centred on the lane, low then mid then
# high -- three nested rings, the same picture. Its paint order is fixed where
# rekordbox sorts by height, but over 15 423 044 analysed columns the low band
# is tallest in 78.8 per cent of them and high is tallest in under 3, so the two
# put the same rings in the same places nearly always. That makes Mixxx's three
# rings regions rather than bands, and the fix is three lines of skin XML
# against WaveformType 19 -- no C++:
#
#   <SignalLowColor>#0055e1</SignalLowColor>    outer rim, low alone
#   <SignalMidColor>#b4690a</SignalMidColor>    middle ring, low and mid
#   <SignalHighColor>#f5ebd7</SignalHighColor>  core, all three
#
# Pixel-exact in 78.8 per cent of columns. That route was taken: the colours
# went in, and then the band gains were measured rather than judged. Both
# programs' stored levels can be read -- rekordbox's PWV7 out of its 399
# analysis files, Mixxx's out of the zlib'd protobuf under ~/.mixxx/analysis --
# and painting each renderer's own columns its own way says rekordbox's lane is
# 47.8 per cent blue, 41.7 amber, 10.5 pale. Mixxx reaches 47.3 / 42.0 / 10.7
# at VisualGain_1/2/3 = 1.15 / 0.69 / 0.06, which is within about a point on
# all three. The lane is close enough that the difference is not what anyone
# would pick out of a line-up. docs/the-skin.md carries the numbers.
#
# WHAT THE CHEAP ROUTE LEFT
#
# Four things, and the biggest of them was not on the list of three.
#
#   The card overview is untouched by any of it. WOverview reads only
#   getVisualGain(All); drawNextPixmapPartLMH takes the three stored bytes and
#   draws three lines with no per-band gain anywhere. So the deck cards are
#   still drawn at equal gains, where the high band covers about 70 per cent of
#   the lane, and measuring the pixels of a card gives 89 to 99.8 per cent of
#   them cream, before and after the lane gains moved. A solid pale block where
#   rekordbox shows a blue-rimmed waveform. No setting reaches it. Of
#   everything below, this is the one worth a rebuild, and it is the cheapest:
#   give drawNextPixmapPartLMH the same per-band table the mixer below already
#   builds. That is a new anchor in woverview.cpp, next to the one this script
#   already cuts for the RGB overview path the box does not use.
#
# Then the three that were on the list. None of them is in the renderer this
# script patches -- if they are judged worth it the target moves from
# waveformrendererrgb.cpp to waveformrendererfiltered.cpp, and part of it has
# to be written rather than just run.
#
#   The pair colours. rekordbox has three and Mixxx's middle ring has one slot,
#   so the pale blue #D2DCFA never appears. About 5 per cent of columns. Fixing
#   it means giving WaveformRendererFiltered a seven-entry region table and
#   sorting the three bars by height before painting -- new code, not a knob.
#
#   The high-band curve, which is now measured and is larger than it looked.
#   On twelve tracks that turn out to be in both libraries -- confirmed by
#   correlating the low-band envelopes, r = 0.81 to 0.89 -- Mixxx draws its
#   high band ten times hotter relative to its own low band than rekordbox
#   draws its own. Only 2.2 of that ten is the bands differing in energy. The
#   rest is that Mixxx's analyser stores high as x^0.632, which lifts quiet
#   detail, where rekordbox draws 0.5 - 0.5*cos(pi*x), which crushes it. The
#   two disagree by 24x at a tenth of full scale, 2.8x at a quarter and 1.0x at
#   the top, so a single multiplier can sit at one point on that curve and
#   nowhere else: at the fitted 0.06 Mixxx's core is 4.6 per cent of the lane
#   in the median column against rekordbox's 1.4, and 18 per cent at the 90th
#   percentile against rekordbox's 33. rekordbox saves its cream for
#   transients; a linear gain spreads it. This is the one the mixer below
#   nearly covers -- it already gives every band a 256-entry table, and a
#   raised cosine is one more table shape beside the gamma -- but it would have
#   to be wired into the Filtered renderer, which does not go through the mixer
#   at all today.
#
#   Normalisation. rekordbox scales every waveform by the loudest column of that
#   track. Mixxx's Filtered renderer scales by a fixed 255 through VisualGain_0,
#   so a quiet track stays small. The overview already works around this with
#   OverviewNormalized 1; the scrolling lane has no equivalent.
#
# THE ONE THAT COLOUR CANNOT FIX
#
# The band edges. rekordbox's three bands overlap and are not a complementary
# crossover. Fitting the whole of rekordbox's own SINEWAVE.wav preset -- 859
# columns of a 435 Hz tone stepping down through a 16:1 amplitude range -- with
# one gain per band gives low 99.25 and mid 96.75 counts per unit amplitude at
# an RMS error of 1.2 counts. Both bands pass the same tone at full gain, to
# within 2.5 %. A complementary pair crosses at -3 dB in power or -6 dB in
# amplitude and can never be equal AND at full gain.
#
# Mixxx cannot be tuned into that shape, and this is now a proof rather than a
# suspicion. Its low band and mid band SHARE the corner kLowMidFreqHz: the
# lowpass falls through it as the bandpass rises through it, so at any one
# frequency the best the pair can do is meet at -3 dB each, exactly at the
# corner. Evaluating the stock filters at 435 Hz:
#
#     Mixxx      low -1.5 dB   mid -7.3 dB   high -64 dB
#     rekordbox  low  0.0 dB   mid -0.2 dB   high silent
#
# and sweeping the corner only trades one band against the other -- 300 Hz
# gives -6.9 / -1.1, 435 Hz gives -3.0 / -3.0, 800 Hz gives -0.8 / -15.3. So
# BAND3_LOW_HZ and BAND3_HIGH_HZ below cannot reach it however they are set.
# What would reach it is DECOUPLING the two corners: a lowpass at ~800 Hz for
# the low band and a bandpass starting at ~250 Hz for the mid band puts both
# within 1 dB of unity at 435 Hz. That is one extra constant in
# analyzerwaveform.cpp, not a new architecture.
#
# Two more differences that colour cannot reach, both measured over all 399
# analysed tracks. First, rekordbox's stored level is an ENVELOPE, not a
# per-column peak: instantaneous attack (up to 6x in one column) and a slow
# per-band release, whose column-to-column floor is 0.86 for low, 0.83 for mid
# and 0.62 for high -- about 90 ms to halve in the low band and 20 ms in the
# high. Mixxx's analyzer stores the plain per-column maximum with no release at
# all, so rekordbox smears every decay and Mixxx does not. Second, the skirts
# look shallow: an estimate off 7147 near-tonal columns puts rekordbox's low
# band near 6-7 dB per octave where a fourth-order Bessel is 24.
#
# What is still open is the rest of the curve, and one file answers it. The
# instrument is built and committed in the recon repository as
# tools/3band-sweep.py: 59 tones at 1/6 octave from 20 Hz to 16.25 kHz, one
# second each at a constant 0.85 peak amplitude, separated by 250 ms of digital
# silence -- the tones give the magnitude responses, the silences give the
# release. Ordinary music cannot substitute: a settled-tone estimator found
# ZERO usable runs in 201 tracks. The one step that cannot be automated is the
# import, because rekordbox has no command line and no watch folder. Until
# someone does File > Import > Import File... on that wav, 600 and 4000 stay.
#
# WHAT MIXXX 2.5.6 DOES, read out of the source:
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
#   by the largest of them. That division throws the level away and keeps only
#   the ratio, so a column ten decibels down is drawn at exactly the same
#   brightness as the loudest column in the track, and no column is ever white,
#   because white needs all three components at once and only the largest
#   survives. Column height comes from a fourth stored value, the overall
#   level, not from the three bands.
#
# That last paragraph is why WaveformType 17 washes a normal music column into
# one pale blue, and it is a real defect against rekordbox -- just not the one
# that had to be fixed, because the answer was to stop using that renderer.
# What this script leaves behind is the mechanism rather than the match: one
# shared mixer for both RGB paths, with the three base colours, a gain and a
# curve per band, the choice of mix and the height rule all read out of the
# skin's signal-colour block, and every default reproducing today's Mixxx
# exactly. Nothing changes until the skin says so. It is worth keeping because
# it is written, it compiles, and its per-band table is the natural home for
# rekordbox's raised cosine if the Filtered route turns out to need it.
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
# it exceeds 1. Additive and preserve let brightness follow level, which is
# what the RGB renderer is missing; neither of them is what rekordbox does,
# because rekordbox does not mix.
#
# Band levels arrive here as the bytes the analyzer stored, so gain and curve
# are 256-entry lookup tables built once at skin load, not pow() in the
# per-pixel loop. Four decks of scrolling waveform at 60 Hz on a Pi 4 cannot
# afford the pow().
#
# The crossovers are left alone by default, for the reason given at the top and
# for one more: changing them re-analyses every track in the library, which
# also changes what the DDJ-1000 jog screens draw. Set BAND3_LOW_HZ and
# BAND3_HIGH_HZ and this script moves them and bumps the stored-waveform
# version string, so Mixxx re-analyses instead of drawing stale data through
# new filters. That only moves two corners; making the bands overlap the way
# rekordbox's do would mean replacing the low-pass, band-pass and high-pass
# triple itself, which is a different patch against createFilters.
#
# THE VERDICT, for whoever reads this next
#
# The lane does not need this build. With the region colours and the measured
# gains it matches rekordbox on all three colour proportions to about a point,
# and put side by side with rekordbox's own render of the same track the only
# things left are the white transient spikes rekordbox draws and the smoothness
# its envelope gives the lobes. Nobody picks that out of a line-up without the
# reference next to it.
#
# The card overview does need it, and that is what this build is now for. It
# reads no per-band gain at all, so it stays at the equal gains where the high
# band covers about 70 per cent of the lane: 89 to 99.8 per cent of a deck
# card's coloured pixels are the cream, a solid pale block where rekordbox
# shows a blue-rimmed waveform. Rendering the same summary data with the gains
# it cannot read turns it back into something close to rekordbox. That is the
# one change here worth an hour of Pi, it needs no analyzer work, no
# re-analysis, and nothing that is blocked on the sweep.
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

# The card overview draws three nested lines per column, low then mid then
# high, in the same fixed order as the scrolling lane -- and reads no per-band
# gain at all, so it is stuck at the equal gains where Mixxx's high band covers
# the lane. Give it the mixer's per-band tables. The colours stay the LMH pens,
# which the skin already sets to the region colours; only the levels change.
text = replace_once(text,
        """    int currentCompletion = 0;
    for (currentCompletion = m_actualCompletion;
            currentCompletion < nextCompletion;
            currentCompletion += 2) {
        unsigned char lowNeg = pWaveform->getLow(currentCompletion);
        unsigned char lowPos = pWaveform->getLow(currentCompletion + 1);
        if (lowPos || lowNeg) {
            pPainter->setPen(lowColorPen);
            pPainter->drawLine(QPoint(currentCompletion / 2, -lowNeg),
                    QPoint(currentCompletion / 2, lowPos));
        }
    }

    for (currentCompletion = m_actualCompletion;
            currentCompletion < nextCompletion;
            currentCompletion += 2) {
        pPainter->setPen(midColorPen);
        pPainter->drawLine(QPoint(currentCompletion / 2,
                                   -pWaveform->getMid(currentCompletion)),
                QPoint(currentCompletion / 2,
                        pWaveform->getMid(currentCompletion + 1)));
    }

    for (currentCompletion = m_actualCompletion;
            currentCompletion < nextCompletion;
            currentCompletion += 2) {
        pPainter->setPen(highColorPen);
        pPainter->drawLine(QPoint(currentCompletion / 2,
                                   -pWaveform->getHigh(currentCompletion)),
                QPoint(currentCompletion / 2,
                        pWaveform->getHigh(currentCompletion + 1)));
    }""",
        """    const WaveformBand3& band3 = m_signalColors.getBand3();
    const auto extent = [](float level) {
        return static_cast<int>(math_clamp(level, 0.0f, 1.0f) * 255.0f + 0.5f);
    };

    int currentCompletion = 0;
    for (currentCompletion = m_actualCompletion;
            currentCompletion < nextCompletion;
            currentCompletion += 2) {
        const int lowNeg = extent(band3.low(pWaveform->getLow(currentCompletion)));
        const int lowPos = extent(band3.low(pWaveform->getLow(currentCompletion + 1)));
        if (lowPos || lowNeg) {
            pPainter->setPen(lowColorPen);
            pPainter->drawLine(QPoint(currentCompletion / 2, -lowNeg),
                    QPoint(currentCompletion / 2, lowPos));
        }
    }

    for (currentCompletion = m_actualCompletion;
            currentCompletion < nextCompletion;
            currentCompletion += 2) {
        pPainter->setPen(midColorPen);
        pPainter->drawLine(QPoint(currentCompletion / 2,
                                   -extent(band3.mid(pWaveform->getMid(currentCompletion)))),
                QPoint(currentCompletion / 2,
                        extent(band3.mid(pWaveform->getMid(currentCompletion + 1)))));
    }

    for (currentCompletion = m_actualCompletion;
            currentCompletion < nextCompletion;
            currentCompletion += 2) {
        pPainter->setPen(highColorPen);
        pPainter->drawLine(QPoint(currentCompletion / 2,
                                   -extent(band3.high(pWaveform->getHigh(currentCompletion)))),
                QPoint(currentCompletion / 2,
                        extent(band3.high(pWaveform->getHigh(currentCompletion + 1)))));
    }""",
        "overview LMH band levels")

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

# -nc keeps the object files, which is the whole point on a Pi where a clean
# build is hours -- but it also keeps debian/*.debhelper.log, and dh reads that
# log to decide which steps of the sequence it has already run. Left in place it
# makes dh skip dh_auto_build outright: the tree gets patched, a package gets
# built, the version gets bumped, and the binary inside it is the one from the
# previous run. Nothing warns you, and the version number says otherwise. This
# is how 2.5.6-0pioneered4 was first built, and it took a strings(1) check on
# the installed binary to notice. Deleting the log makes dh walk the sequence
# again; cmake still builds incrementally, because -nc left obj-*/ alone.
rm -f debian/*.debhelper.log

dpkg-buildpackage -us -uc -b -nc -j4

# Assert the new code actually reached the binary rather than trusting that a
# package came out. The failure above is silent and this is what catches it.
OBJDIR="obj-$(dpkg-architecture -qDEB_HOST_GNU_TYPE)"
if ! strings -a -el "$OBJDIR/mixxx" | grep -q Signal3BandMix; then
    echo "the built binary does not contain the patch -- refusing to install" >&2
    exit 1
fi

cd ~/build
sudo apt-get install -y --allow-downgrades \
    ./mixxx_${VERSION}_arm64.deb ./mixxx-data_${VERSION}_all.deb
echo "installed $VERSION"
