# Workflow 3: PPTX-first (brand-template decks and procedure decks)

Read when the deck must match a corporate template's masters and fonts, or
is a hands-on procedure deck with screenshots.

Slides built through the Slides API cannot faithfully reproduce a corporate
template's masters, divider artwork or fonts. For a template-faithful deck,
build a PPTX and upload it to Drive with conversion. That is more reliable.

The workflow has two halves: **building the PPTX** and **turning it into
Google Slides**.

- **Building requires Anthropic's official `pptx` skill**
  (`document-skills:pptx` from `anthropics/skills`). It duplicates, edits
  and validates template slides; python-pptx cannot duplicate prototype
  slides or load the SVG/EMF art templates use.
  - Check that `pptx` appears in the skill list before step 1. **If it is
    missing, stop** and tell the user to install it:
    `/plugin marketplace add anthropics/skills` →
    `/plugin install document-skills@anthropic-agent-skills`.
    Do not build the PPTX another way.
  - It is not vendored, because its license does not allow redistribution.
- **The Google-specific parts stay in this skill**: conversion on upload,
  QA from the Drive PDF, and the Playwright capture notes below. Japanese
  font handling, screenshot red boxes and macOS visual QA come from the
  deck skill (`jpfont.py`, `annotate_shots.py`, `qa_thumbs.py`).

## Steps

1. **Export the template.**
   - Copy the Google Slides template and export it as PPTX
     (`template-base.pptx`).
   - For `procedure_deck.py`, keep exactly four slides: cover, divider,
     interior, closing.
   - Never commit an internal template to the repository.
2. **Build.** Choose by content:
   - **Procedure deck** (screenshots + numbered steps + copy-paste code) →
     `ProcedureDeck` in `scripts/procedure_deck.py` (usage in its
     docstring). It is a fixed-format generator for this one deck type,
     not a substitute for the pptx skill; step 3 validates its output with
     that skill.
     - Slide types: `two_shots` (two screenshots + explanation),
       `one_shot` (one screenshot + steps + code box), `divider` (divider +
       time estimate), `table`, `code`.
     - Screenshots are looked up in `shot_dirs` in order. List the
       red-boxed directory (deck skill's `annotate_shots.py`) before the
       originals.
   - **Anything else** (layouts outside the fixed types, decks reusing the
     template's icons or SVG/EMF art) → the official `pptx` skill's
     template-editing procedure: unpack → duplicate a prototype slide with
     `add_slide.py` → edit `slideN.xml` → `clean.py` → zip.
3. **Validate locally.**
   - Run the pptx skill's
     `python scripts/office/validate.py deck.pptx --original template-base.pptx`
     on the PPTX, whichever path built it. The path is relative to the pptx
     skill's directory. It reports, with fixes, the breakage that
     PowerPoint or Drive conversion would reject.
   - For a visual check on macOS, use the deck skill's `qa_thumbs.py`. The
     official skill's `thumbnail.py` renders through LibreOffice, where
     Japanese can come out blank on macOS (deck gotcha 3). On Linux
     either works.
4. **Upload with conversion:**
   ```bash
   # New file (My Drive root)
   gws drive files create --params '{"fields":"id,name,webViewLink"}' \
     --json '{"name":"Procedure (sample)","mimeType":"application/vnd.google-apps.presentation","parents":["root"]}' \
     --upload deck.pptx \
     --upload-content-type application/vnd.openxmlformats-officedocument.presentationml.presentation
   # Overwrite an existing file's content (add --json '{"name":"…"}' to rename too)
   gws drive files update --params '{"fileId":"ID"}' --upload deck.pptx \
     --upload-content-type application/vnd.openxmlformats-officedocument.presentationml.presentation
   ```
5. **QA on Google's side.** Export a PDF from Drive and look at it
   (gotchas.md #17).
   - Google renders it, so the template's fonts are used and Japanese
     comes out correctly.
   - Use this PDF for distribution.

## Capturing screenshots with Playwright

- **The OpenShift console loads twice on first display.** The title
  renders correctly once, then the spinner returns. Do not capture right
  after `wait_for`. Wait another 15–20 seconds.
- **On first console login**, the guided-tour dialog and the OpenShift
  Lightspeed panel cover the screen. Close them with Escape and
  Lightspeed's Minimize before capturing. The deck should also tell
  readers to close them first.
- **Importing YAML** (Monaco editor) by typing breaks under
  auto-indentation. Set it with
  `window.monaco.editor.getModels()[0].setValue(yaml)`.
- **Pod terminal** (xterm): type into `.xterm-helper-textarea` with
  `pressSequentially`, then press Enter.
- **Screenshots can only be saved under Playwright's working root.** `/tmp`
  is refused. Write deck images straight to `docs/images/...`.
- **Page snapshots (`.playwright-mcp/*.yml`) can contain connection
  passwords in plain text.** Grep for them and delete them at the end of
  the session.
