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

If you get `403 insufficient authentication scopes`, delete the token cache
and re-login:
```bash
rm ~/.config/gws/token_cache.json
gws auth login --services drive,docs,sheets,slides,calendar,gmail
```

## Workflow

### 1. テンプレート確認 (Inspect)

Ask the user:

> テンプレートとして使う Google Slides はありますか？
> URL があれば貼ってください（なければデフォルトテーマで作成します）

If the user provides a URL like
`https://docs.google.com/presentation/d/XXXXX/edit...`, extract the
presentation ID (`XXXXX`) and set `template_id` in the spec.

**Template layout discovery:**

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

### 2. スライド設計 (Plan the mapping)

**全スライドの構成を先に決めてからYAMLを書く。** この手順がスタイル統一の鍵。

1. **スライド一覧を決める** — 各スライドのレイアウトとタイトルを列挙
2. **`styles:` を定義する** — 2枚以上のスライドで繰り返す要素（サブタイトル、脚注、コンテンツボックスなど）はスタイルとして定義
3. **`brand:` を決める** — フォント、色、サイズ
4. **座標の基準を決める** — インチ座標 (`xi`/`yi`/`wi`/`hi`) を使用。標準スライドは **10in x 7.5in**

**インチ座標クイックリファレンス:**

| 位置 | インチ | EMU相当 |
|------|--------|---------|
| 左マージン | xi: 0.22 | 200000 |
| 右端 | xi: 9.78 | 8940000 |
| タイトル下 | yi: 0.98 | 900000 |
| コンテンツ開始 | yi: 1.53 | 1400000 |
| ボトムゾーン | yi: 6.7-7.0 | 6100000-6400000 |
| 全幅 | wi: 9.51 | 8700000 |
| ハーフ幅 | wi: 4.59 | 4200000 |

### 3. YAML spec作成 (Build the spec)

**ルール: 変更は全てYAML経由で行う。** 直接 batchUpdate を叩かない。YAML specを編集して再実行するのが正しいワークフロー。

```bash
python3 scripts/build_gslides.py deck.yaml
python3 scripts/build_gslides.py deck.yaml --dry-run   # preview JSON
```

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
    yi: 7.1
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

### 4. ビルド実行 (Execute)

```bash
python3 scripts/build_gslides.py deck.yaml --dry-run   # まず確認
python3 scripts/build_gslides.py deck.yaml              # 本番実行
```

出力されたURLをブラウザで開く。

### 5. 確認・修正 (QA loop)

1. Google Slidesで開いて確認: タイトル位置、フォント統一、テキスト溢れ、間隔
2. 問題があればYAMLを修正して再実行（新しいプレゼンテーションが生成される）
3. **確認せずに完了と宣言しない**

## Spec reference

### Top-level keys

| Key | Description |
|-----|-------------|
| `title` | プレゼンテーションタイトル |
| `template_id` | テンプレートのプレゼンテーションID (省略可) |
| `brand` | フォント、サイズ、色のデフォルト設定 |
| `styles` | 名前付きスタイル定義 (省略可) |
| `page_numbers` | 自動ページ番号設定 (省略可) |
| `slides` | スライドのリスト |

### `brand` keys

| Key | Description | Example |
|-----|-------------|---------|
| `font` | デフォルトフォント | `"Noto Sans JP"` |
| `title_size` | タイトルのデフォルトサイズ (pt) | `28` |
| `body_size` | 本文のデフォルトサイズ (pt) | `16` |
| `date_format` | `$today` のstrftime形式 | `"%Y年%-m月%-d日"` |
| `colors` | 名前付き色マップ (6桁hex, `#`なし) | `primary: "0078D4"` |

### `styles:` — 名前付き再利用スタイル

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
    yi: 7.1
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

### `page_numbers:` — 自動ページ番号

| Key | Default | Description |
|-----|---------|-------------|
| `skip_first` | `true` | 最初のスライド(表紙)をスキップ |
| `skip_last` | `false` | 最後のスライド(Closing)をスキップ |
| `size` | `8` | フォントサイズ (pt) |
| `color` | `"595959"` | 文字色 (色名 or hex) |
| `position` | `bottom_left` | `bottom_left`, `bottom_right`, `bottom_center` |

### Position/size values

**インチ座標 (推奨):** `xi`, `yi`, `wi`, `hi` — 標準スライド = **10in x 7.5in**

**EMU座標 (後方互換):** `x`, `y`, `w`, `h` — 1 inch = 914400 EMU

インチキーが存在する場合、EMUキーより優先される。

### Slide ops (`do:` list)

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

## Workflow 2: Direct batchUpdate (escape hatch)

YAML specで表現できない操作のためのエスケープハッチ。
**注意: 反復的なスライド作業では使わない。** 直接 batchUpdate はコンテキストを急速に消費し、コンテキスト溢れの原因になる。

パターンは常に **2フェーズ**:

### Phase 1: プレゼンテーション + スライド作成

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

### Phase 2: Placeholder ID発見 → コンテンツ挿入

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

# 発見したIDでbatchUpdate
gws slides presentations batchUpdate \
  --params "{\"presentationId\": \"$PRES_ID\"}" \
  --json '{ "requests": [ ... ] }'
```

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

## Gotchas

1. **Object ID minimum 5 characters.** `createSlide` with `objectId: "s1"`
   fails. Use `"slide_01"` or longer.

2. **Placeholder IDs are auto-generated.** You cannot specify them at
   creation time. Always GET after createSlide and parse the
   `SLIDES_API...` IDs before inserting text.

3. **Two-phase batchUpdate is mandatory.** You cannot createSlide and
   insertText into its placeholders in the same request.

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
   `"cellLocation": {"rowIndex": R, "columnIndex": C}` in updateTextStyle.

9. **`fields` mask is required.** Every update request needs a `fields`
   string. Omitting it silently does nothing.

10. **Noto Sans JP works natively.** Google Slides supports `Noto Sans JP`
    directly (unlike LibreOffice which needs `Noto Sans CJK JP`).

11. **Image insertion requires a public URL.** `createImage` needs a
    URL accessible to Google's servers.

12. **Multiple SUBTITLE placeholders.** Some template layouts have
    SUBTITLE in both header and footer. The script picks the topmost
    (smallest Y coordinate).

13. **スタイルドリフト防止.** 2枚以上のスライドで同じ要素（サブタイトル、脚注など）が
    異なる座標やサイズになる場合、`styles:` エントリを定義して `style: name` で参照する。
    座標のコピペは不統一の原因になる。

14. **コンテキスト溢れ防止.** YAML specアプローチは直接batchUpdateの約1/10のトークン量。
    反復的な修正は必ずYAMLを編集して再実行する。

15. **インチ→EMU変換.** `xi: 1.0` = 914400 EMU。よく使う値:
    左マージン xi: 0.22 (≈200000), 全幅 wi: 9.51 (≈8700000),
    コンテンツ開始 yi: 1.53 (≈1400000)。

## Files

- `scripts/build_gslides.py` — declarative driver: YAML/JSON spec → Google Slides.
- `scripts/svgtools.py` — render SVG diagrams from HTML to PNG, light-recolor.
- `scripts/recolor_image.py` — dark→light raster diagram recolor.
