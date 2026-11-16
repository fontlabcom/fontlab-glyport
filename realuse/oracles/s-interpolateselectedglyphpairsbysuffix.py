# this_file: realuse/oracles/s-interpolateselectedglyphpairsbysuffix.py
"""Interpolate Selected Glyph Pairs By Suffix (naipefoundry--Naipe-Foundry-Glyphs-
Scripts/InterpolateSelectedGlyphPairsBySuffix.py:277-329, 501-560), defaults
source suffix .ss01, output .ss02, factor 50. The harness adds A.ss01 (A moved
right by 100, width +100, in every master) and selects A and A.ss01 in the font
view. Interpolate pairs A with A.ss01 and creates A.ss02 with, per master, the
50% blend of paths, anchors and width: A moved right by 50, width +50. A and
A.ss01 stay as they were; nothing else changes."""

import copy

from realuse_oracle import (
    Pt,
    anchors,
    close,
    contours,
    glyph_record,
    layers,
    set_contours,
)

SHIFT = 100


def blend(o, master, t=0.5):
    a, b = layers(o.before, "A")[master], layers(o.before, "A.ss01")[master]
    pts = [
        [Pt(p.x + t * (q.x - p.x), p.y + t * (q.y - p.y), p.on) for p, q in zip(c, d)]
        for c, d in zip(contours(a), contours(b))
    ]
    anc = {
        k: (v[0] + t * (anchors(b)[k][0] - v[0]), v[1]) for k, v in anchors(a).items()
    }
    width = a["advanceWidth"] + t * (b["advanceWidth"] - a["advanceWidth"])
    return pts, anc, width


def check(o):
    if not o.clause(
        "A.ss01 was prepared before the run",
        glyph_record(o.before, "A.ss01") is not None,
    ):
        return
    o.clause(
        "A.ss02 created",
        glyph_record(o.before, "A.ss02") is None
        and glyph_record(o.after, "A.ss02") is not None,
    )
    for master in ("Light", "Regular", "Bold"):
        got = layers(o.after, "A.ss02").get(master)
        pts, anc, width = blend(o, master)
        o.clause(
            f"A.ss02/{master}: 50% blend of A and A.ss01 (paths, anchors, width)",
            got is not None
            and [[(round(p.x, 1), p.y) for p in c] for c in contours(got)]
            == [[(round(p.x, 1), p.y) for p in c] for c in pts]
            and anchors(got).keys() == anc.keys()
            and all(close(anchors(got)[k][0], anc[k][0]) for k in anc)
            and close(float(got.get("advanceWidth", 0)), width),
            {
                "width": None if got is None else got.get("advanceWidth"),
                "want_width": width,
            },
        )
    o.nothing_else_changed({"A.ss02"}, font={"glyphsCount"})  # the new glyph counts


def prepared(o):
    for vfj in (o.before, o.after):
        variant = copy.deepcopy(glyph_record(vfj, "A"))
        variant["name"] = "A.ss01"
        variant.pop("unicode", None)
        for layer in variant["layers"]:
            set_contours(
                layer,
                [[Pt(p.x + SHIFT, p.y, p.on) for p in c] for c in contours(layer)],
            )
            for a in layer.get("anchors", []):
                x, y = a["point"].split()
                a["point"] = f"{float(x) + SHIFT:g} {y}"
            layer["advanceWidth"] += SHIFT
        vfj["font"]["glyphs"].append(variant)


def example(o):
    prepared(o)
    new = {"name": "A.ss02", "layers": []}
    for master in ("Light", "Regular", "Bold"):
        pts, anc, width = blend(o, master)
        layer = {
            "name": master,
            "advanceWidth": width,
            "anchors": [
                {"name": k, "point": f"{x:g} {y:g}"} for k, (x, y) in anc.items()
            ],
        }
        set_contours(layer, pts)
        new["layers"].append(layer)
    o.after["font"]["glyphs"].append(new)


def nothing_created(o):
    prepared(o)


def copied_not_blended(o):
    prepared(o)
    new = copy.deepcopy(glyph_record(o.after, "A.ss01"))
    new["name"] = "A.ss02"
    o.after["font"]["glyphs"].append(new)


COUNTEREXAMPLES = [nothing_created, copied_not_blended]
