# this_file: realuse/oracles/s-alignment-pro.py
"""Alignment PRO (joseppatau--Tipo-Pepel-Scripts/Paths & Nodes/Align/
Alignment_PRO.py:799-1077), Align button with its defaults (option "Center X",
scope "Current", paths as group). The harness selects the first two nodes of A's
counter (second path) on Regular. With nodes selected but no full path, the
script is in nodes-only mode: each selected node moves horizontally to the
centre X of the selection's bounds, y unchanged, the third counter node and the
outer path stay. Only A/Regular changes. (With every node selected the script
would align whole paths to their common bounds; A's outer path defines those
bounds, so that would change nothing.)"""

from realuse_oracle import Pt, close, contours, set_contours


def check(o):
    before, after = contours(o.lb("A")), contours(o.la("A"))
    if not o.clause("A keeps two paths", len(after) == 2 == len(before)):
        return
    old, new = before[1], after[1]
    # glyport may start the path at another node than the VFJ: accept the pair
    # of nodes that moved, as long as exactly two moved to their common centre.
    moved = [
        i
        for i in range(min(len(old), len(new)))
        if (old[i].x, old[i].y) != (new[i].x, new[i].y)
    ]
    ok = len(new) == 3 and len(moved) == 2
    if ok:
        cx = (old[moved[0]].x + old[moved[1]].x) / 2
        ok = all(close(new[i].x, cx) and new[i].y == old[i].y for i in moved)
    o.clause(
        "two counter nodes moved to the centre X of the two, y kept; the third unchanged",
        ok,
        {"before": [(p.x, p.y) for p in old], "after": [(p.x, p.y) for p in new]},
    )
    o.clause("outer path unchanged", after[0] == before[0])
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    layer = o.edit_layer("A")
    outer, counter = contours(layer)
    cx = (counter[0].x + counter[1].x) / 2
    counter = [Pt(cx, p.y, p.on) for p in counter[:2]] + counter[2:]
    set_contours(layer, [outer, counter])


def unchanged(o):
    pass


def whole_counter_moved(o):
    layer = o.edit_layer("A")
    outer, counter = contours(layer)
    set_contours(layer, [outer, [Pt(p.x + 50, p.y, p.on) for p in counter]])


COUNTEREXAMPLES = [unchanged, whole_counter_moved]
