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

// The cue positions, for the markers along the jog screen's beat scale. The
// screen has ten slots; hot cues fill them in pad order. Sent as minutes,
// seconds and milliseconds because that is how the table wants them.
//
// Positions are interleaved stereo samples, two per frame, so they divide by
// twice the sample rate. A cue set at exactly one minute arrives as two
// without the halving.
PioneerDDJ1000.sentCues = {};

PioneerDDJ1000.sendCues = function (deck) {
    var group = "[Channel" + deck + "]";
    var rate = engine.getValue(group, "track_samplerate") || 44100;
    var entries = [];
    for (var cue = 1; cue <= 8 && entries.length < 10; cue++) {
        var position = engine.getValue(group, "hotcue_" + cue + "_position");
        if (position < 0) {
            continue;
        }
        var ms = Math.max(0, Math.round(position / (rate * 2) * 1000));
        // A hot cue with an end is a saved loop, and the screens mark the two
        // differently. Mixxx keeps both on the same pads, so the end position
        // is what tells them apart.
        // Greater than zero, not at least zero: a control Mixxx does not have
        // reads as 0, and taking that as an end would mark every plain cue a
        // loop.
        var loop = engine.getValue(group, "hotcue_" + cue + "_endposition") > 0;
        entries.push([Math.min(127, Math.floor(ms / 60000)),
            Math.floor(ms / 1000) % 60, ms % 1000, loop ? 1 : 0]);
    }
    var packed = JSON.stringify(entries);
    if (PioneerDDJ1000.sentCues[deck] === packed) {
        return;
    }
    PioneerDDJ1000.sentCues[deck] = packed;
    var message = [0xF0, 0x7D, 0x50 | (deck - 1), entries.length];
    for (var i = 0; i < entries.length; i++) {
        message.push(entries[i][0], entries[i][1],
            (entries[i][2] >> 7) & 0x7F, entries[i][2] & 0x7F, entries[i][3]);
    }
    message.push(0xF7);
    midi.sendSysexMsg(message, message.length);
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
    // The track's own tempo, not the one the fader is asking for: the beat
    // grid is laid out against it, and a grid built at the adjusted tempo
    // drifts away from the music as soon as the fader moves.
    var tenths = Math.max(0, Math.min(0x3FFF,
        Math.round((engine.getValue(group, "file_bpm")
            || engine.getValue(group, "bpm") || 0) * 10)));
    // Keyed on the tempo as well as the length. A track that has not been
    // analysed yet loads with no BPM at all, the daemon lays its grid out at a
    // guessed 120, and when the analysis finishes nothing would otherwise ever
    // tell it the real figure.
    var packed = ms + ":" + tenths;
    if (PioneerDDJ1000.announcedMs[deck] === packed && !due) {
        return;
    }
    PioneerDDJ1000.announcedMs[deck] = packed;
    PioneerDDJ1000.announcedAt[deck] = now;
    midi.sendSysexMsg([0xF0, 0x7D, deck - 1,
        (ms >> 21) & 0x7F, (ms >> 14) & 0x7F, (ms >> 7) & 0x7F, ms & 0x7F,
        (tenths >> 7) & 0x7F, tenths & 0x7F, 0xF7], 10);
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

// Whether anything this deck plays is actually reaching the master. The jog
// screen greys itself out for a deck that is not, which is what makes a fader
// move show up on the wheel, and it is the host that decides -- rekordbox
// clears the bit whenever the channel is shut out and sets it the moment it
// is let back in.
PioneerDDJ1000.isOnAir = function (group) {
    if (engine.getValue(group, "mute") || engine.getValue(group, "volume") <= 0) {
        return 0;
    }
    // A channel assigned to one side of the crossfader is shut out only when
    // the crossfader is all the way to the other side; one left in the middle
    // is never shut out by it at all.
    var orientation = engine.getValue(group, "orientation");
    var crossfader = engine.getValue("[Master]", "crossfader");
    if (orientation === 0 && crossfader >= 1) {
        return 0;
    }
    if (orientation === 2 && crossfader <= -1) {
        return 0;
    }
    return 1;
};

PioneerDDJ1000.sendGridInfo = function (deck) {
    var group = "[Channel" + deck + "]";
    var bpm = engine.getValue(group, "bpm");
    var rate = engine.getValue(group, "track_samplerate") || 44100;
    var beat = engine.getValue(group, "beat_closest");
    var firstBeat = 0;
    if (bpm > 0 && beat >= 0) {
        var interval = 60000 / bpm;
        // Sample positions are interleaved stereo: two per frame. Measured
        // against a cue set at a known minute, dividing by the rate alone
        // puts every marker at twice its real time.
        var beatMs = beat / (rate * 2) * 1000;
        firstBeat = Math.round(((beatMs % interval) + interval) % interval);
    }
    firstBeat = Math.min(firstBeat, 16383);

    var key = PioneerDDJ1000.ddjKeyCode(engine.getValue(group, "key"));
    // Whichever time readout Mixxx is showing, the jog shows the same one. It
    // rides along here rather than going out as a MIDI setting because there
    // is no such setting: rekordbox switches it on the state record, so this
    // is what the bridge needs to put on the wire.
    var remaining = engine.getValue("[Controls]", "ShowDurationRemaining")
        === PioneerDDJ1000.timeModeRemaining ? 1 : 0;
    var onAir = PioneerDDJ1000.isOnAir(group);
    // Beat sync shows on the jog screen too, not only on the button lamp:
    // pressing SYNC with nothing else happening moves bit 0x10 of byte 5 and
    // the lamp on note 0x58 together, within ten milliseconds.
    var sync = engine.getValue(group, "sync_enabled") ? 1 : 0;
    // MASTER is the other lamp in that corner of the screen, and nothing on
    // the MIDI side carries it -- the state record is the only word of it.
    // Exactly one deck holds it at a time.
    var leader = engine.getValue(group, "sync_leader") ? 1 : 0;
    var packed = firstBeat + ":" + key + ":" + remaining + ":" + onAir
        + ":" + sync + ":" + leader;
    if (PioneerDDJ1000.gridInfo[deck] === packed) {
        return;
    }
    PioneerDDJ1000.gridInfo[deck] = packed;
    midi.sendSysexMsg([0xF0, 0x7D, 0x20 | (deck - 1),
        (firstBeat >> 7) & 0x7F, firstBeat & 0x7F, key, remaining, onAir,
        sync, leader, 0xF7], 11);
    // The jog always shows elapsed time. Switching it to remaining is possible
    // -- the mode note and BF 45 both put the minus sign up -- but the unit
    // then counts down from a track length it computes itself and does not
    // have from us, so it just shows -99:59. There is no track-length field in
    // the protocol to feed it, so remaining is left to the laptop screen.
};

// Mixxx numbers the keys chromatically: 1..12 are C..B major and 13..24 are
// C..B minor, so 13 is C minor and 22 is A minor. The jog display has its own
// order -- majors on the odd codes counting from C, minors on the even ones
// counting from A -- which is why this cannot be a straight offset.
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

PioneerDDJ1000.sendCuePoint = function (deck, group) {
    var rate = engine.getValue(group, "track_samplerate") || 44100;
    var point = engine.getValue(group, "cue_point");
    var ms = point >= 0 ? Math.round(point / (rate * 2) * 1000) : 0;
    ms = Math.max(0, Math.min(0xFFFFFFF, ms));
    if (PioneerDDJ1000.sentCuePoint[deck] === ms) {
        return;
    }
    PioneerDDJ1000.sentCuePoint[deck] = ms;
    midi.sendSysexMsg([0xF0, 0x7D, 0x60 | (deck - 1),
        (ms >> 21) & 0x7F, (ms >> 14) & 0x7F, (ms >> 7) & 0x7F, ms & 0x7F, 0xF7], 8);
};

PioneerDDJ1000.sentCuePoint = {};

PioneerDDJ1000.sendPosition = function (deck, elapsedMs, bpm) {
    var ms = Math.max(0, Math.min(0xFFFFFFF, Math.round(elapsedMs)));
    // The tempo rides along rather than going out as the display CC: the
    // screens are drawn over HID, and the unit takes the MIDI display messages
    // as a second, competing source for the same picture.
    var tenths = Math.max(0, Math.min(0x3FFF, Math.round(bpm * 10)));
    // The speed the fader is asking for, as hundredths of a percent offset by
    // 5000 so it survives as an unsigned pair: 5000 is dead centre.
    var ratio = engine.getValue("[Channel" + deck + "]", "rate_ratio") || 1;
    var speed = Math.max(0, Math.min(9999,
        Math.round((ratio - 1) * 100 * 100) + 5000));
    midi.sendSysexMsg([0xF0, 0x7D, 0x10 | (deck - 1),
        (ms >> 21) & 0x7F, (ms >> 14) & 0x7F, (ms >> 7) & 0x7F, ms & 0x7F,
        (tenths >> 7) & 0x7F, tenths & 0x7F,
        (speed >> 7) & 0x7F, speed & 0x7F, 0xF7], 12);
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
        PioneerDDJ1000.connectWaveformReturn(deck);

    });

    PioneerDDJ1000.skipBothTimeMode();
    PioneerDDJ1000.watchPreferencesButton();

    PioneerDDJ1000.displayTimer = engine.beginTimer(
        PioneerDDJ1000.displayIntervalMs,
        PioneerDDJ1000.updateDisplays
    );
    PioneerDDJ1000.loopLampTimer = engine.beginTimer(300,
        PioneerDDJ1000.updateLoopLamps);

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

