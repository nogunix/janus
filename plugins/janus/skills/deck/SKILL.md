---
name: deck
description: >-
  Build a polished PowerPoint (.pptx) and PDF natively on top of an existing
  .pptx template — keeping the template's master, theme, layouts, logo, footer
  and brand colors while filling in your own content. Use when asked to create /
  generate slides or a slide deck / presentation from a template, rebuild a deck
  in a brand template, restyle content into a corporate template, recolor dark
  diagrams to match a light template, or convert pptx to PDF (incl. Japanese text
  that otherwise renders in Chinese glyphs). Linux + LibreOffice + python-pptx.
---

# Deck-from-template

Create a deck that looks like it was authored in a given template, by **emptying
the template and rebuilding your content on its own layouts** — not by theming a
blank deck (a theme swap changes nothing if content uses hard-coded colors).

## Bring your own template

This skill does not ship a template — brand decks are usually licensed or
internal assets, not something to bundle into a public plugin. Point it at
whatever `.pptx` template the user provides (a corporate brand deck, a past
proposal, anything with the layouts/theme you want to reuse); the skill is
general, not tied to any one template.

## When to use
- "Make a presentation from this template", "put our content into this brand deck".
- "Rebuild / restyle this deck in <template>.pptx".
- "Recolor these dark diagrams to fit the light template."
- "Convert this pptx to PDF" (this skill also fixes Japanese→Chinese font fallback).

## Prerequisites (install if missing)
- `python-pptx`, `numpy`, `pillow`, `pyyaml` (pip)
- `libreoffice-impress` (provides `soffice`) — for pptx→pdf
- `poppler-utils` (`pdffonts`, `pdftoppm`) and ImageMagick `montage` — for QA
- `librsvg2-tools` (`rsvg-convert`) or `inkscape` — only if rendering HTML/SVG diagrams (step 4a)
Quick check: `soffice --version && pdffonts -v 2>&1 | head -1 && python3 -c "import pptx,numpy,PIL"`

All helper scripts live in `scripts/` next to this file. Put `scripts/` on the
path (`sys.path.insert(0, ".../scripts")`) or copy `decklib.py` (plus
`svgtools.py`, which `d.svg()` imports) next to your build.

## Workflow

### 1. Inspect the template's vocabulary
```bash
python3 scripts/inspect_template.py TEMPLATE.pptx
```
This lists the **layouts** (with placeholder `idx` values you fill) and the
**sample slides** (so you can see which layout gives a title slide, a 2-column
content slide, a section divider, a table slide, a "thank you", etc.). Save
the output next to the template (e.g. `LAYOUTS.txt`) so you don't have to
re-run it on later edits to the same deck.
Also convert the template to PDF and look at it (`scripts/topdf.sh`,
`scripts/render.sh`) so you can match each of your content slides to a design.

### 2. Plan the mapping
Decide a slide order and pick a layout for each (cover → TITLE-like; content →
a title+body or 2-column layout; section breaks → a divider layout; tables →
a table layout; closing → a "thank you" layout). Reuse one content layout for
several slides — that's normal and keeps it consistent.

### 3. Build from a declarative spec (default — no per-deck Python)

Write the deck as data; `build_deck.py` makes the decklib calls:

```bash
python3 scripts/build_deck.py deck.yaml          # -o OUT.pptx overrides output
```

```yaml
template: TEMPLATE.pptx
output: OUT.pptx
colors: {red: EE0000, grey: "595959"}
master_replace: {"v0.0-TODO": "My Lab"}
keep_slides: {contains: ["Thank you"], keep_first: true}  # "all" = keep template slides; omit = drop all samples

slides:
  - layout: TITLE                                # names from inspect_template.py
    do:
      - text: {idx: 0, text: My Title, bold: true, size: 32}
      - fit: {idx: 0, left: 2.3, top: 2.2, width: 9.4, height: 1.3}
      - add_textbox: {left: 2.3, top: 6.45, width: 5.0, height: 0.45,
                      text: $today, size: 12, color: grey}    # gotcha #10

  - layout: CUSTOM_4_17_1
    do:
      - text: {idx: 4, text: EYEBROW, color: red, size: 12, bold: true}
      - text: {idx: 0, text: Slide title, bold: true}
      - body: {idx: 2, items: [[Heading, detail line], Heading-only]}
      - prose: {idx: 3, text: "Quoted statement…\n\nSecond paragraph."}
      - picture: {src: diagram_light.png, left: 1.0, top: 2.3, width: 11.4}
      - svg: {src: diagram.svg, left: 7.0, top: 2.45, width: 5.0, light: true}
      - table: {x: 1.0, y: 4.7, w: 5.4, h: 1.6, header: [Task, Time],
                rows: [[Build, 5 min], [Test, 2 min]], title: Timing}
      - refs:
          items:
            - [OpenShift Docs, "https://docs.redhat.com/…"]
            - "KB 7012345 — https://access.redhat.com/solutions/7012345"

move_to_end: {contains: "Thank you"}
```

