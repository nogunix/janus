---
name: gslides
description: >-
  Create Google Slides presentations via gws CLI — declarative YAML spec or
  direct API calls. Supports text, tables, images, shapes, brand guidelines,
  SVG/raster diagram insertion with optional light-recolor. No pptx, no
  LibreOffice — the result is a live Google Slides document in Drive, ready for
  collaborative editing. For brand-template fidelity it can also build the deck
  as PPTX (on Anthropic's pptx skill when installed) and convert it on upload.
  Use when asked to create / generate slides, a deck, or a presentation.
---

# Google Slides via gws CLI

Create Google Slides presentations through the Slides API using `gws slides
presentations`. Primary workflow: **declarative YAML spec** (reproducible,
iterable). Escape hatch: **direct batchUpdate** (for one-off or programmatic
use).

## When to use

- "スライドを作成して", "提案資料を作って"
- "Google Slides で○○のプレゼンを生成して"
- "この内容でスライドを更新して"
- Any slide/deck/presentation request — this is the default slide skill.

## Prerequisites

1. `gws` CLI installed (`pip install gws-cli` or `brew install gws`)
2. OAuth scopes must include `presentations`:
   ```bash
   gws auth login --services drive,docs,sheets,slides,calendar,gmail
   ```
3. GCP project must have **Slides API** enabled:
   ```bash
   gcloud services enable slides.googleapis.com --project=<PROJECT>
   ```
4. Verify: `gws slides presentations create --json '{"title":"test"}' && echo OK`
5. (Optional) `pyyaml` for YAML specs: `pip install pyyaml`
6. (Optional) `rsvg-convert` or `inkscape` for SVG diagram rendering
7. (Optional) ImageMagick `montage` for the `--thumbs` contact sheet

If you get `403 insufficient authentication scopes`, delete the token cache
and re-login:
```bash
rm ~/.config/gws/token_cache.json
gws auth login --services drive,docs,sheets,slides,calendar,gmail
```

## Workflow

### 1. Inspect the template

Ask the user, in their language, whether there is a Google Slides deck to
use as the template, and to paste its URL if so. Without one, build on the
default theme.

From a URL like `https://docs.google.com/presentation/d/XXXXX/edit...`,
take the presentation ID (`XXXXX`) and set `template_id` in the spec.

**List the template's layouts:**

```bash
gws slides presentations get \
  --params '{"presentationId": "TEMPLATE_ID"}' 2>&1 \
  | python3 -c "
import json, sys
lines = sys.stdin.read()
data = json.loads(lines[lines.index('{'):lines.rindex('}')+1])
for l in data.get('layouts', []):
    lp = l.get('layoutProperties', {})
    phs = [e.get('shape',{}).get('placeholder',{}).get('type','')
           for e in l.get('pageElements',[])
           if e.get('shape',{}).get('placeholder',{}).get('type','')
           not in ('SLIDE_NUMBER','')]
    print(f'{lp.get(\"displayName\",\"?\"):45s} {l[\"objectId\"]:30s} {phs}')
"
```

**Default layouts (blank presentation):**

| Layout name | layoutId | Placeholders |
|-------------|----------|-------------|
| TITLE | p2 | CENTERED_TITLE, SUBTITLE |
| SECTION_HEADER | p3 | TITLE |
| TITLE_AND_BODY | p4 | TITLE, BODY |
| TITLE_AND_TWO_COLUMNS | p5 | TITLE, BODY x2 |
| TITLE_ONLY | p6 | TITLE |
| ONE_COLUMN_TEXT | p7 | TITLE, BODY |
| MAIN_POINT | p8 | TITLE |
| BIG_NUMBER | p11 | TITLE, BODY |
| BLANK | p12 | (none) |

### 2. Plan the deck before writing YAML

Settle the whole deck first. This step is what keeps styling consistent.

1. **List the slides**: the layout and title of each.
2. **Define `styles:`** for every element that repeats on two or more
   slides (subtitle, footnote, content box, ...).
3. **Decide `brand:`**: font, colors, sizes.
4. **Fix the coordinate frame.** Use inch keys (`xi`/`yi`/`wi`/`hi`).
   - An API-created deck is **16:9 = 10in x 5.625in**.
   - A copied template keeps **its own page size**. 16:9 decks that came
     from PowerPoint are usually 13.333in x 7.5in.
   - Read `pageSize` (EMU) from `presentations get` (gotchas.md #16).

**Anything below the bottom edge disappears silently.** There is no error.
Use the page height (5.625 on a new deck) as the hard limit for every `yi`.

**Inch quick reference (API-created 10in x 5.625in):**

| Position | Inches | EMU |
|------|--------|---------|
| Left margin | xi: 0.22 | 200000 |
| Right edge | xi: 9.78 | 8940000 |
| Below title (subtitle) | yi: 0.88 | 804672 |
| Content start | yi: 1.25-1.35 | 1143000-1234440 |
| Bottom zone (citations, page numbers) | yi: 5.22-5.35 | 4773168-4892040 |
| Slide bottom | yi: 5.625 | 5143500 |
| Full width | wi: 9.51 | 8700000 |
| Half width | wi: 4.59 | 4200000 |

**Table row height cannot be set.** Slides derives it from font size and
cell padding. Even at `font_size: 8-9` a row takes about 0.66in, so reserve
`N × 0.66` in for N rows including the header. Starting at `yi: 1.2` on
16:9, **header + 5 rows is the limit**. Split longer tables across two
slides.

### 3. Write the YAML spec

**Rule: every change goes through the YAML.** Do not call batchUpdate
directly. Edit the spec and re-run.

Read `references/spec.md` (two examples and the full key reference) before
writing a spec. Minimal form:

```yaml
title: "Proposal"
brand: {font: "Noto Sans JP", title_size: 28, body_size: 16}
slides:
  - layout: TITLE
    do:
      - title: {text: "Proposal", bold: true}
      - subtitle: {text: "For Example Corp.\n$today"}
```

### 4. Build

```bash
python3 scripts/build_gslides.py deck.yaml --dry-run   # check the requests first
python3 scripts/build_gslides.py deck.yaml              # build
```

The script prints the deck URL.

### 5. QA loop

```bash
python3 scripts/build_gslides.py deck.yaml --update PRES_ID --thumbs qa/               # rebuild and capture every slide
python3 scripts/build_gslides.py deck.yaml --update PRES_ID --slides 4,12 --thumbs qa/  # only the slides you fixed
```

1. Read every thumbnail (`qa/NN.png`, plus `qa/sheet.png` when ImageMagick
   is installed). Check for:
   - overflow and awkward line breaks;
   - overlapping elements;
   - anything intruding into the bottom zone;
   - lopsided vertical spacing;
   - mixed fonts.
2. Fix the YAML, then rebuild only those slides with
   `--update PRES_ID --slides N,...`.
   - The URL stays the same, so co-editors and shared links keep working.
   - `--slides` takes 1-based spec positions. It works only when the deck
     has exactly as many slides as the spec. Otherwise run `--update`
     without `--slides`.
3. **Do not report done without looking.** For a deck that will be
   distributed, also check the PDF export (gotchas.md #17).

## References: read at the moment named

| File | Read when |
|---|---|
| `references/spec.md` | Writing or editing a YAML spec: examples, and every top-level, `brand`, `styles`, `page_numbers`, coordinate and `do:` key |
| `references/batchupdate.md` | An operation the spec cannot express needs a direct batchUpdate (Workflow 2) |
| `references/pptx-first.md` | The deck must reproduce a corporate template's masters and fonts, or is a procedure deck with screenshots (Workflow 3, Playwright capture notes) |
| `references/gotchas.md` | The API returns an error or the result is not what you expected. Items are numbered; cite them as `gotchas.md #N` |

## Diagrams

### SVG diagrams (HTML → PNG)

```bash
python3 scripts/svgtools.py page.html outdir --light --names arch flow
```

### Recolor raster diagrams (dark → light)

```bash
python3 scripts/recolor_image.py dark.png light.png
```

## PDF export

```bash
gws drive files export \
  --params '{"fileId": "PRES_ID", "mimeType": "application/pdf"}' \
  -o output.pdf
```

## Image hosting

`createImage` requires a URL accessible to Google's servers:
- **imgur** (anonymous upload): `curl -X POST -H "Authorization: Client-ID YOUR_ID" -F "image=@file.png" https://api.imgur.com/3/image`
- **Google Drive** with public sharing
- Any publicly accessible HTTPS URL

## Must-know (full text in `references/gotchas.md`)

- **#16 Elements below the page's bottom edge vanish silently.** A new deck
  is 10in x 5.625in. A copied template uses its own `pageSize`.
- **#17 Always look at the result after a build.** The API's success
  response says nothing about overflow or overlap.
- **#9 Every update request needs a `fields` mask.** Without one it
  silently does nothing.
- **#4 / #5 gws quirks.**
  - Output starts with `Using keyring backend: keyring`, so parse from the
    first `{`.
  - Request bodies go in `--json`, URL/path parameters in `--params`.
- **#6 Still 403 after adding a scope?** Delete
  `~/.config/gws/token_cache.json` and log in again.
- **#2 You can name placeholder IDs yourself with `placeholderIdMappings`.**
  Then one batchUpdate can both create a slide and fill it.

## Files

- `scripts/build_gslides.py` — declarative driver: YAML/JSON spec → Google Slides; `--update`/`--slides` rebuild in place, `--thumbs` for visual QA.
- `scripts/svgtools.py` — render SVG diagrams from HTML to PNG, light-recolor.
- `scripts/recolor_image.py` — dark→light raster diagram recolor.
- `scripts/procedure_deck.py` — Workflow 3: brand-template procedure decks as PPTX (python-pptx), then upload with conversion.
- `references/` — spec / batchupdate / pptx-first / gotchas (see References above).
