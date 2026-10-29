# Workflow 3: PPTX-first（ブランドテンプレートの資料・手順書）

Read when the deck must match a corporate template's masters/fonts, or is a
hands-on procedure deck with screenshots.


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
5. **QA（Google 上）**: Drive から PDF を書き出して目視する（gotchas.md #17）。
   Google が描画するのでテンプレートのフォントで表示され、日本語の PDF も
   正しく出る。配布用 PDF はこれを使う。

## 画面写真を Playwright で撮るときの注意

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