// The LOOP IN and LOOP OUT button lamps blink rather than hold, and the host
// does the blinking: rekordbox toggles them at a 0.3 s half period, LOOP IN
// alone while an in point is set waiting for its out, both together while the
// loop runs. Driven from one timer over all four decks so they stay in step,
// the way the capture has them.
PioneerDDJ1000.loopLampPhase = 0;

PioneerDDJ1000.updateLoopLamps = function () {
    PioneerDDJ1000.loopLampPhase ^= 1;
    var on = PioneerDDJ1000.loopLampPhase ? 0x7F : 0x00;
    PioneerDDJ1000.decks.forEach(function (deck) {
        var group = "[Channel" + deck + "]";
        var status = 0x90 | (deck - 1);
        var looping = engine.getValue(group, "loop_enabled") > 0;
        var inSet = engine.getValue(group, "loop_start_position") >= 0;
        var outSet = engine.getValue(group, "loop_end_position") >= 0;
        // Lit is the resting state, not dark: the unit's own bring-up burst
        // lights both lamps on every deck and rekordbox never turns them off.
        // Blinking is the activity on top -- IN alone while an in point waits
        // for its out, both while the loop runs.
        var inLamp = 0x7F, outLamp = 0x7F;
        if (looping) {
            inLamp = on; outLamp = on;
        } else if (inSet && !outSet) {
            inLamp = on;
        }
        midi.sendShortMsg(status, 0x10, inLamp);
        midi.sendShortMsg(status, 0x11, outLamp);
    });
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
// Which readout the jog screens show. Its own message, sent the moment the
// setting changes: the grid message it used to ride on is only re-sent when
// the grid itself changes, so switching the readout alone never reached the
// bridge at all.
PioneerDDJ1000.lastTimeMode = -1;

// Polled from the display timer as well as driven by the callback: a control
// change that arrives while the mapping is still starting up has nobody
// connected to it yet, and the screens then sit on the wrong readout forever.
PioneerDDJ1000.timeModeSentAt = 0;

PioneerDDJ1000.pollTimeMode = function () {
    var value = engine.getValue("[Controls]", "ShowDurationRemaining");
    var now = Date.now();
    // Repeated, not just sent on change: the bridge rebuilds itself whenever
    // the controller re-enumerates, and a setting sent once before that is
    // simply lost -- which left the screens on elapsed while Mixxx had been
    // set to remaining all along.
    if (value === PioneerDDJ1000.lastTimeMode &&
            now - PioneerDDJ1000.timeModeSentAt < 5000) {
        return;
    }
    PioneerDDJ1000.lastTimeMode = value;
    PioneerDDJ1000.timeModeSentAt = now;
    PioneerDDJ1000.sendTimeMode();
};

PioneerDDJ1000.sendTimeMode = function () {
    var remaining = engine.getValue("[Controls]", "ShowDurationRemaining")
        === PioneerDDJ1000.timeModeRemaining ? 1 : 0;
    for (var deck = 1; deck <= 4; deck++) {
        midi.sendSysexMsg([0xF0, 0x7D, 0x30 | (deck - 1), remaining, 0xF7], 5);
    }
};

PioneerDDJ1000.skipBothTimeMode = function () {
    var connection = engine.makeConnection("[Controls]", "ShowDurationRemaining", function (value) {
        if (value === PioneerDDJ1000.timeModeBoth) {
            engine.setValue("[Controls]", "ShowDurationRemaining", PioneerDDJ1000.timeModeElapsed);
            return;
        }
        PioneerDDJ1000.sendTimeMode();
    });

    if (connection) {
        PioneerDDJ1000.connections.push(connection);
        // Land on remaining at startup rather than inheriting "both".
        if (engine.getValue("[Controls]", "ShowDurationRemaining") === PioneerDDJ1000.timeModeBoth) {
            engine.setValue("[Controls]", "ShowDurationRemaining", PioneerDDJ1000.timeModeElapsed);
        }
        PioneerDDJ1000.sendTimeMode();
    }
};

// The skin's Mixxx logo is a button pointed at [Pioneered],prefs_btn, and
// Mixxx has no control that opens its preferences -- the dialog is reachable
// from the menu and from Ctrl+P and nowhere else, so a skin button asking for
// it silently creates a control with nobody on the other end. This puts
// somebody there: the daemon presses the shortcut at the desktop.
// SYNC latches, the way it does on the hardware. It was bound to beatsync,
// which lines the beat up once and leaves nothing switched on: the button lamp
// blinked and went out, and the sync indicator on the jog screen never lit at
// all. A capture of rekordbox holds its lamp on until the button is pressed a
// second time.
//
// A long press hands the deck the leader role instead, which is what the
// hardware does and what the second lamp is for.
PioneerDDJ1000.syncPressedAt = {};
PioneerDDJ1000.syncLongPressMs = 600;

PioneerDDJ1000.syncPress = function (channel, control, value, status, group) {
    var deck = (status & 0x0F) + 1;
    if (value) {
        PioneerDDJ1000.syncPressedAt[deck] = Date.now();
        return;
    }
    var held = Date.now() - (PioneerDDJ1000.syncPressedAt[deck] || Date.now());
    if (held >= PioneerDDJ1000.syncLongPressMs) {
        engine.setValue(group, "sync_leader", 1);
        return;
    }
    engine.setValue(group, "sync_enabled",
        engine.getValue(group, "sync_enabled") ? 0 : 1);
};

PioneerDDJ1000.watchPreferencesButton = function () {
    var connection = engine.makeConnection("[Pioneered]", "prefs_btn", function (value) {
        if (value) {
            midi.sendSysexMsg([0xF0, 0x7D, 0x70, 0x01, 0xF7], 5);
        }
    });
    if (connection) {
        PioneerDDJ1000.connections.push(connection);
    }
};

PioneerDDJ1000.shutdown = function () {
    if (PioneerDDJ1000.displayTimer) {
        engine.stopTimer(PioneerDDJ1000.displayTimer);
        PioneerDDJ1000.displayTimer = 0;
    }
    if (PioneerDDJ1000.loopLampTimer) {
        engine.stopTimer(PioneerDDJ1000.loopLampTimer);
        PioneerDDJ1000.loopLampTimer = 0;
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
// True only between letting go of a spinning platter and the throw running
// out. Without it the outer ring would keep feeding the scratch for as long
// as it was turned, because a turning ring looks exactly like a wheel that
// has not come to rest yet.
PioneerDDJ1000.jogThrowing = {};

// A wheel turning at playing speed sends this many ticks a second. Below a
// fraction of it the throw has run out, and the deck should be handed back to
// normal playback while it is still moving -- waiting for the wheel to stop
// dead first means the record stops dead with it.
PioneerDDJ1000.jogTicksPerSecond = function () {
    return PioneerDDJ1000.jogTicksPerRevolution / PioneerDDJ1000.secondsPerRevolution;
};
PioneerDDJ1000.jogReleaseFraction = 0.25;
PioneerDDJ1000.jogSpinDownMs = 80;

// SEARCH runs the track past at a steady speed while it is held. The unit
// sends one note on the press and another once the press becomes a hold, and
// both drive this, so a quick press already starts moving rather than waiting
// for the hold to register.
// It starts gently and winds up the longer the button is held, the way the
// CDJs do -- a tap nudges, a long hold crosses the track. The ramp is driven
// from the display timer rather than a timer of its own.
PioneerDDJ1000.searchRate = 2.0;          // where a press starts
PioneerDDJ1000.searchMaxRate = 20.0;      // where holding it ends up
PioneerDDJ1000.searchRampSeconds = 2.5;   // how long it takes to get there
PioneerDDJ1000.searching = {};

PioneerDDJ1000.startSearch = function (deck, group, direction) {
    if (direction === 0) {
        delete PioneerDDJ1000.searching[deck];
        engine.setValue(group, "rateSearch", 0);
        return;
    }
    if (PioneerDDJ1000.searching[deck]) {
        return;                            // the hold note after the press
    }
    PioneerDDJ1000.searching[deck] = {
        group: group,
        direction: direction,
        since: Date.now(),
    };
    engine.setValue(group, "rateSearch", direction * PioneerDDJ1000.searchRate);
};

PioneerDDJ1000.updateSearch = function (deck) {
    var state = PioneerDDJ1000.searching[deck];
    if (!state) {
        return;
    }
    var elapsed = (Date.now() - state.since) / 1000;
    var through = Math.min(1, elapsed / PioneerDDJ1000.searchRampSeconds);
    var rate = PioneerDDJ1000.searchRate
        + (PioneerDDJ1000.searchMaxRate - PioneerDDJ1000.searchRate) * through * through;
    engine.setValue(state.group, "rateSearch", state.direction * rate);
};

PioneerDDJ1000.searchBackward = function (channel, control, value, status) {
    PioneerDDJ1000.startSearch(PioneerDDJ1000.deckFromStatus(status),
        PioneerDDJ1000.groupFromStatus(status), value ? -1 : 0);
};

PioneerDDJ1000.searchForward = function (channel, control, value, status) {
    PioneerDDJ1000.startSearch(PioneerDDJ1000.deckFromStatus(status),
        PioneerDDJ1000.groupFromStatus(status), value ? 1 : 0);
};

PioneerDDJ1000.jogTouch = function (channel, control, value, status) {
    var deck = PioneerDDJ1000.deckFromStatus(status);

    if (value > 0) {
        PioneerDDJ1000.jogTouched[deck] = true;
        PioneerDDJ1000.jogThrowing[deck] = false;
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
        PioneerDDJ1000.jogThrowing[deck] = engine.isScratching(deck);
    }
};

// Called from the display timer: end a scratch once the platter has stopped
// feeding it, ramping the rate back rather than snapping it.
PioneerDDJ1000.checkJogSpindown = function (deck) {
    if (!PioneerDDJ1000.jogThrowing[deck] || PioneerDDJ1000.jogTouched[deck]) {
        return;
    }
    var idle = Date.now() - (PioneerDDJ1000.jogLastTick[deck] || 0);
    if (idle >= PioneerDDJ1000.jogSpinDownMs) {
        PioneerDDJ1000.endThrow(deck);
    }
};

PioneerDDJ1000.endThrow = function (deck) {
    PioneerDDJ1000.jogThrowing[deck] = false;
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
        if (PioneerDDJ1000.jogThrowing[deck] && !PioneerDDJ1000.jogTouched[deck]) {
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
// Pressing the TRAX encoder means "show me the library" while the waveforms
// are up, and "take this one" once they are not -- and loading a track puts
// the waveforms back, so browsing is one button in and one button out.
PioneerDDJ1000.browsePress = function (channel, control, value) {
    if (value === 0) {
        return;
    }
    PioneerDDJ1000.focusVisiblePane();
    engine.setValue("[Library]", "GoToItem", 1);
};

// LOAD is the way in and out of the library: pressed while the waveforms are
// up it brings the browser forward, pressed there it loads what is selected --
// and the load itself puts the waveforms back.
// VIEW swaps between the waveforms and the library, which is what it does on
// the unit's own screen too.
PioneerDDJ1000.viewButton = function (channel, control, value) {
    if (value === 0) {
        return;
    }
    PioneerDDJ1000.showTab(PioneerDDJ1000.onLibraryTab()
        ? PioneerDDJ1000.tabOverview
        : PioneerDDJ1000.tabLibrary);
};

// SHIFT + BACK leaves the library without loading anything -- the way out for
// when you went in to look rather than to choose.
PioneerDDJ1000.backToOverview = function (channel, control, value) {
    if (value === 0) {
        return;
    }
    PioneerDDJ1000.showTab(PioneerDDJ1000.tabOverview);
};

// BACK shows and hides the tree view, which is this skin's version of what the
// manual describes: moving between the tree and the track list.
PioneerDDJ1000.backButton = function (channel, control, value) {
    if (value === 0) {
        return;
    }
    if (!PioneerDDJ1000.onLibraryTab()) {
        PioneerDDJ1000.showTab(PioneerDDJ1000.tabLibrary);
        return;
    }
    // Showing the tree is not enough: the encoder moves whatever has focus, so
    // the focus has to follow the tree in and out. 1 is the sidebar, 2 the
    // track list.
    var showing = engine.getValue("[Sidebar]", "sidebar_visible") < 1;
    engine.setValue("[Sidebar]", "sidebar_visible", showing ? 1 : 0);
    // Focus follows the tree in and out: the encoder moves whichever library
    // widget Qt has the keyboard on, so showing the tree without focusing it
    // leaves the encoder still scrolling the track list.
};

PioneerDDJ1000.loadPress = function (deck) {
    return function (channel, control, value) {
        if (value === 0) {
            return;
        }
        if (!PioneerDDJ1000.onLibraryTab()) {
            PioneerDDJ1000.showTab(PioneerDDJ1000.tabLibrary);
            return;
        }
        // On the tree the press means "open this one", the way the manual puts
        // it: the cursor moves from the tree to the track list. Only a press on
        // the list itself loads anything.
        //
        // Which pane has the keyboard, not whether the tree is on screen: the
        // sidebar is always on screen in this skin, so asking that instead
        // meant every press navigated and none ever loaded a track.
        if (engine.getValue("[Library]", "focused_widget") === 1) {
            // Mixxx decides what this means: a branch with children opens or
            // closes, a leaf hands over to the track list. Forcing the panes
            // to swap here would stop a branch from ever opening.
            engine.setValue("[Library]", "GoToItem", 1);
            return;
        }
        print("DDJ: LoadSelectedTrack deck " + deck
            + " (loaded before=" + engine.getValue("[Channel" + deck + "]", "track_loaded")
            + ")");
        engine.setValue("[Channel" + deck + "]", "LoadSelectedTrack", 1);
        print("DDJ: after load, track_loaded="
            + engine.getValue("[Channel" + deck + "]", "track_loaded")
            + " duration=" + engine.getValue("[Channel" + deck + "]", "duration"));
    };
};

PioneerDDJ1000.loadDeck1 = PioneerDDJ1000.loadPress(1);
PioneerDDJ1000.loadDeck2 = PioneerDDJ1000.loadPress(2);
PioneerDDJ1000.loadDeck3 = PioneerDDJ1000.loadPress(3);
PioneerDDJ1000.loadDeck4 = PioneerDDJ1000.loadPress(4);

// The skin puts its screens in a stack rather than using Mixxx's own
// maximize_library: [Tab],current selects one, 0 being the waveforms and 1 the
// library.
PioneerDDJ1000.tabOverview = 0;
PioneerDDJ1000.tabLibrary = 1;

PioneerDDJ1000.showTab = function (tab) {
    engine.setValue("[Tab]", "current", tab);
};

PioneerDDJ1000.onLibraryTab = function () {
    return engine.getValue("[Tab]", "current") === PioneerDDJ1000.tabLibrary;
};

// Back to the waveforms as soon as a deck has something on it. Guarded on the
// opening state having been sent, so restoring a session's decks at startup
// does not count as a load.
PioneerDDJ1000.connectWaveformReturn = function (deck) {
    var connection = engine.makeConnection("[Channel" + deck + "]", "track_loaded",
        function (value) {
            if (value > 0 && PioneerDDJ1000.openingSent
                    && PioneerDDJ1000.onLibraryTab()) {
                PioneerDDJ1000.showTab(PioneerDDJ1000.tabOverview);
            }
        });
    if (connection) {
        PioneerDDJ1000.connections.push(connection);
    }
};

// The skin shows either the tree or the track list, never both, so whichever
// is up has to be the one the encoder drives. Focus is claimed here rather
// than when the panes are swapped: Qt only makes a widget focusable once it is
// actually visible, and that happens after the button handler has returned.
// focused_widget counts the search bar first: 1 is the search box -- focusing
// that pops the on-screen keyboard up over everything -- 2 the tree, 3 the
// track list.
PioneerDDJ1000.focusSidebar = 2;
PioneerDDJ1000.focusTracks = 3;

PioneerDDJ1000.focusVisiblePane = function () {
    engine.setValue("[Library]", "focused_widget",
        engine.getValue("[Sidebar]", "sidebar_visible") > 0
            ? PioneerDDJ1000.focusSidebar
            : PioneerDDJ1000.focusTracks);
};

PioneerDDJ1000.browse = function (channel, control, value) {
    PioneerDDJ1000.focusVisiblePane();
    engine.setValue("[Library]", "MoveVertical",
        PioneerDDJ1000.relativeTicks(value) > 0 ? 1 : -1);
};

PioneerDDJ1000.browseFast = function (channel, control, value) {
    PioneerDDJ1000.focusVisiblePane();
    engine.setValue("[Library]", "MoveVertical",
        PioneerDDJ1000.relativeTicks(value) > 0 ? 5 : -5);
};

// -- Beat FX --------------------------------------------------------------
//
// The unit's fourteen effect buttons each select one effect outright, so they
// map to positions in the loaded chain rather than to a next/previous step.
// Mixxx's chain is whatever the user has loaded, so the index is what the
// button carries; the name on the unit's own FX display is the unit's, and it
// shows whichever button was last pressed regardless.
PioneerDDJ1000.effectSlot = "[EffectRack1_EffectUnit1_Effect1]";
PioneerDDJ1000.effectUnit = "[EffectRack1_EffectUnit1]";

PioneerDDJ1000.selectEffectByIndex = function (index) {
    return function (channel, control, value) {
        if (value === 0) {
            return;
        }
        engine.setValue(PioneerDDJ1000.effectSlot, "effect_selector", 0);
        for (var step = 0; step < index; step++) {
            engine.setValue(PioneerDDJ1000.effectSlot, "effect_selector", 1);
        }
    };
};

// The beat buttons step the effect's period, which is what "beat" means on the
// unit: how long the echo, roll or delay lasts.
PioneerDDJ1000.beatStep = function (direction) {
    return function (channel, control, value) {
        if (value === 0) {
            return;
        }
        var current = engine.getValue(PioneerDDJ1000.effectSlot, "parameter1");
        engine.setValue(PioneerDDJ1000.effectSlot, "parameter1",
            Math.max(0, Math.min(1, current + direction * 0.1)));
    };
};

PioneerDDJ1000.beatDown = PioneerDDJ1000.beatStep(-1);
PioneerDDJ1000.beatUp = PioneerDDJ1000.beatStep(1);

PioneerDDJ1000.selectEffect20 = PioneerDDJ1000.selectEffectByIndex(0);
PioneerDDJ1000.selectEffect21 = PioneerDDJ1000.selectEffectByIndex(1);
PioneerDDJ1000.selectEffect22 = PioneerDDJ1000.selectEffectByIndex(2);
PioneerDDJ1000.selectEffect23 = PioneerDDJ1000.selectEffectByIndex(3);
PioneerDDJ1000.selectEffect24 = PioneerDDJ1000.selectEffectByIndex(4);
PioneerDDJ1000.selectEffect25 = PioneerDDJ1000.selectEffectByIndex(5);
PioneerDDJ1000.selectEffect26 = PioneerDDJ1000.selectEffectByIndex(6);
PioneerDDJ1000.selectEffect27 = PioneerDDJ1000.selectEffectByIndex(7);
PioneerDDJ1000.selectEffect28 = PioneerDDJ1000.selectEffectByIndex(8);
PioneerDDJ1000.selectEffect29 = PioneerDDJ1000.selectEffectByIndex(9);
PioneerDDJ1000.selectEffect2A = PioneerDDJ1000.selectEffectByIndex(10);
PioneerDDJ1000.selectEffect2B = PioneerDDJ1000.selectEffectByIndex(11);
PioneerDDJ1000.selectEffect2C = PioneerDDJ1000.selectEffectByIndex(12);
PioneerDDJ1000.selectEffect2D = PioneerDDJ1000.selectEffectByIndex(13);

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

PioneerDDJ1000.resendMs = 4000;
PioneerDDJ1000.resentAt = {};

// The row of LEDs above each channel fader. The manual calls it the channel
// level indicator and says it shows the level "before it passes through the
// channel faders", which is Mixxx's own vu_meter: the fader is applied by the
// mixer afterwards. rekordbox drives it with CC 0x02 on the deck's channel
// about fifteen times a second, and the values it sends climb in steps of
// seven -- 0, 50, 65, 72, 80, 87, 94, 101 in a capture of one track -- so the
// unit is picking a segment out of the number rather than reading it finely.
PioneerDDJ1000.lastLevel = {};

PioneerDDJ1000.sendChannelLevel = function (deck) {
    var level = engine.getValue("[Channel" + deck + "]", "vu_meter");
    var value = Math.max(0, Math.min(127, Math.round(level * 127)));
    if (PioneerDDJ1000.lastLevel[deck] === value) {
        return;
    }
    PioneerDDJ1000.lastLevel[deck] = value;
    midi.sendShortMsg(0xB0 | (deck - 1), 0x02, value);
};

PioneerDDJ1000.updateDeckDisplay = function (deck) {
    var group = "[Channel" + deck + "]";
    var d = PioneerDDJ1000.display;
    var now = Date.now();

    PioneerDDJ1000.checkJogSpindown(deck);
    PioneerDDJ1000.updateSearch(deck);
    PioneerDDJ1000.announceIfChanged(deck);
    PioneerDDJ1000.sendChannelLevel(deck);
    if (deck === 1) {
        PioneerDDJ1000.pollTimeMode();
    }

    var duration = engine.getValue(group, "duration");
    var position = engine.getValue(group, "playposition");
    // playposition runs past 1.0 into the end-of-track roll-out, and below 0
    // ahead of the start; the screens read either as nonsense time.
    position = Math.max(0, Math.min(1, position));
    var elapsed = duration > 0 ? position * duration : 0;

    // Everything below this point is only sent when it changes, which is
    // fine until the bridge restarts -- it comes back knowing nothing, and a
    // value that never changes again is never resent, so the screens sat
    // there missing their grid, cues and cue point. Forget what was sent
    // every few seconds so all of it goes out again.
    if (now - (PioneerDDJ1000.resentAt[deck] || 0) > PioneerDDJ1000.resendMs) {
        PioneerDDJ1000.resentAt[deck] = now;
        delete PioneerDDJ1000.gridInfo[deck];
        delete PioneerDDJ1000.sentCues[deck];
        delete PioneerDDJ1000.sentCuePoint[deck];
        delete PioneerDDJ1000.loopState[deck];
    }

    var bpm = engine.getValue(group, "bpm") || 0;
    PioneerDDJ1000.sendPosition(deck, elapsed * 1000, bpm);
    PioneerDDJ1000.sendGridInfo(deck);
    PioneerDDJ1000.sendCues(deck);
    PioneerDDJ1000.sendCuePoint(deck, group);
    PioneerDDJ1000.sendLoop(deck);

    // The playing-speed pair is the one display CC the HID view itself reads:
    // without it the screen shows -100% and drops the range badge. It only
    // goes out when the tempo actually moves, so it cannot flicker anything.
    // rate_ratio, not rate: the latter is deprecated and reads as zero here,
    // which pinned the readout at 0.0% however far the fader travelled. The
    // ratio is 1.0 at the centre, so the offset from it is the percentage the
    // screen wants, on a scale that runs -100%..+100%.
    var ratio = engine.getValue(group, "rate_ratio");
    if (!ratio) {
        ratio = 1 + engine.getValue(group, "rate")
            * engine.getValue(group, "rateRange");
    }
    PioneerDDJ1000.send14(deck, d.speedMsb, ratio * 4999.5, 9999);

    // The screens themselves are drawn over HID by the bridge, which is how
    // rekordbox drives them. The MIDI display messages -- position ring, BPM,
    // tempo, the time readout, the cue marker, the key -- are a second source
    // for the same picture, and sending both makes the unit flip between them.
    // The Traktor and Serato style mappings use them because they have no HID
    // path; this one does, so everything above goes out over the private
    // SysEx instead and none of that is sent.

    PioneerDDJ1000.sendNoteIfChanged(deck, d.syncMaster, engine.getValue(group, "sync_leader") ? 0x7F : 0x00);
    PioneerDDJ1000.sendNoteIfChanged(deck, d.syncState, engine.getValue(group, "sync_enabled") ? 0x7F : 0x00);
};

