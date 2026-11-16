# this_file: realuse/oracles/p-selectionpalette.py
"""Selection Palette (danielgamage--SelectionPalette/SelectionPalette.glyphsPalette/
.../plugin.py): a palette of image buttons (add/subtract/intersect selection,
grow, continue, undo selection) that only change which nodes are selected; it
never edits outlines. Saved fonts carry no selection, so the observable result
here is the panel itself and an untouched font. (Exercising the buttons needs a
node-selection probe; see the G1 report.)"""


def check(o):
    shown = o.windows + o.extra.get("install", {}).get("windows", [])
    o.clause(
        "the SelectionPalette panel is shown",
        any("SelectionPalette" in w for w in shown),
        shown,
    )
    o.unchanged()


def example(o):
    o.windows = ["ToolWindow:SelectionPalette"]


def no_panel(o):
    pass


COUNTEREXAMPLES = [no_panel]
