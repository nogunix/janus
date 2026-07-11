#!/usr/bin/env python3
"""Recolor a flat dark-theme diagram into "ink on a light background".

Many diagrams/screenshots are a single dark background with brighter strokes &
text in a few accent hues. This re-renders them onto a light background by:
  * alpha = Euclidean distance of each pixel from the detected background colour
    (so anti-aliased edges blend naturally, faint fills fade toward the paper),
  * ink   = chosen per pixel from its HUE (map accent families to a new palette),
  * out   = paper*(1-alpha) + ink*alpha.

Auto-detects the background as the most common border colour, so it works on
unknown images. Override with --bg / palette as needed.

CLI:
    python recolor_image.py in.png out.png
    python recolor_image.py in.png out.png --bg 1E293B --floor 0.10 --span 0.70

Library:
    from recolor_image import recolor
    light = recolor(Image.open("in.png"))          # -> PIL.Image
"""
import argparse
from collections import Counter

import numpy as np
from PIL import Image

# default ink palette (Red Hat light); tweak via recolor(..., palette=...)
DEFAULT_PALETTE = {
    "paper":   "FFFFFF",  # background becomes this
    "neutral": "151515",  # white/grey text -> near-black
    "blue":    "EE0000",  # cyan/sky/blue accents -> red
    "purple":  "CC0000",  # purple/magenta -> red2
    "green":   "15803D",  # green/teal kept green
    "amber":   "B45309",  # amber/orange/yellow -> dark amber
}


def _hex(s):
    s = s.lstrip("#")
    return np.array([int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)], float) / 255


def detect_bg(arr_u8):
    """Most common colour among the 1px border = background."""
    H, W, _ = arr_u8.shape
    border = np.concatenate([
        arr_u8[0, :], arr_u8[H - 1, :], arr_u8[:, 0], arr_u8[:, W - 1]
    ]).reshape(-1, 3)
    return np.array(Counter(map(tuple, border)).most_common(1)[0][0], float) / 255


def recolor(img, bg=None, palette=None, floor=0.10, span=0.70, sat=0.18):
    pal = {**DEFAULT_PALETTE, **(palette or {})}
    paper, neutral = _hex(pal["paper"]), _hex(pal["neutral"])
    ink_blue, ink_purple = _hex(pal["blue"]), _hex(pal["purple"])
    ink_green, ink_amber = _hex(pal["green"]), _hex(pal["amber"])

    a = np.asarray(img.convert("RGB"), float) / 255
    BG = _hex(bg) if bg else detect_bg(np.asarray(img.convert("RGB")))

    # alpha from distance to background; floor swallows subtle bg gradients
    dist = np.sqrt(((a - BG) ** 2).sum(axis=2))
    alpha = np.clip((dist - floor) / span, 0.0, 1.0)

    # HSV hue/sat
    mx = a.max(2); mn = a.min(2); diff = mx - mn
    s = np.where(mx > 1e-6, diff / np.maximum(mx, 1e-6), 0.0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hue = np.zeros_like(mx); nz = diff > 1e-6
    i = (mx == r) & nz; hue[i] = (60 * ((g[i] - b[i]) / diff[i]) % 360)
    i = (mx == g) & nz; hue[i] = (60 * ((b[i] - r[i]) / diff[i]) + 120)
    i = (mx == b) & nz; hue[i] = (60 * ((r[i] - g[i]) / diff[i]) + 240)

    ink = np.empty_like(a); ink[:] = neutral
    hot = s >= sat
    ink[hot & (hue >= 170) & (hue <= 255)] = ink_blue
    ink[hot & (hue > 255) & (hue <= 320)] = ink_purple
    ink[hot & (hue >= 80) & (hue < 170)] = ink_green
    ink[hot & ((hue < 60) | (hue > 320))] = ink_amber

    out = paper * (1 - alpha)[..., None] + ink * alpha[..., None]
    return Image.fromarray(np.clip(out * 255, 0, 255).astype(np.uint8), "RGB")


def recolor_blob(blob, **kw):
    from io import BytesIO
    buf = BytesIO()
    recolor(Image.open(BytesIO(blob)), **kw).save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--bg", default=None, help="background hex, e.g. 1E293B (auto if omitted)")
    ap.add_argument("--floor", type=float, default=0.10)
    ap.add_argument("--span", type=float, default=0.70)
    a = ap.parse_args()
    recolor(Image.open(a.src), bg=a.bg, floor=a.floor, span=a.span).save(a.dst)
    print("wrote", a.dst)
