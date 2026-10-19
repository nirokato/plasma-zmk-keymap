#!/usr/bin/env bash
# Render the widget's keymap view to PNGs without Plasma.
#   tools/preview.sh [keymap.json] [outdir]
# keymap.json defaults to the bundled Corne fixture. SIZES overrides the list
# of renders; LAYERS=n pads the keymap to n layers to check tile arrangements.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=$(realpath -m "${2:-$root/build/preview}")
mkdir -p "$out"
if [[ -n ${1:-} ]]; then
    doc=$(realpath "$1")
else
    doc=$out/fixture.json
    python3 -I "$root/package/contents/code/zmkkeymap.py" render "$root/tests/fixtures/corne-studio-raw.json" > "$doc"
fi
if [[ -n ${LAYERS:-} ]]; then
    python3 -I - "$doc" "$LAYERS" "$out/padded.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
names = ["Nav", "Sym", "Num", "Fn", "Mouse", "Media", "Game"]
while len(doc["layers"]) < int(sys.argv[2]):
    i = len(doc["layers"])
    doc["layers"].append(dict(doc["layers"][i % 3], name=names[(i - 3) % len(names)]))
json.dump(doc, open(sys.argv[3], "w"))
PY
    doc=$out/padded.json
fi
sizes=${SIZES:-'[
 {"name":"wide","w":900,"h":330},
 {"name":"panorama","w":1560,"h":330},
 {"name":"square","w":760,"h":760},
 {"name":"tall","w":520,"h":900},
 {"name":"small","w":460,"h":200},
 {"name":"one-layer","w":900,"h":330,"layer":1,"mode":1},
 {"name":"one-layer-text","w":900,"h":330,"layer":2,"mode":1,"text":true}
]'}
QT_FORCE_STDERR_LOGGING=1 QML_XHR_ALLOW_FILE_READ=1 QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen} \
    timeout 60 qml6 "$root/tools/preview.qml" -- "$doc" "$out" "$sizes"
ls "$out"/*.png
