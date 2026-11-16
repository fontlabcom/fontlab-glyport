# this_file: realuse/oracles/s-italic-bowtie.py
"""Italic Bowtie (morisawausa--Glyphs-Scripts/Italic Bowtie.py:167-188, 223-233,
317-364), Italicize with the defaults: the angle comes from the selected master's
italic angle (the harness sets Regular's to 10 degrees first), origin "1/2
x-height" (478), paths and anchors on, components off, no bowtie/reference. The
selected layer is shifted by -round(tan(angle) * 478 / 2) and skewed by the
angle: x' = x + y * tan(10 deg) + offset, y unchanged, for every node and anchor;
width unchanged. Only A/Regular changes (its layer colour may also be set)."""

import math

from realuse_oracle import Pt, anchors, close, contours, set_contours

ANGLE = 10.0
X_HEIGHT = 478


def slant(x, y):
    offset = -round(math.tan(math.radians(ANGLE)) * X_HEIGHT / 2)
    return x + y * math.tan(math.radians(ANGLE)) + offset, y


def check(o):
    before, after = contours(o.lb("A")), contours(o.la("A"))
    want = [[slant(p.x, p.y) for p in c] for c in before]
    got = [[(p.x, p.y) for p in c] for c in after]
    o.clause(
        "A/Regular: every node slanted by 10 deg around half the x-height (+-1)",
        len(got) == len(want)
        and all(
            len(a) == len(b)
            and all(close(x, u, 1) and close(y, v, 1) for (x, y), (u, v) in zip(a, b))
            for a, b in zip(got, want)
        ),
        {"want": [[(round(x), y) for x, y in c] for c in want], "got": got},
    )
    ab, aa = anchors(o.lb("A")), anchors(o.la("A"))
    o.clause(
        "A/Regular: anchors slanted the same way",
        ab.keys() == aa.keys()
        and all(
            close(aa[k][0], slant(*ab[k])[0], 1) and aa[k][1] == ab[k][1] for k in ab
        ),
        {"before": ab, "after": aa},
    )
    o.clause(
        "A/Regular: width unchanged",
        o.la("A").get("advanceWidth") == o.lb("A").get("advanceWidth"),
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"} | o.composites_follow("A"))


def example(o):
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(*slant(p.x, p.y), p.on) for p in c] for c in contours(layer)]
    )
    for a in layer["anchors"]:
        x, y = (float(v) for v in a["point"].split())
        a["point"] = f"{slant(x, y)[0]:.2f} {y:g}"
    layer["color"] = "#c5a6ff"


def colour_only(o):  # angle 0 or a swallowed exception: only the colour changes
    o.edit_layer("A")["color"] = "#c5a6ff"


def paths_only(o):
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(*slant(p.x, p.y), p.on) for p in c] for c in contours(layer)]
    )


COUNTEREXAMPLES = [colour_only, paths_only]
