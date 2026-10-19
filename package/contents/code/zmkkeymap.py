#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the keymap off a ZMK keyboard over ZMK Studio's USB serial RPC.

Stdlib only, so it can ship inside the plasmoid package. The protobuf and
framing code below covers just the slice of zmk-studio-messages we use.

    zmkkeymap.py probe               device name + lock state (no unlock needed)
    zmkkeymap.py fetch [--wait 60]   read keymap, write cache, print it
    zmkkeymap.py show                print the cached keymap
    zmkkeymap.py render RAW.json     rebuild the keymap from a saved raw dump
"""

import argparse
import datetime
import glob
import grp
import json
import os
import select
import sys
import termios
import time
import tty

FORMAT_VERSION = 1
DEFAULT_OUT = os.path.join(
    os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
    "plasma-zmk-keymap",
    "keymap.json",
)

# --- protobuf wire format ----------------------------------------------------


def enc_varint(n):
    out = bytearray()
    n &= (1 << 64) - 1
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def enc_field(num, value):
    """Encode an int (varint) or bytes (length-delimited) field."""
    if isinstance(value, (bytes, bytearray)):
        return enc_varint(num << 3 | 2) + enc_varint(len(value)) + bytes(value)
    return enc_varint(num << 3 | 0) + enc_varint(int(value))


def parse_msg(buf):
    """Decode a message into {field: [values]}; length-delimited stays bytes."""
    fields = {}
    i = 0
    while i < len(buf):
        key, i = _dec_varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            val, i = _dec_varint(buf, i)
        elif wt == 2:
            ln, i = _dec_varint(buf, i)
            val, i = bytes(buf[i : i + ln]), i + ln
        elif wt == 5:
            val, i = int.from_bytes(buf[i : i + 4], "little"), i + 4
        elif wt == 1:
            val, i = int.from_bytes(buf[i : i + 8], "little"), i + 8
        else:
            raise ValueError(f"unsupported wire type {wt}")
        fields.setdefault(num, []).append(val)
    return fields


def _dec_varint(buf, i):
    n = shift = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7


def first(fields, num, default=None):
    vals = fields.get(num)
    return vals[0] if vals else default


def as_int32(n):
    n &= 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


def unzigzag(n):
    return (n >> 1) ^ -(n & 1)


def as_str(b):
    return b.decode("utf-8", "replace") if b is not None else ""


# --- framing -----------------------------------------------------------------

SOF, ESC, EOF = 0xAB, 0xAC, 0xAD


def frame(payload):
    out = bytearray([SOF])
    for b in payload:
        if b in (SOF, ESC, EOF):
            out.append(ESC)
        out.append(b)
    out.append(EOF)
    return bytes(out)


class Deframer:
    def __init__(self):
        self.buf = None
        self.escaped = False

    def feed(self, data):
        """Yield every complete frame payload contained in data."""
        for b in data:
            if self.buf is None:
                if b == SOF:
                    self.buf = bytearray()
            elif self.escaped:
                self.buf.append(b)
                self.escaped = False
            elif b == ESC:
                self.escaped = True
            elif b == EOF:
                yield bytes(self.buf)
                self.buf = None
            elif b == SOF:
                self.buf = bytearray()
            else:
                self.buf.append(b)


# --- transport -----------------------------------------------------------------

ZMK_USB_IDS = {("1d50", "615e")}


def find_port():
    """Find a ZMK Studio serial port: by-id name first, then USB vid:pid."""
    for path in sorted(glob.glob("/dev/serial/by-id/*")):
        if "zmk" in os.path.basename(path).lower():
            return path
    for tty_dir in sorted(glob.glob("/sys/class/tty/ttyACM*")):
        dev = os.path.realpath(os.path.join(tty_dir, "device"))
        usb = os.path.dirname(dev)
        try:
            ids = tuple(
                open(os.path.join(usb, f)).read().strip()
                for f in ("idVendor", "idProduct")
            )
        except OSError:
            continue
        if ids in ZMK_USB_IDS:
            return "/dev/" + os.path.basename(tty_dir)
    return None


class SerialPort:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            tty.setraw(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[2] |= termios.CLOCAL | termios.CREAD
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            termios.tcflush(self.fd, termios.TCIOFLUSH)
        except termios.error:
            os.close(self.fd)
            raise OSError(f"{path} is not a usable serial port.") from None

    def write(self, data):
        view = memoryview(data)
        while view:
            _, w, _ = select.select([], [self.fd], [], 2)
            if not w:
                raise TimeoutError("serial write timed out")
            view = view[os.write(self.fd, view) :]

    def read(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        return os.read(self.fd, 4096) if r else b""

    def close(self):
        os.close(self.fd)


# --- RPC ---------------------------------------------------------------------

# zmk.studio.Request subsystem field numbers
CORE, BEHAVIORS, KEYMAP = 3, 4, 5
META_ERRORS = {
    0: "generic error",
    1: "keyboard is locked",
    2: "RPC not supported by firmware",
    3: "firmware could not decode request",
    4: "firmware could not encode response",
}


class RpcError(Exception):
    pass


class LockedError(RpcError):
    pass


class StudioClient:
    def __init__(self, port):
        self.port = port
        self.deframer = Deframer()
        self.next_id = 1
        self.notifications = []

    def call(self, subsystem, req_field, req_value=1, timeout=3.0):
        """Send one request; return the subsystem response as parsed fields."""
        rid = self.next_id
        self.next_id += 1
        inner = enc_field(req_field, req_value)
        self.port.write(frame(enc_field(1, rid) + enc_field(subsystem, inner)))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for payload in self.deframer.feed(self.port.read(0.2)):
                resp = parse_msg(payload)
                if 2 in resp:
                    self.notifications.append(parse_msg(resp[2][0]))
                    continue
                rr = parse_msg(first(resp, 1, b""))
                if first(rr, 1) != rid:
                    continue
                if 2 in rr:
                    meta = parse_msg(rr[2][0])
                    if 2 in meta:
                        code = meta[2][0]
                        exc = LockedError if code == 1 else RpcError
                        raise exc(META_ERRORS.get(code, f"error {code}"))
                    return {}
                if subsystem not in rr:
                    raise RpcError("response for a different subsystem")
                return parse_msg(rr[subsystem][0])
        raise TimeoutError("no response from keyboard")

    def wait_unlocked(self, timeout):
        """Block until a lock_state_changed(UNLOCKED) notification arrives."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for note in self.notifications:
                core = parse_msg(first(note, 2, b""))
                if first(core, 1) == 1:
                    return True
            self.notifications.clear()
            for payload in self.deframer.feed(self.port.read(0.5)):
                resp = parse_msg(payload)
                if 2 in resp:
                    self.notifications.append(parse_msg(resp[2][0]))
        return False

    # zmk.core
    def device_info(self):
        r = parse_msg(first(self.call(CORE, 1), 1, b""))
        return {"name": as_str(first(r, 1)), "serial": first(r, 2, b"").hex()}

    def unlocked(self):
        return first(self.call(CORE, 2), 2, 0) == 1

    # zmk.behaviors
    def behaviors(self):
        ids = []
        for v in self.call(BEHAVIORS, 1).get(1, []):
            ids += _packed_varints(parse_msg(v), 1)
        out = {}
        for bid in ids:
            d = parse_msg(first(self.call(BEHAVIORS, 2, enc_field(1, bid)), 2, b""))
            out[bid] = {
                "name": as_str(first(d, 2)),
                "metadata": [_param_set(parse_msg(s)) for s in d.get(3, [])],
            }
        return out

    # zmk.keymap
    def keymap(self):
        km = parse_msg(first(self.call(KEYMAP, 1), 1, b""))
        layers = []
        for raw in km.get(1, []):
            layer = parse_msg(raw)
            bindings = []
            for b in layer.get(3, []):
                f = parse_msg(b)
                bindings.append(
                    [unzigzag(first(f, 1, 0)), first(f, 2, 0), first(f, 3, 0)]
                )
            layers.append(
                {
                    "id": first(layer, 1, 0),
                    "name": as_str(first(layer, 2)),
                    "bindings": bindings,
                }
            )
        return layers

    def physical_layouts(self):
        pl = parse_msg(first(self.call(KEYMAP, 6), 6, b""))
        layouts = []
        for raw in pl.get(2, []):
            layout = parse_msg(raw)
            keys = []
            for k in layout.get(2, []):
                f = parse_msg(k)
                w, h, x, y, r, rx, ry = (unzigzag(first(f, i, 0)) for i in range(1, 8))
                keys.append({"w": w, "h": h, "x": x, "y": y, "r": r, "rx": rx, "ry": ry})
            layouts.append({"name": as_str(first(layout, 1)), "keys": keys})
        return {"active": first(pl, 1, 0), "layouts": layouts}


