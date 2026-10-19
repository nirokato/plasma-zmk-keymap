import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "package", "contents", "code"))

import zmkkeymap as z  # noqa: E402


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name)) as f:
        return json.load(f)


def hid(page, uid, mods=0):
    return mods << 24 | page << 16 | uid


class WireFormat(unittest.TestCase):
    def test_frame_roundtrip_escapes_control_bytes(self):
        payload = bytes([1, z.SOF, 2, z.ESC, 3, z.EOF, 4])
        framed = z.frame(payload)
        self.assertEqual((framed[0], framed[-1]), (z.SOF, z.EOF))
        self.assertIn(bytes([z.ESC, z.SOF]), framed)
        self.assertEqual(list(z.Deframer().feed(framed)), [payload])

    def test_deframer_handles_split_reads_and_noise(self):
        framed = b"\x00junk" + z.frame(b"abc") + z.frame(b"de")
        d = z.Deframer()
        got = []
        for i in range(len(framed)):
            got += d.feed(framed[i : i + 1])
        self.assertEqual(got, [b"abc", b"de"])

    def test_nested_message(self):
        inner = z.enc_field(1, 300) + z.enc_field(2, b"hi")
        msg = z.parse_msg(z.enc_field(5, inner))
        self.assertEqual(z.parse_msg(msg[5][0]), {1: [300], 2: [b"hi"]})

    def test_zigzag(self):
        for n in (0, 1, -1, 2400, -2400):
            self.assertEqual(z.unzigzag((n << 1) ^ (n >> 31)), n)


class Keycodes(unittest.TestCase):
    def test_plain_and_shifted(self):
        self.assertEqual(z.keycode_name(hid(7, 0x04)), "A")
        self.assertEqual(z.keycode_name(hid(7, 0x27)), "N0")
        self.assertEqual(z.keycode_name(hid(7, 0x1E, 0x02)), "EXCL")
        self.assertEqual(z.keycode_name(hid(7, 0x2D, 0x02)), "UNDER")

    def test_modifier_wrappers(self):
        self.assertEqual(z.keycode_name(hid(7, 0x06, 0x01)), "LC(C)")
        self.assertEqual(z.keycode_name(hid(7, 0x04, 0x02)), "LS(A)")
        self.assertEqual(z.keycode_name(hid(7, 0x1E, 0x03)), "LC(EXCL)")

    def test_consumer_and_unknown(self):
        self.assertEqual(z.keycode_name(hid(0x0C, 0xE9)), "C_VOL_UP")
        self.assertEqual(z.keycode_name(hid(0x0C, 0x999)), "C_0x999")


class StockCorne(unittest.TestCase):
    """Keymap read from a real Corne running stock ZMK + Studio."""

    @classmethod
    def setUpClass(cls):
        cls.doc = z.build(fixture("corne-studio-raw.json"))

    def test_shape(self):
        self.assertEqual(len(self.doc["layout"]["keys"]), 42)
        self.assertEqual([l["name"] for l in self.doc["layers"]], ["Base", "Lower", "Raise"])
        for layer in self.doc["layers"]:
            self.assertEqual(len(layer["keys"]), 42)

    def test_bindings(self):
        base, lower, raise_ = (l["keys"] for l in self.doc["layers"])
        self.assertEqual(base[0], {"behavior": "Key Press", "kind": "key", "tap": "TAB"})
        self.assertEqual(base[37]["kind"], "layer")
        self.assertEqual((base[37]["tap"], base[37]["layer"], base[37]["mode"]), ("Lower", 1, "mo"))
        self.assertEqual(lower[13]["tap"], "BT 0")
        self.assertEqual(lower[12]["tap"], "BT Clear")
        self.assertEqual(lower[26], {"kind": "trans"})
        self.assertEqual(raise_[1]["tap"], "EXCL")

    def test_thumb_rotation_survives(self):
        thumbs = self.doc["layout"]["keys"][36:42]
        self.assertEqual([k["r"] for k in thumbs], [0, 1200, 2400, -2400, -1200, 0])


