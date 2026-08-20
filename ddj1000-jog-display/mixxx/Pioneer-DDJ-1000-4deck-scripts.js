// Pioneer DDJ-1000 — four-deck Mixxx mapping, script half.
//
// The XML half handles everything that is a plain control-to-control binding.
// This file covers what needs logic: the jog wheels, library browsing, pad
// colours, and the jog dial displays.
//
// Deck number comes from the MIDI channel. AlphaTheta's MIDI message list
// specifies deck controls on channels 1..4 with identical note numbers, and
// the controller sends on the channel of whichever deck the physical section
// is currently driving — so `status & 0x0F` is the deck index throughout, and
// no deck-switching logic is needed here.
//
// Every address below comes from "DDJ-1000 List of MIDI message version 1.00".

var PioneerDDJ1000 = {};

// -- tunables -------------------------------------------------------------

// Jog feel. alpha/beta drive Mixxx's scratch filter; the ratio is the usual
// starting point and only matters when a platter is actually touched.
PioneerDDJ1000.jogAlpha = 1.0 / 8;
PioneerDDJ1000.jogBeta = PioneerDDJ1000.jogAlpha / 32;

// Measured on the hardware rather than assumed: two slow revolutions of the
// platter add up to 25736 of these, so a revolution is a little under 12900.
// The 2048 that was here made every gesture six times too fast.
PioneerDDJ1000.jogTicksPerRevolution = 12900;
PioneerDDJ1000.jogVinylRpm = 33 + 1 / 3;

// Seconds per platter revolution at 33 1/3 RPM. The position bar on the jog
// display is an angle, so it has to spin like a record rather than track
// progress through the file.
PioneerDDJ1000.secondsPerRevolution = 60 / PioneerDDJ1000.jogVinylRpm;

// Everything the jog drives is expressed per revolution, not per tick: the
// platter's resolution is the sort of number nobody should have to sprinkle
// through a dozen constants.
PioneerDDJ1000.jogBendPerRevolution = 200;
PioneerDDJ1000.jogGridBpmPerRevolution = 4;
PioneerDDJ1000.jogGridSlideSteps = 32;

// Steady blue for a set hot cue. Pads take a colour number in 1..127.
PioneerDDJ1000.hotcuePadColor = 0x2A;
PioneerDDJ1000.hotcuePadColorOff = 0x00;

// Display refresh. 50 ms is smooth enough for the rotating position bar
// without saturating the MIDI link across four decks.
PioneerDDJ1000.displayIntervalMs = 50;

// [Controls],PositionDisplay: 0 elapsed, 1 remaining, 2 both.
PioneerDDJ1000.timeModeElapsed = 0;
PioneerDDJ1000.timeModeRemaining = 1;
PioneerDDJ1000.timeModeBoth = 2;

PioneerDDJ1000.decks = [1, 2, 3, 4];

// -- display addresses (MIDI-OUT, "for JOG display") ----------------------

PioneerDDJ1000.display = {
    positionBarMsb: 0x14,
    bpmMsb: 0x15,
    speedMsb: 0x16,
    cueMarkerMsb: 0x17,
    // 14-bit CCs put the LSB 0x20 above the MSB.
    lsbOffset: 0x20,

    timeMinute: 0x42,
    timeSecond: 0x43,
    timeMode: 0x44,
    keyValue: 0x49,
    keyVariation: 0x4A,
    syncMaster: 0x59,
    syncState: 0x5A,
    ringLed: 0x5B,
    showInfo: 0x5D,
};

// The jog display's key codes, from footnote *3 of the MIDI message list.
// Index is the Data 2 byte; 0x00 means "no key".
PioneerDDJ1000.keyCodes = [
    "---", "C", "Am", "Db", "Bbm", "D", "Bm", "Eb", "Cm", "E", "Dbm", "F",
    "Dm", "F#", "Ebm", "G", "Em", "Ab", "Fm", "A", "F#m", "Bb", "Gm", "B", "Abm",
];

PioneerDDJ1000.connections = [];
PioneerDDJ1000.displayTimer = 0;
// Last value sent per deck per address, so unchanged values are not resent.
PioneerDDJ1000.lastSent = {};

// -- lifecycle ------------------------------------------------------------

