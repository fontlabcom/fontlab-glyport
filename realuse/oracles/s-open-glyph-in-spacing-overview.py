# this_file: realuse/oracles/s-open-glyph-in-spacing-overview.py
"""Open glyph in spacing overview (yanone--Yanone-GlyphsApp-Scripts/Spacing/Open
glyph in spacing overview.py): takes the glyph at the tab's cursor (A), finds its
Unicode category (Lu) and fills the last tab with the uppercase spacing string
HHHHaHHHHaaaHHHH, "a" being the glyph, once per master, each line ended by a
line break; the cursor goes to the first A. Expected: the tab shows 3 x
(HHHH A HHHH AAA HHHH), 48 glyphs; the font is unchanged."""

from realuse_oracle import tab_glyphs

LINE = ["H"] * 4 + ["A"] + ["H"] * 4 + ["A"] * 3 + ["H"] * 4


def check(o):
    shown = tab_glyphs(o.before, o.tab)
    o.clause(
        "the tab shows the Lu spacing string with A, once per master",
        shown == LINE * 3,
        {"tab": o.tab[:120], "count": len(shown)},
    )
    o.unchanged()


def example(o):
    o.tab = "\n".join("HHHHAHHHHAAAHHHH" for _ in range(3)) + "\n"


def lowercase_string(o):
    o.tab = "mmmmAmmmmAAAmmmm" * 3


def one_master(o):
    o.tab = "HHHHAHHHHAAAHHHH"


COUNTEREXAMPLES = [lowercase_string, one_master]
