# this_file: realuse/oracles/s-re-interpolate-re-key-sidebearings.py
"""Re-interpolate + Re-key Sidebearings (mjlagattuta--Glyphs-Scripts/
Metrics-and-Kerning/Re-interpolate + Re-key Sidebearings.py:157-199), glyph A
selected on the middle master Regular of plum-var (Light 300, Regular 400,
Bold 700): the script re-interpolates a copy of the selected layer from the
other masters, copies its LSB and RSB to the layer and deletes the copy. A has no
metrics keys, so both keys end up empty. Expected: A/Regular's sidebearings equal
the linear interpolation of Light's and Bold's at weight 400; the outline is only
shifted (same shape); A keeps exactly its three master layers; Light and Bold and
every other glyph are unchanged. The script swallows every exception, so an
unchanged font is a failure, not a pass."""

from realuse_oracle import Pt, close, contours, location, set_contours, sidebearings


def expected(o):
    lo, hi = location(o.before, "Light")["wt"], location(o.before, "Bold")["wt"]
    t = (location(o.before, o.layer)["wt"] - lo) / (hi - lo)
    (l0, r0), (l1, r1) = (
        sidebearings(o.lb("A", "Light")),
        sidebearings(o.lb("A", "Bold")),
    )
    return l0 + t * (l1 - l0), r0 + t * (r1 - r0)


def shape(layer):
    pts = [p for c in contours(layer) for p in c]
    x0 = min(p.x for p in pts)
    return [(p.x - x0, p.y, p.on) for p in pts]


def check(o):
    lsb, rsb = expected(o)
    got = sidebearings(o.la("A"))
    o.clause(
        f"A/{o.layer}: LSB, RSB re-interpolated to ({lsb:.2f}, {rsb:.2f}) +-1",
        got is not None and close(got[0], lsb, 1.0) and close(got[1], rsb, 1.0),
        {"before": sidebearings(o.lb("A")), "after": got},
    )
    o.clause(
        "A: outline shape unchanged (only shifted)",
        shape(o.la("A")) == shape(o.lb("A")),
    )
    o.clause(
        "A: still exactly the master layers (temporary layer removed)",
        [layer["name"] for layer in o.after_glyph("A")["layers"]]
        == [layer["name"] for layer in o.before_glyph("A")["layers"]],
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    lsb, rsb = expected(o)
    layer = o.edit_layer("A")
    l0, _ = sidebearings(layer)
    box_w = max(p.x for c in contours(layer) for p in c) - min(
        p.x for c in contours(layer) for p in c
    )
    set_contours(
        layer,
        [[Pt(p.x + lsb - l0, p.y, p.on, p.smooth) for p in c] for c in contours(layer)],
    )
    layer["advanceWidth"] = lsb + box_w + rsb


def unchanged(o):
    pass


def all_masters(o):
    for name in ("Light", "Bold"):
        o.edit_layer("A", name)["advanceWidth"] += 20
    example(o)


COUNTEREXAMPLES = [unchanged, all_masters]
