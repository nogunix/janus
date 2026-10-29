# Workflow 2: Direct batchUpdate (escape hatch)

Read only when the YAML spec cannot express an operation.

**Do not use this for iterative slide work.** Raw batchUpdate JSON consumes
context quickly and is a common cause of context overflow (gotchas.md #14).

The default is **two phases**: create, then discover the placeholder IDs,
then insert. Pass `placeholderIdMappings` to `createSlide` to name the
placeholder IDs yourself. That skips discovery and puts creation and
insertion in a single batchUpdate (gotchas.md #2, #3).

## Phase 1: Create the presentation and slides

Create the new slides before deleting the default slide `p`. The API
refuses to leave a presentation with no slides.

```bash
PRES_ID=$(gws slides presentations create \
  --json '{"title":"My Presentation"}' 2>&1 \
  | grep '"presentationId"' | head -1 \
  | sed 's/.*: "//;s/".*//')

gws slides presentations batchUpdate \
  --params "{\"presentationId\": \"$PRES_ID\"}" \
  --json '{
    "requests": [
      {"createSlide": {"objectId": "slide_01", "insertionIndex": 0,
                        "slideLayoutReference": {"layoutId": "p2"}}},
      {"createSlide": {"objectId": "slide_02", "insertionIndex": 1,
                        "slideLayoutReference": {"layoutId": "p4"}}},
      {"deleteObject": {"objectId": "p"}}
    ]
  }'
```

## Phase 2: Discover placeholder IDs, then insert content

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

# batchUpdate with the discovered IDs
gws slides presentations batchUpdate \
  --params "{\"presentationId\": \"$PRES_ID\"}" \
  --json '{ "requests": [ ... ] }'
```
