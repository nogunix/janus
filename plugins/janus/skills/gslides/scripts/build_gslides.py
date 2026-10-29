#!/usr/bin/env python3
"""Build a Google Slides presentation from a declarative YAML/JSON spec.

Usage:
    python3 build_gslides.py deck.yaml
    python3 build_gslides.py deck.yaml --dry-run
    python3 build_gslides.py deck.yaml --update PRES_ID              # rebuild in place
    python3 build_gslides.py deck.yaml --update PRES_ID --slides 4,12  # only these
    python3 build_gslides.py deck.yaml --update PRES_ID --slides 4 --thumbs qa/

Supports two modes:
  1. Blank presentation (default): creates from scratch with default layouts.
  2. Template-based: copies a Google Slides template, strips sample slides,
     and builds on its layouts.  Set `template_id` in the spec.

Spec format:
    # Optional: copy from a Google Slides template
    template_id: "YOUR_TEMPLATE_PRESENTATION_ID"

    title: "My Presentation"
    brand:
      font: "Noto Sans JP"
      title_size: 36
      body_size: 20
      colors:
        primary: "2563EB"
        accent: "FF5C35"
        text: "000000"
        bg: "FFFFFF"

    slides:
      - layout: TITLE                    # layout name (exact match)
        do:
          - title: {text: "Hello", bold: true, size: 40, color: primary}
          - subtitle: {text: "Subtitle text"}
      - layout: TITLE_AND_BODY
        do:
          - title: {text: "Agenda"}
          - body: {text: "Item 1\\nItem 2\\nItem 3"}
      # Template layouts are matched by display name:
      - layout: "Interior title and body"
        do:
          - title: {text: "Details"}
          - body: {text: "Content here"}

DEFAULT LAYOUTS (blank presentation):
    TITLE             (p2)  CENTERED_TITLE + SUBTITLE
    SECTION_HEADER    (p3)  TITLE
    TITLE_AND_BODY    (p4)  TITLE + BODY
    TITLE_AND_TWO_COLUMNS (p5) TITLE + BODY x2
    TITLE_ONLY        (p6)  TITLE
    ONE_COLUMN_TEXT   (p7)  TITLE + BODY
    MAIN_POINT        (p8)  TITLE
    BIG_NUMBER        (p11) TITLE + BODY
    BLANK             (p12) (none)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date

DEFAULT_LAYOUT_MAP = {
    "TITLE": "p2",
    "SECTION_HEADER": "p3",
    "TITLE_AND_BODY": "p4",
    "TITLE_AND_TWO_COLUMNS": "p5",
    "TITLE_ONLY": "p6",
    "ONE_COLUMN_TEXT": "p7",
    "MAIN_POINT": "p8",
    "BIG_NUMBER": "p11",
    "BLANK": "p12",
}

DEFAULT_PLACEHOLDER_ROLE = {
    "TITLE": {"title": "CENTERED_TITLE", "subtitle": "SUBTITLE"},
    "SECTION_HEADER": {"title": "TITLE"},
    "TITLE_AND_BODY": {"title": "TITLE", "body": "BODY"},
    "TITLE_AND_TWO_COLUMNS": {"title": "TITLE", "body": "BODY"},
    "TITLE_ONLY": {"title": "TITLE"},
    "ONE_COLUMN_TEXT": {"title": "TITLE", "body": "BODY"},
    "MAIN_POINT": {"title": "TITLE"},
    "BIG_NUMBER": {"title": "TITLE", "body": "BODY"},
}

EMU_PER_INCH = 914400

# A presentation created through the API is 16:9 at 10in x 5.625in. A copied
# template keeps its own pageSize (13.333in x 7.5in is common), read via GET.
DEFAULT_PAGE_SIZE = (10.0, 5.625)

# Object IDs a fresh build uses are fixed (slide_01, shp_001, ...). An
# in-place --update creates its objects before deleting the old ones, so it
# sets a per-run prefix to keep the two generations from colliding.
ID_PREFIX = ""


def oid(name):
    return ID_PREFIX + name


def run_prefix():
    """Per-run object-ID prefix: starts with a letter, stays short."""
    n, digits = int(time.time() * 10), "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return f"u{out[-6:]}_"


def resolve_dim(op, inch_key, emu_key, default):
    if inch_key in op:
        return int(op[inch_key] * EMU_PER_INCH)
    return op.get(emu_key, default)


def resolve_style(op_args, styles):
    style_name = op_args.pop("style", None)
    if not style_name or not styles:
        return op_args
    style_defaults = styles.get(style_name)
    if not style_defaults:
        print(f"  warn: style '{style_name}' not found", file=sys.stderr)
        return op_args
    merged = dict(style_defaults)
    merged.update(op_args)
    return merged


def hex_to_rgb(h):
    h = h.lstrip("#")
    return {
        "red": int(h[0:2], 16) / 255,
        "green": int(h[2:4], 16) / 255,
        "blue": int(h[4:6], 16) / 255,
    }


def resolve_color(name, brand):
    colors = brand.get("colors", {})
    if name in colors:
        return hex_to_rgb(colors[name])
    if re.match(r'^[0-9a-fA-F]{6}$', name):
        return hex_to_rgb(name)
    return hex_to_rgb("000000")


def _parse_gws_json(output):
    """Parse JSON from gws CLI output, skipping the keyring prefix."""
    try:
        idx = output.index("{")
        depth = 0
        for i, ch in enumerate(output[idx:], start=idx):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return json.loads(output[idx:i + 1])
        return json.loads(output[idx:])
    except (ValueError, json.JSONDecodeError):
        return None


def gws_slides_cmd(args, json_body=None, params=None):
    cmd = ["gws", "slides", "presentations"] + args
    if params:
        cmd += ["--params", json.dumps(params)]
    if json_body:
        cmd += ["--json", json.dumps(json_body, ensure_ascii=False)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    data = _parse_gws_json(output)
    if data is None:
        if result.returncode != 0:
            print(f"gws error: {output[:500]}", file=sys.stderr)
            sys.exit(1)
        return {}
    return data


def gws_drive_cmd(args, params=None, json_body=None):
    cmd = ["gws", "drive", "files"] + args
    if params:
        cmd += ["--params", json.dumps(params)]
    if json_body:
        cmd += ["--json", json.dumps(json_body, ensure_ascii=False)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    data = _parse_gws_json(output)
    if data is None:
        if result.returncode != 0:
            print(f"gws drive error: {output[:500]}", file=sys.stderr)
            sys.exit(1)
        return {}
    return data


# Homebrew's Python is externally managed (PEP 668), so `pip install pyyaml`
# is refused there and Homebrew ships no pyyaml formula. Without PyYAML, a
# YAML spec is converted to JSON by `yq` (brew install yq). mikefarah's yq
# takes `-o=json`; kislyuk's jq wrapper of the same name emits JSON already.
YQ_COMMANDS = (["yq", "-o=json", "."], ["yq", "."])


def load_spec(path):
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    try:
        import yaml
    except ImportError:
        yaml = None
    if yaml:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    if shutil.which("yq"):
        for cmd in YQ_COMMANDS:
            r = subprocess.run(cmd + [path], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
    raise SystemExit(
        "A YAML spec needs PyYAML or yq. Install one of:\n"
        "  brew install yq\n"
        "  python3 -m pip install --user pyyaml   "
        "(Homebrew Python also needs --break-system-packages)\n"
        "or write the spec as .json.")


# ---------------------------------------------------------------------------
# Template support
# ---------------------------------------------------------------------------

def copy_template(template_id, title):
    """Copy a Google Slides template and return the new presentation ID."""
    data = gws_drive_cmd(
        ["copy"],
        params={"fileId": template_id},
        json_body={"name": title},
    )
    new_id = data.get("id")
    if not new_id:
        print(f"Failed to copy template: {data}", file=sys.stderr)
        sys.exit(1)
    return new_id


def discover_layouts(pres_id):
    """GET the presentation and return layout info.

    Returns:
        layout_map: {display_name: layout_object_id}
        layout_placeholders: {layout_object_id: {placeholder_type: [object_ids]}}
        slide_ids: [existing slide object IDs]
        page_size: (width_in, height_in)

    When duplicate display names exist (e.g. light/dark themes), the first
    occurrence wins — override by using the raw layoutId in the spec.
    """
    data = gws_slides_cmd(["get"], params={"presentationId": pres_id})

    layout_map = {}
    layout_placeholders = {}
    for l in data.get("layouts", []):
        lp = l.get("layoutProperties", {})
        name = lp.get("displayName", "")
        lid = l["objectId"]
        # First occurrence of each name wins; raw IDs always work
        if name and name not in layout_map:
            layout_map[name] = lid
        layout_map[lid] = lid

        phs = {}
        for el in l.get("pageElements", []):
            ph = el.get("shape", {}).get("placeholder", {})
            if ph:
                ph_type = ph.get("type", "")
                if ph_type not in ("SLIDE_NUMBER",):
                    phs.setdefault(ph_type, []).append(el["objectId"])
        layout_placeholders[lid] = phs

    slide_ids = [s["objectId"] for s in data.get("slides", [])]
    return layout_map, layout_placeholders, slide_ids, page_size_in(data)


def page_size_in(data):
    """(width, height) in inches from a presentations.get response."""
    ps = data.get("pageSize", {})
    w = ps.get("width", {}).get("magnitude")
    h = ps.get("height", {}).get("magnitude")
    if not w or not h:
        return DEFAULT_PAGE_SIZE
    return (w / EMU_PER_INCH, h / EMU_PER_INCH)


def create_presentation(title):
    data = gws_slides_cmd(["create"], json_body={"title": title})
    pres_id = data.get("presentationId")
    if not pres_id:
        print("Failed to create presentation", file=sys.stderr)
        sys.exit(1)
    return pres_id


def get_placeholder_ids(pres_id):
    """Get placeholder IDs for all slides.

    Returns {slide_obj_id: {placeholder_type: obj_id}}
    For types with multiple instances, picks the topmost (smallest Y) element
    so that SUBTITLE resolves to the header area, not the footer.
    """
    data = gws_slides_cmd(["get"], params={"presentationId": pres_id})
    result = {}
    for slide in data.get("slides", []):
        sid = slide["objectId"]
        candidates = {}  # {ph_type: [(y, obj_id), ...]}
        for el in slide.get("pageElements", []):
            ph = el.get("shape", {}).get("placeholder", {})
            if ph:
                ph_type = ph.get("type", "")
                y = el.get("transform", {}).get("translateY", 0)
                candidates.setdefault(ph_type, []).append((y, el["objectId"]))
        result[sid] = {}
        for ph_type, items in candidates.items():
            items.sort(key=lambda t: t[0])
            result[sid][ph_type] = items[0][1]
    return result


def batch_update(pres_id, requests):
    if not requests:
        return
    data = gws_slides_cmd(["batchUpdate"],
                          params={"presentationId": pres_id},
                          json_body={"requests": requests})
    if "error" in data:
        print(f"batchUpdate error: {data['error']['message']}",
              file=sys.stderr)
        sys.exit(1)
    return data


# ---------------------------------------------------------------------------
# Text styling
# ---------------------------------------------------------------------------

def build_text_style(op, brand):
    style = {}
    fields = []

    font = op.get("font", brand.get("font"))
    if font:
        style["fontFamily"] = font
        fields.append("fontFamily")

    size = op.get("size")
    if size:
        style["fontSize"] = {"magnitude": size, "unit": "PT"}
        fields.append("fontSize")

    if op.get("bold"):
        style["bold"] = True
        fields.append("bold")

    if op.get("italic"):
        style["italic"] = True
        fields.append("italic")

    color = op.get("color")
    if color:
        style["foregroundColor"] = {
            "opaqueColor": {"rgbColor": resolve_color(color, brand)}
        }
        fields.append("foregroundColor")

    link = op.get("link")
    if link:
        style["link"] = {"url": link}
        style["underline"] = True
        fields += ["link", "underline"]

    return style, ",".join(fields)


def build_paragraph_style(op):
    style = {}
    fields = []

    ls = op.get("line_spacing")
    if ls:
        style["lineSpacing"] = ls
        fields.append("lineSpacing")

    sa = op.get("space_above")
    if sa is not None:
        style["spaceAbove"] = {"magnitude": sa, "unit": "PT"}
        fields.append("spaceAbove")

    sb = op.get("space_below")
    if sb is not None:
        style["spaceBelow"] = {"magnitude": sb, "unit": "PT"}
        fields.append("spaceBelow")

    alignment = op.get("alignment")
    if alignment:
        style["alignment"] = alignment
        fields.append("alignment")

    indent_start = op.get("indent_start")
    if indent_start is not None:
        style["indentStart"] = {"magnitude": indent_start, "unit": "PT"}
        fields.append("indentStart")

    return style, ",".join(fields)


# Inline emphasis inside any text op: **bold**, and {name:text} for bold in a
# brand color (a `brand.colors` key) or a 6-digit hex. The Slides API indexes
# text in UTF-16 code units, so an emoji or other non-BMP character counts
# two. Ranges are measured that way here; Python's len() would drift.
MARKUP_RE = re.compile(r"\*\*(.+?)\*\*|\{([A-Za-z]\w*|[0-9a-fA-F]{6}):(.+?)\}", re.S)


def u16len(text):
    return len(text.encode("utf-16-le")) // 2


def parse_markup(text):
    """Return (plain_text, [(start, end, color_or_None), ...]) in UTF-16 units."""
    plain, spans, pos, last = [], [], 0, 0
    for m in MARKUP_RE.finditer(text):
        before = text[last:m.start()]
        plain.append(before)
        pos += u16len(before)
        inner = m.group(1) if m.group(1) is not None else m.group(3)
        color = None if m.group(1) is not None else m.group(2)
        plain.append(inner)
        spans.append((pos, pos + u16len(inner), color))
        pos += u16len(inner)
        last = m.end()
    plain.append(text[last:])
    return "".join(plain), spans


def span_requests(obj_id, spans, brand):
    reqs = []
    for start, end, color in spans:
        style, fields = {"bold": True}, ["bold"]
        if color:
            style["foregroundColor"] = {
                "opaqueColor": {"rgbColor": resolve_color(color, brand)}}
            fields.append("foregroundColor")
        reqs.append({"updateTextStyle": {
            "objectId": obj_id, "style": style, "fields": ",".join(fields),
            "textRange": {"type": "FIXED_RANGE", "startIndex": start,
                          "endIndex": end}}})
    return reqs


def line_request(line_id, slide_obj_id, op, brand):
    """Straight connector from (x1i, y1i) to (x2i, y2i). Returns the requests,
    or [] with a warning for an up-right/down-left diagonal, which a line's
    unflipped bounding box cannot express."""
    x1, y1 = op.get("x1i", 0), op.get("y1i", 0)
    x2, y2 = op.get("x2i", x1), op.get("y2i", y1)
    arrow = op.get("arrow", "none")
    start_arrow, end_arrow = arrow in ("start", "both"), arrow in ("end", "both")
    if x2 < x1 or (x2 == x1 and y2 < y1):
        x1, y1, x2, y2 = x2, y2, x1, y1
        start_arrow, end_arrow = end_arrow, start_arrow
    if y2 < y1:
        print(f"  warn: line on {slide_obj_id} runs up-right; use horizontal, "
              f"vertical or down-right lines. Skipped.", file=sys.stderr)
        return []
    w = max(int((x2 - x1) * EMU_PER_INCH), 1)
    h = max(int((y2 - y1) * EMU_PER_INCH), 1)
    props = {
        "lineFill": {"solidFill": {"color": {"rgbColor": resolve_color(
            op.get("color", "595959"), brand)}}},
        "weight": {"magnitude": op.get("weight", 0.75), "unit": "PT"},
        "startArrow": "FILL_ARROW" if start_arrow else "NONE",
        "endArrow": "FILL_ARROW" if end_arrow else "NONE",
    }
    fields = "lineFill,weight,startArrow,endArrow"
    if op.get("dash"):
        props["dashStyle"] = op["dash"]
        fields += ",dashStyle"
    return [
        {"createLine": {"objectId": line_id, "category": "STRAIGHT",
                        "elementProperties": {
                            "pageObjectId": slide_obj_id,
                            "size": {"width": {"magnitude": w, "unit": "EMU"},
                                     "height": {"magnitude": h, "unit": "EMU"}},
                            "transform": {"scaleX": 1, "scaleY": 1,
                                          "translateX": int(x1 * EMU_PER_INCH),
                                          "translateY": int(y1 * EMU_PER_INCH),
                                          "unit": "EMU"}}}},
        {"updateLineProperties": {"objectId": line_id, "lineProperties": props,
                                  "fields": fields}},
    ]


# ---------------------------------------------------------------------------
# Slide ops
# ---------------------------------------------------------------------------

def resolve_placeholder(slide_obj_id, op_name, layout_name, placeholders,
                        layout_phs):
    """Find the placeholder object ID for a given op (title/subtitle/body).

    Uses the actual placeholder types from the slide. For templates with
    SUBTITLE used for multiple purposes, we use index-based matching.
    """
    ph_map = placeholders.get(slide_obj_id, {})

    if op_name == "title":
        for t in ("CENTERED_TITLE", "TITLE"):
            if t in ph_map:
                return ph_map[t]
    elif op_name == "subtitle":
        if "SUBTITLE" in ph_map:
            return ph_map["SUBTITLE"]
    elif op_name == "body":
        if "BODY" in ph_map:
            return ph_map["BODY"]

    return None


def process_slide_ops(slide_obj_id, layout_name, ops, placeholders, brand,
                      counter, layout_phs=None, styles=None):
    requests = []
    ph_map = placeholders.get(slide_obj_id, {})

    for op_entry in ops:
        (op_name, op_args), = op_entry.items()
        if isinstance(op_args, str):
            op_args = {"text": op_args}
        op_args = dict(op_args or {})

        if op_name in ("shape", "table", "image", "line"):
            op_args = resolve_style(op_args, styles or {})

        # $today substitution
        today_str = date.today().strftime(
            brand.get("date_format", "%Y年%-m月%-d日"))
        for k, v in op_args.items():
            if isinstance(v, str):
                op_args[k] = v.replace("$today", today_str)

        if op_name in ("title", "subtitle", "body"):
            ph_id = resolve_placeholder(slide_obj_id, op_name, layout_name,
                                        placeholders, layout_phs)
            if not ph_id:
                print(f"  warn: {op_name} placeholder not found on "
                      f"{slide_obj_id} (layout: {layout_name}), skipping",
                      file=sys.stderr)
                continue

            text, spans = parse_markup(op_args.get("text", ""))
            requests.append({"insertText": {"objectId": ph_id, "text": text}})

            size = op_args.get("size")
            if not size:
                if op_name == "title":
                    size = brand.get("title_size")
                else:
                    size = brand.get("body_size")
            if size:
                op_args.setdefault("size", size)

            if not op_args.get("font"):
                op_args["font"] = brand.get("font")

            style, fields = build_text_style(op_args, brand)
            if fields:
                requests.append({
                    "updateTextStyle": {
                        "objectId": ph_id,
                        "style": style,
                        "textRange": {"type": "ALL"},
                        "fields": fields,
                    }
                })

            para_style, para_fields = build_paragraph_style(op_args)
            if para_fields:
                requests.append({
                    "updateParagraphStyle": {
                        "objectId": ph_id,
                        "style": para_style,
                        "textRange": {"type": "ALL"},
                        "fields": para_fields,
                    }
                })
            requests.extend(span_requests(ph_id, spans, brand))

            # The Slides API accepts only autofitType NONE on
            # updateShapeProperties — "Autofit types other than NONE are not
            # supported" — and a whole batch fails if TEXT_AUTOFIT is sent.
            # So `autofit: true` (and the old default-on behaviour for
            # body/subtitle) cannot be honoured through the API: shrink-to-fit
            # is a client-side feature. Only the opt-out is expressible.
            # The field mask must be autofit.autofitType; a bare "autofit"
            # expands to the whole subtree, which carries the read-only
            # fontScale and lineSpacingReduction, and is rejected as
            # "Invalid field mask: * includes read-only fields".
            autofit = op_args.get("autofit")
            if autofit is False:
                requests.append({
                    "updateShapeProperties": {
                        "objectId": ph_id,
                        "shapeProperties": {
                            "autofit": {"autofitType": "NONE"}
                        },
                        "fields": "autofit.autofitType",
                    }
                })
            elif autofit:
                sys.stderr.write(
                    f"  warn: autofit: true on {op_name} is ignored — the "
                    f"Slides API only accepts autofitType NONE. Size the text "
                    f"with `size:` or shorten it instead.\n"
                )

        elif op_name == "table":
            counter[0] += 1
            tbl_id = oid(f"tbl_{counter[0]:03d}")
            header = op_args.get("header", [])
            rows = op_args.get("rows", [])
            cols = len(header) if header else (len(rows[0]) if rows else 1)
            total_rows = (1 if header else 0) + len(rows)

            x = resolve_dim(op_args, "xi", "x", 500000)
            y = resolve_dim(op_args, "yi", "y", 1500000)
            w = resolve_dim(op_args, "wi", "w", 7800000)
            h = resolve_dim(op_args, "hi", "h", total_rows * 600000)

            requests.append({
                "createTable": {
                    "objectId": tbl_id,
                    "elementProperties": {
                        "pageObjectId": slide_obj_id,
                        "size": {
                            "width": {"magnitude": w, "unit": "EMU"},
                            "height": {"magnitude": h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": x, "translateY": y,
                            "unit": "EMU",
                        },
                    },
                    "rows": total_rows,
                    "columns": cols,
                }
            })

            row_offset = 0
            if header:
                for ci, cell in enumerate(header):
                    requests.append({
                        "insertText": {
                            "objectId": tbl_id,
                            "text": str(cell),
                            "cellLocation": {
                                "rowIndex": 0, "columnIndex": ci
                            },
                        }
                    })
                header_bg = op_args.get("header_bg")
                if header_bg:
                    requests.append({
                        "updateTableCellProperties": {
                            "objectId": tbl_id,
                            "tableRange": {
                                "location": {
                                    "rowIndex": 0, "columnIndex": 0
                                },
                                "rowSpan": 1, "columnSpan": cols,
                            },
                            "tableCellProperties": {
                                "tableCellBackgroundFill": {
                                    "solidFill": {
                                        "color": {"rgbColor": resolve_color(
                                            header_bg, brand)}
                                    }
                                }
                            },
                            "fields": "tableCellBackgroundFill",
                        }
                    })
                    for ci in range(cols):
                        hdr_style = {
                            "foregroundColor": {
                                "opaqueColor": {
                                    "rgbColor": {"red": 1, "green": 1,
                                                 "blue": 1}
                                }
                            },
                            "bold": True,
                        }
                        font = brand.get("font")
                        if font:
                            hdr_style["fontFamily"] = font
                        requests.append({
                            "updateTextStyle": {
                                "objectId": tbl_id,
                                "cellLocation": {
                                    "rowIndex": 0, "columnIndex": ci
                                },
                                "style": hdr_style,
                                "textRange": {"type": "ALL"},
                                "fields": "foregroundColor,bold"
                                           + (",fontFamily" if font else ""),
                            }
                        })
                row_offset = 1

            for ri, row in enumerate(rows):
                for ci, cell in enumerate(row):
                    requests.append({
                        "insertText": {
                            "objectId": tbl_id,
                            "text": str(cell),
                            "cellLocation": {
                                "rowIndex": ri + row_offset,
                                "columnIndex": ci,
                            },
                        }
                    })

            font = brand.get("font")
            tbl_font_size = op_args.get("font_size", brand.get("body_size", 14))
            if font:
                for ri in range(row_offset, total_rows):
                    for ci in range(cols):
                        requests.append({
                            "updateTextStyle": {
                                "objectId": tbl_id,
                                "cellLocation": {
                                    "rowIndex": ri, "columnIndex": ci
                                },
                                "style": {
                                    "fontFamily": font,
                                    "fontSize": {
                                        "magnitude": tbl_font_size,
                                        "unit": "PT"
                                    },
                                },
                                "textRange": {"type": "ALL"},
                                "fields": "fontFamily,fontSize",
                            }
                        })

        elif op_name == "shape":
            counter[0] += 1
            shape_id = oid(f"shp_{counter[0]:03d}")
            x = resolve_dim(op_args, "xi", "x", 2000000)
            y = resolve_dim(op_args, "yi", "y", 2500000)
            w = resolve_dim(op_args, "wi", "w", 5000000)
            h = resolve_dim(op_args, "hi", "h", 800000)
            requests.append({
                "createShape": {
                    "objectId": shape_id,
                    "shapeType": op_args.get("shape_type", "TEXT_BOX"),
                    "elementProperties": {
                        "pageObjectId": slide_obj_id,
                        "size": {
                            "width": {"magnitude": w, "unit": "EMU"},
                            "height": {"magnitude": h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": x, "translateY": y,
                            "unit": "EMU",
                        },
                    },
                }
            })
            text, spans = parse_markup(op_args.get("text", ""))
            if not op_args.get("font"):
                op_args["font"] = brand.get("font")
            if not op_args.get("size"):
                body_size = brand.get("body_size")
                if body_size:
                    op_args["size"] = body_size
            if text:
                requests.append({
                    "insertText": {"objectId": shape_id, "text": text}
                })
                style, fields = build_text_style(op_args, brand)
                if fields:
                    requests.append({
                        "updateTextStyle": {
                            "objectId": shape_id,
                            "style": style,
                            "textRange": {"type": "ALL"},
                            "fields": fields,
                        }
                    })
                para_style, para_fields = build_paragraph_style(op_args)
                if para_fields:
                    requests.append({
                        "updateParagraphStyle": {
                            "objectId": shape_id,
                            "style": para_style,
                            "textRange": {"type": "ALL"},
                            "fields": para_fields,
                        }
                    })

                requests.extend(span_requests(shape_id, spans, brand))

            # Fill, outline and vertical alignment share one request.
            # `fill: none` / `outline: none` remove the theme fill and outline
            # a non-TEXT_BOX shape would otherwise get.
            shape_props, shape_fields = {}, []
            fill = op_args.get("fill")
            if fill == "none":
                shape_props["shapeBackgroundFill"] = {
                    "propertyState": "NOT_RENDERED"}
                shape_fields.append("shapeBackgroundFill")
            elif fill:
                shape_props["shapeBackgroundFill"] = {"solidFill": {
                    "color": {"rgbColor": resolve_color(fill, brand)}}}
                shape_fields.append("shapeBackgroundFill")
            outline = op_args.get("outline")
            if outline == "none":
                shape_props["outline"] = {"propertyState": "NOT_RENDERED"}
                shape_fields.append("outline")
            elif outline:
                ol = {"outlineFill": {"solidFill": {"color": {
                          "rgbColor": resolve_color(outline, brand)}}},
                      "weight": {"magnitude": op_args.get("outline_weight", 1),
                                 "unit": "PT"}}
                if op_args.get("dash"):
                    ol["dashStyle"] = op_args["dash"]
                shape_props["outline"] = ol
                shape_fields.append("outline")
            if op_args.get("valign"):
                shape_props["contentAlignment"] = op_args["valign"]
                shape_fields.append("contentAlignment")
            if shape_fields:
                requests.append({
                    "updateShapeProperties": {
                        "objectId": shape_id,
                        "shapeProperties": shape_props,
                        "fields": ",".join(shape_fields),
                    }
                })

        elif op_name == "line":
            counter[0] += 1
            requests.extend(line_request(oid(f"lin_{counter[0]:03d}"),
                                         slide_obj_id, op_args, brand))

        elif op_name == "background":
            color = op_args.get("color", "FFFFFF")
            requests.append({
                "updatePageProperties": {
                    "objectId": slide_obj_id,
                    "pageProperties": {
                        "pageBackgroundFill": {
                            "solidFill": {
                                "color": {"rgbColor": resolve_color(
                                    color, brand)}
                            }
                        }
                    },
                    "fields": "pageBackgroundFill",
                }
            })

        elif op_name == "image":
            counter[0] += 1
            img_id = oid(f"img_{counter[0]:03d}")
            url = op_args.get("url", "")
            x = resolve_dim(op_args, "xi", "x", 500000)
            y = resolve_dim(op_args, "yi", "y", 1500000)
            w = resolve_dim(op_args, "wi", "w", 5000000)
            h = resolve_dim(op_args, "hi", "h", 3000000)
            requests.append({
                "createImage": {
                    "objectId": img_id,
                    "url": url,
                    "elementProperties": {
                        "pageObjectId": slide_obj_id,
                        "size": {
                            "width": {"magnitude": w, "unit": "EMU"},
                            "height": {"magnitude": h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": x, "translateY": y,
                            "unit": "EMU",
                        },
                    },
                }
            })

    return requests


# ---------------------------------------------------------------------------
# Page numbers
# ---------------------------------------------------------------------------

# Anything placed below the page height lands off-slide and renders nowhere,
# silently, so positions are measured from the actual page edges. On the
# API-created 10in x 5.625in page they come out at (0.22 | 9.3 | 4.8, 5.25).
def page_number_position(name, page_size=DEFAULT_PAGE_SIZE):
    w, h = page_size
    x = {"bottom_left": 0.22, "bottom_right": w - 0.7,
         "bottom_center": w / 2 - 0.2}.get(name, 0.22)
    return x, h - 0.375


def build_page_numbers(slide_ids, config, brand, page_size=DEFAULT_PAGE_SIZE,
                       only=None):
    """Page-number boxes for slide_ids (spec order). `only` limits them to a
    set of 0-based indexes, for a partial --slides rebuild."""
    slide_count = len(slide_ids)
    skip_first = config.get("skip_first", True)
    skip_last = config.get("skip_last", False)
    size = config.get("size", 8)
    color = config.get("color", "595959")
    pos_name = config.get("position", "bottom_left")
    xi, yi = page_number_position(pos_name, page_size)
    w = int(config.get("wi", 0.4) * EMU_PER_INCH)
    h = int(config.get("hi", 0.25) * EMU_PER_INCH)
    x = int(xi * EMU_PER_INCH)
    y = int(yi * EMU_PER_INCH)

    requests = []
    for i in range(slide_count):
        slide_num = i + 1
        if skip_first and i == 0:
            continue
        if skip_last and i == slide_count - 1:
            continue
        if only is not None and i not in only:
            continue
        slide_id = slide_ids[i]
        pn_id = oid(f"pagenum_{slide_num:02d}")
        requests.append({
            "createShape": {
                "objectId": pn_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": w, "unit": "EMU"},
                        "height": {"magnitude": h, "unit": "EMU"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": x, "translateY": y,
                        "unit": "EMU",
                    },
                },
            }
        })
        requests.append({
            "insertText": {"objectId": pn_id, "text": str(slide_num)}
        })
        text_style = {"fontSize": {"magnitude": size, "unit": "PT"}}
        fields = ["fontSize"]
        font = brand.get("font")
        if font:
            text_style["fontFamily"] = font
            fields.append("fontFamily")
        text_style["foregroundColor"] = {
            "opaqueColor": {"rgbColor": resolve_color(color, brand)}
        }
        fields.append("foregroundColor")
        requests.append({
            "updateTextStyle": {
                "objectId": pn_id,
                "style": text_style,
                "textRange": {"type": "ALL"},
                "fields": ",".join(fields),
            }
        })
    return requests


# ---------------------------------------------------------------------------
# Slide plan, partial rebuild, thumbnails
# ---------------------------------------------------------------------------

def parse_positions(text, n_slides):
    """'4,12' → [4, 12] (1-based spec positions, sorted, deduplicated)."""
    try:
        pos = sorted({int(t) for t in text.split(",") if t.strip()})
    except ValueError:
        raise SystemExit(f"--slides: not a comma-separated list of numbers: {text}")
    bad = [q for q in pos if not 1 <= q <= n_slides]
    if bad or not pos:
        raise SystemExit(f"--slides: positions must be 1..{n_slides}, got {text}")
    return pos


def slide_requests(new_ids, layout_ids, existing, targets=None):
    """Phase 1 requests: create the new slides, then delete what they replace.

    The API refuses to delete the last slide, so creation always comes first.
    Full build (targets None): create every slide at the front, delete every
    existing one. Partial rebuild: for each 1-based target, insert the new
    slide at its index — pushing the old one down a place — and delete the
    old one by ID, so every other slide keeps its position.
    """
    reqs = []
    indexes = range(len(new_ids)) if targets is None else [t - 1 for t in targets]
    for i in indexes:
        reqs.append({"createSlide": {
            "objectId": new_ids[i], "insertionIndex": i,
            "slideLayoutReference": {"layoutId": layout_ids[i]}}})
        if targets is not None:
            reqs.append({"deleteObject": {"objectId": existing[i]}})
    if targets is None:
        reqs += [{"deleteObject": {"objectId": sid}} for sid in existing]
    return reqs


def thumbnails(pres_id, outdir, positions=None, size="LARGE"):
    """Download per-slide thumbnails as outdir/NN.png (1-based positions).

    getThumbnail is rate-limited (it counts as an expensive read), so calls
    are spaced and retried. Downloads go through curl, like gws itself."""
    os.makedirs(outdir, exist_ok=True)
    # A reused directory must not mix a stale run into the review.
    for f in os.listdir(outdir):
        if re.fullmatch(r"\d{2,}\.png|sheet\.png", f):
            os.remove(os.path.join(outdir, f))
    data = gws_slides_cmd(["get"], params={"presentationId": pres_id,
                                           "fields": "slides(objectId)"})
    paths = []
    for n, sl in enumerate(data.get("slides", []), start=1):
        if positions and n not in positions:
            continue
        url = None
        for attempt in range(4):
            t = gws_slides_cmd(["pages", "getThumbnail"], params={
                "presentationId": pres_id, "pageObjectId": sl["objectId"],
                "thumbnailProperties.thumbnailSize": size})
            url = t.get("contentUrl")
            if url:
                break
            time.sleep(5 * (attempt + 1))
        if not url:
            print(f"  warn: no thumbnail for slide {n}", file=sys.stderr)
            continue
        path = os.path.join(outdir, f"{n:02d}.png")
        subprocess.run(["curl", "-s", "-o", path, url], check=True)
        paths.append(path)
        time.sleep(1.2)
    return paths


# ImageMagick has no usable default font on stock macOS, so a -label without
# -font fails the whole montage. Label only when a known font file exists.
LABEL_FONTS = ("/System/Library/Fonts/Helvetica.ttc",
               "/usr/share/fonts/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def contact_sheet(paths, out, tile="3x"):
    """Montage thumbnails into one image (labelled by slide number when a
    font is available). Returns None when ImageMagick is absent or fails —
    the per-slide PNGs are still there to read."""
    if not paths or not shutil.which("montage"):
        return None
    font = next((f for f in LABEL_FONTS if os.path.exists(f)), None)
    label = ["-font", font, "-label", "%t", "-pointsize", "24"] if font else []
    r = subprocess.run(["montage", *label, *paths, "-tile", tile,
                        "-geometry", "1000x563+6+6", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  warn: montage failed: {r.stderr.strip()[:200]}",
              file=sys.stderr)
        return None
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global ID_PREFIX
    ap = argparse.ArgumentParser(
        description="Build a Google Slides presentation from a YAML/JSON spec.")
    ap.add_argument("spec", help="deck spec (.yaml/.yml/.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print batchUpdate JSON without sending")
    ap.add_argument("--update", metavar="PRES_ID",
                    help="rebuild into this existing presentation (URL kept) "
                         "instead of creating a new one")
    ap.add_argument("--slides", metavar="N,M",
                    help="with --update: rebuild only these 1-based spec "
                         "positions; the deck must have one slide per spec entry")
    ap.add_argument("--thumbs", metavar="DIR",
                    help="after building, save per-slide thumbnails to DIR "
                         "(only the rebuilt ones with --slides) and a contact "
                         "sheet DIR/sheet.png when ImageMagick is installed")
    args = ap.parse_args()

    spec = load_spec(os.path.abspath(args.spec))
    brand = spec.get("brand", {})
    title = spec.get("title", "Untitled")
    slides = spec.get("slides", [])
    styles = spec.get("styles", {})
    template_id = spec.get("template_id")

    if not slides:
        print("No slides in spec", file=sys.stderr)
        sys.exit(1)
    if args.slides and not args.update:
        ap.error("--slides needs --update PRES_ID")
    targets = parse_positions(args.slides, len(slides)) if args.slides else None

    # -----------------------------------------------------------------------
    # Phase 0: Create, copy, or open the presentation
    # -----------------------------------------------------------------------
    page_size = DEFAULT_PAGE_SIZE
    layout_phs = {}
    if args.update:
        pres_id = args.update
        ID_PREFIX = run_prefix()
        print(f"Updating presentation: {pres_id}")
        found, layout_phs, existing_slides, page_size = discover_layouts(pres_id)
        if not existing_slides and not found:
            print(f"Cannot read presentation {pres_id}", file=sys.stderr)
            sys.exit(1)
        # A deck built from scratch still carries the default p2..p12 layouts.
        layout_map = found if template_id else {**found, **DEFAULT_LAYOUT_MAP}
        if targets and len(existing_slides) != len(slides):
            print(f"--slides: the deck has {len(existing_slides)} slides but "
                  f"the spec has {len(slides)}, so positions do not line up. "
                  "Run --update without --slides to rebuild every slide.",
                  file=sys.stderr)
            sys.exit(1)
    elif template_id:
        print(f"Copying template: {template_id}")
        if args.dry_run:
            pres_id = "DRY_RUN_ID"
            layout_map = {}
            existing_slides = []
        else:
            pres_id = copy_template(template_id, title)
            print(f"  Copied as: {pres_id}")
            layout_map, layout_phs, existing_slides, page_size = \
                discover_layouts(pres_id)
            print(f"  Layouts: {len(layout_map)}, "
                  f"Sample slides to strip: {len(existing_slides)}")
    else:
        print(f"Creating presentation: {title}")
        if args.dry_run:
            pres_id = "DRY_RUN_ID"
        else:
            pres_id = create_presentation(title)
        layout_map = dict(DEFAULT_LAYOUT_MAP)
        existing_slides = ["p"]  # default blank slide
    print(f"  ID: {pres_id}  page: {page_size[0]:.3f}in x {page_size[1]:.3f}in")

    slide_ids = [oid(f"slide_{i + 1:02d}") for i in range(len(slides))]
    layout_ids = [layout_map.get(sl.get("layout", "BLANK"),
                                 sl.get("layout", "BLANK")) for sl in slides]
    build_idx = (range(len(slides)) if targets is None
                 else [t - 1 for t in targets])

    # -----------------------------------------------------------------------
    # Phase 1: Create new slides, then delete the ones they replace
    # -----------------------------------------------------------------------
    phase1_requests = slide_requests(slide_ids, layout_ids, existing_slides,
                                     targets)
    if args.dry_run:
        print("\n=== Phase 1 (create slides + strip replaced) ===")
        print(json.dumps({"requests": phase1_requests}, indent=2,
                         ensure_ascii=False))
    else:
        print(f"  Creating {len(build_idx)} slides, "
              f"removing {len(existing_slides) if targets is None else len(targets)}...")
        batch_update(pres_id, phase1_requests)

    # -----------------------------------------------------------------------
    # Phase 2: Discover placeholder IDs → insert content
    # -----------------------------------------------------------------------
    if args.dry_run:
        print("\n(skipping placeholder ID discovery in dry-run)")
        placeholder_map = {}
    else:
        placeholder_map = get_placeholder_ids(pres_id)

    counter = [0]
    phase2_requests = []
    for i in build_idx:
        sl = slides[i]
        ops = sl.get("do", [])
        if not ops:
            continue
        reqs = process_slide_ops(slide_ids[i], sl.get("layout", "BLANK"), ops,
                                 placeholder_map, brand, counter,
                                 layout_phs=layout_phs if template_id
                                 else None,
                                 styles=styles)
        phase2_requests.extend(reqs)

    if args.dry_run:
        print("\n=== Phase 2 (content + styling) ===")
        print(json.dumps({"requests": phase2_requests}, indent=2,
                         ensure_ascii=False))
    else:
        if phase2_requests:
            print(f"  Inserting content ({len(phase2_requests)} operations)...")
            batch_update(pres_id, phase2_requests)

    # -----------------------------------------------------------------------
    # Phase 3: Page numbers (optional)
    # -----------------------------------------------------------------------
    page_numbers_config = spec.get("page_numbers")
    if page_numbers_config:
        phase3_requests = build_page_numbers(
            slide_ids, page_numbers_config, brand, page_size,
            only=None if targets is None else set(build_idx))
        if args.dry_run:
            print("\n=== Phase 3 (page numbers) ===")
            print(json.dumps({"requests": phase3_requests}, indent=2,
                             ensure_ascii=False))
        else:
            if phase3_requests:
                print(f"  Adding page numbers "
                      f"({len(phase3_requests)} operations)...")
                batch_update(pres_id, phase3_requests)

    url = f"https://docs.google.com/presentation/d/{pres_id}/edit"

    # -----------------------------------------------------------------------
    # Phase 4: Thumbnails for visual QA (optional)
    # -----------------------------------------------------------------------
    if args.thumbs and not args.dry_run:
        print(f"  Fetching thumbnails into {args.thumbs} ...")
        paths = thumbnails(pres_id, args.thumbs, positions=targets)
        sheet = contact_sheet(paths, os.path.join(args.thumbs, "sheet.png"))
        print(f"  {len(paths)} thumbnails" +
              (f", contact sheet: {sheet}" if sheet else
               " (no contact sheet: ImageMagick `montage` not found)"))

    print(f"\nDone: {url}")
    return url


if __name__ == "__main__":
    main()
