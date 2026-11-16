# this_file: realuse/oracles/s-getfromnextfont.py
"""Get from next font (guidoferreyra--Glyphs-Scripts/getFromNextFont.py:60-120),
driven through its window: source font cafe (the other open font), its layer
Regular, "import Anchors" and "import Sidebearings" checked, Import. For the
selected layer A/Regular of plum-var the script copies every anchor of cafe's A
(replacing anchors of the same name, keeping the others) and, as cafe's A has no
metrics keys, sets LSB and RSB to cafe A's values. Only A/Regular changes; the
outline keeps its shape."""

from realuse_oracle import (
    Pt,
    anchors,
    close,
    contours,
    fixture,
    layers,
    set_contours,
    sidebearings,
)


def source():
    return layers(fixture("cafe"), "A")["Regular"]


def expected_anchors(o):
    want = dict(anchors(o.lb("A")))
    want.update(anchors(source()))
    return want


def check(o):
    o.clause(
        "A: anchors = plum-var's, with cafe A's anchors imported by name",
        anchors(o.la("A")) == expected_anchors(o),
        {"after": anchors(o.la("A")), "cafe": anchors(source())},
    )
    want, got = sidebearings(source()), sidebearings(o.la("A"))
    o.clause(
        f"A: LSB, RSB = cafe A's {want}",
        got is not None and close(got[0], want[0]) and close(got[1], want[1]),
        {"before": sidebearings(o.lb("A")), "after": got},
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    layer = o.edit_layer("A")
    layer["anchors"] = [
        {"name": n, "point": f"{x:g} {y:g}"}
        for n, (x, y) in expected_anchors(o).items()
    ]
    (lsb, rsb), (l0, _) = sidebearings(source()), sidebearings(layer)
    pts = [p for c in contours(layer) for p in c]
    width = max(p.x for p in pts) - min(p.x for p in pts)
    set_contours(
        layer,
        [[Pt(p.x + lsb - l0, p.y, p.on, p.smooth) for p in c] for c in contours(layer)],
    )
    layer["advanceWidth"] = lsb + width + rsb


def unchanged(o):  # round 3: Import stayed disabled, nothing imported
    pass


def anchors_only(o):
    o.edit_layer("A")["anchors"] = [
        {"name": n, "point": f"{x:g} {y:g}"}
        for n, (x, y) in expected_anchors(o).items()
    ]


COUNTEREXAMPLES = [unchanged, anchors_only]
