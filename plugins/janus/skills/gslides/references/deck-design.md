# Deck design: what to put on the slides

Read before planning a deck whose content you are shaping — an article,
report or investigation turned into slides — rather than one whose slides
the user dictated. It covers the process, the slide anatomy, color and
type rules, a component catalog, and how each component is built with
`build_gslides.py` ops.

Distilled from another team's consulting-style Slides skill (gslides-deck).
Its brand values are replaced by roles, so bring your own colors and font.

## Process

1. **Gather the material.**
   - Fetch every URL.
   - Download figures in the source and look at them. Their numbers and
     structure become your diagrams.
   - Summarize foreign-language sources into the deck's language. Keep
     product names and proper nouns as written.
2. **Ask for the presenter name on the cover** every time. Never guess or
   reuse one.
3. **Show an outline and get approval before building.** Building is the
   expensive step; an outline costs one message. Use this form:
   ```
   Cover: title / subtitle / presenter
   01 Summary          | key message (one-sentence conclusion) | components / figure idea
   — Divider "1. ..."
   02 <label>          | key message                           | components
   ...
   ```
4. **Build**, then **QA every slide** with `--thumbs` (SKILL.md §5).
5. **Report**:
   - the URL and the outline;
   - which parts became diagrams;
   - content caveats: what was translated or condensed, and where the
     sources are cited.

## Principles

1. **One slide, one message.** The key message at the top is the slide's
   conclusion. The body holds only the evidence for it.
2. **Accent color is for words; structure color is for structure.**
   - The accent marks labels, key messages, emphasis and "risk / problem".
   - A second, calmer color carries headers, pills, card frames and chips.
   - Never use the accent for structure.
3. **Organize with flat gray panels.** No shadows, gradients or 3D.
4. **Diagram first.**
   - Make numbers big.
   - Comparisons → grid tables; flows → chips and arrows; parallel ideas
     → cards.
   - Keep text-only slides to a minimum.
5. **Tell the story by repetition.** Re-show an overview slide with the
   current row framed in the accent and the other rows dimmed (C9).

Rough area ratio: white 70 / gray panels 15 / structure color 10 /
accent 5.

## Chapter pattern

Divider → focus on the overview (C9) → definition → examples ×n → pause
(C8) → summary. An article usually makes 15–25 slides.

## Slide anatomy

```
┌────────────────────────────────────────────────────────┐
│ section label (accent, small)              [tag]       │
│        KEY MESSAGE — accent, centered, ≤ 2 lines       │
│  ┌──────────────── body region ─────────────────┐      │
│  │ components (catalog below)                   │      │
│  └──────────────────────────────────────────────┘      │
│  [takeaway bar]                        source link →   │
│ (footer reserved: page number, logo)                   │
└────────────────────────────────────────────────────────┘
```

Inches scale with the page; point sizes do not. The same design on the
two common page sizes:

| Region | 10in x 5.625in (API-created) | 13.333in x 7.5in (PowerPoint 16:9) |
|---|---|---|
| Section label | x 0.37, y 0.15, h 0.35 | x 0.49, y 0.20, h 0.45 |
| Key message box | x 0.73, y 0.71, w 8.55, h 0.78 | x 0.97, y 0.95, w 11.40, h 1.04 |
| Content columns | x 0.73 → 9.28 (w 8.55), gutter 0.22 | x 0.97 → 12.37 (w 11.40), gutter 0.30 |
| Body region | y 1.46 → 4.84 | y 1.95 → 6.45 |
| Takeaway bar | y 4.13, h 0.67 | y 5.51, h 0.89 |
| Source link | y 4.73, right-aligned | y 6.31, right-aligned |
| Footer, keep empty | y ≥ 5.03 | y ≥ 6.70 |

A slide without a key message (e.g. a bullet summary) may start its body
just below the label.

## Type

| Role | pt on 13.333in | pt on 10in | Weight / color |
|---|---|---|---|
| Cover title | 40–45 | 30–34 | regular |
| Divider title | 34 | 26 | accent |
| Pause overlay (C8) | 22 | 17 | bold, ink |
| Key message | 18 | 14 | accent, centered, line spacing 115 |
| Section label / card title | 15 | 11–12 | accent / ink |
| Body, pill text | 14 | 11 | ink / white on structure color |
| Dense body, table cells | 12 | 9–10 | ink, line spacing 115 |
| Captions, sources | 9–10 | 8 | ink / accent underlined |

- **Body text never goes below the dense size.** That is 12pt on
  13.333in or 9pt on 10in. Only captions, sources and legends go smaller.
- **Text boxes do not shrink to fit** (spec.md, Text autofit). Give each
  box the height its text needs, or shorten the text. Check overflow in
  the thumbnails.
- **Use one emphasis style per span**: bold + structure color, or bold +
  accent. Never both.

## Components

Sizes are for 13.333in; multiply by 0.75 for a 10in page. Keep gaps and
heights when you change how many items sit in a row. Each component is
built from `shape` / `line` ops with `styles:` (starter kit at the end).

