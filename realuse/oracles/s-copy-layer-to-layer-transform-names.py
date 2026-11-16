# this_file: realuse/oracles/s-copy-layer-to-layer-transform-names.py
"""Copy Layer to Layer, Transform Glyph Names (jenskutilek--Glyphs-Scripts/Layers/
Copy Layer to Layer Transform Names.py: buttonCallback), Copy with the defaults:
source = this font, first master (Light); target = this font, second master
(Regular); paths, components, anchors and metrics included, not to the
background. For the selected glyph A (".pcap" -> ".sc" renaming does not apply)
A/Regular's paths, anchors and width are replaced by A/Light's. Light and Bold
and every other glyph stay unchanged."""

import copy

from realuse_oracle import anchors, components, contours


def check(o):
    src, dst = o.lb("A", "Light"), o.la("A", "Regular")
    o.clause("A/Regular: paths = A/Light's", contours(dst) == contours(src))
    o.clause(
        "A/Regular: components = A/Light's (none)", components(dst) == components(src)
    )
    o.clause(
        "A/Regular: anchors = A/Light's",
        anchors(dst) == anchors(src),
        {"after": anchors(dst)},
    )
    o.clause(
        "A/Regular: width = A/Light's (554)",
        dst.get("advanceWidth") == src.get("advanceWidth"),
    )
    o.only_layer_changed("A", "Regular")
    o.nothing_else_changed({"A"})


def example(o):
    src, dst = o.lb("A", "Light"), o.edit_layer("A", "Regular")
    for key in ("elements", "anchors", "advanceWidth"):
        dst[key] = copy.deepcopy(src[key])


def unchanged(o):
    pass


def into_bold(o):  # wrong target master
    src, dst = o.lb("A", "Light"), o.edit_layer("A", "Bold")
    for key in ("elements", "anchors", "advanceWidth"):
        dst[key] = copy.deepcopy(src[key])


COUNTEREXAMPLES = [unchanged, into_bold]
