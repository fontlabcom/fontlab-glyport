# this_file: realuse/oracles/s-change-x-height-script.py
"""Change X-Height (filipenegrao--glyphsapp-scripts/in_progress/
change-x-height-script.py:178-191), an unfinished script. For the selected layer
A/Regular it draws two "safe zone" rectangles into the layer's background: a
horizontal band 20 units around the two on-curve heights closest to half the
glyph's width (A: 299 -> y 279..319, from x 0 to the first layer's width, 554),
and a vertical band from the descender to the ascender (-235..765) between the
on-curve x closest to half of the first master's x-height (239: 246 -> 226) and
the next closest (196 -> 216). Its last statement registers an undefined
callback, so Glyphs stops there with a NameError (corpus defect). Expected: the
two rectangles in A/Regular's background (FontLab mask layer), the foreground and
the rest of the font unchanged, and that NameError at line 191."""

from realuse_oracle import Pt, bounds, contours, layers, set_contours

BANDS = [(0, 279, 554, 319), (216, -235, 226, 765)]


def mask(o):
    found = layers(o.after, "A")
    name = next((n for n in found if n.startswith("mask") and o.layer in n), None)
    return found.get(name) if name else None


def check(o):
    shapes = sorted(
        bounds(c) for c in contours(mask(o)) if len(c) == 4 and all(p.on for p in c)
    )
    o.clause(
        "A/Regular background: the two safe-zone rectangles",
        shapes == sorted(BANDS),
        {
            "mask": [n for n in layers(o.after, "A") if n.startswith("mask")],
            "rects": shapes,
        },
    )
    o.clause(
        "A/Regular foreground unchanged", contours(o.la("A")) == contours(o.lb("A"))
    )
    run = o.extra.get("run", {})
    o.clause(
        "stops like Glyphs: NameError for the undefined callback at line 191",
        run.get("error") == "NameError"
        and any("change-x-height-script.py:191" in f for f in run.get("frames", [])),
        {k: run.get(k) for k in ("error", "message", "frames")},
    )
    o.nothing_else_changed({"A"})


def example(o):
    rects = [
        [Pt(x0, y0), Pt(x0, y1), Pt(x1, y1), Pt(x1, y0)] for x0, y0, x1, y1 in BANDS
    ]
    layer = {"name": "mask.Regular", "elements": []}
    set_contours(layer, rects)
    o.after_glyph("A")["layers"].append(layer)
    o.extra = {
        "run": {
            "error": "NameError",
            "frames": ["change-x-height-script.py:191 in <module>"],
        }
    }


def background_unsupported(o):  # round 3: GSLayer.background missing, nothing drawn
    o.extra = {
        "run": {
            "error": "UnsupportedAttribute",
            "frames": ["change-x-height-script.py:183"],
        }
    }


def drawn_in_foreground(o):
    layer = o.edit_layer("A")
    set_contours(
        layer, contours(layer) + [[Pt(0, 279), Pt(0, 319), Pt(554, 319), Pt(554, 279)]]
    )
    o.extra = {
        "run": {
            "error": "NameError",
            "frames": ["change-x-height-script.py:191 in <module>"],
        }
    }


COUNTEREXAMPLES = [background_unsupported, drawn_in_foreground]