| # | Component | Use for | Build |
|---|---|---|---|
| C1 | **Grid table** | comparisons, mappings (≤ 8 rows) | Header cells: `RECTANGLE`, structure fill, white 14pt, h 0.44. Rows: h 0.49, gap 0.08; first column light-structure fill, others gray panel. Build from shapes, not `table` — table rows cannot be sized (SKILL.md §2) |
| C2 | **Label + description rows** | three axes, definitions | Left: structure-color `ROUND_RECTANGLE` pill, white text, `valign: MIDDLE`. Right: gray panel; first line is the heading, then the description. Row pitch ≈ pill height + 0.15 |
| C3 | **Outlined cards** | 3–4 parallel concepts | `ROUND_RECTANGLE`, white fill, `outline` structure color 1.5pt. Title "① Name (English)", optional icon image, 12–14pt description. 4 cards ≈ 2.72 wide; 3 cards ≈ 3.82 |
| C4 | **Header columns** | three reasons or points | Structure-color header bar (h 0.45–0.61, "① heading"), gray body 0.05 below it holding 12pt text |
| C5 | **Takeaway bar** | the one-line conclusion | `ROUND_RECTANGLE`, `panelAlt` fill, `outline: none`, full content width, centered 14pt; color only the key words with `{struct:...}` or `{accent:...}` |
| C6 | **Process flow** | steps, pipelines | Chips (structure fill, white 13pt) with `CHEVRON` shapes or `line` arrows (`arrow: end`) between them; captions below. Group with a light-structure panel or a dashed outline (`dash: DASH`) |
| C7 | **Quote block** | a source's key sentence | Gray panel: translation in bold 14pt, original in italic 12pt below it, source link under the panel |
| C8 | **Pause overlay** | a beat before a turn | Copy the previous slide's spec, then add a full-slide `panelAlt` rectangle and a centered 22pt bold message of 2–4 lines. Through the API the rectangle is opaque, so it is a plain message slide |
| C9 | **Focus on the overview** | "where we are" at a chapter start | Repeat the C1/C2 slide's spec. Frame the current rows with a `RECTANGLE` with `fill: none` and an accent `outline` at 2.25pt and set the other rows' `color` to a muted gray |
| C10 | **Top-right tag** | the phase or role a slide belongs to | Small structure-color rectangle, white 12pt, top right |
| C11 | **Source link** | every slide that cites outside work | 9–10pt, accent, right-aligned, bottom right, above the footer; `link:` makes it clickable |
| C12 | **Bullets** | summaries | 14pt ink. Sub-headings get a structure-color `{struct:●}` and bold. Bold only the key words |

## Writing

- **Section label**: a noun phrase, e.g. "Spec-driven Development とは",
  "Write strategy - work log".
- **Key message**: the conclusion in one sentence, at most two lines
  (about 45 full-width characters per line on 13.333in). In Japanese, use
  である調, e.g. 「ATDD は、AI の出力を仕様に照らして判定する評価基準になる」.
- **Terms**: write them as 日本語（English）. Number items with ①②③. Put
  key terms in 「」.
- **Body**: noun-ending phrases or short sentences, at most two lines per
  cell.

## Starter styles (10in API-created page)

Rename the colors to your brand. `accent` is for words, `struct` for
structure.

```yaml
brand:
  font: "Noto Sans JP"
  body_size: 11
  colors: {accent: "EE0000", struct: "37A3A3", structLight: "DAF2F2",
           ink: "434343", panel: "F3F3F3", panelAlt: "EEEEEE", muted: "CCCCCC"}
styles:
  label:       {xi: 0.37, yi: 0.15, wi: 7.0, hi: 0.35, size: 11, color: accent, valign: MIDDLE}
  key_message: {xi: 0.73, yi: 0.71, wi: 8.55, hi: 0.78, size: 14, color: accent,
                alignment: CENTER, valign: MIDDLE, line_spacing: 115}
  card:        {shape_type: ROUND_RECTANGLE, fill: "FFFFFF", outline: struct,
                outline_weight: 1.5, valign: TOP, alignment: CENTER, size: 10}
  header:      {shape_type: RECTANGLE, fill: struct, outline: none, color: "FFFFFF",
                size: 11, alignment: CENTER, valign: MIDDLE}
  cell:        {shape_type: RECTANGLE, fill: panel, outline: none, size: 9,
                valign: MIDDLE, line_spacing: 115}
  takeaway:    {shape_type: ROUND_RECTANGLE, fill: panelAlt, outline: none, xi: 0.73,
                yi: 4.13, wi: 8.55, hi: 0.67, size: 11, alignment: CENTER, valign: MIDDLE}
  source:      {xi: 4.28, yi: 4.73, wi: 5.0, hi: 0.22, size: 8, color: accent, alignment: END}
```

Use the `BLANK` layout (or the template's blank interior) and draw the
label and key message as shapes. Placeholder title boxes put the
conclusion where the template wants a title, not where this anatomy wants
it.
