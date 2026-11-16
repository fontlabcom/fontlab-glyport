# this_file: realuse/oracles/s-start-from-scratch.py
"""Start-from-scratch (pedroarilla--glyphs-scripts/Cleaning/Start-from-scratch.py:
StartFromScratchMain), "Anchors" ticked, the other options at their defaults:
only selected glyphs, only the selected master, only master layers. Expected:
A/Regular loses all its anchors; its outline and width stay; A/Light, A/Bold and
every other glyph keep theirs; the Output logs "Deleting anchors". Composites
built on A re-place their marks on A/Regular as Glyphs' automatic alignment does
when A loses its anchors (calibrated 2026-10-16)."""

from realuse_oracle import anchors, contours


def check(o):
    o.clause(
        "A/Regular: no anchors left",
        o.lb("A") is not None and anchors(o.lb("A")) and not anchors(o.la("A")),
        anchors(o.la("A")),
    )
    o.clause(
        "A/Regular: outline and width unchanged",
        contours(o.la("A")) == contours(o.lb("A"))
        and o.la("A")["advanceWidth"] == o.lb("A")["advanceWidth"],
    )
    o.clause(
        "Output logs the anchor deletion", "Deleting anchors" in o.text, o.text[-300:]
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"} | o.composites_follow("A"))


def example(o):
    o.edit_layer("A")["anchors"] = []
    o.output = [
        "Start-from-scratch @ 12:00:00\n\n\tGetting selected glyphs...\n\tDeleting anchors...\n"
    ]


def unchanged(o):
    pass


def all_masters(o):
    for name in ("Light", "Regular", "Bold"):
        o.edit_layer("A", name)["anchors"] = []
    o.output = ["\tDeleting anchors...\n"]


COUNTEREXAMPLES = [unchanged, all_masters]
