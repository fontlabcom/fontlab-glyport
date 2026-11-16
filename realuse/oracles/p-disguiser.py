# this_file: realuse/oracles/p-disguiser.py
"""Disguiser (mekkablue--Disguiser/.../plugin.py:33-49), run from the Filter menu
with glyph A shown in an edit tab and no selection: in an edit view the filter
appends one closed rectangle path, made of four line nodes at the corners of the
layer's bounds, to the shown layer. Existing paths stay as they were; other layers
and glyphs are untouched (the font-view branch, which replaces every master's
paths, does not apply)."""

from realuse_oracle import Pt, bounds, contours, oncurves, same_cycle, set_contours


def rectangle(layer):
    x0, y0, x1, y1 = bounds(oncurves(layer))
    return [Pt(x0, y0, True), Pt(x1, y0, True), Pt(x1, y1, True), Pt(x0, y1, True)]


def check(o):
    before, after = contours(o.lb("A")), contours(o.la("A"))
    o.clause(
        "A: the shown layer gained exactly one path",
        len(after) == len(before) + 1,
        {"before": len(before), "after": len(after)},
    )
    o.clause("A: the original paths are unchanged", after[: len(before)] == before)
    added = after[len(before) :]
    want = rectangle(o.lb("A"))
    o.clause(
        "A: the new path is the rectangle of the layer's bounds (4 line nodes)",
        len(added) == 1
        and same_cycle(
            [(p.x, p.y, p.on) for p in added[0]], [(p.x, p.y, p.on) for p in want]
        ),
        {
            "added": [[(p.x, p.y) for p in c] for c in added],
            "bounds": bounds(oncurves(o.lb("A"))),
        },
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    layer = o.edit_layer("A")
    set_contours(layer, contours(layer) + [rectangle(layer)])


def unchanged(o):
    pass


def every_master(o):  # the font-view branch: all masters replaced
    for name in ("Light", "Regular", "Bold"):
        layer = o.edit_layer("A", name)
        set_contours(layer, [rectangle(layer)])


def wrong_rectangle(o):
    layer = o.edit_layer("A")
    r = rectangle(layer)
    r[2] = Pt(r[2].x + 10, r[2].y, True)
    set_contours(layer, contours(layer) + [r])


COUNTEREXAMPLES = [unchanged, every_master, wrong_rectangle]