Each `do:` entry is `- <decklib method>: {<its kwargs>}` — ops: `text`,
`body`, `prose`, `disclaimer`, `fit`, `move`, `clear`, `picture`, `svg`,
`refs`, `table`, `add_textbox`, `add_code_block`. The driver enforces the
rules you'd otherwise have to remember:
- `refs` always runs last on its slide, wherever it's written (gotcha #7).
- A wrong placeholder `idx` **fails loudly** with the layout's available
  idx list (raw decklib silently no-ops on a missing placeholder).
- `$today` in any string becomes the build date (`date_format:` to change
  the format; default `%Y年%-m月%-d日` — gotcha #10).
- Colors are a `colors:` name or a hex string; `template`/`output`/`src`
  paths resolve relative to the spec file. `.json` specs also work.

Iterate by editing the YAML and re-running — the same spec reproduces the
same deck. Fall back to the Python API (3b) only for things the ops can't
express (custom shapes, conditional content, loops).

### 3b. Build with `decklib` directly (escape hatch)
```python
import sys; sys.path.insert(0, "scripts")
from decklib import Deck, RGB
RED = RGB("EE0000"); GREY = RGB("595959")

d = Deck("TEMPLATE.pptx")   # your template; ea_font="Noto Sans CJK JP"
d.master_replace_text("v0.0-TODO", "My Lab")    # fix leftover template chrome text

# keep an original template slide verbatim (e.g. its Thank-you), drop the rest.
# keep_first=True avoids dragging in hidden duplicate sample slides:
d.strip_slides(keep=lambda s: "Thank you" in d.slide_text(s), keep_first=True)

s = d.add("TITLE")
d.text(s, 0, "My Title", bold=True, size=32)
d.fit(s, 0, 2.3, 2.2, 9.4, 1.3)                 # see gotcha #1 — always FULL geometry
# Cover date (gotcha #10): auto-fill from the build date so it never goes stale.
# If the TITLE layout exposes a free DATE/SUBTITLE placeholder, d.text into it;
# otherwise (common — placeholders all taken) drop a textbox at fixed inches:
from datetime import date
d.add_textbox(s, 2.3, 6.45, 5.0, 0.45,
              date.today().strftime("%Y年%-m月%-d日"), size=12, color=GREY)

s = d.add("CUSTOM_4_17_1")                       # a 2-column content layout
d.text(s, 4, "EYEBROW", color=RED, size=12, bold=True)
d.text(s, 0, "Slide title", bold=True)
d.body(s, 2, [("Heading", "detail line"), ("Heading 2", "detail 2")])
d.body(s, 3, [("Right column", "detail")])
d.prose(s, 3, "Quoted statement…\n\nSecond paragraph.")   # narrative text, no bullets
d.picture(s, "diagram_light.png", 1.0, 2.3, width=11.4)   # path or raw bytes
d.table(s, 1.0, 2.7, 5.4, 3.0, ("Task", "Time"),
        [("Build", "5 min"), ("Test", "2 min")], title="Timing")
d.refs(s, [("OpenShift Docs", "https://docs.redhat.com/…"),
           "KB 7012345 — https://access.redhat.com/solutions/7012345"])  # call LAST

d.move_to_end(lambda s: "Thank you" in d.slide_text(s))   # if a kept slide must be last
d.save("OUT.pptx")
```
Key `decklib` calls: `add(layout)`, `text(slide, idx, …)`, `body(slide, idx, pairs)`,
`prose(slide, idx, text)`, `disclaimer(slide, idx, conditions, notes)`,
`table(...)`, `picture(...)`, `svg(slide, src, l,t, …)`, `refs(slide, items)`,
`add_textbox(slide, l,t,w,h, text, …)`, `fit(slide, idx, l,t,w,h)`, `clear`,
`strip_slides`, `move_to_end`, `master_replace_text`, `save`. `RGB("EE0000")` for colors.

Reference footnotes: `d.refs(slide, items)` — call it **last** on each slide; it
measures the content below the placeholders' *rendered text* and places the refs
in the free zone above the bottom margin. With 3+ refs (or too little room) it
auto-compacts them into one wrapped `a | b | c` line a point smaller, so they
never overlap a full-height 2-column body. Template-specific placement rules
(left margin, footer clearance, compact threshold) are the keyword args
`left/width/bottom_margin/compact_at`.
Disclaimer slides: `d.disclaimer(slide, idx, conditions=[…], notes=[…])` —
conditions as bullets, notes as smaller grey ※-lines.
Code blocks: `d.add_code_block(slide, l, t, w, code, lang="yaml")` — a dark
(#1E1E1E) rounded panel with a deliberately small corner radius and
VS Code Dark+ syntax colors (`lang`: `yaml` / `bash` / `none`). The code
stays real text (editable in pptx, copy-pastable from the PDF), every line
is forced `PP_ALIGN.LEFT` (theme defaults can center shape text), and
`height` auto-sizes from the line count. In a spec, YAML's `|` block
scalar keeps the snippet verbatim:
```yaml
      - add_code_block:
          left: 2.7
          top: 2.3
          width: 8.0
          lang: yaml
          code: |
            apiVersion: trustyai.opendatahub.io/v1alpha1
            kind: TrustyAIService
```

### 4a. Diagrams authored in HTML/SVG (preferred for new diagrams)
If the diagrams live as inline `<svg>` in an HTML page, render them to crisp PNGs
straight from that vector source — and recolor to a light palette on the SVG hex
values (no raster artifacts):
```bash
python3 scripts/svgtools.py page.html diagrams --light --names arch spire trustee
```
or in the build:
```python
from svgtools import html_to_pngs
html_to_pngs("index.html", "diagrams", names=["arch","spire","trustee"], light=True, width=2000)
d.picture(s, open("diagrams/arch.png","rb").read(), 0.9, 2.45, width=7.0)
```
`--light` maps each SVG hex by luminance+hue (dark fills→white, muted borders→grey,
accents→red/amber/green, light text→near-black). Needs `rsvg-convert` (or
`inkscape`). This keeps the diagram **editable in HTML** and re-rendered each build.

For a standalone `.svg` file (or SVG markup string) skip the pipeline entirely —
one call renders and places it, optionally light-recolored:
```python
d.svg(s, "diagram.svg", 0.9, 2.45, width=7.0, light=True)
```
(The svgtools CLI also accepts a bare `.svg` file in place of the HTML page.)

### 4b. Recolor existing raster diagrams to fit a light template (fallback)
Raster diagrams built for a dark deck look out of place on a light template.
Recolor them to "ink on white":
```bash
python3 scripts/recolor_image.py dark.png light.png        # auto-detects bg
```
or in the build (recolor blobs pulled from another deck before placing):
```python
from recolor_image import recolor_blob
light_bytes = recolor_blob(original_png_bytes)             # -> PNG bytes
d.picture(s, light_bytes, 1.0, 2.3, width=11.4)
```
It maps the dark background→white and accent hues→a new palette (default Red Hat:
cyan/blue→red, purple→red2, green kept, amber→dark amber, light text→near-black).
Tune with `recolor(img, bg=..., palette={...}, floor=, span=)`; raise `--floor`
if a background gradient leaves a tint.

### 5. Convert to PDF (with the Japanese-font fix)
```bash
scripts/topdf.sh OUT.pptx .
```
This runs LibreOffice with `LANG=ja_JP.UTF-8` and a throwaway profile, then prints
the embedded CJK fonts and **warns if Chinese (`NotoSansCJKsc`) slipped in**.

### 6. Visual QA loop — always look at the result
```bash
scripts/render.sh OUT.pdf 80 /tmp/qa            # PNGs + /tmp/qa-montage.png
```
Read the montage, then read individual pages, fix the build script, and repeat.
Do not declare done without viewing the rendered pages.

## Gotchas (the things that actually break)
1. **Placeholder geometry zero-bug.** Setting only `.width` or `.top` on an
   inherited placeholder leaves the other dims at 0 → the box flies to the
   top-left or collapses to zero width and the text vanishes. Always set **all
   four** (`d.fit` does this).
2. **Japanese renders as Chinese in the PDF.** LibreOffice falls back to
   `NotoSansCJKsc` (Simplified Chinese) under an en_US locale. Fixes, both applied
   by the skill: force the East-Asian font to **`Noto Sans CJK JP`** on every run
   (decklib default) **and** convert with **`LANG=ja_JP.UTF-8`** (topdf.sh). The
   family **`Noto Sans JP` is often NOT installed** — use `Noto Sans CJK JP`.
   Verify with `pdffonts out.pdf | grep -i cjk` → want `...CJKjp`, not `...CJKsc`.
3. **Theme swap alone does nothing** when slides use hard-coded RGB/fonts. To make
   a deck look like a template you must rebuild on its layouts (this skill) or
   remap every color/font.
4. **Build slides on empty template layouts**, don't text-replace the template's
   sample slides — the samples are full of TODO text and tip callouts you'd have
   to scrub. `strip_slides` keeps only what you explicitly want (e.g. a closing
   slide) and you add fresh slides on the layouts.
5. **Diagrams are raster.** You can recolor them (step 4) but not re-typeset them;
   if a diagram must change content, it has to be recreated.
6. **`\n\n` inside `body()` text renders as an empty ▸ bullet.** `body()` is for
   (head, detail) bullet pairs; blank lines inside it become bullet glyphs with
   no text. For narrative text with paragraph breaks (quotes, official
   statements, disclaimers) use `d.prose()` — no bullets, spaced paragraphs.
7. **Reference footnotes overlap a full-height body if placed at a fixed top.**
   Use `d.refs()` as the LAST call on the slide — it measures the rendered
   content and compacts/moves the refs into the free bottom zone instead.
8. **Don't number slides in build-script comments** (`# Slide 7: …`) — every
   insertion/move renumbers them all by hand and they drift. Comment with
   section names only (`# Cover`, `# 結論`, `# Closing`); the deck's page
   numbers come from the template's own numbering, not the script.
9. **Body text overflows into the footer** when it's oversized or overlong —
   18pt heads with many pairs run past the bottom margin. Build rule: cap
   `body()` at **16pt head / 14pt detail**, at most **5–6 (head, detail)
   pairs per slide**, and split into two slides beyond that; `tight=True`
   compresses spacing (1pt before/after) when a slide is dense. `body()`
   warns on stderr when you exceed the caps, and the rendered-PDF check
   (step 6) is what actually catches an overflow — look at the pages.
10. **Put a date on the cover, and auto-fill it.** A title slide with no date looks
   unfinished, and a hard-coded date silently goes stale on the next rebuild — fill
   it from `date.today()` at build time. Use a free DATE/SUBTITLE placeholder via
   `d.text` if the layout has one (check `d.describe_layouts()`); if every
   placeholder is taken, add a `d.add_textbox` at fixed inches (see step 3). For a
   fixed event/presentation date rather than the build date, pass that string
   explicitly instead of `date.today()`.

## Files
- `scripts/build_deck.py` — declarative driver: YAML/JSON deck spec → pptx (step 3). Needs `decklib.py` beside it.
- `scripts/decklib.py` — the builder library (`Deck`, `RGB`). `d.svg()` needs `svgtools.py` importable beside it.
- `scripts/svgtools.py` — render inline-SVG diagrams from HTML to PNG, light-recolor on hex (`html_to_pngs`, CLI). Needs `rsvg-convert`/`inkscape`.
- `scripts/recolor_image.py` — dark→light *raster* diagram recolor (`recolor`, `recolor_blob`, CLI).
- `scripts/inspect_template.py` — dump a template's layouts & sample slides.
- `scripts/topdf.sh` — pptx→pdf with the JP-font fix + CJK-font report.
- `scripts/render.sh` — pdf→PNGs + contact sheet for review.