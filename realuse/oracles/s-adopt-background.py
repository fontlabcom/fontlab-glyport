# this_file: realuse/oracles/s-adopt-background.py
"""Adopt Background (justanotherfoundry--freemix-glyphsapp/Adopt Background.py),
with every node selected (curation): each selected node of the current layer takes the position of its
best-matching counterpart in the layer's background; unselected anchors
stay. The harness fills A/Regular's background with A's own outline moved
by (10, 5) before the run. Expected: A/Regular's nodes all moved by (10, 5),
anchors and width unchanged, the background unchanged, nothing else changed."""

from realuse_oracle import Pt, anchors, contours, layers, set_contours

DX, DY = 10, 5


def masks(vfj):
    return {n: la for n, la in layers(vfj, "A").items() if n.startswith("mask")}


def check(o):
    if not o.clause(
        "prepared background exists before the run",
        bool(masks(o.before)),
        sorted(layers(o.before, "A")),
    ):
        return
    want = [[(p.x + DX, p.y + DY) for p in c] for c in contours(o.lb("A"))]
    o.clause(
        "A/Regular: every node adopted its background position (+10, +5)",
        [[(p.x, p.y) for p in c] for c in contours(o.la("A"))] == want,
    )
    o.clause(
        "A/Regular: anchors and width unchanged",
        anchors(o.la("A")) == anchors(o.lb("A"))
        and o.la("A")["advanceWidth"] == o.lb("A")["advanceWidth"],
    )
    o.clause(
        "A/Regular background unchanged",
        {n: contours(la) for n, la in masks(o.after).items()}
        == {n: contours(la) for n, la in masks(o.before).items()},
    )
    o.nothing_else_changed({"A"})


def prepared(o):
    for vfj in (o.before, o.after):
        regular = layers(vfj, "A")["Regular"]
        mask = {"name": "mask.Regular", "elements": []}
        set_contours(
            mask, [[Pt(p.x + DX, p.y + DY, p.on) for p in c] for c in contours(regular)]
        )
        next(g for g in vfj["font"]["glyphs"] if g["name"] == "A")["layers"].append(
            mask
        )


def example(o):
    prepared(o)
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(p.x + DX, p.y + DY, p.on) for p in c] for c in contours(layer)]
    )


def unchanged(o):
    prepared(o)


def no_background(o):
    pass


COUNTEREXAMPLES = [unchanged, no_background]