def _packed_varints(fields, num):
    out = []
    for v in fields.get(num, []):
        if isinstance(v, bytes):
            i = 0
            while i < len(v):
                n, i = _dec_varint(v, i)
                out.append(n)
        else:
            out.append(v)
    return out


def _param_set(fields):
    return {
        "param1": [_param_desc(parse_msg(v)) for v in fields.get(1, [])],
        "param2": [_param_desc(parse_msg(v)) for v in fields.get(2, [])],
    }


def _param_desc(f):
    desc = {"name": as_str(first(f, 1))}
    if 2 in f:
        desc["type"] = "nil"
    elif 3 in f:
        desc["type"], desc["value"] = "constant", f[3][0]
    elif 4 in f:
        rng = parse_msg(f[4][0])
        desc["type"] = "range"
        desc["min"], desc["max"] = as_int32(first(rng, 1, 0)), as_int32(first(rng, 2, 0))
    elif 5 in f:
        desc["type"] = "hid_usage"
    elif 6 in f:
        desc["type"] = "layer_id"
    return desc


# --- HID usages --------------------------------------------------------------
# Names follow ZMK's dt-bindings/zmk/keys.h so they read like a .keymap file.

KEYBOARD_PAGE = {
    **{0x04 + i: chr(ord("A") + i) for i in range(26)},
    **{0x1E + i: f"N{(i + 1) % 10}" for i in range(10)},
    0x28: "RET", 0x29: "ESC", 0x2A: "BSPC", 0x2B: "TAB", 0x2C: "SPACE",
    0x2D: "MINUS", 0x2E: "EQUAL", 0x2F: "LBKT", 0x30: "RBKT", 0x31: "BSLH",
    0x32: "NUHS", 0x33: "SEMI", 0x34: "SQT", 0x35: "GRAVE", 0x36: "COMMA",
    0x37: "DOT", 0x38: "FSLH", 0x39: "CAPS",
    **{0x3A + i: f"F{i + 1}" for i in range(12)},
    0x46: "PSCRN", 0x47: "SLCK", 0x48: "PAUSE_BREAK", 0x49: "INS", 0x4A: "HOME",
    0x4B: "PG_UP", 0x4C: "DEL", 0x4D: "END", 0x4E: "PG_DN", 0x4F: "RIGHT",
    0x50: "LEFT", 0x51: "DOWN", 0x52: "UP", 0x53: "KP_NUM", 0x54: "KP_SLASH",
    0x55: "KP_MULTIPLY", 0x56: "KP_MINUS", 0x57: "KP_PLUS", 0x58: "KP_ENTER",
    **{0x59 + i: f"KP_N{i + 1}" for i in range(9)},
    0x62: "KP_N0", 0x63: "KP_DOT", 0x64: "NUBS", 0x65: "K_APP", 0x66: "K_POWER",
    0x67: "KP_EQUAL",
    **{0x68 + i: f"F{i + 13}" for i in range(12)},
    0x74: "K_EXEC", 0x75: "K_HELP", 0x76: "K_MENU", 0x77: "K_SELECT",
    0x78: "K_STOP", 0x79: "K_AGAIN", 0x7A: "K_UNDO", 0x7B: "K_CUT",
    0x7C: "K_COPY", 0x7D: "K_PASTE", 0x7E: "K_FIND", 0x7F: "K_MUTE",
    0x80: "K_VOL_UP", 0x81: "K_VOL_DN", 0x85: "KP_COMMA", 0x87: "INT_RO",
    0x88: "INT_KANA", 0x89: "INT_YEN", 0x8A: "INT_HENKAN", 0x8B: "INT_MUHENKAN",
    0x90: "LANG1", 0x91: "LANG2",
    0xE0: "LCTRL", 0xE1: "LSHFT", 0xE2: "LALT", 0xE3: "LGUI",
    0xE4: "RCTRL", 0xE5: "RSHFT", 0xE6: "RALT", 0xE7: "RGUI",
}

