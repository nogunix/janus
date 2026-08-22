---
name: gslides
description: >-
  Create Google Slides presentations via gws CLI — declarative YAML spec or
  direct API calls. Supports text, tables, images, shapes, brand guidelines,
  SVG/raster diagram insertion with optional light-recolor. No pptx, no
  LibreOffice — the result is a live Google Slides document in Drive, ready for
  collaborative editing. Use when asked to create / generate slides, a deck, or
  a presentation.
---

# Google Slides via gws CLI

Create Google Slides presentations through the Slides API using `gws slides
presentations`. Two workflows: **declarative YAML spec** (preferred — reproducible,
iterable) or **direct batchUpdate** (for one-off or programmatic use).

Supports **template-based creation**: copy an existing Google Slides template,
strip the sample slides, and rebuild with the template's branded layouts.

## When to use

- "スライドを作成して", "提案資料を作って"
- "Google Slides で○○のプレゼンを生成して"
- "この内容でスライドを更新して"
- Any slide/deck/presentation request — this is the default slide skill.

## Template workflow

When a user asks to create slides, **always ask**:

> テンプレートとして使う Google Slides はありますか？
> URL があれば貼ってください（なければデフォルトテーマで作成します）

If the user provides a URL like:
```
https://docs.google.com/presentation/d/XXXXX/edit...
```
Extract the presentation ID (`XXXXX`) and set `template_id` in the spec.

The script copies the template, strips all sample slides, and creates new
slides using the template's layouts — theme, colors, logo, footer are all
inherited automatically.

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

If you get `403 insufficient authentication scopes`, delete the token cache
and re-login:
```bash
rm ~/.config/gws/token_cache.json
gws auth login --services drive,docs,sheets,slides,calendar,gmail
```

## Workflow 1: Declarative YAML spec (default)

Write the deck as data; `build_gslides.py` handles the two-phase API calls:

```bash
python3 scripts/build_gslides.py deck.yaml
python3 scripts/build_gslides.py deck.yaml --dry-run   # preview JSON without calling API
```

### Spec format (blank)

```yaml
title: "HubSpot導入のご提案"
brand:
  font: "Noto Sans JP"
  title_size: 36
  body_size: 20
  date_format: "%Y年%-m月%-d日"
  colors:
    primary: "2563EB"
    accent: "FF5C35"
    text: "000000"
    bg: "FFFFFF"
    sub_bg: "F3F4F6"

slides:
  - layout: TITLE
    do:
      - title: {text: "HubSpot導入のご提案", bold: true, size: 40, color: primary}
      - subtitle: {text: "統合CRMプラットフォーム\n$today", size: 18}

  - layout: TITLE_AND_BODY
    do:
      - title: {text: "現状の課題", bold: true}
      - body: {text: "❶ 顧客情報が分散\n\n❷ ROIが見えない\n\n❸ 営業プロセスが属人化"}

  - layout: TITLE_AND_BODY
    do:
      - title: {text: "解決策：HubSpot CRM", color: primary, bold: true}
      - body: {text: "Marketing Hub\n効果を統合ダッシュボードで可視化\n\nSales Hub\nAIによる商談スコアリング"}

  - layout: TITLE_ONLY
    do:
      - title: {text: "導入スケジュール", bold: true}
      - table:
          header: [フェーズ, 期間, 主な活動]
          header_bg: primary
          rows:
            - ["Phase 1: 要件定義", "1〜2ヶ月目", "現状分析、ゴール設定"]
            - ["Phase 2: 構築・移行", "3〜4ヶ月目", "CRM設定、トレーニング"]
            - ["Phase 3: 運用", "5〜6ヶ月目", "KPIモニタリング、改善"]

  - layout: TITLE_AND_BODY
    do:
      - title: {text: "投資対効果", bold: true}
      - body: {text: "営業生産性 30〜40% 向上\nマーケティングROI 20〜30% 改善\n顧客対応品質 25% 向上"}

  - layout: MAIN_POINT
    do:
      - title: {text: "お問い合わせ\n次のステップ", bold: true, color: primary}
```

### Spec reference

**Top-level keys:**
- `title` — presentation title
- `brand` — font, sizes, colors (referenced by name in ops)
- `slides` — list of slides

**`brand` keys:**
- `font` — default font family (e.g. `"Noto Sans JP"`)
- `title_size` — default title font size in pt
- `body_size` — default body font size in pt
- `date_format` — strftime format for `$today` substitution
- `colors` — named color map (hex without `#`); use names in ops

**Slide ops (`do:` list):**