// The jog screens want the track's artwork and waveform, which only the bridge
// daemon can build (it needs the file). Mixxx's scripting API exposes no path,
// so announce the duration on load and let the daemon match it against the
// library database. A private manufacturer id (0x7D) keeps this off the wire to
// the controller -- the bridge intercepts it.
PioneerDDJ1000.announceTrack = function (deck) {
    var group = "[Channel" + deck + "]";
    var ms = Math.round(engine.getValue(group, "duration") * 1000);
    if (!engine.getValue(group, "track_loaded") || ms <= 0) {
        ms = 0;
    }
    midi.sendSysexMsg([0xF0, 0x7D, deck - 1,
        (ms >> 21) & 0x7F, (ms >> 14) & 0x7F, (ms >> 7) & 0x7F, ms & 0x7F, 0xF7], 8);
};

// Announced from the display timer rather than from a track_loaded callback:
// the callback fires before the duration is readable, so it would report zero.
PioneerDDJ1000.announcedMs = {};
PioneerDDJ1000.announcedAt = {};
PioneerDDJ1000.announceRepeatMs = 5000;

PioneerDDJ1000.announceIfChanged = function (deck) {
    var group = "[Channel" + deck + "]";
    var ms = engine.getValue(group, "track_loaded")
        ? Math.round(engine.getValue(group, "duration") * 1000)
        : 0;
    // Repeat even when nothing changed: the daemon on the other end may have
    // restarted, and it has no other way to learn what is on the decks.
    var now = Date.now();
    var due = !PioneerDDJ1000.announcedAt[deck]
        || now - PioneerDDJ1000.announcedAt[deck] > PioneerDDJ1000.announceRepeatMs;
    if (PioneerDDJ1000.announcedMs[deck] === ms && !due) {
        return;
    }
    PioneerDDJ1000.announcedMs[deck] = ms;
    PioneerDDJ1000.announcedAt[deck] = now;
    midi.sendSysexMsg([0xF0, 0x7D, deck - 1,
        (ms >> 21) & 0x7F, (ms >> 14) & 0x7F, (ms >> 7) & 0x7F, ms & 0x7F, 0xF7], 8);
};

// The jog screens want the playhead to the millisecond, but the display notes
// only carry whole seconds, so the daemon had to run its own clock between
// them and the needle shivered once a second. Send the real figure instead;
// bit 0x10 of the deck byte marks it as a position rather than a duration.
// Where the grid starts and what key the track is in. The screen lines its
// beat scale up against the first beat, so a grid that starts at zero puts the
// scale out by however far into the bar the track really begins. Mixxx has no
// "first beat" control, but any beat modulo the beat interval is the same
// thing on a constant grid. Bit 0x20 of the deck byte marks the message.
PioneerDDJ1000.gridInfo = {};

PioneerDDJ1000.sendGridInfo = function (deck) {
    var group = "[Channel" + deck + "]";
    var bpm = engine.getValue(group, "bpm");
    var rate = engine.getValue(group, "track_samplerate") || 44100;
    var beat = engine.getValue(group, "beat_closest");
    var firstBeat = 0;
    if (bpm > 0 && beat >= 0) {
        var interval = 60000 / bpm;
        // beat_closest counts engine samples, which are frames times two.
        var beatMs = beat / (rate * 2) * 1000;
        firstBeat = Math.round(((beatMs % interval) + interval) % interval);
    }
    firstBeat = Math.min(firstBeat, 16383);

    var key = PioneerDDJ1000.ddjKeyCode(engine.getValue(group, "key"));
    var packed = firstBeat + ":" + key;
    if (PioneerDDJ1000.gridInfo[deck] === packed) {
        return;
    }
    PioneerDDJ1000.gridInfo[deck] = packed;
    midi.sendSysexMsg([0xF0, 0x7D, 0x20 | (deck - 1),
        (firstBeat >> 7) & 0x7F, firstBeat & 0x7F, key, 0x00, 0xF7], 8);
};

// Mixxx numbers the keys chromatically, 1..12 major from C and 13..24 minor
// from C. The jog display has its own order: majors on the odd codes from C,
// minors on the even ones from A.
PioneerDDJ1000.ddjKeyCode = function (value) {
    var key = Math.round(value);
    if (key >= 1 && key <= 12) {
        return 2 * (key - 1) + 1;
    }
    if (key >= 13 && key <= 24) {
        return 2 * (((key - 13) - 9 + 12) % 12) + 2;
    }
    return 0;
};

// The running loop. The screen shades the looped stretch of the waveform and
// moves its marker to the loop in, so it wants both ends in milliseconds.
PioneerDDJ1000.loopState = {};

