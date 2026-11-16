# this_file: realuse/oracles/p-pencilmodifier.py
"""Pencil Modifier (michaelrafailyk--PencilModifier/PencilModifier.glyphsPlugin/
.../plugin.py: start, toggleMenuItemState): adds Path > Pencil Modifier with
setting toggles, all on by default; choosing "Simplify Drawn Path" turns that
setting off, ticks the menu item off and stores
com.michaelrafailyk.PencilModifier.SimplifyPath = false in the app defaults. Its
real work happens while drawing with the Pencil tool (event monitors and tool
callbacks), which needs a native tool hook (see FIXES). Expected here: the stored
setting is false and the font is unchanged."""

import json


def check(o):
    data = {}
    if "glyphs-defaults.json" in o.files:
        try:
            data = json.loads(o.read("glyphs-defaults.json"))
        except ValueError:
            data = {}
    o.clause(
        "defaults: com.michaelrafailyk.PencilModifier.SimplifyPath = false",
        data.get("com.michaelrafailyk.PencilModifier.SimplifyPath") is False,
        {k: v for k, v in data.items() if "PencilModifier" in k},
    )
    o.unchanged()


def example(o):
    import tempfile
    from pathlib import Path

    o.scratch = Path(tempfile.mkdtemp(prefix="pencil-oracle-"))
    (o.scratch / "glyphs-defaults.json").write_text(
        json.dumps({"com.michaelrafailyk.PencilModifier.SimplifyPath": False})
    )
    o.files = {"glyphs-defaults.json": 60}


def not_toggled(o):
    pass


COUNTEREXAMPLES = [not_toggled]