CONSUMER_PAGE = {
    0x30: "C_POWER", 0x32: "C_SLEEP", 0x6F: "C_BRI_UP", 0x70: "C_BRI_DN",
    0xB0: "C_PLAY", 0xB1: "C_PAUSE", 0xB3: "C_FF", 0xB4: "C_RW",
    0xB5: "C_NEXT", 0xB6: "C_PREV", 0xB7: "C_STOP", 0xB8: "C_EJECT",
    0xCD: "C_PP", 0xE2: "C_MUTE", 0xE9: "C_VOL_UP", 0xEA: "C_VOL_DN",
    0x183: "C_AL_MEDIA", 0x18A: "C_AL_MAIL", 0x192: "C_AL_CALC",
    0x194: "C_AL_FILES", 0x196: "C_AL_WWW", 0x221: "C_AC_SEARCH",
    0x223: "C_AC_HOME", 0x224: "C_AC_BACK", 0x225: "C_AC_FORWARD",
    0x227: "C_AC_REFRESH", 0x22A: "C_AC_BOOKMARKS",
}

SHIFTED = {
    "N1": "EXCL", "N2": "AT", "N3": "HASH", "N4": "DLLR", "N5": "PRCNT",
    "N6": "CARET", "N7": "AMPS", "N8": "STAR", "N9": "LPAR", "N0": "RPAR",
    "MINUS": "UNDER", "EQUAL": "PLUS", "LBKT": "LBRC", "RBKT": "RBRC",
    "BSLH": "PIPE", "SEMI": "COLON", "SQT": "DQT", "GRAVE": "TILDE",
    "COMMA": "LT", "DOT": "GT", "FSLH": "QMARK",
}

