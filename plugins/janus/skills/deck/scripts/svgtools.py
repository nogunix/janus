#!/usr/bin/env python3
"""Turn HTML/SVG diagrams into deck-ready PNGs.

Diagrams authored as inline <svg> in an HTML page are vector source: extract
them, optionally remap their colours to a light palette, and render crisp PNGs
with `rsvg-convert` (falls back to `inkscape`). Recolouring is done on the SVG's
hex colours (discrete, no raster artifacts), classified by luminance + hue so it
works on unknown diagrams.

CLI:
    python svgtools.py page.html outdir --light            # all svgs -> outdir/diagram_N.png
    python svgtools.py page.html outdir --light --names arch spire trustee

Library:
    from svgtools import extract_svgs, auto_light_map, recolor_svg, render_svg
    svgs = extract_svgs(open("page.html").read())
    light = recolor_svg(svgs[0], auto_light_map(svg_colors(svgs[0])))
    render_svg(light, "arch.png", width=2000)
"""
import argparse
import os
import re
import shutil
import subprocess
import tempfile

SVG_RE = re.compile(r"<svg.*?</svg>", re.S)
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

# light Red Hat palette (same spirit as recolor_image)
DEFAULT_PALETTE = {
    "paper": "FFFFFF", "line": "D0D0D0", "neutral": "1A1A1A",
    "blue": "EE0000", "purple": "CC0000", "green": "15803D", "amber": "B45309",
}


def extract_svgs(html):
    return SVG_RE.findall(html)


def svg_colors(svg):
    return sorted({m.lower() for m in HEX_RE.findall(svg)})


def _lum_sat_hue(hexstr):
    r, g, b = (int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    sat = (mx - mn) / mx if mx else 0.0
    if mx == mn:
        hue = 0.0
    elif mx == r:
        hue = (60 * ((g - b) / (mx - mn)) + 360) % 360
    elif mx == g:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - g) / (mx - mn)) + 240
    return lum, sat, hue


def auto_light_map(hexes, palette=None):
    """Map dark-theme hex colours to a light palette: dark fills->paper, muted
    borders->light line, bright accents->ink by hue, light text->near-black."""
    pal = {**DEFAULT_PALETTE, **(palette or {})}
    out = {}
    for h in hexes:
        lum, sat, hue = _lum_sat_hue(h)
        if lum < 0.22:                          # dark background fill
            out[h] = "#" + pal["paper"]
        elif lum < 0.45 and sat < 0.50:         # dark, low-chroma border
            out[h] = "#" + pal["line"]
        elif sat < 0.20:                        # light grey / white text
            out[h] = "#" + pal["neutral"]
        elif 170 <= hue <= 255:
            out[h] = "#" + pal["blue"]
        elif 255 < hue <= 320:
            out[h] = "#" + pal["purple"]
        elif 80 <= hue < 170:
            out[h] = "#" + pal["green"]
        else:
            out[h] = "#" + pal["amber"]
    return out


def recolor_svg(svg, mapping):
    """mapping: {'#aabbcc': '#xxyyzz'} (keys lower-case)."""
    return HEX_RE.sub(lambda m: mapping.get(m.group(0).lower(), m.group(0)), svg)


def render_svg(svg_text, out_png, width=2000, background="white"):
    """Render an SVG string to PNG via rsvg-convert (or inkscape)."""
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg_text)
        tmp = f.name
    try:
        if shutil.which("rsvg-convert"):
            cmd = ["rsvg-convert", "-w", str(width)]
            if background:
                cmd += ["-b", background]
            cmd += [tmp, "-o", out_png]
        elif shutil.which("inkscape"):
            cmd = ["inkscape", tmp, "--export-type=png",
                   f"--export-width={width}", f"--export-filename={out_png}"]
        else:
            raise RuntimeError("need rsvg-convert or inkscape to render SVG")
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        os.unlink(tmp)
    return out_png


def html_to_pngs(html_path, outdir, names=None, light=True, width=2000, palette=None):
    """Extract every <svg> from an HTML file and render to outdir.
    names: optional list of output base names (else diagram_0, diagram_1, ...)."""
    os.makedirs(outdir, exist_ok=True)
    svgs = extract_svgs(open(html_path, encoding="utf-8").read())
    outs = []
    for i, svg in enumerate(svgs):
        if light:
            svg = recolor_svg(svg, auto_light_map(svg_colors(svg), palette))
        name = names[i] if names and i < len(names) else f"diagram_{i}"
        out = os.path.join(outdir, f"{name}.png")
        render_svg(svg, out, width=width)
        outs.append(out)
    return outs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("html"); ap.add_argument("outdir")
    ap.add_argument("--light", action="store_true", help="remap colours to light palette")
    ap.add_argument("--width", type=int, default=2000)
    ap.add_argument("--names", nargs="*", default=None)
    a = ap.parse_args()
    for p in html_to_pngs(a.html, a.outdir, names=a.names, light=a.light, width=a.width):
        print("wrote", p)
