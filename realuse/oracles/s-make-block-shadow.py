# this_file: realuse/oracles/s-make-block-shadow.py
"""Make Block Shadow (harbortype--glyphs-scripts/Paths/Make Block Shadow.py: Main),
defaults angle -45, distance 100, on the selected layer A/Regular. The script
finds the outline's extremes along the shadow direction, doubles each of them and
moves the run of nodes between paired extremes by (cos, sin)(-45 deg) * 100 =
(+70.71, -70.71), then rounds coordinates: each path becomes the block extrusion
of itself. Expected: every node of A/Regular is either an original node or an
original moved by (71, -71) (+-1), both kinds occur, each path gained an even
number (>= 2) of nodes, and the bounds grow to (13, -71, 656, 688). Only
A/Regular changes."""

import math

from realuse_oracle import Pt, bounds, close, contours, set_contours

D = 100 * math.cos(math.radians(45))


def check(o):
    before, after = contours(o.lb("A")), contours(o.la("A"))
    old = {(p.x, p.y) for c in before for p in c}
    moved = {(x + D, y - D) for x, y in old}

    def near(p, pool):
        return any(close(p.x, x, 1) and close(p.y, y, 1) for x, y in pool)

    pts = [p for c in after for p in c]
    o.clause("A/Regular: same number of paths", len(after) == len(before))
    o.clause(
        "A/Regular: every node is an original or an original shifted by (71, -71)",
        bool(pts) and all(near(p, old) or near(p, moved) for p in pts),
        [(p.x, p.y) for p in pts if not (near(p, old) or near(p, moved))][:10],
    )
    o.clause(
        "A/Regular: some nodes shifted, some kept",
        any(near(p, moved) and not near(p, old) for p in pts)
        and any(near(p, old) for p in pts),
    )
    o.clause(
        "A/Regular: each path gained an even number (>= 2) of nodes",
        len(after) == len(before)
        and all(
            len(a) - len(b) >= 2 and (len(a) - len(b)) % 2 == 0
            for a, b in zip(after, before)
        ),
        [len(c) for c in after],
    )
    box = bounds(pts)
    o.clause(
        "A/Regular: bounds (13, -71, 656, 688) +-1",
        box is not None
        and all(close(a, b, 1) for a, b in zip(box, (13, -71, 656, 688))),
        box,
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    # A's outer path: the extrusion inserts doubled extremes at (13,0) and
    # (352,688)... drawn by hand as the union outline of A and its shadow.
    d = round(D)
    outer = [
        Pt(13, 0),
        Pt(13 + d, -d),
        Pt(100 + d, -d),
        Pt(173 + d, 227 - d),
        Pt(422, 227),
        Pt(495, 0),
        Pt(495 + d, -d),
        Pt(585 + d, -d),
        Pt(352 + d, 688 - d),
        Pt(352, 688),
        Pt(246, 688),
        Pt(246, 688),
    ]
    counter = [
        Pt(196, 299),
        Pt(297, 615),
        Pt(297 + d, 615 - d),
        Pt(399 + d, 299 - d),
        Pt(399, 299),
    ]
    set_contours(o.edit_layer("A"), [outer, counter])


def unchanged(o):
    pass


def translated(o):  # the whole outline moved instead of extruded
    layer = o.edit_layer("A")
    set_contours(layer, [[Pt(p.x + D, p.y - D) for p in c] for c in contours(layer)])


COUNTEREXAMPLES = [unchanged, translated]
