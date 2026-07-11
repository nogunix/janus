#!/usr/bin/env python3
"""Print a template's reusable vocabulary: its layouts (with placeholder indices)
and its sample slides (which layout each uses, hidden or not).

    python inspect_template.py template.pptx
    python inspect_template.py template.pptx --layouts
    python inspect_template.py template.pptx --slides
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from decklib import Deck

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    d = Deck(args[0])
    if "--slides" in flags or not flags:
        print("==== SAMPLE SLIDES (pick ones to repurpose / which layout to reuse) ====")
        d.describe_slides()
    if "--layouts" in flags or not flags:
        print("\n==== LAYOUTS (placeholder idx -> fill with d.text/d.body) ====")
        d.describe_layouts()
