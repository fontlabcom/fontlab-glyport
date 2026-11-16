# this_file: realuse/oracles/s-align-selected-nodes-to-guide-intersecti.py
"""Align Selected Nodes to Guide Intersections (danielgamage--Glyphs-Scripts/
Nodes/Align Selected Nodes to Guide Intersections.py): intersects every pair of
the current master's global guides and moves each selected node to the nearest
intersection. Regular has a horizontal guide at y 250; the harness adds a
vertical one at x 300 and a horizontal one at y 600, so the intersections are
(300, 250) and (300, 600). Every node of A/Regular is selected. Expected: each
node sits on the intersection nearest to its old position; nothing else moves."""

import math

from realuse_oracle import contours

POINTS = [(300.0, 250.0), (300.0, 600.0)]


def nearest(p):
    return min(POINTS, key=lambda q: math.hypot(q[0] - p.x, q[1] - p.y))


def check(o):
    want = [[nearest(p) for p in c] for c in contours(o.lb("A"))]
    got = [[(p.x, p.y) for p in c] for c in contours(o.la("A"))]
    o.clause(
        "A/Regular: every node moved to its nearest guide intersection",
        got == want,
        {"after": got},
    )
    o.only_layer_changed("A")
    o.nothing_else_changed(
        {"A"}, font={"masters"}
    )  # the prepared guides live in the master


def example(o):
    from realuse_oracle import Pt, set_contours

    layer = o.edit_layer("A")
    set_contours(layer, [[Pt(*nearest(p)) for p in c] for c in contours(layer)])


def unchanged(o):  # plum-var's own guides are parallel: no intersection at all
    pass


def all_to_one(o):
    from realuse_oracle import Pt, set_contours

    layer = o.edit_layer("A")
    set_contours(layer, [[Pt(300, 250) for p in c] for c in contours(layer)])


COUNTEREXAMPLES = [unchanged, all_to_one]
