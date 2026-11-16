# this_file: realuse/oracles/p-magicremove.py
"""Magic Remover palette (mekkablue--MagicRemove/.../plugin.py:91-255): with one
layer in an edit tab and items selected, its button deletes the selected items on
every compatible master/special layer of the glyph. The harness selects anchor
"top" on A/Regular and presses the button (no modifier keys: no background
backup, no path breaking). Expected: anchor "top" is gone from A's Light, Regular
and Bold (all three are compatible), every other anchor and all outlines stay,
and nothing else in the font changes."""

from realuse_oracle import anchors, contours, layers


def check(o):
    names = sorted(layers(o.before, "A"))
    for name in names:
        before, after = anchors(o.lb("A", name)), anchors(o.la("A", name))
        want = {k: v for k, v in before.items() if k != "top"}
        o.clause(
            f"A/{name}: anchor top removed, other anchors kept",
            after == want,
            {"before": sorted(before), "after": sorted(after)},
        )
        o.clause(
            f"A/{name}: outline unchanged",
            contours(o.la("A", name)) == contours(o.lb("A", name)),
        )
    o.nothing_else_changed({"A"})


def example(o):
    for name in layers(o.after, "A"):
        layer = o.edit_layer("A", name)
        layer["anchors"] = [a for a in layer.get("anchors", []) if a["name"] != "top"]


def unchanged(o):  # round 3: the palette opened, nothing was removed
    pass


def only_current_layer(o):
    layer = o.edit_layer("A")
    layer["anchors"] = [a for a in layer.get("anchors", []) if a["name"] != "top"]


COUNTEREXAMPLES = [unchanged, only_current_layer]
