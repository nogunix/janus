# Workflow 2: Direct batchUpdate (escape hatch)

Read only when the YAML spec cannot express an operation.

YAML specで表現できない操作のためのエスケープハッチ。
**注意: 反復的なスライド作業では使わない。** 直接 batchUpdate はコンテキストを急速に消費し、コンテキスト溢れの原因になる。

基本は **2フェーズ**（作成 → プレースホルダーIDを発見 → 挿入）。
`createSlide` に `placeholderIdMappings` を付けてプレースホルダーに自分でIDを振れば、
発見を省いて作成と挿入を1回の batchUpdate にまとめられる（gotchas.md #2）。

## Phase 1: プレゼンテーション + スライド作成

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

## Phase 2: Placeholder ID発見 → コンテンツ挿入

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
