// SPDX-License-Identifier: MIT
// Geometry and legend formatting for keymap documents written by zmkkeymap.py.
.pragma library

// Bounding box of a physical layout in key units (ZMK stores 1/100 u and
// 1/100 degree), with rotated keys accounted for.
function bounds(keys) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const k of keys) {
        const a = k.r / 100 * Math.PI / 180;
        const cos = Math.cos(a), sin = Math.sin(a);
        for (const [cx, cy] of [[k.x, k.y], [k.x + k.w, k.y], [k.x, k.y + k.h], [k.x + k.w, k.y + k.h]]) {
            const px = k.r ? k.rx + (cx - k.rx) * cos - (cy - k.ry) * sin : cx;
            const py = k.r ? k.ry + (cx - k.rx) * sin + (cy - k.ry) * cos : cy;
            minX = Math.min(minX, px); maxX = Math.max(maxX, px);
            minY = Math.min(minY, py); maxY = Math.max(maxY, py);
        }
    }
    if (minX === Infinity) {
        return { x: 0, y: 0, w: 1, h: 1 };
    }
    return { x: minX / 100, y: minY / 100, w: (maxX - minX) / 100, h: (maxY - minY) / 100 };
}

const SYMBOL = {
    BSPC: "⌫", DEL: "⌦", TAB: "⇥", CAPS: "⇪", LSHFT: "⇧", RSHFT: "⇧",
};

const TEXT = {
    BSPC: "Bksp", DEL: "Del", TAB: "Tab", CAPS: "Caps", LSHFT: "Shift", RSHFT: "Shift",
};

const COMMON = {
    RET: "Enter", KP_ENTER: "Enter", SPACE: "Space", ESC: "Esc", INS: "Ins", HOME: "Home", END: "End", PG_UP: "PgUp", PG_DN: "PgDn",
    LEFT: "←", RIGHT: "→", UP: "↑", DOWN: "↓",
    LCTRL: "Ctrl", RCTRL: "Ctrl", LALT: "Alt", RALT: "Alt", LGUI: "Meta", RGUI: "Meta",
    PSCRN: "PrtSc", SLCK: "ScrLk", PAUSE_BREAK: "Pause", K_APP: "Menu", KP_NUM: "NumLk",
    MINUS: "-", EQUAL: "=", LBKT: "[", RBKT: "]", BSLH: "\\", NUHS: "#", NUBS: "\\",
    SEMI: ";", SQT: "'", GRAVE: "`", COMMA: ",", DOT: ".", FSLH: "/",
    EXCL: "!", AT: "@", HASH: "#", DLLR: "$", PRCNT: "%", CARET: "^", AMPS: "&",
    STAR: "*", LPAR: "(", RPAR: ")", UNDER: "_", PLUS: "+", LBRC: "{", RBRC: "}",
    PIPE: "|", COLON: ":", DQT: "\"", TILDE: "~", LT: "<", GT: ">", QMARK: "?",
    KP_SLASH: "/", KP_MULTIPLY: "*", KP_MINUS: "-", KP_PLUS: "+", KP_DOT: ".", KP_EQUAL: "=",
    KP_COMMA: ",",
    C_VOL_UP: "Vol+", C_VOL_DN: "Vol−", C_MUTE: "Mute", K_VOL_UP: "Vol+", K_VOL_DN: "Vol−",
    K_MUTE: "Mute", C_PP: "Play", C_PLAY: "Play", C_PAUSE: "Pause", C_NEXT: "Next",
    C_PREV: "Prev", C_STOP: "Stop", C_FF: "Fwd", C_RW: "Rew", C_EJECT: "Eject",
    C_BRI_UP: "Bri+", C_BRI_DN: "Bri−", C_POWER: "Power", C_SLEEP: "Sleep",
    C_AL_CALC: "Calc", C_AL_WWW: "Web", C_AL_MAIL: "Mail", C_AL_FILES: "Files",
    C_AL_MEDIA: "Media", C_AC_SEARCH: "Search", C_AC_HOME: "Home", C_AC_BACK: "Back",
    C_AC_FORWARD: "Fwd", C_AC_REFRESH: "Reload", C_AC_BOOKMARKS: "Bkmk",
    K_UNDO: "Undo", K_CUT: "Cut", K_COPY: "Copy", K_PASTE: "Paste", K_FIND: "Find",
    K_AGAIN: "Again", K_HELP: "Help", K_MENU: "Menu", K_POWER: "Power",
};

const MODS = { LC: "Ctrl", RC: "Ctrl", LS: "Shift", RS: "Shift", LA: "Alt", RA: "Alt", LG: "Meta", RG: "Meta" };

function keyName(code, symbols) {
    const table = symbols ? SYMBOL : TEXT;
    if (code in table) return table[code];
    if (code in COMMON) return COMMON[code];
    let m = /^(?:KP_)?N(\d)$/.exec(code);
    if (m) return m[1];
    return code;
}

// "LC(LS(T))" -> "Ctrl+⇧T"; a lone shifted letter stays a letter.
function keycode(code, symbols) {
    const mods = [];
    let m;
    while ((m = /^(L[CSAG]|R[CSAG])\((.*)\)$/.exec(code))) {
        mods.push(m[1]);
        code = m[2];
    }
    let label = keyName(code, symbols);
    if (!mods.length) return label;
    const shift = mods.some(x => x[1] === "S");
    const others = mods.filter(x => x[1] !== "S").map(x => MODS[x] + "+");
    if (shift && !(others.length === 0 && /^[A-Z]$/.test(code))) {
        others.push(symbols ? "⇧" : "Shift+");
    }
    return others.join("") + label;
}

// {tap, hold} display strings for one key of a layer document.
function legend(key, symbols) {
    if (!key) return { tap: "", hold: "" };
    switch (key.kind) {
    case "key":
        return { tap: keycode(key.tap, symbols), hold: "" };
    case "holdtap":
        return {
            tap: keycode(key.tap, symbols),
            hold: key.layer !== undefined ? key.hold : keycode(key.hold, symbols),
        };
    case "layer":
    case "other":
        return { tap: key.tap, hold: "" };
    default:
        return { tap: "", hold: "" };
    }
}

function describe(key) {
    if (!key) return "";
    switch (key.kind) {
    case "trans": return "Transparent";
    case "none": return "None";
    case "layer": return key.behavior + ": " + key.tap;
    case "holdtap": return key.behavior + ": tap " + key.tap + ", hold " + key.hold;
    default: return (key.behavior || "") + (key.tap ? ": " + key.tap : "");
    }
}
