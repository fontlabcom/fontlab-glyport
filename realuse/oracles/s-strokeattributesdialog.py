# this_file: realuse/oracles/s-strokeattributesdialog.py
"""StrokeAttributesDialog (yintzuyuan--Glyphs_Scripts/StrokeAttributesDialog.py:
applyCallback, processLayers), Add button with the default width 10 and no
height: no path is selected, so every path of A's layers on the current master
(Regular) gets the path attribute strokeWidth = 10, saved with the font; the
script reports 1 glyph and 2 paths. Expected: the Output report, A/Regular's
saved data changed (the attribute) while its outline stays, other masters and
glyphs unchanged."""

from realuse_oracle import contours


def check(o):
    o.clause(
        "Output: stroke width 10 added to 2 paths of 1 glyph",
        "寬度=10" in o.text and "處理了 1 個字符的 2 條路徑" in o.text,
        o.text[-200:],
    )
    o.clause(
        "A/Regular: stroke attribute saved with the paths (layer data changed)",
        o.changed_layers("A") == {o.layer},
        sorted(o.changed_layers("A")),
    )
    o.clause("A/Regular: outline unchanged", contours(o.la("A")) == contours(o.lb("A")))
    o.nothing_else_changed({"A"})


def example(o):
    for element in o.edit_layer("A")["elements"]:
        element["stroke"] = {"thickness": 10}
    o.output = ["已新增筆劃屬性: 寬度=10，處理了 1 個字符的 2 條路徑。\n"]


def removed_instead(o):  # the last button ("remove") was pressed
    o.output = ["已移除筆劃屬性，處理了 1 個字符的 2 條路徑。\n"]


def not_saved(o):
    o.output = ["已新增筆劃屬性: 寬度=10，處理了 1 個字符的 2 條路徑。\n"]


COUNTEREXAMPLES = [removed_instead, not_saved]
