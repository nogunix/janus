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
   blank slide with objectId `p`. Delete it in the first batchUpdate, after
   the requests that create your slides — a presentation may never be left
   with zero slides.

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

13. **Prevent style drift.** When the same element (subtitle, footnote, ...)
    appears on two or more slides, define it once under `styles:` and
    reference it with `style: name`. Copy-pasted coordinates drift apart.

14. **Prevent context overflow.** A YAML spec costs roughly 1/10 the tokens
    of the equivalent raw batchUpdate JSON. Make iterative fixes by editing
    the YAML and re-running.

15. **Inch → EMU.** `xi: 1.0` = 914400 EMU. Common values: left margin
    xi 0.22 (≈200000), full width wi 9.51 (≈8700000), content start yi 1.3
    (≈1188720).

16. **An API-created deck is 16:9 at 10in x 5.625in — not the 7.5in of 4:3.**
    - **A deck copied from a template keeps the template's size** (13.333in
      x 7.5in for a 16:9 deck that came from PowerPoint). Coordinates made
      for 10in then crowd the top-left and leave the right and bottom
      empty.
    - **Check the real size** in `pageSize` from `presentations get`.
      `build_gslides.py` reads `pageSize`, computes `page_numbers:`
      positions from the page edges, and prints `page: W x H` at build
      time.
    - **An element with `yi` past the page height drops off the slide
      without an error.** Putting citations or page numbers around 6.5–7.1
      on a 5.625in page fails this way: the build succeeds and nothing
      shows.

17. **Always look at the result after a build.** The API's success response
    cannot detect overflow or overlap.
    - **Per slide**: `build_gslides.py --thumbs DIR` (`pages.getThumbnail`)
      is fastest. With `--slides`, it captures only the rebuilt slides.
    - **Whole deck / distribution copy**: export a PDF and check that no
      page is cut off at the bottom.
      `gws drive files export --params '{"fileId":"ID","mimeType":"application/pdf"}' -o deck.pdf`
      (`-o` accepts only paths under the current directory; `/tmp` is
      refused).

18. **Uploading a PPTX converts it to Google Slides.**
    - **New file**: `files create` with
      `"mimeType":"application/vnd.google-apps.presentation"` in `--json`
      and the PPTX MIME type in `--upload-content-type`.
    - **Existing file**: `files update` replaces an existing deck's content
      wholesale with the PPTX. Version history can restore it.

19. **Overwriting the user's existing file can be blocked by the permission
    check.** Claude Code's auto mode may treat overwriting another
    person's (the user's) file as an external write and deny it.
    - Do not try to work around it. Create a new file instead, or ask the
      user to run the command themselves with the `!` prefix.
    - Updating a file you created yourself goes through.

20. **Over 20 slides, watch for duplicate part names in a PPTX.** Stacking
    `add_slide` while the template's prototype slides remain produces
    `Duplicate name: ppt/slides/slideNN.xml`. Before saving, run
    `prs.part.rename_slide_parts([s.rId for s in prs.slides._sldIdLst])`
    (`procedure_deck.py`'s `save()` already does).

21. **`gws drive files delete` leaves an empty `download.html` in the
    current directory.** The response body is empty and gws saves it to a
    file. Run deletes outside the repository, or remove the file
    afterwards, or it shows up as an untracked file.

22. **`createSlide` may only use a layout from the master of the slide
    before the insertion point.** Inserting an interior slide right after
    a cover that belongs to a different master fails with "layout is not
    present in the current master". Insert after a slide of the same master,
    then move it with `updateSlidesPosition`. (Reported by the gslides-deck
    skill's authors on a two-master template; not reproduced here.)

23. **`duplicateObject` gives the copy's child elements new IDs.** After
    duplicating a sample slide you cannot address its title box by the old
    ID. Either pass `objectIds: {"<old id>": "<new id>", ...}` in the same
    request to choose them, or GET afterwards and find elements by position
    or text.

24. **`files.copy` keeps a template's original `g…` element IDs, but may
    regenerate IDs you assigned through the API** (e.g. `tpl_interior_blank`).
    Key template lookups on the `g…` IDs, or on layout display names.
    (Reported by the gslides-deck skill's authors; not reproduced here.)

25. **Text indexes are UTF-16 code units.** `FIXED_RANGE` `startIndex` /
    `endIndex` count an emoji or other non-BMP character as two. Ranges
    computed with Python's `len()` drift after the first such character.
    `build_gslides.py`'s inline markup measures in UTF-16 (`u16len`). Do
    the same in any hand-written batchUpdate.
