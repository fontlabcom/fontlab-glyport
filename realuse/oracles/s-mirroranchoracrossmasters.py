# this_file: realuse/oracles/s-mirroranchoracrossmasters.py
"""Mirror Anchor Across Masters (kylewaynebenson--Glyphs-Scripts/Anchors/
MirrorAnchorAcrossMasters.py: mirror_anchor_with_options), anchor "ogonek"
selected on A/Regular, OK with the defaults: Y top, X right, relative to shapes.
The anchor's offset from Regular's top-right bounds corner (585, 688) is
(-13, -688); each other master gets the anchor at its own top-right corner plus
that offset. Expected: ogonek at (519, 0) in A/Light (corner 532, 688) and
(616, 0) in A/Bold (corner 629, 688); A/Regular and all other anchors and
outlines unchanged."""

from realuse_oracle import anchors, bounds, close, points


def expected(o, master):
    ax, ay = anchors(o.lb("A"))["ogonek"]
    _, _, rx, ty = bounds(points(o.lb("A")))
    _, _, mx, my = bounds(points(o.lb("A", master)))
    return mx + (ax - rx), my + (ay - ty)


def check(o):
    for master in ("Light", "Bold"):
        want = expected(o, master)
        got = anchors(o.la("A", master)).get("ogonek")
        o.clause(
            f"A/{master}: ogonek at {want}",
            got is not None and close(got[0], want[0]) and close(got[1], want[1]),
            got,
        )
        others = {k: v for k, v in anchors(o.la("A", master)).items() if k != "ogonek"}
        o.clause(
            f"A/{master}: other anchors unchanged",
            others
            == {k: v for k, v in anchors(o.lb("A", master)).items() if k != "ogonek"},
        )
    o.clause("A/Regular unchanged", o.la("A") == o.lb("A"))
    o.nothing_else_changed({"A"})


def example(o):
    for master in ("Light", "Bold"):
        x, y = expected(o, master)
        for a in o.edit_layer("A", master)["anchors"]:
            if a["name"] == "ogonek":
                a["point"] = f"{x:g} {y:g}"


def unchanged(o):  # Light/Bold keep their own ogonek (510, 0) and (626, 0)
    pass


def copied_absolute(o):
    for master in ("Light", "Bold"):
        for a in o.edit_layer("A", master)["anchors"]:
            if a["name"] == "ogonek":
                a["point"] = "572 0"


COUNTEREXAMPLES = [unchanged, copied_absolute]
