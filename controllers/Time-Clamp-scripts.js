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
    if (TimeClamp.zoomConnection) {
        TimeClamp.modeConnections.push(TimeClamp.zoomConnection);
    }
    TimeClamp.applyMode("mode4");
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
    var cards;
    if (mode === "mode2") {
        cards = TimeClamp.pairB ? [0, 1] : [1, 0];
    } else {
        cards = [1, 1];
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
    if (!cards[0]) {
        engine.setValue("[Pioneered]", "show_cardtop", 0);
    }
    if (!cards[1]) {
        engine.setValue("[Pioneered]", "show_cardbot", 0);
    }
    if (cards[0]) {
        engine.setValue("[Pioneered]", "show_cardtop", 1);
    }
    if (cards[1]) {
        engine.setValue("[Pioneered]", "show_cardbot", 1);
    }
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

TimeClamp.shutdown = function () {
    if (TimeClamp.connection) {
        TimeClamp.connection.disconnect();
    }
    TimeClamp.modeConnections.forEach(function (c) { c.disconnect(); });
};