# implicit-modifier bits (bits 24-31 of a ZMK keycode) -> ZMK wrapper macro
MOD_WRAPPERS = [
    (0x01, "LC"), (0x02, "LS"), (0x04, "LA"), (0x08, "LG"),
    (0x10, "RC"), (0x20, "RS"), (0x40, "RA"), (0x80, "RG"),
]


def keycode_name(usage):
    """ZMK keycode for a HID usage, e.g. 0x02070004 -> 'LS(A)', '!' -> 'EXCL'."""
    mods, page, uid = usage >> 24, (usage >> 16) & 0xFF, usage & 0xFFFF
    if page in (0, 0x07):
        name = KEYBOARD_PAGE.get(uid, f"0x{uid:02X}")
    elif page == 0x0C:
        name = CONSUMER_PAGE.get(uid, f"C_0x{uid:03X}")
    else:
        name = f"0x{page:02X}:{uid:04X}"
    if mods & 0x02 and name in SHIFTED:
        name, mods = SHIFTED[name], mods & ~0x02
    for bit, wrapper in reversed(MOD_WRAPPERS):
        if mods & bit:
            name = f"{wrapper}({name})"
    return name


# --- bindings -> legends -----------------------------------------------------

BT_COMMANDS = {0: "BT Clear", 1: "BT Next", 2: "BT Prev", 4: "BT Clear All"}
OUT_COMMANDS = {0: "USB/BLE", 1: "USB", 2: "BLE"}
RGB_COMMANDS = {
    0: "RGB Toggle", 1: "RGB On", 2: "RGB Off", 3: "Hue+", 4: "Hue-", 5: "Sat+",
    6: "Sat-", 7: "Bright+", 8: "Bright-", 9: "Speed+", 10: "Speed-",
    11: "Effect+", 12: "Effect-", 13: "RGB Color",
}
SIMPLE_LABELS = {
    "reset": "Reset", "bootloader": "Boot", "studio unlock": "Studio",
    "caps word": "Caps Word", "key repeat": "Repeat", "soft off": "Off",
    "grave/escape": "Esc/`",
}


