# this_file: realuse/oracles/p-guides.py
"""Guides Palette (3type--GuidesPalette/Guides.glyphsPalette/.../plugin.py:
settings, updateConfig): when the palette is set up for a font without its
configuration, it writes the font custom parameter "Guides Palette Config" with
its defaults (sortBy "", showCoordinates, showAngle on, tagPrefix "guide_"); the
"Assign Guides" panel lists the master's named global guides. Expected: the panel
is shown, the saved font carries "Guides Palette Config" with tagPrefix guide_,
and no glyph changes."""

import json


def font_text(vfj):
    return json.dumps({k: v for k, v in vfj["font"].items() if k != "glyphs"})


def check(o):
    shown = o.windows + o.extra.get("install", {}).get("windows", [])
    o.clause(
        "the 'Assign Guides' panel is shown",
        any("Assign Guides" in w for w in shown),
        shown,
    )
    o.clause(
        "font custom parameter 'Guides Palette Config' written",
        "Guides Palette Config" not in font_text(o.before)
        and "Guides Palette Config" in font_text(o.after)
        and "guide_" in font_text(o.after),
    )
    o.clause("no glyph changed", not o.touched(), sorted(o.touched())[:5])


def example(o):
    o.windows = ["ToolWindow:Assign Guides"]
    o.after["font"].setdefault("lib", {})["Guides Palette Config"] = {
        "sortBy": "",
        "showCoordinates": True,
        "showAngle": True,
        "tagPrefix": "guide_",
    }


def panel_only(o):
    o.windows = ["ToolWindow:Assign Guides"]


COUNTEREXAMPLES = [panel_only]
