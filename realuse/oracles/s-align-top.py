# this_file: realuse/oracles/s-align-top.py
"""Align Top (slobzheninov--Glyphs-Scripts/Align/Align Top.py: alignToSelection), with
every node of A/Regular selected (both paths fully selected, so the selection is
neither one element nor one path, nor all at one height): each selected path is
moved vertically so its highest node meets the selection's top (688).
A's outer path already reaches it; the counter moves up by 73 (615 -> 688).
Only A/Regular changes."""

from realuse_oracle import Pt, contours, set_contours

SHIFT = 73


def check(o):
    before, after = contours(o.lb("A")), contours(o.la("A"))
    o.clause(
        "A/Regular: outer path unchanged", len(after) == 2 and after[0] == before[0]
    )
    want = [(p.x, p.y + SHIFT) for p in before[1]]
    got = [(p.x, p.y) for p in after[1]] if len(after) == 2 else None
    o.clause(
        f"A/Regular: counter moved by {SHIFT} in y",
        got == want,
        {"after": got, "want": want},
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    layer = o.edit_layer("A")
    outer, counter = contours(layer)
    set_contours(layer, [outer, [Pt(p.x, p.y + SHIFT, p.on) for p in counter]])


def unchanged(o):
    pass


def everything_moved(o):
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(p.x, p.y + SHIFT, p.on) for p in c] for c in contours(layer)]
    )


COUNTEREXAMPLES = [unchanged, everything_moved]
