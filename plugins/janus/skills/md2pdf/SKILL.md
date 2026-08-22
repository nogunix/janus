---
name: md2pdf
description: >-
  Convert Markdown to PDF with proper Japanese typography via pandoc + weasyprint.
  Use when asked to create / generate a PDF from a markdown file, convert md to
  PDF, or produce a printable document. Handles CJK fonts, tables, code blocks,
  SVG images, and mermaid diagrams. Triggers: "PDFにして", "PDF作成", "md to pdf",
  "ドキュメントをPDFに".
---

# md2pdf

Convert Markdown to a print-ready PDF with proper Japanese (CJK) font rendering,
styled tables, syntax-highlighted code blocks, and embedded images/SVGs.

## When to use
- "PDFにして", "PDF作成して", "mdからPDF生成"
- "このマークダウンをPDFに変換"
- "レポートをPDFで出力"
- janus synthesize の `report.md` → `report.pdf` 最終出力

## Prerequisites (install if missing)
- `pandoc` (brew / apt)
- `weasyprint` (brew / pip)
Quick check: `pandoc --version && weasyprint --version`

All helper files live in `scripts/` and `css/` next to this file.

## Workflow

### 1. Convert with the bundled CSS

```bash
scripts/md2pdf.sh INPUT.md OUTPUT.pdf
```

This runs pandoc with weasyprint as the PDF engine, using the bundled
`css/default.css` for Japanese font support and clean typography.

The script auto-detects the CSS path relative to itself, so it works from
any working directory.

### 2. Convert with a custom CSS

```bash
scripts/md2pdf.sh INPUT.md OUTPUT.pdf --css /path/to/custom.css
```

### 3. Programmatic usage (from Claude)

```bash
SKILL_DIR="$(dirname "$(realpath "$0")")"
pandoc INPUT.md -o OUTPUT.pdf \
  --pdf-engine=weasyprint \
  --css="$SKILL_DIR/css/default.css"
```

### 4. Verify the output

Open the PDF and check:
- Japanese text renders correctly (not Chinese glyphs)
- Tables have borders and proper alignment
- Code blocks have background shading
- Images/SVGs are embedded and sized correctly

## CSS customization

The bundled `css/default.css` provides:
- **Fonts**: Hiragino Kaku Gothic ProN (macOS) → Noto Sans CJK JP (Linux) fallback
- **Page**: A4, 2cm margins
- **Tables**: bordered, zebra-striped header
- **Code**: monospace with light grey background
- **Headings**: h1 with bottom border, h2 with light border

To override, copy `css/default.css`, edit, and pass with `--css`.

## Gotchas
1. **Chinese glyphs instead of Japanese.** weasyprint picks the first CJK font
   it finds. The CSS font-family order matters — `Hiragino Kaku Gothic ProN`
   (macOS) or `Noto Sans CJK JP` (Linux) must come before any Chinese variant.
   `Noto Sans JP` is often NOT installed — use `Noto Sans CJK JP`.
2. **SVG images with relative paths.** pandoc resolves image paths relative to
   the input file, not the working directory. Use absolute paths or run from
   the input file's directory.
3. **Large tables overflow the page.** weasyprint breaks tables across pages
   but can clip wide tables. Keep table content concise or use `font-size: 9pt`
   for data-heavy tables.
4. **Mermaid diagrams.** pandoc doesn't render mermaid natively. Pre-render
   mermaid blocks to SVG/PNG before conversion, or use a pandoc filter.

## Files
- `scripts/md2pdf.sh` — CLI wrapper: `md2pdf.sh INPUT.md OUTPUT.pdf [--css FILE]`
- `css/default.css` — default stylesheet with Japanese font support
