# this_file: realuse/oracles/p-dottype.py
"""Dot Type filter (TheJonassss--DotType/DotType.glyphsFilter/.../plugin.py:
filter, _make_dot), Filter menu, Apply with the dialog defaults: round dots, size
22, margin 8 (spacing 30), offsets 0, no gradient, no grid, original not kept;
no master overrides the size, so every master uses those values. A dot is
centred at (30 col, 30 row + 11) wherever that point lies inside the outline of
A/Regular; the outline is then replaced by the dots, each a 4-segment circle of
radius 11. Expected: A/Regular holds exactly those circles (centres on the
outline's edge may go either way), nothing else changes."""

import math

from realuse_oracle import Pt, bounds, contours, on_outline, set_contours

SPACING, HALF = 30, 11


def inside(x, y, polygons):
    hits = 0
    for poly in polygons:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a.y > y) != (b.y > y) and x < a.x + (y - a.y) * (b.x - a.x) / (
                b.y - a.y
            ):
                hits += 1
    return hits % 2 == 1


def grid(src):
    x0, y0, x1, y1 = bounds([p for c in src for p in c])
    found = set()
    for row in range(
        math.floor((y0 - HALF) / SPACING), math.ceil((y1 - HALF) / SPACING) + 1
    ):
        for col in range(math.floor(x0 / SPACING), math.ceil(x1 / SPACING) + 1):
            x, y = col * SPACING, row * SPACING + HALF
            if inside(x, y, src):
                found.add((x, y))
    return found


def centre(c):
    on = [p for p in c if p.on]
    return round(sum(p.x for p in on) / len(on), 1), round(
        sum(p.y for p in on) / len(on), 1
    )


def is_circle(c, x, y):
    on = [p for p in c if p.on]
    return (
        len(c) == 12
        and len(on) == 4
        and all(abs(math.dist((p.x, p.y), (x, y)) - HALF) <= 0.5 for p in on)
    )


def check(o):
    src, new = contours(o.lb("A")), contours(o.la("A"))
    want = grid(src)
    got = {centre(c) for c in new if c}
    edge = {p for p in want ^ got if on_outline(p[0], p[1], src, 0.5)}
    o.clause(
        f"A/Regular: one dot per grid point inside A ({len(want)})",
        (want ^ got) <= edge,
        {"missing": sorted(want - got)[:5], "extra": sorted(got - want)[:5]},
    )
    o.clause(
        "every dot is a circle of radius 11",
        bool(new) and all(is_circle(c, *centre(c)) for c in new),
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def circle(x, y, h=HALF):
    k = h * 0.5522847498
    return [
        Pt(x, y + h),
        Pt(x + k, y + h, False),
        Pt(x + h, y + k, False),
        Pt(x + h, y),
        Pt(x + h, y - k, False),
        Pt(x + k, y - h, False),
        Pt(x, y - h),
        Pt(x - k, y - h, False),
        Pt(x - h, y - k, False),
        Pt(x - h, y),
        Pt(x - h, y + k, False),
        Pt(x - k, y + h, False),
    ]


def example(o):
    layer = o.edit_layer("A")
    set_contours(layer, [circle(x, y) for x, y in sorted(grid(contours(layer)))])


def unchanged(o):
    pass


def kept_outline(o):  # original paths kept as well (keepOrigin)
    layer = o.edit_layer("A")
    src = contours(layer)
    set_contours(layer, [circle(x, y) for x, y in sorted(grid(src))] + src)


COUNTEREXAMPLES = [unchanged, kept_outline]
