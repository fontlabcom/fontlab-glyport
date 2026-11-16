# this_file: realuse/oracles/s-tab-component-glyphs-with-anchors.py
"""Tab: Component Glyphs with Anchors (Mark2Mark--Glyphsapp-Scripts-Free/Font/
Tab - Component Glyphs with Anchors.py:27-41): opens a new tab with every glyph
whose layer for the selected master has no paths, at least one component and at
least one anchor, in font order. Expected on plum-var (current master Regular):
the tab shows exactly those glyphs, computed from the before copy (69 composites
such as Aacute ... ygrave), and the font is unchanged."""

from realuse_oracle import anchors, components, contours, layers, tab_glyphs


def candidates(o):
    found = []
    for g in o.before["font"]["glyphs"]:
        layer = layers(o.before, g["name"]).get(o.layer)
        if layer and not contours(layer) and components(layer) and anchors(layer):
            found.append(g["name"])
    return found


def check(o):
    want, shown = candidates(o), tab_glyphs(o.before, o.tab)
    o.clause(
        f"the new tab shows exactly the {len(want)} component-only glyphs with anchors, in font order",
        shown == want,
        {
            "missing": [n for n in want if n not in shown][:10],
            "extra": [n for n in shown if n not in want][:10],
        },
    )
    o.unchanged()


def example(o):
    o.tab = "".join(
        chr(int(g["unicode"], 16)) if g.get("unicode") else "/" + g["name"]
        for name in candidates(o)
        for g in o.before["font"]["glyphs"]
        if g["name"] == name
    )


def old_tab(o):  # the tab the harness opened, not the script's
    o.tab = "A"


def one_missing(o):
    example(o)
    o.tab = o.tab[1:]


def font_changed(o):
    example(o)
    o.edit_layer("Aacute")["advanceWidth"] += 10


COUNTEREXAMPLES = [old_tab, one_missing, font_changed]
