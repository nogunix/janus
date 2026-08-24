#!/usr/bin/env python3
"""Build a Google Slides presentation from a declarative YAML/JSON spec.

Usage:
    python3 build_gslides.py deck.yaml
    python3 build_gslides.py deck.yaml --dry-run

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
import subprocess
import sys
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


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        if path.endswith(".json"):
            return json.load(f)
        import yaml
        return yaml.safe_load(f)


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
    return layout_map, layout_placeholders, slide_ids


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

        if op_name in ("shape", "table", "image"):
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

            text = op_args.get("text", "")
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

            use_autofit = op_args.get("autofit",
                                      op_name in ("body", "subtitle"))
            if use_autofit:
                requests.append({
                    "updateShapeProperties": {
                        "objectId": ph_id,
                        "shapeProperties": {
                            "autofit": {"autofitType": "TEXT_AUTOFIT"}
                        },
                        "fields": "autofit",
                    }
                })

        elif op_name == "table":
            counter[0] += 1
            tbl_id = f"tbl_{counter[0]:03d}"
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
            shape_id = f"shp_{counter[0]:03d}"
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
            text = op_args.get("text", "")
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

            fill = op_args.get("fill")
            if fill:
                requests.append({
                    "updateShapeProperties": {
                        "objectId": shape_id,
                        "shapeProperties": {
                            "shapeBackgroundFill": {
                                "solidFill": {
                                    "color": {"rgbColor": resolve_color(
                                        fill, brand)}
                                }
                            }
                        },
                        "fields": "shapeBackgroundFill",
                    }
                })

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
            img_id = f"img_{counter[0]:03d}"
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

PAGE_NUMBER_POSITIONS = {
    "bottom_left":   (0.22, 7.1),
    "bottom_right":  (9.5, 7.1),
    "bottom_center": (4.8, 7.1),
}


def build_page_numbers(slide_count, config, brand):
    skip_first = config.get("skip_first", True)
    skip_last = config.get("skip_last", False)
    size = config.get("size", 8)
    color = config.get("color", "595959")
    pos_name = config.get("position", "bottom_left")
    xi, yi = PAGE_NUMBER_POSITIONS.get(pos_name,
                                        PAGE_NUMBER_POSITIONS["bottom_left"])
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
        slide_id = f"slide_{slide_num:02d}"
        pn_id = f"pagenum_{slide_num:02d}"
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
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Build a Google Slides presentation from a YAML/JSON spec.")
    ap.add_argument("spec", help="deck spec (.yaml/.yml/.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print batchUpdate JSON without sending")
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

    # -----------------------------------------------------------------------
    # Phase 0: Create or copy presentation
    # -----------------------------------------------------------------------
    if template_id:
        print(f"Copying template: {template_id}")
        if args.dry_run:
            pres_id = "DRY_RUN_ID"
            layout_map = {}
            existing_slides = []
        else:
            pres_id = copy_template(template_id, title)
            print(f"  Copied as: {pres_id}")
            layout_map, layout_phs, existing_slides = discover_layouts(pres_id)
            print(f"  Layouts: {len(layout_map)}, "
                  f"Sample slides to strip: {len(existing_slides)}")
    else:
        print(f"Creating presentation: {title}")
        if args.dry_run:
            pres_id = "DRY_RUN_ID"
        else:
            pres_id = create_presentation(title)
        layout_map = dict(DEFAULT_LAYOUT_MAP)
        layout_phs = {}
        existing_slides = ["p"]  # default blank slide
    print(f"  ID: {pres_id}")

    # -----------------------------------------------------------------------
    # Phase 1: Create new slides, then delete old ones
    # (API requires at least one slide at all times — create first)
    # -----------------------------------------------------------------------
    phase1_requests = []

    # Create new slides first
    for i, sl in enumerate(slides):
        layout_name = sl.get("layout", "BLANK")
        layout_id = layout_map.get(layout_name, layout_name)
        slide_id = f"slide_{i + 1:02d}"
        phase1_requests.append({
            "createSlide": {
                "objectId": slide_id,
                "insertionIndex": i,
                "slideLayoutReference": {"layoutId": layout_id},
            }
        })

    # Then delete all existing (sample) slides
    for sid in existing_slides:
        phase1_requests.append({"deleteObject": {"objectId": sid}})

    if args.dry_run:
        print("\n=== Phase 1 (create slides + strip samples) ===")
        print(json.dumps({"requests": phase1_requests}, indent=2,
                         ensure_ascii=False))
    else:
        n_del = len(existing_slides)
        print(f"  Creating {len(slides)} slides, "
              f"stripping {n_del} samples...")
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
    for i, sl in enumerate(slides):
        layout_name = sl.get("layout", "BLANK")
        slide_id = f"slide_{i + 1:02d}"
        ops = sl.get("do", [])
        if not ops:
            continue
        reqs = process_slide_ops(slide_id, layout_name, ops,
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
        phase3_requests = build_page_numbers(len(slides),
                                              page_numbers_config, brand)
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
    print(f"\nDone: {url}")
    return url


if __name__ == "__main__":
    main()