def _matches(desc, value):
    t = desc.get("type")
    if t == "constant":
        return desc["value"] == value
    if t == "range":
        return desc["min"] <= value <= desc["max"]
    if t == "nil":
        return value == 0
    return t in ("hid_usage", "layer_id")


def _pick(descs, value):
    for d in descs:
        if _matches(d, value):
            return d
    return None


def _param_types(metadata, p1, p2):
    """Return the (param1, param2) descriptions that best explain a binding."""
    best = (None, None)
    for pset in metadata:
        d1 = _pick(pset["param1"], p1) if pset["param1"] else {"type": "nil"}
        d2 = _pick(pset["param2"], p2) if pset["param2"] else {"type": "nil"}
        if d1 and d2:
            return d1, d2
        if d1 and not best[0]:
            best = (d1, d2)
    return best


class Resolver:
    def __init__(self, behaviors, layers):
        self.behaviors = behaviors
        self.layer_index = {layer["id"]: i for i, layer in enumerate(layers)}
        self.layer_names = [layer_name(layer, i) for i, layer in enumerate(layers)]

    def layer_ref(self, layer_id):
        idx = self.layer_index.get(layer_id, layer_id)
        name = self.layer_names[idx] if 0 <= idx < len(self.layer_names) else f"L{idx}"
        return idx, name

    def key(self, binding):
        bid, p1, p2 = binding
        beh = self.behaviors.get(bid)
        if beh is None:
            return {"kind": "other", "tap": "?", "behavior": f"behavior #{bid}"}
        name = beh["name"]
        low = name.lower()
        if low == "transparent":
            return {"kind": "trans"}
        if low == "none":
            return {"kind": "none"}

        d1, d2 = _param_types(beh["metadata"], p1, p2)
        t1 = (d1 or {}).get("type")
        t2 = (d2 or {}).get("type")
        out = {"behavior": name}

        if t1 == "hid_usage" and t2 in (None, "nil"):
            out.update(kind="key", tap=keycode_name(p1))
            if low != "key press":
                out["via"] = name
        elif t1 == "hid_usage" and t2 == "hid_usage":
            out.update(kind="holdtap", tap=keycode_name(p2), hold=keycode_name(p1))
        elif t1 == "layer_id" and t2 == "hid_usage":
            idx, lname = self.layer_ref(p1)
            out.update(kind="holdtap", tap=keycode_name(p2), hold=lname, layer=idx)
        elif t1 == "layer_id":
            idx, lname = self.layer_ref(p1)
            mode = (
                "tog" if "toggle" in low
                else "sl" if "sticky" in low
                else "to" if low.startswith("to ")
                else "mo"
            )
            out.update(kind="layer", tap=lname, layer=idx, mode=mode)
        else:
            out.update(kind="other", tap=self.other_label(low, name, p1, p2, d1, d2))
        return out

    @staticmethod
    def other_label(low, name, p1, p2, d1, d2):
        if low == "bluetooth":
            if p1 == 3:
                return f"BT {p2}"
            if p1 == 5:
                return f"BT Off {p2}"
            return BT_COMMANDS.get(p1, f"BT {p1}")
        if low.startswith("output"):
            return OUT_COMMANDS.get(p1, f"OUT {p1}")
        if "underglow" in low or low.startswith("rgb"):
            return RGB_COMMANDS.get(p1, f"RGB {p1}")
        if low in SIMPLE_LABELS:
            return SIMPLE_LABELS[low]
        parts = []
        for d, v in ((d1, p1), (d2, p2)):
            if not d or d.get("type") == "nil":
                continue
            parts.append(d["name"] if d.get("type") == "constant" and d["name"] else str(v))
        return " ".join([name] + parts)


def layer_name(layer, index):
    return layer["name"] or f"Layer {index}"


