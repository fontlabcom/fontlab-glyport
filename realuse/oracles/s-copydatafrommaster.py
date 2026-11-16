# this_file: realuse/oracles/s-copydatafrommaster.py
"""copyDataFromMaster (jansindl3r--Glyphs-Scripts/glyphs/copyDataFromMaster.py:
copyAnchors), driven: source layer Light (default), destination Bold, "Copy
Shapes" ticked, X offset 0. For the selected glyph A the destination layer is
cleared and receives the source's width, shapes and anchors. Expected: A/Bold's
paths, anchors and width equal A/Light's; A/Light and A/Regular unchanged;
nothing else changes."""

import copy

from realuse_oracle import anchors, contours


def check(o):
    src, dst = o.lb("A", "Light"), o.la("A", "Bold")
    o.clause("A/Bold: paths = A/Light's", contours(dst) == contours(src))
    o.clause("A/Bold: anchors = A/Light's", anchors(dst) == anchors(src), anchors(dst))
    o.clause(
        "A/Bold: width = A/Light's", dst.get("advanceWidth") == src.get("advanceWidth")
    )
    o.only_layer_changed("A", "Bold")
    o.nothing_else_changed({"A"})


def example(o):
    src, dst = o.lb("A", "Light"), o.edit_layer("A", "Bold")
    for key in ("elements", "anchors", "advanceWidth"):
        dst[key] = copy.deepcopy(src[key])


def light_cleared(o):  # the defaults: Light into Light clears the source first
    o.edit_layer("A", "Light")["elements"] = []
    o.edit_layer("A", "Light")["anchors"] = []


def width_only(o):
    o.edit_layer("A", "Bold")["advanceWidth"] = o.lb("A", "Light")["advanceWidth"]


COUNTEREXAMPLES = [light_cleared, width_only]
