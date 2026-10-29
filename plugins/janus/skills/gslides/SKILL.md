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
4. **座標の基準を決める** — インチ座標 (`xi`/`yi`/`wi`/`hi`) を使用。APIで作成したスライドは **16:9 = 10in x 5.625in**。
   テンプレートを複製した場合は**テンプレートのページサイズ**になる（PowerPoint 由来の 16:9 は 13.333in x 7.5in が多い）。
   `presentations get` の `pageSize`（EMU）を読んで決めること（gotchas.md #16）

**下端を超えた要素は画面外に落ちる。** エラーにならず、黙って消える。
縦位置を決めるときは必ずページの高さ（新規作成なら 5.625）を上限として設計すること。

**インチ座標クイックリファレンス (16:9、APIで新規作成した 10in x 5.625in):**

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

spec を書く前に `references/spec.md`（例2つ＋全キーの仕様）を読む。最小形:

```yaml
title: "提案資料"
brand: {font: "Noto Sans JP", title_size: 28, body_size: 16}
slides:
  - layout: TITLE
    do:
      - title: {text: "提案資料", bold: true}
      - subtitle: {text: "○○株式会社 様\n$today"}
```

### 4. ビルド実行 (Execute)

```bash
python3 scripts/build_gslides.py deck.yaml --dry-run   # まず確認
python3 scripts/build_gslides.py deck.yaml              # 本番実行
```

出力されたURLをブラウザで開く。

### 5. 確認・修正 (QA loop)

```bash
python3 scripts/build_gslides.py deck.yaml --update PRES_ID --thumbs qa/              # 全枚を作り直して全枚を撮る
python3 scripts/build_gslides.py deck.yaml --update PRES_ID --slides 4,12 --thumbs qa/  # 直した枚だけ
```

1. サムネイル（`qa/NN.png`、ImageMagick があれば `qa/sheet.png`）を Read で全枚見る:
   はみ出し・不自然な改行、要素の重なり、下端への侵入、上下の偏った余白、フォント統一
2. 問題があれば YAML を直し、`--update PRES_ID --slides N,…` でその枚だけ作り直す。
   URL は変わらない（共同編集・共有済みのリンクが生きたまま）。`--slides` の番号は spec の
   1 始まりの位置で、デッキの枚数が spec と同じときだけ使える（違えば `--slides` なしで全枚）
3. **確認せずに完了と宣言しない**。配布用は PDF でも確認する（gotchas.md #17）

## References — read when the moment comes

| ファイル | 読むとき |
|---|---|
| `references/spec.md` | YAML spec を書く・直すとき（例、top-level / `brand` / `styles` / `page_numbers` / 座標 / `do:` の全仕様） |
| `references/batchupdate.md` | spec で表現できない操作を batchUpdate で直接送るとき（Workflow 2） |
| `references/pptx-first.md` | 社内テンプレートのマスター・フォントを忠実に再現したいとき、画面写真入りの手順書を作るとき（Workflow 3、Playwright 撮影の注意） |
| `references/gotchas.md` | API がエラーを返したとき、結果が想定と違うとき（番号付き。他のファイルは `gotchas.md #N` で参照する） |

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

## Must-know (全文は `references/gotchas.md`)

- **#16 ページの下端を超えた要素は黙って消える。** APIで新規作成したデッキは 10in x 5.625in、テンプレート複製はテンプレートの `pageSize`。
- **#17 ビルド後は必ず PDF に書き出して目視する。** はみ出し・重なりは API の成功応答ではわからない。
- **#9 update 系リクエストは `fields` マスク必須。** 省くと黙って何もしない。
- **#4 / #5 gws の癖。** 出力の先頭に `Using keyring backend: keyring` が付く（`{` から読む）。本文は `--json`、パラメータは `--params`。
- **#6 スコープを足しても 403 が続く** ときは `~/.config/gws/token_cache.json` を消して再ログイン。
- **#2 プレースホルダーIDは `placeholderIdMappings` で自分で振れる。** 振れば作成と文字入れを1回の batchUpdate にまとめられる。

## Files

- `scripts/build_gslides.py` — declarative driver: YAML/JSON spec → Google Slides; `--update`/`--slides` rebuild in place, `--thumbs` for visual QA.
- `scripts/svgtools.py` — render SVG diagrams from HTML to PNG, light-recolor.
- `scripts/recolor_image.py` — dark→light raster diagram recolor.
- `scripts/procedure_deck.py` — Workflow 3: brand-template procedure decks as PPTX (python-pptx), then upload with conversion.
- `references/` — spec / batchupdate / pptx-first / gotchas (see References above).