PioneerDDJ1000.sendLoop = function (deck) {
    var group = "[Channel" + deck + "]";
    var rate = (engine.getValue(group, "track_samplerate") || 44100) * 2;
    var on = engine.getValue(group, "loop_enabled") > 0;
    var start = engine.getValue(group, "loop_start_position");
    var end = engine.getValue(group, "loop_end_position");
    var startMs = 0;
    var endMs = 0;
    if (on && start >= 0 && end > start) {
        startMs = Math.round(start / rate * 1000);
        endMs = Math.round(end / rate * 1000);
    } else {
        on = false;
    }

    var packed = (on ? 1 : 0) + ":" + startMs + ":" + endMs;
    if (PioneerDDJ1000.loopState[deck] === packed) {
        return;
    }
    PioneerDDJ1000.loopState[deck] = packed;
    midi.sendSysexMsg([0xF0, 0x7D, 0x40 | (deck - 1), on ? 0x01 : 0x00,
        (startMs >> 21) & 0x7F, (startMs >> 14) & 0x7F, (startMs >> 7) & 0x7F, startMs & 0x7F,
        (endMs >> 21) & 0x7F, (endMs >> 14) & 0x7F, (endMs >> 7) & 0x7F, endMs & 0x7F,
        0xF7], 13);
};

PioneerDDJ1000.sendPosition = function (deck, elapsedMs) {
    var ms = Math.max(0, Math.min(0xFFFFFFF, Math.round(elapsedMs)));
    midi.sendSysexMsg([0xF0, 0x7D, 0x10 | (deck - 1),
        (ms >> 21) & 0x7F, (ms >> 14) & 0x7F, (ms >> 7) & 0x7F, ms & 0x7F, 0xF7], 8);
};

PioneerDDJ1000.init = function () {
    // The jog displays are unlocked by the djbox-ddj-handshake daemon, not
    // from here: the 66-byte authentication response has to reach the unit in
    // one USB transfer, and Mixxx's MIDI output splits it.

    PioneerDDJ1000.decks.forEach(function (deck) {
        var group = "[Channel" + deck + "]";

        PioneerDDJ1000.lastSent[deck] = {};

        for (var pad = 1; pad <= 8; pad++) {
            PioneerDDJ1000.connectHotcueLed(deck, pad);
        }

        PioneerDDJ1000.connectLoopState(deck);

    });

    PioneerDDJ1000.skipBothTimeMode();

    PioneerDDJ1000.displayTimer = engine.beginTimer(
        PioneerDDJ1000.displayIntervalMs,
        PioneerDDJ1000.updateDisplays
    );

    // Once the panel has answered, arm soft takeover
    // so the knobs stay honest later too -- a section switched to another deck
    // leaves the panel showing one deck's settings while it drives another's,
    // and without this the first touch snaps the value across.
    engine.beginTimer(8000, PioneerDDJ1000.armSoftTakeover, true);
};

// The LOOP IN and LOOP OUT buttons change meaning once a loop is running --
// they halve and double it instead of setting the ends -- and the unit only
// knows to send those other notes if the host tells it a loop is active. On
// the global channel, note 0x04 plus the deck.
PioneerDDJ1000.connectLoopState = function (deck) {
    var connection = engine.makeConnection("[Channel" + deck + "]", "loop_enabled",
        function (value) {
            midi.sendShortMsg(0x9F, 0x03 + deck, value > 0 ? 0x7F : 0x00);
        });
    if (connection) {
        PioneerDDJ1000.connections.push(connection);
        connection.trigger();
    }
};

PioneerDDJ1000.armSoftTakeover = function () {
    PioneerDDJ1000.decks.forEach(function (deck) {
        var group = "[Channel" + deck + "]";
        engine.softTakeover(group, "rate", true);
        engine.softTakeover(group, "pregain", true);

        var eq = "[EqualizerRack1_" + group + "_Effect1]";
        engine.softTakeover(eq, "parameter1", true);
        engine.softTakeover(eq, "parameter2", true);
        engine.softTakeover(eq, "parameter3", true);
        engine.softTakeover("[QuickEffectRack1_" + group + "]", "super1", true);
    });
};

