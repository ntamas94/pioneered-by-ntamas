#!/bin/bash
# Rebuild Mixxx with the scratch filter told how long its window really was.
#
# WHY
#
# Turn a DDJ-1000 platter one revolution and the track moves about 10 % further
# than the hand asked for. It is not the mapping's constants, not the wheel's
# resolution, not the jog daemon, and not the alpha-beta filter: the error is
# the same at any platter speed, which rules out every dynamic explanation, and
# it grows with CPU load, which rules out every constant one.
#
# It is one assumption in ControllerScriptInterfaceLegacy, and the file says so
# out loud:
#
#     // Use 1ms for the Alpha-Beta dt. We're assuming the OS actually gives us
#     // a 1ms timer.
#     constexpr int kScratchTimerMs = 1;
#     constexpr double kAlphaBetaDt = kScratchTimerMs / 1000.0;
#
# scratchEnable() initialises the filter with that fixed dt and starts a
# QObject timer of the same nominal period. scratchTick() only adds the wheel's
# ticks to an accumulator. scratchProcess(), once per firing, hands the filter
# the track time those ticks are worth, and AlphaBetaFilter::observation()
# divides by the dt it was given to get a velocity:
#
#     m_v = predicted_v + residual_x * m_beta / m_dt;
#
# So the numerator is a real distance measured over a real window and the
# denominator is a constant. If the timer actually fires every T, the window
# holds T's worth of ticks and the velocity comes out too large by exactly
# T / 1 ms. scratch2 is then applied by the engine over real time, so the deck
# travels too far by the same factor, at any speed the wheel is turned.
#
# The timer was measured on this box with a bare Qt event loop in a worker
# thread -- the same shape as the controller thread -- asking for
# startTimer(1):
#
#     idle              mean 1.0618 ms  median 1.0641  min 0.0054  max 2.5573
#     three cores busy  mean 1.1438 ms  median 1.0693  p99 2.3625
#
# Never 1.000 ms, and worse under load. Mixxx's own controller thread is also
# parsing MIDI at 1 kHz and running the mapping's JS in that loop, so its
# periods are worse again, and they can be read straight out of the bug: the
# excess travel *is* E[T] / 1 ms, so the 1.1502 a software drag measures on
# the stock binary says the mean period inside Mixxx is 1.1502 ms idle, and
# the 1.2036 under load says 1.2036 ms.
#
# WHAT THIS CHANGES, AND THE ONE THAT DID NOT WORK
#
# One branch of scratchProcess(): the observation is divided by a running mean
# of the timer's real period instead of by the 1 ms it was told.
#
# The obvious version of this -- divide by the window that just elapsed --
# was built first, measured, and is WRONG. It makes the error worse: the same
# 1x software drag that came back 1.1502 on the stock binary came back 1.3574
# on that one. Dividing per firing is only right if the ticks in a window
# arrived in proportion to its length, and they do not. Ticks reach the
# accumulator when the controller thread next gets round to its MIDI, in
# batches of seven, while the timer's own gaps on this box run from 5.4 us to
# 2.5 ms -- 0.56 % of them are the 5.4 us double-fires Qt produces. A batch
# divided by a 5 us window is a velocity spike, and what the filter then
# averages is E[dx/T], which by Jensen is at or above E[dx]/E[T] and here was
# well above it.
#
# The error being corrected is in the *mean* period, so the mean is what the
# divisor has to be. With a divisor that is nearly constant the filter
# averages E[dx]/E[T], which is the true rate whatever the joint distribution
# of ticks and windows -- the property the instantaneous divisor lacks. The
# smoothing is an EWMA at 1/64 per firing, about 70 ms, and it is deliberately
# not reset between scratches: the scheduler does not change when a hand
# leaves the platter, so the second gesture starts from an estimate that is
# already right.
#
# The other two observation branches are deliberately left alone. Ramp, brake,
# spinback and soft start feed the filter a *target rate* already expressed
# against kAlphaBetaDt -- m_rampTo * m_rampFactor with m_rampFactor == 0.001,
# and m_rampTo * kAlphaBetaDt -- so they mean the same thing whatever the
# window was, and scaling them would break them. Only the tick branch measures
# a distance over a window.
#
# This fixes every controller that uses engine.scratchEnable on every Mixxx,
# not just this jog, which is why it is done here rather than worked around in
# the mapping.
#
# Log: ~/build/scratchdt.log
set -euo pipefail

