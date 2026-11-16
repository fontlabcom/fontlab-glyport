# this_file: realuse/oracles/s-node-nudger.py
"""Node Nudger (loweredcase--glyphs-tools/Drawing/Node Nudger.py: run), driven to
mode "Fixed" with X +30 and Y -20 (defaults otherwise: both axes, preserve curves,
no handle nudging, no new layer/glyph) on the selected layer A/Regular. Every
on-curve node moves by (30, -20); A has no off-curves. Anchors and width stay.
The script reports the count: 11 nodes in 1 layer. Only A/Regular changes."""

from realuse_oracle import Pt, anchors, contours, set_contours

DX, DY = 30, -20


def check(o):
    want = [[(p.x + DX, p.y + DY) for p in c] for c in contours(o.lb("A"))]
    got = [[(p.x, p.y) for p in c] for c in contours(o.la("A"))]
    o.clause("A/Regular: every node moved by (30, -20)", got == want, {"after": got})
    o.clause(
        "A/Regular: anchors and width unchanged",
        anchors(o.la("A")) == anchors(o.lb("A"))
        and o.la("A").get("advanceWidth") == o.lb("A").get("advanceWidth"),
    )
    o.clause(
        "Output: 11 nodes nudged in 1 layer, fixed mode",
        "nudged 11 node(s) in 1 layer(s)" in o.text and "Mode=Fixed" in o.text,
        o.text[-300:],
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(p.x + DX, p.y + DY, p.on) for p in c] for c in contours(layer)]
    )
    o.output = [
        "✔ Node Nudger: nudged 11 node(s) in 1 layer(s). Mode=Fixed, AffectX=True, ...\n"
    ]


def defaults_noop(o):  # round 3 clicked Run with empty random ranges
    o.output = ["✔ Node Nudger: nudged 0 node(s) in 1 layer(s). Mode=Random, ...\n"]


def x_only(o):
    layer = o.edit_layer("A")
    set_contours(layer, [[Pt(p.x + DX, p.y, p.on) for p in c] for c in contours(layer)])
    o.output = ["✔ Node Nudger: nudged 11 node(s) in 1 layer(s). Mode=Fixed\n"]


COUNTEREXAMPLES = [defaults_noop, x_only]