// Clicking Mixxx's time readout cycles elapsed -> remaining -> both. The XZ
// only has the first two, so bounce straight past "both" and keep the readout
// to a single number. This lives in the mapping because the skin cannot
// override a compiled widget's click handler.
PioneerDDJ1000.skipBothTimeMode = function () {
    var connection = engine.makeConnection("[Controls]", "ShowDurationRemaining", function (value) {
        if (value === PioneerDDJ1000.timeModeBoth) {
            engine.setValue("[Controls]", "ShowDurationRemaining", PioneerDDJ1000.timeModeElapsed);
        }
    });

    if (connection) {
        PioneerDDJ1000.connections.push(connection);
        // Land on remaining at startup rather than inheriting "both".
        if (engine.getValue("[Controls]", "ShowDurationRemaining") === PioneerDDJ1000.timeModeBoth) {
            engine.setValue("[Controls]", "ShowDurationRemaining", PioneerDDJ1000.timeModeElapsed);
        }
    }
};

PioneerDDJ1000.shutdown = function () {
    if (PioneerDDJ1000.displayTimer) {
        engine.stopTimer(PioneerDDJ1000.displayTimer);
        PioneerDDJ1000.displayTimer = 0;
    }

    PioneerDDJ1000.connections.forEach(function (connection) {
        connection.disconnect();
    });
    PioneerDDJ1000.connections = [];

    PioneerDDJ1000.decks.forEach(function (deck) {
        // Blank the display and turn the ring off, so the unit does not sit
        // showing stale numbers after Mixxx quits.
        PioneerDDJ1000.sendNote(deck, PioneerDDJ1000.display.showInfo, 0x7F);
        PioneerDDJ1000.sendNote(deck, PioneerDDJ1000.display.ringLed, 0x00);
    });
};

// -- low level ------------------------------------------------------------

PioneerDDJ1000.deckFromStatus = function (status) {
    // 0x90..0x93 and 0xB0..0xB3 both carry the deck in the low nibble.
    return (status & 0x0F) + 1;
};

PioneerDDJ1000.groupFromStatus = function (status) {
    return "[Channel" + PioneerDDJ1000.deckFromStatus(status) + "]";
};

// Pad note status per deck: channels 8/10/12/14.
PioneerDDJ1000.padStatusForDeck = function (deck) {
    return 0x97 + (deck - 1) * 2;
};

PioneerDDJ1000.sendNote = function (deck, note, value) {
    midi.sendShortMsg(0x90 + deck - 1, note, value & 0x7F);
};

// Send a 14-bit value as MSB/LSB on a CC pair, skipping unchanged values.
// `always` skips the change filter. The jog screens are also fed from this
// stream by the bridge daemon, which has no other source for the deck state, so
// values it needs (BPM) have to keep arriving even when they do not change --
// otherwise a daemon that starts mid-track never learns them.
PioneerDDJ1000.send14 = function (deck, msbCc, value, max, always) {
    var clamped = Math.max(0, Math.min(max, Math.round(value)));
    var cache = PioneerDDJ1000.lastSent[deck];
    if (!always && cache[msbCc] === clamped) {
        return;
    }
    cache[msbCc] = clamped;

    var status = 0xB0 + deck - 1;
    midi.sendShortMsg(status, msbCc, (clamped >> 7) & 0x7F);
    midi.sendShortMsg(status, msbCc + PioneerDDJ1000.display.lsbOffset, clamped & 0x7F);
};

PioneerDDJ1000.sendNoteIfChanged = function (deck, note, value) {
    var cache = PioneerDDJ1000.lastSent[deck];
    var clamped = value & 0x7F;
    if (cache["n" + note] === clamped) {
        return;
    }
    cache["n" + note] = clamped;
    PioneerDDJ1000.sendNote(deck, note, clamped);
};

// -- jog wheel ------------------------------------------------------------

// The platter is heavy and free-running: let go of it mid-spin and it keeps
// turning, and the record should keep turning with it. So letting go does not
// end the scratch -- the platter coming to rest does, and the check for that
// rides on the display timer rather than a timer of its own.
PioneerDDJ1000.jogTouched = {};
PioneerDDJ1000.jogLastTick = {};
PioneerDDJ1000.jogSpeed = {};

// A wheel turning at playing speed sends this many ticks a second. Below a
// fraction of it the throw has run out, and the deck should be handed back to
// normal playback while it is still moving -- waiting for the wheel to stop
// dead first means the record stops dead with it.
PioneerDDJ1000.jogTicksPerSecond = function () {
    return PioneerDDJ1000.jogTicksPerRevolution / PioneerDDJ1000.secondsPerRevolution;
};
PioneerDDJ1000.jogReleaseFraction = 0.25;
PioneerDDJ1000.jogSpinDownMs = 80;

