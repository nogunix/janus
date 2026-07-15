#!/usr/bin/env python3
"""Build a deck from a declarative YAML/JSON spec — no per-deck Python.

Usage:
    python3 build_deck.py deck.yaml [-o OUT.pptx]

The spec maps 1:1 onto decklib.Deck calls; each `do:` entry is
`- <method>: {<kwargs>}`. See the deck skill's SKILL.md for the schema.
Relative paths in the spec (template, output, picture/svg src) resolve
against the spec file's directory.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date

from decklib import RGB, Deck
from pptx.enum.text import PP_ALIGN

# Slide-scoped Deck methods callable from a spec's `do:` list.
OPS = ("text", "body", "prose", "disclaimer", "fit", "move", "clear",
       "picture", "svg", "refs", "table", "add_textbox", "add_code_block")
COLOR_KEYS = ("color", "head_color", "desc_color", "note_color")
PATH_KEYS = ("src",)
ALIGNS = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER,
          "right": PP_ALIGN.RIGHT}


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        if path.endswith(".json"):
            return json.load(f)
        import yaml
        return yaml.safe_load(f)


class Builder:
    def __init__(self, spec, base_dir):
        self.spec = spec
        self.base = base_dir
        self.colors = spec.get("colors") or {}
        self.today = date.today().strftime(
            spec.get("date_format", "%Y年%-m月%-d日"))

    def path(self, p):
        return p if os.path.isabs(p) else os.path.join(self.base, p)

    def value(self, key, val):
        if isinstance(val, str) and key != "code":  # code is verbatim
            val = val.replace("$today", self.today)
        if key in COLOR_KEYS and isinstance(val, str):
            return RGB(self.colors.get(val.lstrip("$"), val.lstrip("$")))
        if key in PATH_KEYS and isinstance(val, str) \
                and not val.lstrip().startswith("<"):
            return self.path(val)
        if key == "align" and isinstance(val, str):
            return ALIGNS[val.lower()]
        if key == "items" and isinstance(val, list):
            # body: [head, desc] pairs (bare string = no desc);
            # refs: strings or [label, url] pairs — tuples work for both.
            return [(it, None) if isinstance(it, str) else tuple(it)
                    for it in val]
        if isinstance(val, str):
            return val
        return val

    def contains_pred(self, deck, rule):
        texts = rule if isinstance(rule, list) else [rule]
        return lambda s: any(t in deck.slide_text(s) for t in texts)

    def build(self):
        spec = self.spec
        deck = Deck(self.path(spec["template"]),
                    ea_font=spec.get("ea_font", "Noto Sans CJK JP"))
        for find, replace in (spec.get("master_replace") or {}).items():
            deck.master_replace_text(find, replace)

        keep = spec.get("keep_slides")
        if keep != "all":
            keep = keep or {}
            pred = (self.contains_pred(deck, keep["contains"])
                    if keep.get("contains") else lambda s: False)
            deck.strip_slides(keep=pred,
                              keep_first=keep.get("keep_first", False))

        for i, sl in enumerate(spec.get("slides") or [], start=1):
            slide = deck.add(sl["layout"])
            ops = []
            for entry in sl.get("do") or []:
                (name, kwargs), = entry.items()
                if name not in OPS:
                    raise ValueError(
                        f"unknown op {name!r}; valid ops: {', '.join(OPS)}")
                kwargs = dict(kwargs or {})
                if name == "text" and "text" in kwargs:  # alias for `s`
                    kwargs["s"] = kwargs.pop("text")
                kwargs = {k: self.value(k, v) for k, v in kwargs.items()}
                ops.append((name, kwargs))
            # refs measures rendered content, so it must run last on the
            # slide (SKILL.md gotcha #7) — enforce instead of instruct.
            ops.sort(key=lambda op: op[0] == "refs")
            for name, kwargs in ops:
                # decklib silently no-ops on a missing placeholder idx
                # (ph() returns None); a spec typo must fail loudly instead.
                if "idx" in kwargs and deck.ph(slide, kwargs["idx"]) is None:
                    have = sorted(p.placeholder_format.idx
                                  for p in slide.placeholders)
                    raise SystemExit(
                        f"slide {i} (layout {sl['layout']}), op {name!r}: "
                        f"no placeholder idx={kwargs['idx']}; "
                        f"this layout has idx {have}")
                try:
                    getattr(deck, name)(slide, **kwargs)
                except Exception as e:
                    raise SystemExit(
                        f"slide {i} (layout {sl['layout']}), "
                        f"op {name!r}: {type(e).__name__}: {e}") from e

        if spec.get("move_to_end"):
            deck.move_to_end(
                self.contains_pred(deck, spec["move_to_end"]["contains"]))
        return deck


def main():
    ap = argparse.ArgumentParser(
        description="Build a pptx from a declarative deck spec.")
    ap.add_argument("spec", help="deck spec (.yaml/.yml/.json)")
    ap.add_argument("-o", "--output", help="override the spec's output path")
    args = ap.parse_args()

    spec_path = os.path.abspath(args.spec)
    spec = load_spec(spec_path)
    builder = Builder(spec, os.path.dirname(spec_path))
    deck = builder.build()
    out = args.output or builder.path(spec.get("output", "out.pptx"))
    deck.save(out)
    print(f"wrote {out} ({len(deck.prs.slides._sldIdLst)} slides)")


if __name__ == "__main__":
    main()