def build(raw):
    """Turn a raw Studio dump into the renderer-facing keymap document."""
    layouts = raw["physical_layouts"]
    layout = layouts["layouts"][layouts["active"]]
    behaviors = {int(k): v for k, v in raw["behaviors"].items()}
    resolver = Resolver(behaviors, raw["layers"])
    return {
        "format": FORMAT_VERSION,
        "source": "zmk-studio",
        "fetched": raw.get("fetched"),
        "device": raw["device"],
        "layout": layout,
        "layers": [
            {
                "name": layer_name(layer, i),
                "keys": [resolver.key(b) for b in layer["bindings"]],
            }
            for i, layer in enumerate(raw["layers"])
        ],
        "raw": raw,
    }


# --- commands ----------------------------------------------------------------


def emit(doc, code=0):
    json.dump(doc, sys.stdout, indent=None, separators=(",", ":"))
    sys.stdout.write("\n")
    return code


def fail(kind, message):
    return emit({"error": kind, "message": message}, 1)


def open_client(port):
    path = port or find_port()
    if not path:
        raise FileNotFoundError(
            "No ZMK Studio serial port found. Connect the keyboard over USB with "
            "ZMK Studio enabled, or set its serial port in the widget settings."
        )
    try:
        return path, StudioClient(SerialPort(path))
    except FileNotFoundError:
        raise FileNotFoundError(f"Serial port {path} doesn't exist.") from None
    except PermissionError:
        raise PermissionError(f"No permission to open {path}. {permission_hint(path)}") from None


def permission_hint(path):
    try:
        group = grp.getgrgid(os.stat(path).st_gid).gr_name
    except (OSError, KeyError):
        return "Add yourself to the group that owns it, then log out and back in."
    return (
        f"Add yourself to the {group} group (sudo usermod -aG {group} $USER), "
        "then log out and back in."
    )


def cmd_probe(args):
    path, client = open_client(args.port)
    try:
        info = client.device_info()
        return emit({"port": path, **info, "unlocked": client.unlocked()})
    finally:
        client.port.close()


def cmd_fetch(args):
    path, client = open_client(args.port)
    try:
        device = client.device_info()
        if not client.unlocked():
            print(
                "keyboard is locked; press your &studio_unlock key",
                file=sys.stderr,
                flush=True,
            )
            if not client.wait_unlocked(args.wait):
                return fail(
                    "locked",
                    "Keyboard stayed locked. Press the key bound to "
                    "&studio_unlock, then refresh.",
                )
        layers = client.keymap()
        used = {b[0] for layer in layers for b in layer["bindings"]}
        behaviors = {
            bid: beh for bid, beh in client.behaviors().items() if bid in used
        }
        raw = {
            "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "device": {**device, "port": path},
            "behaviors": {str(k): v for k, v in sorted(behaviors.items())},
            "layers": layers,
            "physical_layouts": client.physical_layouts(),
        }
    finally:
        client.port.close()

    doc = build(raw)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, args.out)
    return emit(doc)


def cmd_show(args):
    try:
        with open(args.out) as f:
            return emit(json.load(f))
    except FileNotFoundError:
        return fail("no-cache", "No keymap read yet. Refresh with the keyboard on USB.")


def cmd_render(args):
    with open(args.raw) as f:
        raw = json.load(f)
    return emit(build(raw.get("raw", raw)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", help="serial device (default: autodetect)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="keymap cache file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--wait", type=float, default=60, help="seconds to wait for unlock")
    sub.add_parser("show")
    render = sub.add_parser("render")
    render.add_argument("raw")
    args = ap.parse_args(argv)
    args.out = os.path.expanduser(args.out)

    handler = {
        "probe": cmd_probe,
        "fetch": cmd_fetch,
        "show": cmd_show,
        "render": cmd_render,
    }[args.cmd]
    try:
        return handler(args)
    except (OSError, TimeoutError, RpcError) as e:
        kind = "locked" if isinstance(e, LockedError) else "device"
        return fail(kind, str(e))


if __name__ == "__main__":
    sys.exit(main())