PioneerDDJ1000.jogTouch = function (channel, control, value, status) {
    var deck = PioneerDDJ1000.deckFromStatus(status);

    if (value > 0) {
        PioneerDDJ1000.jogTouched[deck] = true;
        PioneerDDJ1000.jogSpeed[deck] = undefined;
        engine.scratchEnable(
            deck,
            PioneerDDJ1000.jogTicksPerRevolution,
            PioneerDDJ1000.jogVinylRpm,
            PioneerDDJ1000.jogAlpha,
            PioneerDDJ1000.jogBeta,
            true
        );
    } else {
        PioneerDDJ1000.jogTouched[deck] = false;
    }
};

// Called from the display timer: end a scratch once the platter has stopped
// feeding it, ramping the rate back rather than snapping it.
PioneerDDJ1000.checkJogSpindown = function (deck) {
    if (PioneerDDJ1000.jogTouched[deck] || !engine.isScratching(deck)) {
        return;
    }
    var idle = Date.now() - (PioneerDDJ1000.jogLastTick[deck] || 0);
    if (idle >= PioneerDDJ1000.jogSpinDownMs) {
        PioneerDDJ1000.endThrow(deck);
    }
};

PioneerDDJ1000.endThrow = function (deck) {
    PioneerDDJ1000.jogSpeed[deck] = undefined;
    // Ramped, so the rate is eased back to playing speed instead of jumping.
    engine.scratchDisable(deck, true);
};

// Follow a coasting wheel, and hand the deck back once it has slowed to a
// crawl rather than waiting for it to stop.
PioneerDDJ1000.coast = function (deck, ticks) {
    var now = Date.now();
    var elapsed = now - (PioneerDDJ1000.jogLastTick[deck] || now);
    PioneerDDJ1000.jogLastTick[deck] = now;
    engine.scratchTick(deck, ticks);

    if (elapsed <= 0) {
        return;
    }
    var speed = Math.abs(ticks) * 1000 / elapsed;
    var previous = PioneerDDJ1000.jogSpeed[deck];
    var smoothed = previous === undefined ? speed : previous + (speed - previous) * 0.25;
    PioneerDDJ1000.jogSpeed[deck] = smoothed;
    if (smoothed < PioneerDDJ1000.jogTicksPerSecond() * PioneerDDJ1000.jogReleaseFraction) {
        PioneerDDJ1000.endThrow(deck);
    }
};

// Turning the platter while the top is touched: scratch.
PioneerDDJ1000.jogScratch = function (channel, control, value, status) {
    var deck = PioneerDDJ1000.deckFromStatus(status);
    if (PioneerDDJ1000.loopAdjusting[deck]) {
        PioneerDDJ1000.nudgeLoopIn(PioneerDDJ1000.groupFromStatus(status),
            PioneerDDJ1000.jogTicks(value));
        return;
    }
    if (!engine.isScratching(deck)) {
        return;
    }
    PioneerDDJ1000.jogLastTick[deck] = Date.now();
    engine.scratchTick(deck, PioneerDDJ1000.jogTicks(value));
};

// Turning the outer ring, or the platter without touching the top: pitch bend.
//
// This address is also how a throw is heard. The wheel is one piece -- the
// touch plate on top and the rim turn together -- but only the plate reports
// while a hand is on it. Let go mid-spin and 0x22 stops dead while this keeps
// counting, so this is what carries the record on until the wheel rests.
PioneerDDJ1000.jogBend = function (channel, control, value, status) {
    var deck = PioneerDDJ1000.deckFromStatus(status);
    if (PioneerDDJ1000.loopAdjusting[deck]) {
        PioneerDDJ1000.nudgeLoopIn(PioneerDDJ1000.groupFromStatus(status),
            PioneerDDJ1000.jogTicks(value));
        return;
    }
    if (engine.isScratching(deck)) {
        if (!PioneerDDJ1000.jogTouched[deck]) {
            PioneerDDJ1000.coast(deck, PioneerDDJ1000.jogTicks(value));
        }
        return;
    }
    engine.setValue(
        PioneerDDJ1000.groupFromStatus(status),
        "jog",
        PioneerDDJ1000.jogTicks(value)
            * PioneerDDJ1000.jogBendPerRevolution
            / PioneerDDJ1000.jogTicksPerRevolution
    );
};

