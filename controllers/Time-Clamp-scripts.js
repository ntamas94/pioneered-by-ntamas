// Keeps the track time two-state.
//
// WNumberPos::mousePressEvent cycles elapsed -> remaining -> both -> elapsed
// and there is no skin attribute to shorten that. The control it writes is
// [Controls],ShowDurationRemaining ([Controls],PositionDisplay is only the
// config-file key, not a control). Watching that control and pushing "both"
// straight back to "elapsed" leaves two reachable modes.
//
// Clamping to elapsed rather than remaining matters: clamping to remaining
// would land back on the mode the next click leaves, so the time would stick.

var TimeClamp = {};

TimeClamp.ELAPSED = 0;
TimeClamp.BOTH = 2;

TimeClamp.clamp = function (value) {
    if (value === TimeClamp.BOTH) {
        engine.setValue("[Controls]", "ShowDurationRemaining", TimeClamp.ELAPSED);
    }
};

TimeClamp.init = function () {
    TimeClamp.connection = engine.makeConnection(
        "[Controls]", "ShowDurationRemaining", TimeClamp.clamp);
    TimeClamp.clamp(engine.getValue("[Controls]", "ShowDurationRemaining"));
    ["mode2", "mode24", "mode4"].forEach(TimeClamp.watchMode);
    TimeClamp.zoomConnection = engine.makeConnection(
        "[Pioneered]", "zoomcycle", TimeClamp.zoomCycle);
    TimeClamp.autoDjConnection = engine.makeConnection(
        "[AutoDJ]", "enabled", TimeClamp.autoDjSync);
    TimeClamp.fxLenConnection = engine.makeConnection(
        "[EffectRack1_EffectUnit1_Effect1]", "meta", TimeClamp.fxLen);
    if (TimeClamp.fxLenConnection) {
        TimeClamp.modeConnections.push(TimeClamp.fxLenConnection);
        TimeClamp.fxLen(engine.getValue("[EffectRack1_EffectUnit1_Effect1]", "meta"));
    }
    if (TimeClamp.autoDjConnection) {
        TimeClamp.modeConnections.push(TimeClamp.autoDjConnection);
    }
    if (TimeClamp.zoomConnection) {
        TimeClamp.modeConnections.push(TimeClamp.zoomConnection);
    }
    TimeClamp.oskConnection = engine.makeConnection(
        "[Pioneered]", "osk", TimeClamp.oskPress);
    if (TimeClamp.oskConnection) {
        TimeClamp.modeConnections.push(TimeClamp.oskConnection);
    }
    TimeClamp.oskReqConnection = engine.makeConnection(
        "[Pioneered]", "osk_req", TimeClamp.oskReq);
    if (TimeClamp.oskReqConnection) {
        TimeClamp.modeConnections.push(TimeClamp.oskReqConnection);
    }
    engine.beginTimer(1000, TimeClamp.oskBeat);
    TimeClamp.applyMode("mode4");
};

// On-screen keyboard. The KBD button is a plain push on [Pioneered],osk:
// each press flips the desired state. The patched WSearchLineEdit sets
// [Pioneered],osk_req while the search box has focus (Android-style
// auto-show). A once-a-second heartbeat broadcasts the desired state as
// 0xB0 0x20 0x7F/0x00; the djbox-osk-midi daemon shows or hides the
// overlay when the level changes. Level + heartbeat instead of edges makes
// the chain self-healing against dropped or late MIDI events.
TimeClamp.oskState = 0;

TimeClamp.oskPress = function (value) {
    if (value !== 1) {
        return;
    }
    TimeClamp.oskState = TimeClamp.oskState ? 0 : 1;
};

TimeClamp.oskReq = function (value) {
    TimeClamp.oskState = value ? 1 : 0;
};

TimeClamp.oskBeat = function () {
    midi.sendShortMsg(0xB0, 0x20, TimeClamp.oskState ? 0x7F : 0x00);
};

TimeClamp.cpuIn = function (channel, control, value) {
    engine.setValue("[Pioneered]", "cpu", value);
};

