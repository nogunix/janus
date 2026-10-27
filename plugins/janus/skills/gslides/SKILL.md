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
4. **座標の基準を決める** — インチ座標 (`xi`/`yi`/`wi`/`hi`) を使用。APIで作成したスライドは **16:9 = 10in x 5.625in**

**`yi` が 5.625 を超えた要素は画面外に落ちる。** エラーにならず、黙って消える。
縦位置を決めるときは必ず 5.625 を上限として設計すること。

**インチ座標クイックリファレンス (16:9):**

| 位置 | インチ | EMU相当 |
|------|--------|---------|
| 左マージン | xi: 0.22 | 200000 |
| 右端 | xi: 9.78 | 8940000 |
| タイトル下（サブタイトル） | yi: 0.88 | 804672 |
| コンテンツ開始 | yi: 1.25-1.35 | 1143000-1234440 |
| ボトムゾーン（出典・ページ番号） | yi: 5.22-5.35 | 4773168-4892040 |
| スライド下端 | yi: 5.625 | 5143500 |
| 全幅 | wi: 9.51 | 8700000 |
| ハーフ幅 | wi: 4.59 | 4200000 |

**テーブルの行高は指定できない。** Slidesはフォントサイズとセル余白から自動で決め、
`font_size: 8-9` でも1行あたり約 0.66in になる。ヘッダ込みで N 行なら
`N × 0.66` インチを確保すること。16:9 では `yi: 1.2` 開始で **ヘッダ＋5行が上限**。
行数が多い表は2枚に分割する。

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

**インチ座標 (推奨):** `xi`, `yi`, `wi`, `hi` — APIで作成したスライド = **16:9 = 10in x 5.625in**

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

## Workflow 3: PPTX-first（ブランドテンプレートの資料・手順書）

Slides API で作るスライドは、社内テンプレートのマスター・中扉のデザイン・
フォントを忠実に再現できない。テンプレートに忠実な資料は PPTX で組み、
Drive にアップロードして変換する方が確実。

このワークフローは **PPTX を組む部分**と **Google スライドにする部分**に分かれる。
組む部分は、Anthropic 公式の `pptx` スキル（`anthropics/skills` の
document-skills）が入っていればそれに乗る。テンプレートの複製・編集・検証は
向こうの方が手厚い。入っていなければ、このスキルの `procedure_deck.py` と
deck スキルの `decklib.py` で組む。どちらでも 4〜5 は同じ。

- 公式 `pptx` スキルは同梱しない（ライセンスが再配布を認めていない）。使える
  かはスキル一覧に `pptx`（`document-skills:pptx`）があるかで判断する。
  無いことは普通の状態で、エラーにしない。入れるならユーザーが
  `/plugin marketplace add anthropics/skills` →
  `/plugin install document-skills@anthropic-agent-skills`。
- Google スライドに固有の部分（アップロード時の変換、Drive の PDF での QA、
  Playwright の撮影の注意、赤枠の `annotate_shots.py`）はこのスキルが持つ。

1. **テンプレートを書き出す**: Google スライドのテンプレートをコピーし、PPTX で
   書き出す（`template-base.pptx`）。`procedure_deck.py` を使うなら表紙・中扉・
   本文・締めの 4 枚だけ残す。社内テンプレートはリポジトリにコミットしない。
2. **組む**: 内容で選ぶ。
   - **画面写真＋番号付き手順＋コピペ用コードの手順書** →
     `scripts/procedure_deck.py` の `ProcedureDeck`（使用例は docstring）。
     `two_shots`（画面 2 枚＋説明）、`one_shot`（画面 1 枚＋手順＋コード枠）、
     `divider`（中扉＋目安時間）、`table`、`code` がある。画面写真は
     `shot_dirs` の先頭から探すので、赤枠付き（deck スキルの
     `annotate_shots.py`）を先に、元画像を後に並べる。
   - **それ以外**（定型に収まらないレイアウト、テンプレートのアイコンや
     SVG/EMF の図を流用する資料）→ 公式 `pptx` スキルの「テンプレートを
     編集する」手順（展開 → `add_slide.py` で見本スライドを複製 →
     `slideN.xml` を編集 → `clean.py` → zip）。python-pptx は見本スライドの
     複製も SVG/EMF の読み込みもできないので、ここは向こうに任せる。
     公式スキルが無ければ deck スキル（`decklib.py`）で組む。
3. **検証（ローカル）**:
   - 公式 `pptx` スキルがあれば、どちらで組んだ PPTX にも
     `python scripts/office/validate.py deck.pptx --original template-base.pptx`
     を通す（パスは pptx スキルのディレクトリ基準）。PowerPoint や Drive の
     変換が拒む壊れ方を、直し方つきで指摘する。
   - 目視は、macOS なら deck スキルの `qa_thumbs.py`。公式スキルの
     `thumbnail.py` は LibreOffice で描画するので、macOS では日本語が空白に
     なりうる（deck Gotcha 12）。Linux ならどちらでもよい。