SOURCE=${SCRATCHDT_SOURCE:-$HOME/build/mixxx-2.5.6}
VERSION=${SCRATCHDT_VERSION:-2.5.6-0pioneered6}

if [ ! -d "$SOURCE" ]; then
    echo "no source tree at $SOURCE" >&2
    echo "That tree is upstream Mixxx 2.5.6 with Debian's debian/ directory" >&2
    echo "from mixxx 2.5.0+dfsg-3 copied in, BUILD_BENCH and ENGINEPRIME" >&2
    echo "turned off in debian/rules, and pioneered-mixxx.patch applied." >&2
    exit 1
fi

cd "$SOURCE"

python3 - <<'PYEOF'
import pathlib

root = pathlib.Path(".")
CPP = "src/controllers/scripting/legacy/controllerscriptinterfacelegacy.cpp"
HDR = "src/controllers/scripting/legacy/controllerscriptinterfacelegacy.h"


def read(rel):
    return (root / rel).read_text(encoding="utf-8")


def write(rel, text):
    (root / rel).write_text(text, encoding="utf-8")


def replace_once(text, old, new, what):
    assert old in text, "anchor gone: " + what
    assert text.count(old) == 1, "anchor is not unique: " + what
    return text.replace(old, new, 1)


def replace_either(text, pristine, first, new, what):
    """Apply a hunk to a pristine tree, or over the first attempt at it.

    The first version of this script divided by the window that had just
    elapsed, and that tree exists on the box it was built on. Three of its
    hunks are replaced here rather than reversed; the other four are what this
    version wants too, unchanged.
    """
    if first is not None and first in text:
        return replace_once(text, first, new, what + ", over the first attempt")
    return replace_once(text, pristine, new, what)


header, text = read(HDR), read(CPP)
if "m_meanScratchDt" in header and "m_meanScratchDt" in text:
    # Re-running to rebuild is a normal thing to want, and the anchors are
    # gone by then. Only a tree patched in one file and not the other is a
    # problem, and that one cannot be repaired by running this again.
    print("already patched -- building what is there")
    raise SystemExit(0)
assert "m_meanScratchDt" not in header + text, "half-patched -- undo it by hand"

# ------------------------------------------------------------- the header

if "m_lastScratchProcess" not in header:
    header = replace_once(header,
            "    QVarLengthArray<mixxx::Duration> m_lastMovement;",
            "    QVarLengthArray<mixxx::Duration> m_lastMovement;\n"
            "    // When scratchProcess() last ran for each deck, so the window it\n"
            "    // hands the filter can be measured rather than assumed.\n"
            "    QVarLengthArray<mixxx::Duration> m_lastScratchProcess;",
            "m_lastScratchProcess declaration")

header = replace_once(header,
        "    QVarLengthArray<mixxx::Duration> m_lastScratchProcess;",
        "    QVarLengthArray<mixxx::Duration> m_lastScratchProcess;\n"
        "    // A running mean of what that timer's period really is. Never\n"
        "    // reset: the scheduler does not change when a hand leaves the\n"
        "    // platter, so the next gesture starts from an estimate that is\n"
        "    // already right.\n"
        "    QVarLengthArray<double> m_meanScratchDt;",
        "m_meanScratchDt declaration")

# ------------------------------------------------------------- the source

