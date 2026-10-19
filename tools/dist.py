#!/usr/bin/env python3
"""Zip package/ into dist/<id>.plasmoid, installable from Plasma's
"Install Widget From Local File" or `kpackagetool6 -i`."""

import json
import pathlib
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
package = root / "package"
plugin_id = json.loads((package / "metadata.json").read_text())["KPlugin"]["Id"]
out = root / "dist" / f"{plugin_id}.plasmoid"
out.parent.mkdir(exist_ok=True)

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(package.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            zf.write(path, path.relative_to(package))
print(out)