// SHIFT and the platter stretch the beat grid; SHIFT and the outer ring slide
// the whole thing. Both are what the manual says these gestures do, and both
// map onto controls Mixxx already has.
PioneerDDJ1000.jogGridStretch = function (channel, control, value, status) {
    var group = PioneerDDJ1000.groupFromStatus(status);
    var bpm = engine.getValue(group, "file_bpm");
    if (bpm <= 0) {
        return;
    }
    engine.setValue(group, "file_bpm", bpm
        + PioneerDDJ1000.jogTicks(value)
        * PioneerDDJ1000.jogGridBpmPerRevolution
        / PioneerDDJ1000.jogTicksPerRevolution);
};

PioneerDDJ1000.gridSlideCarry = {};

PioneerDDJ1000.jogGridSlide = function (channel, control, value, status) {
    var group = PioneerDDJ1000.groupFromStatus(status);
    var deck = PioneerDDJ1000.deckFromStatus(status);
    // beats_translate moves the grid by a fixed step, so the ticks have to be
    // collected up rather than acted on one by one -- a revolution sends
    // thousands of them.
    var perStep = PioneerDDJ1000.jogTicksPerRevolution
        / PioneerDDJ1000.jogGridSlideSteps;
    var carry = (PioneerDDJ1000.gridSlideCarry[deck] || 0)
        + PioneerDDJ1000.jogTicks(value);
    while (Math.abs(carry) >= perStep) {
        engine.setValue(group,
            carry > 0 ? "beats_translate_later" : "beats_translate_earlier", 1);
        carry -= carry > 0 ? perStep : -perStep;
    }
    PioneerDDJ1000.gridSlideCarry[deck] = carry;
};

// Adjusting the loop in point: the manual puts this on SHIFT + LOOP IN, after
// which the jog moves the point until the button is pressed again.
PioneerDDJ1000.loopAdjusting = {};

PioneerDDJ1000.loopInAdjust = function (channel, control, value, status) {
    if (value === 0) {
        return;
    }
    var deck = PioneerDDJ1000.deckFromStatus(status);
    PioneerDDJ1000.loopAdjusting[deck] = !PioneerDDJ1000.loopAdjusting[deck];
};

PioneerDDJ1000.nudgeLoopIn = function (group, ticks) {
    var start = engine.getValue(group, "loop_start_position");
    if (start < 0) {
        return;
    }
    // Engine samples are frames times two, and a couple of milliseconds a tick
    // is fine enough to place a loop by ear.
    var rate = (engine.getValue(group, "track_samplerate") || 44100) * 2;
    engine.setValue(group, "loop_start_position",
        Math.max(0, start + ticks * 2 * rate / 1000));
};

// Run through the track. Turned gently this is fine positioning -- a full slow
// revolution covers jogSearchSecondsPerRevolution -- and spun hard it
// accelerates, so getting from one end of a track to the other does not mean
// winding the platter round twenty times. That is how the search behaves on
// the CDJs, and it is the only way one control can do both jobs.
PioneerDDJ1000.jogSearchSecondsPerRevolution = 30;
PioneerDDJ1000.jogSearchMaxAcceleration = 6;

PioneerDDJ1000.jogSearch = function (channel, control, value, status) {
    var group = PioneerDDJ1000.groupFromStatus(status);
    var duration = engine.getValue(group, "duration");
    if (duration <= 0) {
        return;
    }
    var ticks = PioneerDDJ1000.jogTicks(value);
    var seconds = ticks * PioneerDDJ1000.jogSearchSecondsPerRevolution
        / PioneerDDJ1000.jogTicksPerRevolution;

    // Each report carries how far the platter moved since the last one, so its
    // size is the speed. One tick is a crawl, a hard spin lands in the twenties.
    var acceleration = Math.min(PioneerDDJ1000.jogSearchMaxAcceleration,
        1 + Math.abs(ticks) / 4);

    var position = engine.getValue(group, "playposition")
        + seconds * acceleration / duration;
    engine.setValue(group, "playposition", Math.max(0, Math.min(1, position)));
};

// The browse and parameter encoders count away from zero: 0x01..0x1E
// clockwise, 0x7F..0x62 counter-clockwise.
PioneerDDJ1000.relativeTicks = function (value) {
    return value > 0x40 ? value - 0x80 : value;
};