// View radio. Waveform rows and deck cards are independent:
//   2 DECK   one deck pair, matching cards
//   2/4 DECK one deck pair, all four cards
//   4 DECK   everything
// Pressing the active 2 or 2/4 button again flips between decks 1-2 and 3-4.
TimeClamp.currentMode = "mode4";
TimeClamp.pairB = false; // false: decks 1-2, true: decks 3-4

TimeClamp.applyMode = function (mode) {
    var rows;
    if (mode === "mode4") {
        rows = [1, 1, 1, 1];
    } else if (TimeClamp.pairB) {
        rows = [0, 0, 1, 1];
    } else {
        rows = [1, 1, 0, 0];
    }
    // cards: [smalltop, smallbot, bigtop, bigbot]
    var cards;
    if (mode === "mode2") {
        cards = TimeClamp.pairB ? [0, 0, 0, 1] : [0, 0, 1, 0];
    } else {
        cards = [1, 1, 0, 0];
    }
    // disp* drive the button lights; mode* are momentary triggers.
    ["mode2", "mode24", "mode4"].forEach(function (m) {
        engine.setValue("[Pioneered]", "disp" + m.slice(4), m === mode ? 1 : 0);
    });
    // Hide first, show after: the other order flashes all four rows during
    // a pair flip.
    rows.forEach(function (visible, i) {
        if (!visible) {
            engine.setValue("[Pioneered]", "show_wf" + (i + 1), 0);
        }
    });
    rows.forEach(function (visible, i) {
        if (visible) {
            engine.setValue("[Pioneered]", "show_wf" + (i + 1), 1);
        }
    });
    // Same hide-first rule for the card rows.
    var cardKeys = ["card_smalltop", "card_smallbot", "card_bigtop", "card_bigbot"];
    cardKeys.forEach(function (k, i) {
        if (!cards[i]) {
            engine.setValue("[Pioneered]", k, 0);
        }
    });
    cardKeys.forEach(function (k, i) {
        if (cards[i]) {
            engine.setValue("[Pioneered]", k, 1);
        }
    });
};

// ZOOM cycles inwards and wraps, the Pioneer way: each press zooms in one
// step on every deck; past the tightest step it jumps back out to the widest.
TimeClamp.ZOOM_WIDEST = 8;

TimeClamp.zoomCycle = function (value) {
    if (value !== 1) {
        return;
    }
    var zoom = engine.getValue("[Channel1]", "waveform_zoom") - 1;
    if (zoom < 1) {
        zoom = TimeClamp.ZOOM_WIDEST;
    }
    for (var deck = 1; deck <= 4; deck++) {
        engine.setValue("[Channel" + deck + "]", "waveform_zoom", zoom);
    }
};

TimeClamp.modeConnections = [];

TimeClamp.watchMode = function (mode) {
    var connection = engine.makeConnection("[Pioneered]", mode, function (value) {
        if (value !== 1) {
            return;
        }
        if (mode === TimeClamp.currentMode && mode !== "mode4") {
            // Second press on the active button: flip the deck pair.
            TimeClamp.pairB = !TimeClamp.pairB;
        } else {
            TimeClamp.currentMode = mode;
            TimeClamp.pairB = false;
        }
        TimeClamp.applyMode(mode);
    });
    if (connection) {
        TimeClamp.modeConnections.push(connection);
    }
};

// CONTINUE mode with beatmatching: while AutoDJ runs, decks 1-2 get sync
// lock and quantize, so transitions land on the beat.
TimeClamp.autoDjSync = function (value) {
    for (var d = 1; d <= 2; d++) {
        engine.setValue("[Channel" + d + "]", "sync_enabled", value ? 1 : 0);
        engine.setValue("[Channel" + d + "]", "quantize", value ? 1 : 0);
    }
};

// LENGTH as a percentage: mirror the Beat FX meta knob (0..1) into a
// display control scaled to 0..100 for the skin.
TimeClamp.fxLen = function (value) {
    engine.setValue("[Pioneered]", "fxlen", Math.round(value * 100));
};

TimeClamp.shutdown = function () {
    if (TimeClamp.connection) {
        TimeClamp.connection.disconnect();
    }
    TimeClamp.modeConnections.forEach(function (c) { c.disconnect(); });
};