4. **アップロードして変換**:
   ```bash
   # 新規作成（マイドライブ直下）
   gws drive files create --params '{"fields":"id,name,webViewLink"}' \
     --json '{"name":"手順書（サンプル）","mimeType":"application/vnd.google-apps.presentation","parents":["root"]}' \
     --upload deck.pptx \
     --upload-content-type application/vnd.openxmlformats-officedocument.presentationml.presentation
   # 既存ファイルを上書き（中身を差し替え、名前も変えるなら --json '{"name":"…"}' を足す）
   gws drive files update --params '{"fileId":"ID"}' --upload deck.pptx \
     --upload-content-type application/vnd.openxmlformats-officedocument.presentationml.presentation
   ```
5. **QA（Google 上）**: Drive から PDF を書き出して目視する（Gotcha 17）。
   Google が描画するのでテンプレートのフォントで表示され、日本語の PDF も
   正しく出る。配布用 PDF はこれを使う。

### 画面写真を Playwright で撮るときの注意

- **OpenShift コンソールは最初の表示で 2 回読み込む**。タイトルが一度
  正しく出た後にもう一度スピナーに戻るので、`wait_for` の直後に撮らず、
  もう 15〜20 秒待ってから撮る。
- **コンソール初回ログイン**ではガイドツアーのダイアログと OpenShift
  Lightspeed のパネルが画面を覆う。Escape と Lightspeed の Minimize で閉じて
  から撮る（資料にも「事前に閉じる」と書く）。
- **YAML のインポート**（Monaco エディタ）は打鍵すると自動インデントで崩れる。
  `window.monaco.editor.getModels()[0].setValue(yaml)` で入れる。
- **Pod のターミナル**（xterm）は `.xterm-helper-textarea` に
  `pressSequentially` で打ち、Enter で実行する。
- **スクリーンショットの保存先**は Playwright の作業ルート配下だけ（`/tmp` は
  拒否される）。資料用は直接 `docs/images/...` に書き出す。
- **ページのスナップショット（`.playwright-mcp/*.yml`）に接続情報の
  パスワードがそのまま残る**ことがある。作業の最後に grep して削除する。

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
    コンテンツ開始 yi: 1.3 (≈1188720)。

16. **スライドは 16:9 (10in x 5.625in)。** 4:3 の 7.5in ではない。
    `yi` が 5.625 を超えた要素はエラーにならず画面外へ落ちる。出典行や
    ページ番号を 6.5-7.1 あたりに置くと、ビルドは成功したのに紙面に
    何も出ない、という形で失敗する。

17. **ビルド後は必ずPDFに書き出して目視する.** はみ出しと重なりはAPIの
    成功応答では検出できない。
    `gws drive files export --params '{"fileId":"ID","mimeType":"application/pdf"}' -o deck.pdf`
    （`-o` はカレントディレクトリ配下しか受け付けない。`/tmp` は拒否される）
    書き出したPDFを読んで、各ページの下端が切れていないか確認する。

18. **PPTX のアップロードで Google スライドに変換される.** `files create` の
    `--json` に `"mimeType":"application/vnd.google-apps.presentation"` を付け、
    `--upload-content-type` に PPTX の MIME を渡す。`files update` は既存の
    Google スライドの中身を PPTX で丸ごと置き換える（版の履歴から戻せる）。

19. **ユーザーの既存ファイルへの上書きは、権限確認で止められることがある.**
    Claude Code の auto mode は他人（ユーザー）のファイルの上書きを外部書き込みと
    して拒否しうる。回避を試みず、新規ファイルとして作るか、ユーザーに
    `!` 付きでコマンドを実行してもらう。自分で作ったファイルの更新は通る。

20. **20 枚を超える PPTX は部品名の重複に注意.** テンプレートの見本スライドを
    残したまま `add_slide` を重ねると `Duplicate name: ppt/slides/slideNN.xml`
    になる。保存前に `prs.part.rename_slide_parts([s.rId for s in prs.slides._sldIdLst])`
    （`procedure_deck.py` の `save()` は実施済み）。

## Files

- `scripts/build_gslides.py` — declarative driver: YAML/JSON spec → Google Slides.
- `scripts/svgtools.py` — render SVG diagrams from HTML to PNG, light-recolor.
- `scripts/recolor_image.py` — dark→light raster diagram recolor.
- `scripts/procedure_deck.py` — Workflow 3: brand-template procedure decks as PPTX (python-pptx), then upload with conversion.