FIRST_CONSTS = (
        "// The shortest window scratchProcess() will believe. The measured\n"
        "// window is a divisor, so a timer that appeared to fire twice in the\n"
        "// same instant would turn a handful of ticks into an enormous\n"
        "// velocity. An eighth of the nominal period is far below anything a\n"
        "// scheduler has ever produced here.\n"
        "constexpr double kMinScratchDt = kAlphaBetaDt / 8;")
NEW_CONSTS = (
        "// How fast the running estimate of the scratch timer's real period\n"
        "// follows it: an EWMA at this weight per firing, so about seventy\n"
        "// milliseconds. It is meant to be slow. The instantaneous window is\n"
        "// the wrong divisor -- the comment in scratchProcess says why -- and\n"
        "// the whole value of the estimate is that it is nearly constant while\n"
        "// the thing it divides is not.\n"
        "constexpr double kScratchDtSmoothing = 1.0 / 64;\n"
        "// A sample longer than this is not a period. It is a stall, or a\n"
        "// timer that was only just started, and it is clamped on the way in.\n"
        "constexpr double kMaxScratchDt = 0.020;")

text = replace_either(text,
        "constexpr double kBrakeRampToRate = 0.01;",
        "constexpr double kBrakeRampToRate = 0.01;\n" + FIRST_CONSTS,
        "constexpr double kBrakeRampToRate = 0.01;\n" + NEW_CONSTS,
        "the smoothing constants")

if "m_lastScratchProcess.resize" not in text:
    text = replace_once(text,
            "    m_lastMovement.resize(kDecks);",
            "    m_lastMovement.resize(kDecks);\n"
            "    m_lastScratchProcess.resize(kDecks);",
            "constructor resize")

text = replace_once(text,
        "    m_lastScratchProcess.resize(kDecks);",
        "    m_lastScratchProcess.resize(kDecks);\n"
        "    m_meanScratchDt.resize(kDecks);",
        "constructor resize, the mean")

text = replace_once(text,
        "        m_dx[i] = 0.0;",
        "        m_dx[i] = 0.0;\n"
        "        m_meanScratchDt[i] = kAlphaBetaDt;",
        "constructor init")

if "m_lastScratchProcess[deck] = mixxx::Time::elapsed();" not in text:
    text = replace_once(text,
            "    m_dx[deck] = 1.0 / intervalsPerSecond;\n"
            "    m_intervalAccumulator[deck] = 0.0;",
            "    m_dx[deck] = 1.0 / intervalsPerSecond;\n"
            "    m_intervalAccumulator[deck] = 0.0;\n"
            "    m_lastScratchProcess[deck] = mixxx::Time::elapsed();",
            "scratchEnable window start")
    text = replace_once(text,
            "    // setup timer and set scratch2\n"
            "    timerId = startTimer(kScratchTimerMs);",
            "    // setup timer and set scratch2\n"
            "    m_lastScratchProcess[deck] = mixxx::Time::elapsed();\n"
            "    timerId = startTimer(kScratchTimerMs);",
            "brake window start")
    text = replace_once(text,
            "    // setup timer, start playing and set scratch2\n"
            "    timerId = startTimer(kScratchTimerMs);",
            "    // setup timer, start playing and set scratch2\n"
            "    m_lastScratchProcess[deck] = mixxx::Time::elapsed();\n"
            "    timerId = startTimer(kScratchTimerMs);",
            "softStart window start")

FIRST_WINDOW = (
        "    // How long the window about to be handed to the filter really was.\n"
        "    // The filter was told kAlphaBetaDt at init and divides by that to\n"
        "    // turn a distance into a velocity, but the window is whatever\n"
        "    // startTimer(kScratchTimerMs) delivered, and that is a request the\n"
        "    // scheduler answers when it can -- 1.07 ms idle and 1.14 ms with\n"
        "    // three cores busy, measured on a Raspberry Pi 4. Every fraction of\n"
        "    // overrun is ticks divided by time that never passed, so the deck\n"
        "    // travels too far by exactly the ratio, at any platter speed.\n"
        "    const mixxx::Duration processTime = mixxx::Time::elapsed();\n"
        "    const double realDt =\n"
        "            (processTime - m_lastScratchProcess[deck]).toDoubleSeconds();\n"
        "    m_lastScratchProcess[deck] = processTime;\n"
        "\n"
        "    // Give the filter a data point:\n")