| Op | Description | Key args |
|----|-------------|----------|
| `title` | Fill the TITLE/CENTERED_TITLE placeholder | `text`, `size`, `bold`, `italic`, `color`, `font`, `autofit` |
| `subtitle` | Fill the SUBTITLE placeholder | same as title (autofit on by default) |
| `body` | Fill the BODY placeholder | same as title (autofit on by default) |
| `table` | Create a table on the slide | `header`, `rows`, `header_bg`, `x`, `y`, `w`, `h`, `font_size` |
| `shape` | Add a free-form text box or shape | `text`, `x`, `y`, `w`, `h`, `size`, `bold`, `color`, `fill`, `shape_type`, paragraph style keys |
| `background` | Set slide background color | `color` |
| `image` | Insert an image by URL | `url`, `x`, `y`, `w`, `h` |

**Paragraph style keys** (available on title/subtitle/body/shape):
- `line_spacing` — line spacing in percentage (e.g. `100` = single, `150` = 1.5x)
- `space_above` / `space_below` — paragraph spacing in pt
- `alignment` — `START`, `CENTER`, `END`, `JUSTIFIED`
- `indent_start` — left indent in pt

**Text autofit:** `body` and `subtitle` ops enable TEXT_AUTOFIT by default —
text that overflows the placeholder shrinks automatically. Set `autofit: false`
to disable, or `autofit: true` on `title` to enable it there.

**Color values:** a key from `brand.colors` (e.g. `primary`) or a raw 6-digit hex (e.g. `2563EB`).

**Position/size values:** in EMU (1 inch = 914400 EMU). Standard slide = 9144000×6858000 EMU.

**`$today`** in any text string is replaced with the build date.

Iterate by editing the YAML and re-running — same spec reproduces the same deck
(minus the presentation ID). Use `--dry-run` to preview the API calls.

### Spec format (template-based)

```yaml
template_id: "YOUR_TEMPLATE_PRESENTATION_ID"
title: "サービス提案書"
brand:
  font: "Noto Sans JP"
  title_size: 28
  body_size: 16

slides:
  - layout: "Title slide"          # layout display name from the template
    do:
      - title: {text: "サービス提案書"}
      - subtitle: {text: "○○株式会社 様"}

  - layout: "Title and body"
    do:
      - title: {text: "現状の課題"}
      - body: {text: "課題1\n課題2\n課題3"}

  - layout: "Section header"
    do:
      - title: {text: "Approach"}

  - layout: "Two column"
    do:
      - title: {text: "提案内容"}
      - body: {text: "左カラムの内容"}

  - layout: "Closing"
    do:
      - title: {text: "Thank you"}
```

The `template_id` is the Google Slides presentation ID (from the URL).
Layout names must match the template's layout display names exactly.

## Workflow 2: Direct batchUpdate (escape hatch)

For one-off decks or when Workflow 1 can't express what you need, call the
API directly. The pattern is always **two phases**:

### Phase 1: Create presentation + slides

```bash
PRES_ID=$(gws slides presentations create \
  --json '{"title":"My Presentation"}' 2>&1 \
  | grep '"presentationId"' | head -1 \
  | sed 's/.*: "//;s/".*//')

gws slides presentations batchUpdate \
  --params "{\"presentationId\": \"$PRES_ID\"}" \
  --json '{
    "requests": [
      {"deleteObject": {"objectId": "p"}},
      {"createSlide": {"objectId": "slide_01", "insertionIndex": 0,
                        "slideLayoutReference": {"layoutId": "p2"}}},
      {"createSlide": {"objectId": "slide_02", "insertionIndex": 1,
                        "slideLayoutReference": {"layoutId": "p4"}}}
    ]
  }'
```

### Phase 2: Discover placeholder IDs → insert content

```bash
gws slides presentations get \
  --params "{\"presentationId\": \"$PRES_ID\"}" 2>&1 \
  | python3 -c "
import json, sys
lines = sys.stdin.read()
data = json.loads(lines[lines.index('{'):])
for s in data.get('slides', []):
    print(f'--- {s[\"objectId\"]} ---')
    for el in s.get('pageElements', []):
        ph = el.get('shape', {}).get('placeholder', {})
        if ph:
            print(f'  {el[\"objectId\"]}: {ph.get(\"type\")}')
"

# Then batchUpdate with the discovered IDs
gws slides presentations batchUpdate \
  --params "{\"presentationId\": \"$PRES_ID\"}" \
  --json '{ "requests": [ ... ] }'
```

## Available layouts

### Default theme (no template)

