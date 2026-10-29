# Gotchas

Numbered so other files can cite them (`gotchas.md #16`). Keep numbers
stable: append new items, do not renumber.


1. **Object ID minimum 5 characters.** `createSlide` with `objectId: "s1"`
   fails. Use `"slide_01"` or longer.

2. **Placeholder IDs are auto-generated — unless you map them.** By default
   `createSlide` assigns `SLIDES_API...` IDs you must discover with a GET.
   Pass `placeholderIdMappings` to name them yourself:
   ```json
   {"createSlide": {"objectId": "slide_02", "insertionIndex": 1,
     "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
     "placeholderIdMappings": [
       {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": "slide_02_title"},
       {"layoutPlaceholder": {"type": "BODY",  "index": 0}, "objectId": "slide_02_body"}]}}
   ```
   For a template layout, `{"layoutPlaceholderObjectId": "<layout element id>"}`
   replaces `layoutPlaceholder`. A placeholder you do not want can be mapped
   and then `deleteObject`-ed in the same batch.

3. **Two phases only when the IDs are unknown.** Requests in one
   batchUpdate apply in order, so with mapped IDs a single batch can
   `createSlide` and then `insertText` into its placeholders. Without a
   mapping you must GET between the two. `build_gslides.py` still uses the
   GET (it works either way).

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

16. **APIで新規作成したスライドは 16:9 (10in x 5.625in)。** 4:3 の 7.5in ではない。
    ただしテンプレートを複製したデッキはテンプレートのサイズを引き継ぐ
    （PowerPoint 由来の 16:9 なら 13.333in x 7.5in）。10in 前提の座標を
    そのまま置くと、左上に寄って右と下が空く。実際のサイズは
    `presentations get` の `pageSize` で確かめる。`build_gslides.py` は
    `pageSize` を読み、`page_numbers:` の位置もページの端から計算する
    （ビルド時に `page: W x H` と表示する）。
    `yi` が 5.625 を超えた要素はエラーにならず画面外へ落ちる。出典行や
    ページ番号を 6.5-7.1 あたりに置くと、ビルドは成功したのに紙面に
    何も出ない、という形で失敗する。

17. **ビルド後は必ずPDFに書き出して目視する.** はみ出しと重なりはAPIの
    成功応答では検出できない。
    `gws drive files export --params '{"fileId":"ID","mimeType":"application/pdf"}' -o deck.pdf`
    （`-o` はカレントディレクトリ配下しか受け付けない。`/tmp` は拒否される）
    書き出したPDFを読んで、各ページの下端が切れていないか確認する。
    スライド単位で見るなら `build_gslides.py --thumbs DIR`（`pages.getThumbnail`、
    `--slides` と組み合わせると作り直した枚だけ）の方が速い。

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

21. **`gws drive files delete` はカレントディレクトリに空の `download.html` を残す.**
    応答本文が空のため、gws がそれをファイルに保存する。リポジトリ内で実行すると
    未追跡ファイルが増えるので、削除はリポジトリの外で行うか、後で消す。
