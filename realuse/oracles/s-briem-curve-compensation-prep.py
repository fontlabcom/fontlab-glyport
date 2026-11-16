# this_file: realuse/oracles/s-briem-curve-compensation-prep.py
"""Briem curve compensation prep (jpt--font-scripts/Glyphs/Briem curve
compensation prep.py: main). The harness sets Regular's italic angle to 10 first.
For the selected layer A/Regular (x-height 478) the script adds two layers to A:
"Regular Slanted": the outline sheared with the factor radians(10) (as written,
not tan) and shifted by -round(tan(10 deg) * 239) = -42; and "Regular Slanted
and Rotated": sheared with radians(5), shifted by -round(tan(5 deg) * 239) = -21,
then rotated by -5 degrees around (bounds width / 2, bounds height / 2) of
A/Regular = (286, 344). A has no curves, so adding extremes adds nothing. The
master layers stay unchanged; nothing else changes."""

import math

from realuse_oracle import Pt, close, contours, layers, set_contours

SLANTED, ROTATED = "Regular Slanted", "Regular Slanted and Rotated"


def slanted(p):
    return p.x + math.radians(10) * p.y - round(math.tan(math.radians(10)) * 239), p.y


def rotated(p):
    x, y = p.x + math.radians(5) * p.y - round(math.tan(math.radians(5)) * 239), p.y
    a, cx, cy = math.radians(-5), 286, 344
    return (
        cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a),
        cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a),
    )


def matches(layer, f, source):
    got = [[(p.x, p.y) for p in c] for c in contours(layer)]
    want = [[f(p) for p in c] for c in contours(source)]
    return len(got) == len(want) and all(
        len(a) == len(b)
        and all(close(x, u, 1.5) and close(y, v, 1.5) for (x, y), (u, v) in zip(a, b))
        for a, b in zip(got, want)
    )


def check(o):
    found = layers(o.after, "A")
    src = o.lb("A", "Regular")
    o.clause(
        f"A: layer {SLANTED!r} added, sheared radians(10), shifted -42",
        SLANTED in found and matches(found[SLANTED], slanted, src),
        sorted(found),
    )
    o.clause(
        f"A: layer {ROTATED!r} added, sheared radians(5), shifted -21, rotated -5 deg",
        ROTATED in found and matches(found[ROTATED], rotated, src),
    )
    o.clause(
        "A: master layers unchanged",
        o.changed_layers("A") == {SLANTED, ROTATED},
        sorted(o.changed_layers("A")),
    )
    o.nothing_else_changed({"A"})


def add(o, name, f):
    layer = {"name": name, "advanceWidth": o.lb("A", "Regular")["advanceWidth"]}
    set_contours(
        layer, [[Pt(*f(p)) for p in c] for c in contours(o.lb("A", "Regular"))]
    )
    o.after_glyph("A")["layers"].append(layer)


def example(o):
    add(o, SLANTED, slanted)
    add(o, ROTATED, rotated)


def angle_zero(o):  # copies without the italic angle
    add(o, SLANTED, lambda p: (p.x, p.y))
    add(o, ROTATED, lambda p: (p.x, p.y))


def no_rotation(o):
    add(o, SLANTED, slanted)
    add(o, ROTATED, lambda p: (p.x + math.radians(5) * p.y - 21, p.y))


COUNTEREXAMPLES = [angle_zero, no_rotation]