| Layout name | layoutId | Placeholders |
|-------------|----------|-------------|
| TITLE | p2 | CENTERED_TITLE, SUBTITLE |
| SECTION_HEADER | p3 | TITLE |
| TITLE_AND_BODY | p4 | TITLE, BODY |
| TITLE_AND_TWO_COLUMNS | p5 | TITLE, BODY ×2 |
| TITLE_ONLY | p6 | TITLE |
| ONE_COLUMN_TEXT | p7 | TITLE, BODY |
| MAIN_POINT | p8 | TITLE |
| BIG_NUMBER | p11 | TITLE, BODY |
| BLANK | p12 | (none) |

### Template layouts (discovered dynamically)

When `template_id` is set, `build_gslides.py` automatically discovers the
template's layouts and maps them by display name. Use the display name
(e.g. `"Interior title and body"`) in the spec's `layout:` field.

To inspect a template's layouts manually:

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

## Diagrams

### SVG diagrams (preferred for new diagrams)

Render SVG diagrams from HTML to PNG, optionally recoloring to a light palette:

```bash
python3 scripts/svgtools.py page.html outdir --light --names arch flow
```

Or in Python:
```python
from svgtools import html_to_pngs
html_to_pngs("index.html", "diagrams", names=["arch"], light=True, width=2000)
```

Then host the PNG (e.g. on Google Drive with public link) and insert via
the `image` op in the spec or `createImage` in a batchUpdate.

### Recolor raster diagrams (dark → light)

```bash
python3 scripts/recolor_image.py dark.png light.png
```

Or in Python:
```python
from recolor_image import recolor_blob
light_bytes = recolor_blob(original_png_bytes)
```

Maps dark backgrounds → white, accent hues → new palette. Tune with
`--bg`, `--floor`, `--span`.

## PDF export

```bash
gws drive files export \
  --params '{"fileId": "PRES_ID", "mimeType": "application/pdf"}' \
  -o output.pdf
```

## Common patterns

### Citation / reference URLs at slide bottom

Add a small gray text box at the bottom of content slides for source URLs:

```yaml
- shape:
    text: "[1] https://example.com/docs\n[2] https://example.com/spec"
    x: 520000
    y: 6200000
    w: 8100000
    h: 400000
    size: 10
    color: "999999"
```

### Image hosting

`createImage` requires a URL accessible to Google's servers. Options:
- **imgur** (anonymous upload): `curl -X POST -H "Authorization: Client-ID YOUR_ID" -F "image=@file.png" https://api.imgur.com/3/image`
- **Google Drive** with public sharing (may be blocked by org policy)
- Any publicly accessible HTTPS URL

If org policy blocks Drive public sharing, use an external host like imgur.

## Gotchas

1. **Object ID minimum 5 characters.** `createSlide` with `objectId: "s1"`
   fails. Use `"slide_01"` or longer.

2. **Placeholder IDs are auto-generated.** You cannot specify them at
   creation time. Always GET after createSlide and parse the
   `SLIDES_API...` IDs before inserting text.

3. **Two-phase batchUpdate is mandatory.** You cannot createSlide and
   insertText into its placeholders in the same request — the placeholder
   IDs don't exist until the slide is created.

4. **gws CLI prefixes JSON output with `Using keyring backend: keyring`.**
   When piping to python, strip: `data = json.loads(output[output.index('{'):])`

5. **`--json` not `--body`.** gws CLI uses `--json` for request bodies,
   `--params` for URL/path parameters.

6. **Token cache survives scope changes.** After adding the `presentations`
   scope, delete `~/.config/gws/token_cache.json` and re-login if you still
   get 403.

7. **Default slide `p` must be deleted.** A new presentation always has one
   blank slide with objectId `p`. Delete it in the first batchUpdate.

8. **Table text styling requires cellLocation.** Include
   `"cellLocation": {"rowIndex": R, "columnIndex": C}` in updateTextStyle
   for table cells.

9. **`fields` mask is required.** Every update request needs a `fields`
   string. Omitting it silently does nothing.

10. **Noto Sans JP works natively.** Google Slides supports `Noto Sans JP`
    directly (unlike LibreOffice which needs `Noto Sans CJK JP`).

11. **Image insertion requires a public URL.** `createImage` needs a
    URL accessible to Google's servers. Upload to Drive first and use a
    sharing link, or host elsewhere.

12. **Multiple SUBTITLE placeholders.** Some template layouts have
    SUBTITLE in both the header area and footer. The script picks the
    topmost (smallest Y coordinate) so `subtitle:` fills the header,
    not the footer.

## Files

- `scripts/build_gslides.py` — declarative driver: YAML/JSON spec → Google Slides (Workflow 1).
- `scripts/svgtools.py` — render SVG diagrams from HTML to PNG, light-recolor on hex.
- `scripts/recolor_image.py` — dark→light raster diagram recolor.
