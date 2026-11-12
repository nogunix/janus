---
name: deck
description: >-
  Build a polished PowerPoint (.pptx) and PDF natively on top of an existing
  .pptx template — keeping the template's master, theme, layouts, logo, footer
  and brand colors while filling in your own content. Use when asked to create /
  generate slides or a slide deck / presentation from a template, rebuild a deck
  in a brand template, restyle content into a corporate template, recolor dark
  diagrams to match a light template, or convert pptx to PDF (incl. Japanese text
  that otherwise renders in Chinese glyphs). Builds on Anthropic's pptx skill
  (document-skills:pptx, required) and adds the Japanese-font fix, diagram
  recoloring, screenshot callouts and PDF/visual QA.
---

# Deck-from-template

A thin layer over **Anthropic's official `pptx` skill**. That skill builds
and edits the PPTX: it creates new decks with pptxgenjs, edits templates by
unpacking and editing the slide XML, duplicates slides with `add_slide.py`,
and validates with `validate.py`. This skill adds only what the pptx skill
lacks for JANUS decks:

- Japanese text that renders as Japanese, not Chinese, in the PDF
  (`jpfont.py` + `topdf.sh`)
- dark diagrams recolored for a light template (`svgtools.py`,
  `recolor_image.py`)
- red click-target boxes on screenshots (`annotate_shots.py`)
- visual QA where LibreOffice cannot render Japanese (`qa_thumbs.py`)

## 0. Required: the pptx skill

Before anything else, check that `pptx` (`document-skills:pptx`) is in the
skill list.

**If it is missing, stop.** Do not build the deck another way. Tell the
user, in their language, that this skill requires it and how to install it:

```
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
```

The skill is not vendored here because its license does not allow
redistribution.

When it is present, invoke it (Skill tool, `document-skills:pptx`) so its
instructions are loaded. Paths written `pptx:scripts/…` below are relative
to that skill's directory.

## Bring your own template

This skill does not ship a template. Brand decks are usually licensed or
internal assets, not something to bundle into a public plugin. Use whatever
`.pptx` the user provides: a corporate brand deck, a past proposal, or
anything else with the layouts and theme they want. With no template, the
pptx skill's pptxgenjs path builds from scratch.

## When to use
- "Make a presentation from this template", "put our content into this brand deck".
- "Rebuild / restyle this deck in <template>.pptx".
- "Recolor these dark diagrams to fit the light template."
- "Convert this pptx to PDF" (this skill also fixes Japanese→Chinese font fallback).

## Prerequisites
- Everything the pptx skill lists (pptxgenjs, `markitdown[pptx]`, Pillow,
  `defusedxml`, `lxml`, LibreOffice, Poppler).
- `numpy`, `pillow` for `recolor_image.py` and `annotate_shots.py`;
  `python-pptx` for `qa_thumbs.py`.
- ImageMagick `montage` for contact sheets.
- `librsvg2-tools` (`rsvg-convert`) or `inkscape`, only for SVG diagrams (step 3a).

All helper scripts live in `scripts/` next to this file.

## Workflow

### 1. Read the template and plan the mapping

Follow the pptx skill's "Editing existing decks and templates" section:
`pptx:scripts/thumbnail.py TEMPLATE.pptx template-thumbs` plus
`markitdown TEMPLATE.pptx`. Pick a layout per slide: cover, content (title
+ body, 2-column), section divider, table, closing. Reuse layouts; keep
the deck consistent.

Build on the **template's own layouts**. Do not theme a blank deck: a theme
swap changes nothing when the content uses hard-coded colors.

### 2. Build with the pptx skill

Use the pptx skill's procedure as written: unpack → `add_slide.py` →
`clean.py` → edit `slideN.xml` → zip. With no template, use pptxgenjs.
Follow its gotchas and its design guidance. Insert diagrams from step 3
as pictures.

JANUS rules for the content:
- **Put a date on the cover, and generate it at build time** (format
  `%Y年%-m月%-d日` for Japanese decks). A cover with no date looks
  unfinished, and a hard-coded date goes stale on the next rebuild. For an
  event date, write that date explicitly.
- **Bullet slides: at most 5–6 (heading, detail) pairs, 16pt heading /
  14pt detail.** Beyond that, split the slide. Oversized or overlong
  bodies run into the template footer.
- **Narrative text** (quotes, official statements, disclaimers) goes in
  plain paragraphs with no bullets. Blank lines inside a bulleted list
  render as empty bullet glyphs.
- **Reference footnotes** go at the bottom of the slide, above the
  footer. Use one compact `a | b | c` line when there are three or more.
  Check that they do not overlap the body.
- **Code samples** are real text, not images. Use a monospace font,
  left-aligned (theme defaults can center shape text), on a dark panel.

### 3. Diagrams