// The jog platter and its outer ring use the other convention the MIDI message
// list describes -- centred on 0x40, "increases from 65 clockwise, decreases
// from 63 counter-clockwise". Decoding those with the function above turns one
// tick forward into sixty-three backwards, which is exactly as bad as it
// sounds.
PioneerDDJ1000.jogTicks = function (value) {
    return value - 0x40;
};

// -- library --------------------------------------------------------------

// The DDJ encoder reports a magnitude per message (0x01..0x1E depending on
// how fast it is spun). Browse one row per detent regardless of speed; the
// shifted knob pages by 5. (No timer coalescing: a one-shot engine timer
// that gets re-armed while firing can wedge and the knob goes dead.)
PioneerDDJ1000.browse = function (channel, control, value) {
    engine.setValue("[Library]", "MoveVertical",
        PioneerDDJ1000.relativeTicks(value) > 0 ? 1 : -1);
};

PioneerDDJ1000.browseFast = function (channel, control, value) {
    engine.setValue("[Library]", "MoveVertical",
        PioneerDDJ1000.relativeTicks(value) > 0 ? 5 : -5);
};

// -- pad lighting ---------------------------------------------------------

// The pads are RGB: a note with data2 in 1..127 lights that colour, 0x00 dims
// it. The XML outputs already handle on/off; this adds the colour so a set hot
// cue reads at a glance.
PioneerDDJ1000.connectHotcueLed = function (deck, pad) {
    var group = "[Channel" + deck + "]";
    var key = "hotcue_" + pad + "_enabled";
    var status = PioneerDDJ1000.padStatusForDeck(deck);
    var note = pad - 1; // hot cue mode occupies notes 0x00..0x07

    var connection = engine.makeConnection(group, key, function (value) {
        midi.sendShortMsg(
            status,
            note,
            value ? PioneerDDJ1000.hotcuePadColor : PioneerDDJ1000.hotcuePadColorOff
        );
    });

    if (connection) {
        PioneerDDJ1000.connections.push(connection);
        connection.trigger();
    }
};

// -- jog dial displays ----------------------------------------------------

// Called on a timer rather than from control connections: the position bar has
// to move continuously, and polling four decks once per tick is cheaper and
// steadier than reacting to every playposition change.
PioneerDDJ1000.updateDisplays = function () {
    if (!PioneerDDJ1000.openingSent) {
        PioneerDDJ1000.openingSent = true;
        PioneerDDJ1000.sendOpeningState();
    }
    PioneerDDJ1000.decks.forEach(PioneerDDJ1000.updateDeckDisplay);
};

// Everything the controller has to be told once, sent from the first timer
// tick rather than from init: Mixxx opens the MIDI output *after* running the
// script's init, so anything sent from there is dropped with "not open for
// output" and the unit never hears it.
PioneerDDJ1000.openingSent = false;

PioneerDDJ1000.sendOpeningState = function () {
    // The pad and loop lights were set up during init too, so their opening
    // values went the same way. Fire them again now that anything sent will
    // actually leave.
    PioneerDDJ1000.connections.forEach(function (connection) {
        connection.trigger();
    });

    PioneerDDJ1000.decks.forEach(function (deck) {
        // Wake the display and light the platter ring.
        PioneerDDJ1000.sendNote(deck, PioneerDDJ1000.display.showInfo, 0x00);
        PioneerDDJ1000.sendNote(deck, PioneerDDJ1000.display.ringLed, 0x01);
        PioneerDDJ1000.sendNote(deck, PioneerDDJ1000.display.timeMode, 0x00);

        // Ask where the knobs and faders are sitting: the unit reports a
        // position only when something moves, so without this Mixxx disagrees
        // with the panel until every control has been touched once.
        PioneerDDJ1000.sendNote(deck, 0x21, 0x20);

        // And tell it whether a loop is running, which decides what the LOOP
        // IN and LOOP OUT buttons send.
        midi.sendShortMsg(0x9F, 0x03 + deck,
            engine.getValue("[Channel" + deck + "]", "loop_enabled") > 0 ? 0x7F : 0x00);
    });
};

