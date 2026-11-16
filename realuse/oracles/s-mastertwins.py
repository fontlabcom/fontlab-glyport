# this_file: realuse/oracles/s-mastertwins.py
"""MasterTwins (rsztype--Scripts/MasterTwins.py: copy_layer, copyMasters), Apply
with "Selected glyphs only" ticked and the defaults: copy from the front master
(Regular) into the next one (Bold), including paths, components, anchors, metrics
and hints. Expected: A/Bold gets A/Regular's paths, anchors, hints and width;
A/Light and A/Regular are unchanged; no other glyph changes."""

import copy

from realuse_oracle import anchors, components, contours


def check(o):
    src, dst = o.lb("A", "Regular"), o.la("A", "Bold")
    o.clause("A/Bold: paths = A/Regular's", contours(dst) == contours(src))
    o.clause("A/Bold: components = A/Regular's", components(dst) == components(src))
    o.clause(
        "A/Bold: anchors = A/Regular's",
        anchors(dst) == anchors(src),
        {"after": anchors(dst)},
    )
    o.clause("A/Bold: hints = A/Regular's", dst.get("hints") == src.get("hints"))
    o.clause(
        "A/Bold: width = A/Regular's",
        dst.get("advanceWidth") == src.get("advanceWidth"),
    )
    o.only_layer_changed("A", "Bold")
    o.nothing_else_changed({"A"})


def example(o):
    src = o.lb("A", "Regular")
    dst = o.edit_layer("A", "Bold")
    for key in ("elements", "anchors", "hints", "advanceWidth"):
        dst[key] = copy.deepcopy(src[key])


def unchanged(o):
    pass


def paths_only(o):
    o.edit_layer("A", "Bold")["elements"] = copy.deepcopy(
        o.lb("A", "Regular")["elements"]
    )


def whole_font(o):  # "Selected glyphs only" ignored
    example(o)
    o.edit_layer("B", "Bold")["elements"] = copy.deepcopy(
        o.lb("B", "Regular")["elements"]
    )


COUNTEREXAMPLES = [unchanged, paths_only, whole_font]
