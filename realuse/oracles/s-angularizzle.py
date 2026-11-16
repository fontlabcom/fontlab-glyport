# this_file: realuse/oracles/s-angularizzle.py
"""Angularizzle (NaN-xyz--GlyphsApp-Scripts/Angularizzle/Angularizzle.py:
MainAngela, ListToPath), Process with the defaults (min plane 80, keep detail).
With one glyph selected the script samples the selected layer's paths taken at
start-up (A/Regular) into straight segments about 80 units long and writes them,
as line-only paths, into the glyph's FIRST layer (layers[0] = Light, as written)
after clearing it. Expected: A/Light has two closed line-only paths whose nodes
all lie on A/Regular's outline, more nodes than A/Regular had, and A/Regular's
bounds; A/Regular and A/Bold unchanged; nothing else changes."""

import math

from realuse_oracle import Pt, bounds, close, contours, points, set_contours


def on_outline(p, paths, tolerance=1.5):
    for c in paths:
        for a, b in zip(c, c[1:] + c[:1]):
            dx, dy = b.x - a.x, b.y - a.y
            t = (
                0.0
                if dx == dy == 0
                else max(
                    0.0,
                    min(
                        1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)
                    ),
                )
            )
            if math.hypot(a.x + t * dx - p.x, a.y + t * dy - p.y) <= tolerance:
                return True
    return False


def check(o):
    src, new = contours(o.lb("A", "Regular")), contours(o.la("A", "Light"))
    pts = [p for c in new for p in c]
    o.clause(
        "A/Light: two line-only paths",
        len(new) == 2 and all(p.on for p in pts),
        [len(c) for c in new],
    )
    o.clause(
        "A/Light: every node lies on A/Regular's outline",
        bool(pts) and all(on_outline(p, src) for p in pts),
        [(p.x, p.y) for p in pts if not on_outline(p, src)][:10],
    )
    o.clause(
        "A/Light: subdivided (more nodes than A/Regular)",
        len(pts) > len(points(o.lb("A", "Regular"))),
    )
    b0, b1 = bounds(points(o.lb("A", "Regular"))), bounds(pts)
    o.clause(
        "A/Light: A/Regular's bounds (+-2)",
        b1 is not None and all(close(a, b, 2) for a, b in zip(b0, b1)),
        {"want": b0, "got": b1},
    )
    o.only_layer_changed("A", "Light")
    o.nothing_else_changed({"A"})


def subdivide(c, step=80):
    out = []
    for a, b in zip(c, c[1:] + c[:1]):
        n = max(1, math.ceil(math.hypot(b.x - a.x, b.y - a.y) / step))
        out += [
            Pt(a.x + (b.x - a.x) * i / n, a.y + (b.y - a.y) * i / n) for i in range(n)
        ]
    return out


def example(o):
    set_contours(
        o.edit_layer("A", "Light"),
        [subdivide(c) for c in contours(o.lb("A", "Regular"))],
    )


def unchanged(o):
    pass


def into_regular(o):  # the "obvious" target, not what the script does
    set_contours(
        o.edit_layer("A", "Regular"),
        [subdivide(c) for c in contours(o.lb("A", "Regular"))],
    )


COUNTEREXAMPLES = [unchanged, into_regular]
