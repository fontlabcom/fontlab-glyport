# this_file: realuse/oracles/s-quadrant-mover-ui.py
"""Quadrant mover (UI) (Ricard-Garcia--TR-Glyphs-Scripts/Paths/Quadrant mover
(UI).py: applyCallback), "Apply to selected layers" with the defaults: angle
0..25 degrees, distance 20..80. For each path of A/Regular it picks a random
distance and angle, moves the path away from the layer's centre along the line
from that centre to the path's centre, then rotates it by the angle around its
new centre; it prints how many paths it moved. Randomised, so the oracle checks
properties: each path is moved rigidly (same nodes, same distances between
them), its centre moved 20..80 units, rotated counter-clockwise by 0..25 deg;
Output "transformed 2 path(s)"; only A/Regular changes."""

import math

from realuse_oracle import Pt, bounds, contours, set_contours


def centre(c):
    x0, y0, x1, y1 = bounds(c)
    return (x0 + x1) / 2, (y0 + y1) / 2


def rigid(a, b):
    return len(a) == len(b) and all(
        abs(math.dist((p.x, p.y), (q.x, q.y)) - math.dist((r.x, r.y), (s.x, s.y)))
        <= 1.5
        for (p, q), (r, s) in zip(zip(a, a[1:] + a[:1]), zip(b, b[1:] + b[:1]))
    )


def turn(a, b):
    """Rotation (degrees) from contour a's first edge to b's."""

    def heading(c):
        return math.degrees(math.atan2(c[1].y - c[0].y, c[1].x - c[0].x))

    return (heading(b) - heading(a) + 180) % 360 - 180


def shift(a, b):
    """The script's shift s: q = R(p - c) + c + s for every node (c = a's bounds
    centre, R = the rotation); None when no single shift explains all nodes."""
    if len(a) != len(b) or len(a) < 2:
        return None
    t = math.radians(turn(a, b))
    cx, cy = centre(a)
    found = [
        (
            q.x - (cx + (p.x - cx) * math.cos(t) - (p.y - cy) * math.sin(t)),
            q.y - (cy + (p.x - cx) * math.sin(t) + (p.y - cy) * math.cos(t)),
        )
        for p, q in zip(a, b)
    ]
    if any(math.dist(found[0], f) > 1.5 for f in found):
        return None
    return math.hypot(*found[0])


def check(o):
    before, after = contours(o.lb("A")), contours(o.la("A"))
    o.clause("A/Regular: same number of paths", len(after) == len(before) == 2)
    for i, (a, b) in enumerate(zip(before, after)):
        moved = shift(a, b)
        o.clause(f"path {i}: moved rigidly", rigid(a, b))
        o.clause(
            f"path {i}: shifted 20..80 units before its rotation (+-2)",
            moved is not None and 18 <= moved <= 82,
            moved,
        )
        o.clause(
            f"path {i}: rotated 0..25 deg counter-clockwise (+-0.5)",
            -0.5 <= turn(a, b) <= 25.5,
            turn(a, b),
        )
    o.clause(
        "Output: 2 paths transformed",
        "Quadrant mover: transformed 2 path(s)." in o.text,
        o.text[-200:],
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def moved(c, dx, dy, deg):
    cx, cy = centre(c)
    cx, cy = cx + dx, cy + dy
    t = math.radians(deg)
    out = []
    for p in c:
        x, y = p.x + dx - cx, p.y + dy - cy
        out.append(
            Pt(
                cx + x * math.cos(t) - y * math.sin(t),
                cy + x * math.sin(t) + y * math.cos(t),
            )
        )
    return out


def example(o):
    layer = o.edit_layer("A")
    outer, counter = contours(layer)
    set_contours(layer, [moved(outer, 0, -30, 10), moved(counter, 0, 50, 20)])
    o.output = ["Quadrant mover: transformed 2 path(s).\nDone!\n"]


def unchanged(o):
    o.output = ["Done!\n"]


def scaled(o):  # not rigid
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(p.x * 1.2, p.y * 1.2 + 40) for p in c] for c in contours(layer)]
    )
    o.output = ["Quadrant mover: transformed 2 path(s).\n"]


COUNTEREXAMPLES = [unchanged, scaled]
