# YAML spec reference (build_gslides.py)

Read when writing or editing a YAML spec for `scripts/build_gslides.py`.
Coordinates assume an API-created deck (10in x 5.625in) unless the spec
copies a template — then use the template's `pageSize` (gotchas.md #16).

## Examples

**Example: blank deck, with styles and inch coordinates**

```yaml
title: "Proposal"
brand:
  font: "Noto Sans JP"
  title_size: 28
  body_size: 16
  colors:
    primary: "0078D4"
    grey: "595959"
    ltgrey: "888888"
    bg: "FFFFFF"

styles:
  section_subtitle:
    size: 14
    color: ltgrey
    xi: 0.38
    yi: 0.98
    wi: 9.19
    hi: 0.38
  citation:
    size: 8
    color: "999999"
    xi: 0.22
    yi: 5.3
    wi: 9.5
    hi: 0.27

page_numbers:
  skip_first: true
  skip_last: true
  size: 8
  color: "595959"
  position: bottom_left

slides:
  - layout: TITLE
    do:
      - title: {text: "Proposal", bold: true, size: 40, color: primary}
      - subtitle: {text: "For Example Corp.\n$today", size: 18}

  - layout: TITLE_ONLY
    do:
      - title: {text: "Current challenges", bold: true}
      - shape:
          style: section_subtitle
          text: "Three key challenges identified"
      - shape:
          text: "1. Challenge A\n2. Challenge B\n3. Challenge C"
          xi: 0.22
          yi: 1.53
          wi: 9.51
          hi: 4.0
          size: 14
      - shape:
          style: citation
          text: "[1] https://example.com/reference"

  - layout: MAIN_POINT
    do:
      - title: {text: "Contact", bold: true, color: primary}
```

**Example: template-based**

```yaml
template_id: "YOUR_TEMPLATE_PRESENTATION_ID"
title: "Service proposal"
brand:
  font: "Noto Sans JP"
  title_size: 28
  body_size: 16

slides:
  - layout: "Title slide"
    do:
      - title: {text: "Service proposal"}
      - subtitle: {text: "For Example Corp."}

  - layout: "Title and body"
    do:
      - title: {text: "Current challenges"}
      - body: {text: "Challenge 1\nChallenge 2\nChallenge 3"}

  - layout: "Closing"
    do:
      - title: {text: "Thank you"}
```

## Top-level keys

| Key | Description |
|-----|-------------|
| `title` | Presentation title |
| `template_id` | Presentation ID of a template to copy (optional) |
| `brand` | Default font, sizes and colors |
| `styles` | Named reusable styles (optional) |
| `page_numbers` | Automatic page numbers (optional) |
| `slides` | List of slides |

## `brand` keys

| Key | Description | Example |
|-----|-------------|---------|
| `font` | Default font | `"Noto Sans JP"` |
| `title_size` | Default title size (pt) | `28` |
| `body_size` | Default body size (pt) | `16` |
| `date_format` | strftime format for `$today` | `"%Y年%-m月%-d日"` |
| `colors` | Named color map (6-digit hex, no `#`) | `primary: "0078D4"` |

## `styles:` — named reusable styles

Reference one from a shape/table/image op with `style: name`. Values set on the op override the style's defaults.

```yaml
styles:
  section_subtitle:
    size: 14
    color: ltgrey
    xi: 0.38
    yi: 0.98
    wi: 9.19
    hi: 0.38
  citation:
    size: 8
    color: "999999"
    xi: 0.22
    yi: 5.3
    wi: 9.5
    hi: 0.27
  content_box:
    xi: 0.22
    wi: 9.51
    size: 11
    line_spacing: 120
```

Usage:
```yaml
- shape:
    style: section_subtitle
    text: "Subtitle for this slide"
- shape:
    style: citation
    text: "[1] https://example.com"
```

Overriding the position:
```yaml
- shape:
    style: content_box
    text: "Left column"
    xi: 0.22
    wi: 4.5
```

## `page_numbers:` — automatic page numbers

| Key | Default | Description |
|-----|---------|-------------|
| `skip_first` | `true` | Skip the first slide (cover) |
| `skip_last` | `false` | Skip the last slide (closing) |
| `size` | `8` | Font size (pt) |
| `color` | `"595959"` | Text color (color name or hex) |
| `position` | `bottom_left` | `bottom_left`, `bottom_right`, `bottom_center` — computed from the real page size, so they sit at the edge of a larger template page too |

## Position/size values

**Inch coordinates (preferred):** `xi`, `yi`, `wi`, `hi` — an API-created deck is **16:9 = 10in x 5.625in**; a copied template uses its own `pageSize`.

**EMU coordinates (backward compatible):** `x`, `y`, `w`, `h` — 1 inch = 914400 EMU.

When both are present, the inch key wins.

## Slide ops (`do:` list)

| Op | Description | Key args |
|----|-------------|----------|
| `title` | Fill the TITLE/CENTERED_TITLE placeholder | `text`, `size`, `bold`, `italic`, `color`, `font`, `autofit` |
| `subtitle` | Fill the SUBTITLE placeholder | same as `title` (autofit on by default) |
| `body` | Fill the BODY placeholder | same as `title` (autofit on by default) |
| `table` | Create a table | `header`, `rows`, `header_bg`, `xi`/`yi`/`wi`/`hi`, `font_size`, `style` |
| `shape` | Add a text box or shape | `text`, `xi`/`yi`/`wi`/`hi`, `size`, `bold`, `color`, `fill`, `shape_type`, `style`, paragraph style keys |
| `background` | Set the slide background color | `color` |
| `image` | Insert an image by URL | `url`, `xi`/`yi`/`wi`/`hi`, `style` |

**Paragraph style keys** (usable on title/subtitle/body/shape):
`line_spacing` (%), `space_above` / `space_below` (pt), `alignment` (`START`/`CENTER`/`END`/`JUSTIFIED`), `indent_start` (pt)

**Text autofit:** `body` and `subtitle` have TEXT_AUTOFIT on by default. `autofit: false` turns it off; `autofit: true` turns it on for `title` too.

**Color values:** a `brand.colors` key (e.g. `primary`) or 6-digit hex (e.g. `2563EB`)

**Font inheritance:** shape/table inherit `brand.font` and `brand.body_size`; explicit values win.

**`$today`** is replaced with the build date.