PioneerDDJ1000.updateDeckDisplay = function (deck) {
    var group = "[Channel" + deck + "]";
    var d = PioneerDDJ1000.display;

    PioneerDDJ1000.checkJogSpindown(deck);
    PioneerDDJ1000.announceIfChanged(deck);

    var duration = engine.getValue(group, "duration");
    var position = engine.getValue(group, "playposition");
    var elapsed = duration > 0 ? position * duration : 0;

    PioneerDDJ1000.sendPosition(deck, elapsed * 1000);
    PioneerDDJ1000.sendGridInfo(deck);
    PioneerDDJ1000.sendLoop(deck);

    // Position bar: an angle in 0..359 degrees that spins once per platter
    // revolution, so the display behaves like a turntable rather than a
    // progress bar. Max is 0x0167 = 359.
    var revolutions = elapsed / PioneerDDJ1000.secondsPerRevolution;
    var degrees = Math.floor((revolutions - Math.floor(revolutions)) * 360);
    PioneerDDJ1000.send14(deck, d.positionBarMsb, degrees, 359);

    // BPM is sent as tenths: 0x4E0F = 9999 is 999.9 BPM.
    var bpm = engine.getValue(group, "bpm") || 0;
    PioneerDDJ1000.send14(deck, d.bpmMsb, bpm * 10, 9999, true);

    // Playing speed spans -100.0%..+100.0% over the same 0..9999 range, so
    // zero rate sits at the midpoint.
    var rate = engine.getValue(group, "rate") * engine.getValue(group, "rateRange");
    PioneerDDJ1000.send14(deck, d.speedMsb, (rate + 1) * 4999.5, 9999);

    // Elapsed time, split the way the display expects it. The time marker goes
    // out with every update rather than only on change: the screens fall back
    // to the idle logo if the deck stops being told it has something to show,
    // which is why the community mappings re-send it each time too.
    var totalSeconds = Math.floor(elapsed);
    if (engine.getValue(group, "track_loaded")) {
        PioneerDDJ1000.sendNote(deck, d.timeMode, 0x7F);
        PioneerDDJ1000.sendNote(deck, d.timeMinute, Math.min(99, Math.floor(totalSeconds / 60)));
        PioneerDDJ1000.sendNote(deck, d.timeSecond, totalSeconds % 60);
    } else {
        PioneerDDJ1000.sendNoteIfChanged(deck, d.timeMinute, 0);
        PioneerDDJ1000.sendNoteIfChanged(deck, d.timeSecond, 0);
    }

    // Cue marker, as an angle on the same scale. 0x7F/0x7F hides it.
    var cuePoint = engine.getValue(group, "cue_point");
    var sampleRate = engine.getValue(group, "track_samplerate") || 44100;
    if (cuePoint >= 0 && duration > 0) {
        // cue_point is in engine samples: frames * 2.
        var cueSeconds = cuePoint / (sampleRate * 2);
        var cueRevs = cueSeconds / PioneerDDJ1000.secondsPerRevolution;
        var cueDegrees = Math.floor((cueRevs - Math.floor(cueRevs)) * 360);
        PioneerDDJ1000.send14(deck, d.cueMarkerMsb, cueDegrees, 359);
    } else {
        PioneerDDJ1000.send14(deck, d.cueMarkerMsb, 16383, 16383); // 0x7F/0x7F
    }

    // Key, mapped onto the controller's own 25-entry table.
    var key = engine.getValue(group, "key");
    PioneerDDJ1000.sendNoteIfChanged(deck, d.keyValue, PioneerDDJ1000.keyToDisplayCode(key));

    PioneerDDJ1000.sendNoteIfChanged(deck, d.syncMaster, engine.getValue(group, "sync_master") ? 0x7F : 0x00);
    PioneerDDJ1000.sendNoteIfChanged(deck, d.syncState, engine.getValue(group, "sync_enabled") ? 0x7F : 0x00);
};

// Mixxx reports key as an Open Key / Lancelot style integer 1..24 where odd
// values are minor. The controller wants an index into its own table, which
// interleaves major and minor differently, so map through the note name.
PioneerDDJ1000.keyToDisplayCode = function (mixxxKey) {
    if (!mixxxKey || mixxxKey < 1 || mixxxKey > 24) {
        return 0x00; // "---"
    }
    // Mixxx KeyUtils: 1..12 are C..B major, 13..24 are A..G# minor.
    var majors = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
    var minors = ["Am", "Bbm", "Bm", "Cm", "Dbm", "Dm", "Ebm", "Em", "Fm", "F#m", "Gm", "Abm"];
    var name = mixxxKey <= 12 ? majors[mixxxKey - 1] : minors[mixxxKey - 13];

    var index = PioneerDDJ1000.keyCodes.indexOf(name);
    return index > 0 ? index : 0x00;
};
