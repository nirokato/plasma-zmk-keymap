# ZMK Keymap for Plasma

A KDE Plasma 6 widget that shows the keymap actually on your ZMK keyboard, read
straight off the board over ZMK Studio's USB connection. No zmk-config repo,
keymap-drawer run, or hand-kept SVG to drift out of date.

> **Just for fun.** Built for my own desk and shared as-is. Issues and pull
> requests are off; fork it and make it yours. MIT licensed: keep the
> copyright and license notice in your copy, and a link back is appreciated.

![All layers as tiles](docs/tiles.png)

Every layer is a tile, arranged in whichever grid gives the biggest keys for
the widget's shape: side by side when wide, stacked when tall, 2x2 and so on in
between, with a short last row centered. Resize the widget and the tiles
re-flow. Keys use the board's real physical layout (rotated thumb clusters
included) and the Plasma color scheme, so it follows light, dark, and the
background-less desktop mode.

![One layer at a time](docs/one-layer.png)

Set **Layers** to *One at a time* for a single layer with a tab strip; scroll
or click a layer key to switch.

- Transparent keys show the base layer through them, faintly.
- The key that holds a layer is highlighted on that layer.
- Hold-taps show the tap legend with the hold underneath.
- Legends come as symbols or words.

## What you need

- **Plasma 6.** Developed on 6.8; it targets the 6.0 API but older releases
  are untested.
- **`python3`** on plasmashell's `PATH`. Standard library only, nothing to
  pip install.
- **ZMK firmware with Studio over USB**, built for the half that plugs into
  the computer (the central half on a split). In a zmk-config `build.yaml`:

  ```yaml
  include:
    - board: nice_nano_v2
      shield: corne_left
      snippet: studio-rpc-usb-uart
      cmake-args: -DCONFIG_ZMK_STUDIO=y
  ```

  The board needs a physical layout, which most in-tree shields have. See
  <https://zmk.dev/docs/features/studio>.
- **A key bound to `&studio_unlock`** somewhere in the keymap. ZMK only hands
  out the keymap after it's pressed.
- **Access to the keyboard's serial port.** Usually that means being in the
  group that owns `/dev/ttyACM*`: `uucp` on Arch, `dialout` on
  Debian/Ubuntu/Fedora/openSUSE. Log out and back in after adding yourself.

## Install

Download [com.nirokato.zmkkeymap.plasmoid](https://github.com/nirokato/plasma-zmk-keymap/releases/latest/download/com.nirokato.zmkkeymap.plasmoid),
then either right-click the desktop, **Add Widgets... > Get New... > Install
Widget From Local File...**, or:

```sh
kpackagetool6 -t Plasma/Applet -i com.nirokato.zmkkeymap.plasmoid   # -u to upgrade
```

From a clone, `make install` / `make upgrade` do the same with `package/`.
After an upgrade, `plasmashell --replace` makes a running Plasma load the new
version.

## Use

Add **ZMK Keymap** to the desktop. With the keyboard on USB, click
**Read from Keyboard** (also *Read Keymap from Keyboard* in the right-click
menu) and press your `&studio_unlock` key if asked. The keymap is cached in
`~/.local/share/plasma-zmk-keymap/keymap.json`, so the widget keeps working
with the keyboard unplugged or on Bluetooth. Read it again after flashing new
firmware or changing the keymap in Studio.

Settings: layer arrangement, symbol or word legends, base layer through
transparent keys, the serial port (autodetected by default), and the cache
file location.

## Troubleshooting

- **"No ZMK Studio serial port found":** the keyboard isn't on USB, the
  firmware lacks Studio, or the board uses its own USB IDs. Autodetect looks
  for `zmk` in `/dev/serial/by-id/` names and ZMK's default `1d50:615e`;
  otherwise set the port (e.g. `/dev/serial/by-id/usb-...-if00`) in settings.
- **"No permission to open ...":** join the group the message names, then log
  out and back in.
- **"Keyboard stayed locked":** the widget waits two minutes for
  `&studio_unlock`; press it and read again.
- **Legends look wrong for my layout:** legends are the US HID names ZMK uses;
  a different OS keyboard layout isn't reflected.

## The helper

`package/contents/code/zmkkeymap.py` does the talking to the keyboard and is
usable on its own:

```sh
python3 zmkkeymap.py probe   # name + lock state, no unlock needed
python3 zmkkeymap.py fetch   # read keymap, update the cache
python3 zmkkeymap.py show    # print the cache
```

It speaks the ZMK Studio RPC protocol (protobuf over a framed serial stream)
with a hand-rolled codec covering just the messages it needs, and turns
behavior bindings into legends using the behavior metadata the firmware
reports. The cache keeps the raw RPC data next to the rendered layers, so
legend changes can be re-run with `zmkkeymap.py render <file>`.

## Development

```sh
make test        # helper unit tests, including a real Corne fixture
make preview     # render the view offscreen to build/preview/*.png
make lint        # qmllint
make dist        # dist/com.nirokato.zmkkeymap.plasmoid
```

`tools/preview.sh` renders `KeymapView` without Plasma at a spread of sizes;
`LAYERS=5 tools/preview.sh` pads the keymap to check tile arrangements, and
`plasmawindowed com.nirokato.zmkkeymap` runs the real widget in a window.

## Limits

- Studio's RPC doesn't expose combos, conditional layers, or macro contents,
  so those don't appear.
- Behaviors the firmware doesn't describe to Studio show as `?`.
- USB only; Studio's BLE transport isn't implemented.

## License

MIT, see [LICENSE](LICENSE).
