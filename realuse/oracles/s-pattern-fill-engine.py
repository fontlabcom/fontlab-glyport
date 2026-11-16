# this_file: realuse/oracles/s-pattern-fill-engine.py
"""Pattern Fill Engine (joseppatau--Tipo-Pepel-Scripts/Creative/Pattern Fill
Engine.py: generate_for_layer, apply), driven: pattern glyph "period", the other
row values at their defaults (scale 100, no rotation, offsets or margins), scope
"Current Glyph", master = current (Regular). The script tiles copies of period's
outline over A's bounds edge to edge, intersects the tiles with A's outline and
replaces A/Regular's paths with the result. Expected: A/Regular now holds many
small paths (more than A's two), every node inside A's bounds (+-1) and on or
inside A's original outline; width unchanged; only A/Regular changes."""

import math

from realuse_oracle import Pt, bounds, contours, points, set_contours


def inside(p, polygons, tolerance=1.0):
    """Even-odd point-in-polygon on A's straight outline, with an edge tolerance."""
    hits = 0
    for poly in polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            dx, dy = b.x - a.x, b.y - a.y
            t = 0.0
            if dx or dy:
                t = max(
                    0.0,
                    min(
                        1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)
                    ),
                )
            if math.hypot(a.x + t * dx - p.x, a.y + t * dy - p.y) <= tolerance:
                return True
            if (a.y > p.y) != (b.y > p.y) and p.x < a.x + (p.y - a.y) * dx / dy:
                hits += 1
    return hits % 2 == 1


def check(o):
    src, new = contours(o.lb("A")), contours(o.la("A"))
    pts = [p for c in new for p in c if p.on]
    o.clause(
        "A/Regular: replaced by many pattern pieces (> 2 paths)", len(new) > 2, len(new)
    )
    x0, y0, x1, y1 = bounds(points(o.lb("A")))
    o.clause(
        "A/Regular: every node within A's bounds",
        bool(pts)
        and all(x0 - 1 <= p.x <= x1 + 1 and y0 - 1 <= p.y <= y1 + 1 for p in pts),
    )
    o.clause(
        "A/Regular: every node on or inside A's outline (clipped)",
        bool(pts) and all(inside(p, src) for p in pts),
        [(p.x, p.y) for p in pts if not inside(p, src)][:10],
    )
    o.clause(
        "A/Regular: width unchanged",
        o.la("A")["advanceWidth"] == o.lb("A")["advanceWidth"],
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def square(x, y, size=20):
    return [Pt(x, y), Pt(x + size, y), Pt(x + size, y + size), Pt(x, y + size)]


def example(o):
    set_contours(
        o.edit_layer("A"),
        [square(x, y) for x, y in ((40, 10), (520, 10), (260, 235), (240, 640))],
    )


def unchanged(o):
    pass


def unclipped(o):  # tiles not intersected with A
    set_contours(
        o.edit_layer("A"),
        [square(x, y) for x in range(0, 600, 60) for y in range(0, 700, 60)],
    )


COUNTEREXAMPLES = [unchanged, unclipped]