NEW_WINDOW = (
        "    // What the timer's period really is, kept as a running mean.\n"
        "    //\n"
        "    // The filter was told kAlphaBetaDt at init and divides by it to turn\n"
        "    // a distance into a velocity, but the window is whatever\n"
        "    // startTimer(kScratchTimerMs) delivered, and that is a request the\n"
        "    // scheduler answers when it can. A bare Qt event loop on a Raspberry\n"
        "    // Pi 4 gives 1.06 ms of it idle; inside Mixxx, where the same loop\n"
        "    // also parses the wheel's 1 kHz MIDI and runs the mapping's JS, it\n"
        "    // is 1.15 ms idle and 1.20 ms with three cores busy. That overrun is\n"
        "    // ticks divided by time that never passed, and the deck travels too\n"
        "    // far by exactly the ratio, at any platter speed.\n"
        "    //\n"
        "    // The mean of it, and not the window that has just elapsed. Dividing\n"
        "    // by that would be right only if the ticks in it had arrived in\n"
        "    // proportion to its length, and they do not: they arrive when this\n"
        "    // thread next gets round to its MIDI, in batches, while the timer's\n"
        "    // own gaps include the five microsecond double-fires Qt produces for\n"
        "    // half a percent of firings. A batch divided by a five microsecond\n"
        "    // window is a velocity spike, and what the filter then averages is\n"
        "    // E[dx/T], which Jensen puts above the E[dx]/E[T] that is wanted. It\n"
        "    // was built that way first and measured: 1.3574 times as far as the\n"
        "    // ticks were worth, against 1.1502 for leaving it alone.\n"
        "    const mixxx::Duration processTime = mixxx::Time::elapsed();\n"
        "    const double realDt =\n"
        "            (processTime - m_lastScratchProcess[deck]).toDoubleSeconds();\n"
        "    m_lastScratchProcess[deck] = processTime;\n"
        "    if (realDt > 0.0) {\n"
        "        const double sample =\n"
        "                realDt < kMaxScratchDt ? realDt : kMaxScratchDt;\n"
        "        m_meanScratchDt[deck] +=\n"
        "                (sample - m_meanScratchDt[deck]) * kScratchDtSmoothing;\n"
        "    }\n"
        "\n"
        "    // Give the filter a data point:\n")

text = replace_either(text,
        "    // Give the filter a data point:\n",
        FIRST_WINDOW, NEW_WINDOW, "the running mean")

PRISTINE_OBS = (
        "        // This will (and should) be 0 if no net ticks have been accumulated\n"
        "        // (i.e. the wheel is stopped)\n"
        "        filter->observation(m_dx[deck] * m_intervalAccumulator[deck]);")
FIRST_OBS = (
        "        // This will (and should) be 0 if no net ticks have been accumulated\n"
        "        // (i.e. the wheel is stopped)\n"
        "        //\n"
        "        // Scaled into the window the filter believes in. This is the only\n"
        "        // branch that measures anything: the two above feed it a target\n"
        "        // rate already expressed against kAlphaBetaDt, which means the\n"
        "        // same thing however long the window was, so they are left alone.\n"
        "        const double window = realDt > kMinScratchDt ? realDt : kMinScratchDt;\n"
        "        filter->observation(m_dx[deck] * m_intervalAccumulator[deck] *\n"
        "                (kAlphaBetaDt / window));")
