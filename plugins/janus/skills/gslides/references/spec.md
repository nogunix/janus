# YAML spec reference (build_gslides.py)

Read when writing or editing a YAML spec for `scripts/build_gslides.py`.
Coordinates assume an API-created deck (10in x 5.625in) unless the spec
copies a template — then use the template's `pageSize` (gotchas.md #16).

## Examples

**Spec例 (blank, スタイル + インチ座標使用):**

```yaml
title: "提案資料"
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
      - title: {text: "提案資料", bold: true, size: 40, color: primary}
      - subtitle: {text: "○○株式会社 様\n$today", size: 18}

  - layout: TITLE_ONLY
    do:
      - title: {text: "現状の課題", bold: true}
      - shape:
          style: section_subtitle
          text: "3つの主要課題を特定"
      - shape:
          text: "❶ 課題A\n❷ 課題B\n❸ 課題C"
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
      - title: {text: "お問い合わせ", bold: true, color: primary}
```

**Spec例 (template-based):**

```yaml
template_id: "YOUR_TEMPLATE_PRESENTATION_ID"
title: "サービス提案書"
brand:
  font: "Noto Sans JP"
  title_size: 28
  body_size: 16

slides:
  - layout: "Title slide"
    do:
      - title: {text: "サービス提案書"}
      - subtitle: {text: "○○株式会社 様"}

  - layout: "Title and body"
    do:
      - title: {text: "現状の課題"}
      - body: {text: "課題1\n課題2\n課題3"}

  - layout: "Closing"
    do:
      - title: {text: "Thank you"}
```

## Top-level keys

| Key | Description |
|-----|-------------|
| `title` | プレゼンテーションタイトル |
| `template_id` | テンプレートのプレゼンテーションID (省略可) |
| `brand` | フォント、サイズ、色のデフォルト設定 |
| `styles` | 名前付きスタイル定義 (省略可) |
| `page_numbers` | 自動ページ番号設定 (省略可) |
| `slides` | スライドのリスト |

## `brand` keys

| Key | Description | Example |
|-----|-------------|---------|
| `font` | デフォルトフォント | `"Noto Sans JP"` |
| `title_size` | タイトルのデフォルトサイズ (pt) | `28` |
| `body_size` | 本文のデフォルトサイズ (pt) | `16` |
| `date_format` | `$today` のstrftime形式 | `"%Y年%-m月%-d日"` |
| `colors` | 名前付き色マップ (6桁hex, `#`なし) | `primary: "0078D4"` |

## `styles:` — 名前付き再利用スタイル

shape/table/image opで `style: name` として参照。明示的な値がスタイルのデフォルトを上書きする。

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

使用例:
```yaml
- shape:
    style: section_subtitle
    text: "このスライドのサブタイトル"
- shape:
    style: citation
    text: "[1] https://example.com"
```

位置を上書きしたい場合:
```yaml
- shape:
    style: content_box
    text: "左カラム"
    xi: 0.22
    wi: 4.5
```

## `page_numbers:` — 自動ページ番号

| Key | Default | Description |
|-----|---------|-------------|
| `skip_first` | `true` | 最初のスライド(表紙)をスキップ |
| `skip_last` | `false` | 最後のスライド(Closing)をスキップ |
| `size` | `8` | フォントサイズ (pt) |
| `color` | `"595959"` | 文字色 (色名 or hex) |
| `position` | `bottom_left` | `bottom_left`, `bottom_right`, `bottom_center`（ページの実寸から計算。テンプレートの大きいページでも端に付く） |

## Position/size values

**インチ座標 (推奨):** `xi`, `yi`, `wi`, `hi` — APIで作成したスライド = **16:9 = 10in x 5.625in**（テンプレート複製時はテンプレートの `pageSize`）

**EMU座標 (後方互換):** `x`, `y`, `w`, `h` — 1 inch = 914400 EMU

インチキーが存在する場合、EMUキーより優先される。

## Slide ops (`do:` list)

| Op | Description | Key args |
|----|-------------|----------|
| `title` | TITLE/CENTERED_TITLE placeholderを埋める | `text`, `size`, `bold`, `italic`, `color`, `font`, `autofit` |
| `subtitle` | SUBTITLE placeholderを埋める | 同上 (autofit: デフォルトon) |
| `body` | BODY placeholderを埋める | 同上 (autofit: デフォルトon) |
| `table` | テーブルを作成 | `header`, `rows`, `header_bg`, `xi`/`yi`/`wi`/`hi`, `font_size`, `style` |
| `shape` | テキストボックスや図形を追加 | `text`, `xi`/`yi`/`wi`/`hi`, `size`, `bold`, `color`, `fill`, `shape_type`, `style`, paragraph style keys |
| `background` | スライド背景色を設定 | `color` |
| `image` | URL指定で画像を挿入 | `url`, `xi`/`yi`/`wi`/`hi`, `style` |

**Paragraph style keys** (title/subtitle/body/shapeで利用可):
`line_spacing` (%), `space_above` / `space_below` (pt), `alignment` (`START`/`CENTER`/`END`/`JUSTIFIED`), `indent_start` (pt)

**Text autofit:** `body` と `subtitle` はデフォルトでTEXT_AUTOFITが有効。`autofit: false` で無効化、`autofit: true` で `title` にも有効化。

**Color values:** `brand.colors` のキー名 (e.g. `primary`) or 6桁hex (e.g. `2563EB`)

**フォント継承:** shape/table は `brand.font` と `brand.body_size` を自動継承。明示的に指定した場合はそちらが優先。

**`$today`** はビルド日に置換される。
