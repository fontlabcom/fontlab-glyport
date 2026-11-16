# this_file: realuse/oracles/p-stitcher.py
"""Stitcher filter (mekkablue--Stitcher/Stitcher.glyphsFilter/.../plugin.py:
process, placeDots, dotCoordsOnPath), Filter menu with its dialog's defaults:
interval 100, component "_circle", no balancing, using the background. The
harness adds the glyph _circle (a 20-unit square around its origin) first. For
A/Regular the paths are copied into the background and removed from the
foreground, then _circle components are placed along each background path: at
its first node and then every time the walked distance reaches 100 units (the
closing duplicate dropped). Expected: A/Regular has no paths, only _circle
components, about perimeter/100 per path, each placed on A's outline; the
background (FontLab mask) holds A's original outline; other glyphs unchanged
(except the prepared _circle)."""

from realuse_oracle import (
    Pt,
    contours,
    layers,
    on_outline,
    perimeter,
    placed,
    same_cycle,
    set_contours,
)


def mask(vfj):
    return next(
        (
            la
            for n, la in layers(vfj, "A").items()
            if n.startswith("mask") and "Regular" in n
        ),
        None,
    )


def check(o):
    src = contours(o.lb("A"))
    dots = placed(o.la("A"))
    o.clause("A/Regular: no paths left in the foreground", not contours(o.la("A")))
    low = sum(int(perimeter(c) // 100) for c in src)
    o.clause(
        f"A/Regular: about {low}..{low + 2 * len(src)} _circle components",
        low <= len(dots) <= low + 2 * len(src) and {d[0] for d in dots} == {"_circle"},
        len(dots),
    )
    o.clause(
        "every component sits on A's outline",
        bool(dots) and all(on_outline(x, y, src) for _, x, y in dots),
        [d for d in dots if not on_outline(d[1], d[2], src)][:5],
    )
    back = contours(mask(o.after))

    def key(c):
        return [(p.x, p.y) for p in c]

    o.clause(
        "A/Regular background holds A's outline",
        len(back) == len(src)
        and all(same_cycle(key(a), key(b)) for a, b in zip(src, back)),
    )
    o.clause(
        "A/Light and A/Bold unchanged", not (o.changed_layers("A") & {"Light", "Bold"})
    )
    o.nothing_else_changed({"A"})


def prepared(o):
    for vfj in (o.before, o.after):
        dot = {"name": "_circle", "layers": []}
        for m in ("Light", "Regular", "Bold"):
            layer = {"name": m, "advanceWidth": 0}
            set_contours(layer, [[Pt(-10, -10), Pt(10, -10), Pt(10, 10), Pt(-10, 10)]])
            dot["layers"].append(layer)
        vfj["font"]["glyphs"].append(dot)


def walk(c, step=100.0):
    import itertools
    import math

    pts, out, left = c + c[:1], [(c[0].x, c[0].y)], step
    for a, b in itertools.pairwise(pts):
        seg = math.dist((a.x, a.y), (b.x, b.y))
        pos = 0.0
        while seg - pos >= left:
            pos += left
            out.append((a.x + (b.x - a.x) * pos / seg, a.y + (b.y - a.y) * pos / seg))
            left = step
        left -= seg - pos
    return out


def example(o):
    prepared(o)
    layer = o.edit_layer("A")
    src = contours(layer)
    layer["elements"] = [
        {
            "component": {"glyphName": "_circle"},
            "transform": {"xOffset": x, "yOffset": y},
        }
        for c in src
        for x, y in walk(c)
    ]
    back = {"name": "mask.Regular", "elements": []}
    set_contours(back, src)
    o.after_glyph("A")["layers"].append(back)


def unchanged(o):
    prepared(o)


def background_only(o):  # outline moved away, nothing placed
    prepared(o)
    back = {"name": "mask.Regular", "elements": []}
    set_contours(back, contours(o.lb("A")))
    o.after_glyph("A")["layers"].append(back)
    o.edit_layer("A")["elements"] = []


COUNTEREXAMPLES = [unchanged, background_only]
