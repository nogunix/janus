#!/usr/bin/env python3
"""Force the East-Asian typeface on every text run of a .pptx (Japanese fix).

LibreOffice (and some PowerPoint installs) resolve Japanese text with no
explicit East-Asian font to a Simplified-Chinese face (Han unification):
the PDF comes out with NotoSansCJKsc glyphs. Setting `<a:ea typeface=…>`
on every run pins the Japanese face. Run this on the finished deck — after
the pptx skill has built it, before topdf.sh — so no run is missed however
the deck was produced (pptxgenjs, template XML editing, python-pptx).

Touches ppt/slides/, slideLayouts/, slideMasters/ and notesSlides/ XML:
every <a:rPr>, <a:defRPr> and <a:endParaRPr>, and a bare <a:r> with no
<a:rPr> gets one. An existing <a:ea> has its
typeface replaced; otherwise one is inserted at the schema position
(after <a:latin>, before <a:cs>/<a:sym>/<a:hlinkClick>/…/<a:extLst>).
The XML is edited as text, not re-serialized, so namespace prefixes and
everything else stay byte-for-byte (ElementTree round-trips corrupt OOXML).

Usage:
  python3 jpfont.py DECK.pptx [-o OUT.pptx] [--font "Noto Sans CJK JP"]
  python3 jpfont.py DECK.pptx --check     # report runs lacking the font; exit 1 if any
Stdlib only.
"""

import argparse
import os
import re
import sys
import tempfile
import zipfile

DEFAULT_FONT = "Noto Sans CJK JP"
PARTS = re.compile(r"^ppt/(slides|slideLayouts|slideMasters|notesSlides)/[^/]+\.xml$")
PROPS = re.compile(
    r"<a:(rPr|defRPr|endParaRPr)\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/>|>(.*?)</a:\1>)",
    re.S,
)
EA = re.compile(r"<a:ea\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*?(?:/>|>.*?</a:ea>)", re.S)
BARE_RUN = re.compile(r"<a:r>(\s*)<a:t\b")
# Children that must come after <a:ea> in CT_TextCharacterProperties.
AFTER_EA = re.compile(r"<a:(cs|sym|hlinkClick|hlinkMouseOver|rtl|extLst)\b")


def _attr(value):
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def set_ea(xml, font):
    """Return (new_xml, n_props_touched)."""
    tag = f'<a:ea typeface="{_attr(font)}"/>'
    count = 0

    def fix(m):
        nonlocal count
        count += 1
        name, attrs, close, body = m.group(1), m.group(2), m.group(3), m.group(4)
        if close == "/>":
            return f"<a:{name}{attrs}>{tag}</a:{name}>"
        if EA.search(body):
            body = EA.sub(tag, body, count=1)
        else:
            after = AFTER_EA.search(body)
            body = body[:after.start()] + tag + body[after.start():] if after else body + tag
        return f"<a:{name}{attrs}>{body}</a:{name}>"

    xml = PROPS.sub(fix, xml)
    xml, bare = BARE_RUN.subn(lambda m: f"<a:r>{m.group(1)}<a:rPr>{tag}</a:rPr><a:t", xml)
    return xml, count + bare


def missing(xml, font):
    """Count run properties whose East-Asian typeface is not `font`."""
    want = f'typeface="{_attr(font)}"'
    n = len(BARE_RUN.findall(xml))
    for m in PROPS.finditer(xml):
        ea = EA.search(m.group(4) or "")
        if not ea or want not in ea.group(0):
            n += 1
    return n


def process(src, dst, font):
    touched = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if PARTS.match(info.filename):
                xml, n = set_ea(data.decode("utf-8"), font)
                touched += n
                data = xml.encode("utf-8")
            zout.writestr(info, data, compress_type=info.compress_type)
    return touched


def check(src, font):
    out = {}
    with zipfile.ZipFile(src) as z:
        for name in z.namelist():
            if name.startswith("ppt/slides/") and PARTS.match(name):
                n = missing(z.read(name).decode("utf-8"), font)
                if n:
                    out[name] = n
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("deck")
    ap.add_argument("-o", "--output", help="write here instead of rewriting DECK in place")
    ap.add_argument("--font", default=DEFAULT_FONT)
    ap.add_argument("--check", action="store_true",
                    help="only report slide runs without the font (exit 1 if any)")
    a = ap.parse_args(argv)

    if a.check:
        bad = check(a.deck, a.font)
        for name, n in sorted(bad.items()):
            print(f"{name}: {n} run(s) without East-Asian font {a.font!r}")
        if not bad:
            print(f"ok: every slide run sets East-Asian font {a.font!r}")
        return 1 if bad else 0

    dst = a.output or a.deck
    fd, tmp = tempfile.mkstemp(suffix=".pptx", dir=os.path.dirname(os.path.abspath(dst)))
    os.close(fd)
    try:
        n = process(a.deck, tmp, a.font)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"{dst}: East-Asian font {a.font!r} set on {n} run propert{'y' if n == 1 else 'ies'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