NEW_OBS = (
        "        // This will (and should) be 0 if no net ticks have been accumulated\n"
        "        // (i.e. the wheel is stopped)\n"
        "        //\n"
        "        // Scaled into the window the filter believes in. This is the only\n"
        "        // branch that measures anything: the two above feed it a target\n"
        "        // rate already expressed against kAlphaBetaDt, which means the\n"
        "        // same thing however long the window was, so they are left alone.\n"
        "        filter->observation(m_dx[deck] * m_intervalAccumulator[deck] *\n"
        "                (kAlphaBetaDt / m_meanScratchDt[deck]));")

text = replace_either(text, PRISTINE_OBS, FIRST_OBS, NEW_OBS, "the scaled observation")

# Both files together, once every anchor has been found: a half-patched tree
# would refuse to be patched again and would have to be undone by hand.
write(HDR, header)
write(CPP, text)
print("patched")
PYEOF

if [ "${SCRATCHDT_PATCH_ONLY:-0}" = "1" ]; then
    echo "PATCH ONLY -- not building"
    exit 0
fi

DEBEMAIL="dj@pidj" DEBFULLNAME="ntamas" dch --local "" --distribution unstable \
    "Scratch filter divides by the mean period, not the nominal one" || true
sed -i "1s/^mixxx (.*)/mixxx ($VERSION)/" debian/changelog

# -nc keeps the object files, which is the whole point on a Pi where a clean
# build is hours -- but it also makes dpkg-buildpackage skip "debian/rules
# build" and go straight to "debian/rules binary", and dh then decides for
# itself whether the build sequence still needs running. It decides from two
# files, and both have to go:
#
#   debian/*.debhelper.log      which dh_ commands of the sequence have run
#   debian/debhelper-build-stamp  that the whole build sequence is done
#
# The stamp is the one that bites. Left in place, dh binary starts at dh_prep:
# no dh_auto_configure, no dh_auto_build, nothing compiled at all. The tree
# gets patched, a package gets built, the version gets bumped, and the binary
# inside it is the one from the previous run. Nothing warns you, and the
# version number says otherwise -- this happened here on the first run of this
# script, with the .cpp two days newer than the .o inside the package.
# Deleting both makes dh walk the sequence again; cmake still builds
# incrementally, because -nc left obj-*/ alone.
rm -f debian/debhelper-build-stamp debian/*.debhelper.log

STAMP=$(mktemp)
# noautodbgsym because the debug package is xz over half a gigabyte of DWARF
# and takes longer to compress on this box than the recompile and the link put
# together -- ten of the twenty minutes a one-file change costs. Nothing here
# has ever opened it.
DEB_BUILD_OPTIONS=noautodbgsym nice -n 15 dpkg-buildpackage -us -uc -b -nc -j3

# Assert the new code actually reached the package rather than trusting that a
# package came out. Two checks, because the silent failure above defeats one of
# them at a time: the translation unit has to have been recompiled since this
# run started, and the binary inside the package has to differ from the one
# already installed.
OBJDIR="obj-$(dpkg-architecture -qDEB_HOST_GNU_TYPE)"
if [ -z "$(find "$OBJDIR" -name controllerscriptinterfacelegacy.cpp.o \
        -newer "$STAMP" -print -quit)" ]; then
    echo "controllerscriptinterfacelegacy.cpp was not recompiled -- refusing" >&2
    exit 1
fi
NEW=$(dpkg-deb --fsys-tarfile "../mixxx_${VERSION}_arm64.deb" \
        | tar -xO ./usr/bin/mixxx | md5sum | cut -d' ' -f1)
OLD=$(md5sum /usr/bin/mixxx | cut -d' ' -f1)
if [ "$NEW" = "$OLD" ]; then
    echo "the packaged binary is byte for byte the installed one -- refusing" >&2
    exit 1
fi
rm -f "$STAMP"

cd ~/build
sudo apt-get install -y --allow-downgrades \
    ./mixxx_${VERSION}_arm64.deb ./mixxx-data_${VERSION}_all.deb
echo "installed $VERSION"
