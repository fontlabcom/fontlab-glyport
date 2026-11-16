# this_file: realuse/oracles/p-greenharmony.py
"""Green Harmony filter (slobzheninov--GreenHarmony/GreenHarmony.glyphsFilter/
.../plugin.py: harmonize, filter), Filter menu, no selection, no modifier key:
every smooth on-curve node of the shown layer that sits between two off-curve
handles is moved along the line between those handles to the "harmonic"
position: with I the intersection of the lines through the outer handle pairs,
r0 = |NN-N| / |N-I|, r1 = |I-P| / |P-PP|, t = sqrt(r0 r1) / (sqrt(r0 r1) + 1),
node = N + t (P - N). Handles never move. The target shows "S" (asymmetric
curves, so several nodes really move). Expected: S/Regular's nodes equal that
computation (+-0.5), all handles unchanged, other masters and glyphs unchanged."""

import math

from realuse_oracle import Pt, close, contours, set_contours

GLYPH = "S"
CONTEXT = {"current": [[GLYPH, "Regular"]], "tab": GLYPH}


def intersect(a, b, c, d):
    den = (a.x - b.x) * (c.y - d.y) - (a.y - b.y) * (c.x - d.x)
    if den == 0:
        return None
    u = a.x * b.y - a.y * b.x
    v = c.x * d.y - c.y * d.x
    return Pt(
        (u * (c.x - d.x) - (a.x - b.x) * v) / den,
        (u * (c.y - d.y) - (a.y - b.y) * v) / den,
    )


def harmonized(contour):
    out = list(contour)
    n = len(contour)
    for i, node in enumerate(contour):
        nxt, prv = contour[(i + 1) % n], contour[i - 1]
        if not (node.on and node.smooth and not nxt.on and not prv.on):
            continue
        nn, pp = contour[(i + 2) % n], contour[i - 2]
        cross = intersect(nxt, nn, prv, pp)
        if (
            cross is None
            or math.dist((nxt.x, nxt.y), (cross.x, cross.y)) == 0
            or math.dist((prv.x, prv.y), (pp.x, pp.y)) == 0
        ):
            continue
        r0 = math.dist((nn.x, nn.y), (nxt.x, nxt.y)) / math.dist(
            (nxt.x, nxt.y), (cross.x, cross.y)
        )
        r1 = math.dist((cross.x, cross.y), (prv.x, prv.y)) / math.dist(
            (prv.x, prv.y), (pp.x, pp.y)
        )
        ratio = math.sqrt(r0 * r1)
        t = ratio / (ratio + 1)
        out[i] = Pt(
            nxt.x + t * (prv.x - nxt.x), nxt.y + t * (prv.y - nxt.y), True, True
        )
    return out


def check(o):
    want = [harmonized(c) for c in contours(o.lb(GLYPH))]
    got = contours(o.la(GLYPH))
    ok = len(got) == len(want) and all(
        len(a) == len(b)
        and all(close(p.x, q.x) and close(p.y, q.y) for p, q in zip(a, b))
        for a, b in zip(got, want)
    )
    o.clause(
        f"{GLYPH}/Regular: smooth nodes moved to their harmonic positions, handles kept",
        ok,
        {"want": [[(round(p.x, 1), round(p.y, 1)) for p in c] for c in want][:2]},
    )
    moved = sum(
        1
        for a, b in zip(want, contours(o.lb(GLYPH)))
        for p, q in zip(a, b)
        if not (close(p.x, q.x) and close(p.y, q.y))
    )
    o.clause(
        f"{GLYPH}: the computation moves nodes (the target is not a no-op)",
        moved > 0,
        moved,
    )
    o.only_layer_changed(GLYPH)
    o.nothing_else_changed({GLYPH})


def example(o):
    layer = o.edit_layer(GLYPH)
    set_contours(layer, [harmonized(c) for c in contours(layer)])


def unchanged(o):
    pass


def handles_moved(o):
    example(o)
    layer = o.edit_layer(GLYPH)
    set_contours(
        layer,
        [
            [Pt(p.x + (0 if p.on else 3), p.y, p.on, p.smooth) for p in c]
            for c in contours(layer)
        ],
    )


COUNTEREXAMPLES = [unchanged, handles_moved]
