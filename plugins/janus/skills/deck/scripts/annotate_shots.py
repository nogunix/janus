#!/usr/bin/env python3
"""Draw red boxes on screenshots to show where to click (procedure docs).

Originals are never modified: annotated copies are written to OUTDIR under the
spec's output names, so a build script can prefer OUTDIR and fall back to the
raw shots. One source image can yield several outputs (the same screen used on
two slides with different targets).

Spec (JSON):
    {
      "src_dirs": ["shots", "shots-extra"],        # searched in order for <src>.png
      "out_dir": "shots-annot",
      "color": "EE0000", "width": 4, "pad": 3,      # optional
      "boxes": {
        "a1-projects":     {"src": "a1-projects", "rects": [[24,155,266,190], [1358,96,1539,136]]},
        "a1-projects-del": {"src": "a1-projects", "rects": [[559,167,823,204]]}
      }
    }
Rects are [x1, y1, x2, y2] in the source image's own pixels. Relative paths
resolve against the spec file's directory.

Getting coordinates: read the screenshot at native size (a 1600x900 capture
shown unscaled maps 1:1), or take them from Playwright's snapshot with
boxes=true. Always look at the annotated output afterwards -- a box that
misses its target is worse than no box.

Usage:  python3 annotate_shots.py spec.json
Needs:  pillow
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    spec_path = Path(argv[1]).resolve()
    spec = json.loads(spec_path.read_text())
    base = spec_path.parent
    src_dirs = [base / d for d in spec["src_dirs"]]
    out_dir = base / spec["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    color = tuple(int(spec.get("color", "EE0000")[i:i + 2], 16) for i in (0, 2, 4))
    width, pad = spec.get("width", 4), spec.get("pad", 3)

    missing = 0
    for out_name, entry in spec["boxes"].items():
        src = next((d / f"{entry['src']}.png" for d in src_dirs
                    if (d / f"{entry['src']}.png").exists()), None)
        if src is None:
            print(f"  {out_name}: source {entry['src']}.png not found", file=sys.stderr)
            missing += 1
            continue
        img = Image.open(src).convert("RGB")
        draw = ImageDraw.Draw(img)
        for x1, y1, x2, y2 in entry["rects"]:
            draw.rectangle((x1 - pad, y1 - pad, x2 + pad, y2 + pad), outline=color, width=width)
        img.save(out_dir / f"{out_name}.png")
        print(f"  {out_name}: {len(entry['rects'])} box(es)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
