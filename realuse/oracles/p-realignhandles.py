# this_file: realuse/oracles/p-realignhandles.py
"""Realign Handles filter (mekkablue--RealignHandles/RealignHandles.glyphsFilter/
.../plugin.py: straightenBCPs), Filter menu, no modifier (current layer only).
The harness tilts one handle of a smooth extreme of O/Regular by +15 in y first.
For every smooth node between two handles where one handle is horizontal or
vertical, the other handle is turned onto that line (its length kept);
otherwise the node moves onto the line between its handles. Expected: every
smooth on-curve node of O/Regular is collinear with its two handles again, the
tilted handle is back on the horizontal through its node with its distance to
the node unchanged, and only O/Regular changes."""

import math

from realuse_oracle import Pt, contours, set_contours

GLYPH = "O"
CONTEXT = {"current": [[GLYPH, "Regular"]], "tab": GLYPH}


def misaligned(contour, tolerance=0.5):
    bad = []
    for i, node in enumerate(contour):
        nxt, prv = contour[(i + 1) % len(contour)], contour[i - 1]
        if node.on and node.smooth and not nxt.on and not prv.on:
            cross = (nxt.x - node.x) * (prv.y - node.y) - (nxt.y - node.y) * (
                prv.x - node.x
            )
            if (
                abs(cross) / max(1e-9, math.dist((nxt.x, nxt.y), (prv.x, prv.y)))
                > tolerance
            ):
                bad.append(i)
    return bad


def tilted(contours_):
    """The prepared handle: first off-curve after a smooth on-curve, +15 in y."""
    c = [list(x) for x in contours_]
    for i, p in enumerate(c[0]):
        if not p.on and c[0][i - 1].on and c[0][i - 1].smooth:
            c[0][i] = Pt(p.x, p.y + 15, False)
            return c, i
    return c, None


def check(o):
    before, after = contours(o.lb(GLYPH)), contours(o.la(GLYPH))
    o.clause(
        "a handle was tilted before the run",
        any(misaligned(c) for c in before),
        [misaligned(c) for c in before],
    )
    o.clause(
        f"{GLYPH}/Regular: every smooth node collinear with its handles",
        bool(after) and not any(misaligned(c) for c in after),
        [misaligned(c) for c in after],
    )
    tilt = next(
        (
            i
            for i, p in enumerate(before[0] if before else [])
            if not p.on
            and before[0][i - 1].on
            and before[0][i - 1].smooth
            and abs(p.y - before[0][i - 1].y) > 1
        ),
        None,
    )
    if tilt is not None and after and len(after[0]) == len(before[0]):
        node, p, q = before[0][tilt - 1], before[0][tilt], after[0][tilt]
        o.clause(
            "the tilted handle is horizontal again, same distance to its node",
            abs(q.y - node.y) <= 0.5
            and abs(
                math.dist((q.x, q.y), (node.x, node.y))
                - math.dist((p.x, p.y), (node.x, node.y))
            )
            <= 0.5,
            {"before": (p.x, p.y), "after": (q.x, q.y)},
        )
    o.only_layer_changed(GLYPH)
    o.nothing_else_changed({GLYPH})


def prepared(o):
    for vfj in (o.before, o.after):
        from realuse_oracle import layers

        layer = layers(vfj, GLYPH)["Regular"]
        new, _ = tilted(contours(layer))
        set_contours(layer, new)


def example(o):
    prepared(o)
    layer = o.edit_layer(GLYPH)
    c = [list(x) for x in contours(layer)]
    _, i = tilted(contours(layer))
    node, p = c[0][i - 1], c[0][i]
    length = math.dist((p.x, p.y), (node.x, node.y))
    c[0][i] = Pt(node.x + math.copysign(length, p.x - node.x), node.y, False)
    set_contours(layer, c)


def unchanged(o):
    prepared(o)


COUNTEREXAMPLES = [unchanged]