class HoldTaps(unittest.TestCase):
    def setUp(self):
        hid_param = {"name": "Key", "type": "hid_usage"}
        behaviors = {
            1: {"name": "Mod-Tap", "metadata": [{"param1": [hid_param], "param2": [hid_param]}]},
            2: {
                "name": "Layer-Tap",
                "metadata": [{"param1": [{"name": "Layer", "type": "layer_id"}], "param2": [hid_param]}],
            },
            3: {"name": "Toggle Layer", "metadata": [{"param1": [{"name": "Layer", "type": "layer_id"}], "param2": []}]},
            4: {"name": "Sticky Key", "metadata": [{"param1": [hid_param], "param2": []}]},
            5: {"name": "Output Selection", "metadata": [{"param1": [{"name": "USB", "type": "constant", "value": 1}], "param2": []}]},
        }
        layers = [{"id": 0, "name": "", "bindings": []}, {"id": 7, "name": "Sym", "bindings": []}]
        self.r = z.Resolver(behaviors, layers)

    def test_mod_tap(self):
        k = self.r.key([1, hid(7, 0xE3), hid(7, 0x04)])
        self.assertEqual((k["kind"], k["tap"], k["hold"]), ("holdtap", "A", "LGUI"))

    def test_layer_tap_resolves_layer_id_to_index(self):
        k = self.r.key([2, 7, hid(7, 0x2C)])
        self.assertEqual((k["kind"], k["tap"], k["hold"], k["layer"]), ("holdtap", "SPACE", "Sym", 1))

    def test_layer_modes_and_unnamed_layers(self):
        k = self.r.key([3, 0, 0])
        self.assertEqual((k["kind"], k["tap"], k["mode"]), ("layer", "Layer 0", "tog"))

    def test_non_keypress_key_is_marked(self):
        k = self.r.key([4, hid(7, 0xE1), 0])
        self.assertEqual((k["tap"], k["via"]), ("LSHFT", "Sticky Key"))

    def test_other_and_unknown(self):
        self.assertEqual(self.r.key([5, 1, 0])["tap"], "USB")
        self.assertEqual(self.r.key([99, 0, 0])["kind"], "other")


class FakePort:
    """Answers each request with a canned response for the same request id."""

    def __init__(self, respond):
        self.respond = respond
        self.pending = b""
        self.deframer = z.Deframer()

    def write(self, data):
        for payload in self.deframer.feed(data):
            req = z.parse_msg(payload)
            rid = req[1][0]
            sub = next(k for k in req if k != 1)
            body = self.respond(sub, z.parse_msg(req[sub][0]))
            rr = z.enc_field(1, rid) + z.enc_field(sub, body)
            note = z.enc_field(2, z.enc_field(2, z.enc_field(1, 0)))
            self.pending += z.frame(note) + z.frame(z.enc_field(1, rr))

    def read(self, timeout):
        out, self.pending = self.pending, b""
        return out

    def close(self):
        pass


class Rpc(unittest.TestCase):
    def test_device_info_ignores_interleaved_notifications(self):
        def respond(sub, req):
            self.assertEqual((sub, req), (z.CORE, {1: [1]}))
            return z.enc_field(1, z.enc_field(1, b"Corne") + z.enc_field(2, b"\x01\xab"))

        client = z.StudioClient(FakePort(respond))
        self.assertEqual(client.device_info(), {"name": "Corne", "serial": "01ab"})
        self.assertEqual(len(client.notifications), 1)

    def test_locked_error(self):
        # meta.Response{simple_error: UNLOCK_REQUIRED} in RequestResponse field 2
        meta_error = z.enc_field(1, 1) + z.enc_field(2, z.enc_field(2, 1))
        port = FakePort(None)
        port.write = lambda data: setattr(port, "pending", z.frame(z.enc_field(1, meta_error)))
        with self.assertRaises(z.LockedError):
            z.StudioClient(port).keymap()


if __name__ == "__main__":
    unittest.main()