#### 3a. Diagrams authored in HTML/SVG (preferred for new diagrams)
Render inline `<svg>` from an HTML page, or a bare `.svg`, to crisp PNGs.
Recolor on the SVG hex values to a light palette:
```bash
python3 scripts/svgtools.py page.html diagrams --light --names arch spire trustee
python3 scripts/svgtools.py diagram.svg diagrams --light
```
`--light` maps each hex by luminance and hue: dark fills→white, muted
borders→grey, accents→red/amber/green, light text→near-black. It needs
`rsvg-convert` (or `inkscape`). The diagram stays editable in its source
and is re-rendered on each build.

#### 3b. Recolor existing raster diagrams (fallback)
```bash
python3 scripts/recolor_image.py dark.png light.png        # auto-detects bg
```
This maps the dark background→white and accent hues→a new palette. The
default is Red Hat: cyan/blue→red, purple→red2, green kept, amber→dark
amber, light text→near-black. Raise `--floor` if a background gradient
leaves a tint. A raster diagram can be recolored but not re-typeset; if
its content must change, recreate it.

#### 3c. Screenshot callouts (red boxes)
Keep raw captures and write annotated copies to a separate directory:
```bash
python3 scripts/annotate_shots.py shots.json        # spec format in the script's docstring
```
Coordinates are the source image's pixels. Check the annotated output: a
box that misses its target misleads more than no box.

### 4. Japanese font fix (required for any deck with Japanese text)
```bash
python3 scripts/jpfont.py OUT.pptx                 # in place; -o NEW.pptx to keep the original
python3 scripts/jpfont.py OUT.pptx --check         # exit 1 if any slide run lacks it
```
This sets the East-Asian typeface **`Noto Sans CJK JP`** on every run. It
covers runs pptxgenjs or hand-edited XML left without one. Run it **after
the last edit** and before conversion. The XML is edited as text, so the
pptx skill's validator still passes. Then validate:
```bash
python pptx:scripts/office/validate.py OUT.pptx --original TEMPLATE.pptx
```

### 5. Convert to PDF
```bash
scripts/topdf.sh OUT.pptx .
```
This runs LibreOffice with `LANG=ja_JP.UTF-8` and a throwaway profile, then
prints the embedded CJK fonts. It **warns if Chinese (`NotoSansCJKsc`)
slipped in**. Use it instead of the pptx skill's `soffice.py` whenever the
deck has Japanese text.

### 6. Visual QA — always look at the result
```bash
scripts/render.sh OUT.pdf 80 /tmp/qa            # PNGs + /tmp/qa-montage.png
```
Read the montage, then the individual pages. Check the pptx skill's
visual QA list (overflow first). Fix, rebuild, and repeat. Do not declare
done without viewing the rendered pages.

**On macOS, where LibreOffice drops Japanese glyphs** (gotcha 3), skip
topdf/render and QuickLook each slide instead:
```bash
python3 scripts/qa_thumbs.py OUT.pptx /tmp/qa      # /tmp/qa/montage.png + s01.pptx.png …
```

## Gotchas
1. **Japanese renders as Chinese in the PDF.** LibreOffice falls back to
   `NotoSansCJKsc` (Simplified Chinese) under an en_US locale. Two fixes,
   both required: `jpfont.py` (East-Asian font on every run) **and**
   `topdf.sh` (`LANG=ja_JP.UTF-8`). The family `Noto Sans JP` is often
   **not** installed; use `Noto Sans CJK JP`. Verify with
   `pdffonts out.pdf | grep -i cjk`: you want `...CJKjp`, not `...CJKsc`.
2. **Edits after `jpfont.py` can reintroduce runs without the font.** Rerun
   it (it is idempotent), or gate on `--check`.
3. **Some macOS LibreOffice builds render no Japanese at all in
   pptx→pdf.** The text is in the PDF (`pdftotext` finds it), but every
   CJK glyph is blank, and fonts and cache resets do not help. This also
   breaks the pptx skill's `thumbnail.py` and its image conversion. Use
   `qa_thumbs.py` for visual QA. For a deliverable PDF, either convert on
   Linux or upload the pptx to Google Slides and export from there
   (`gslides/references/pptx-first.md`); Google renders Japanese
   correctly. Never leave a glyph-less PDF in the output folder.
4. **Do not number slides in build-script comments** (`# Slide 7: …`).
   Every insertion renumbers them by hand and they drift. Use section
   names (`# Cover`, `# 結論`, `# Closing`).

## Files
- `scripts/jpfont.py` — force the East-Asian font on every run; `--check` reports gaps (stdlib only).
- `scripts/topdf.sh` — pptx→pdf with the JP locale fix + CJK-font report.
- `scripts/render.sh` — pdf→PNGs + contact sheet for review.
- `scripts/qa_thumbs.py` — per-slide QuickLook thumbnails + contact sheet (macOS; no LibreOffice).
- `scripts/svgtools.py` — render SVG diagrams (inline in HTML or standalone) to PNG, light-recolor on hex. Needs `rsvg-convert`/`inkscape`.
- `scripts/recolor_image.py` — dark→light *raster* diagram recolor.
- `scripts/annotate_shots.py` — red click-target boxes on screenshots from a JSON spec (pillow).
