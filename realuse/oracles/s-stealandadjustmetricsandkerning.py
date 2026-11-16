# this_file: realuse/oracles/s-stealandadjustmetricsandkerning.py
"""Steal and adjust metrics and kerning (rolandhuse--glyphsscripts/Kerning/
stealandadjustmetricsandkerning.py: main). Its three NSAlert prompts are answered
1 (source Light), 2 (target Regular), 50 (%). Without stem values it
approximates stems from weight classes (Light 300, Regular 400 -> 60, 80):
adjustment = -(80 - 60) / 2 * 50% = -5. For the selected glyph A: A/Regular's
LSB and RSB become A/Light's minus 5 (22 - 5 = 17 each); the script prints that
line. A/Light, A/Bold and other glyphs' outlines are unchanged (kerning may be
copied with the same adjustment). Composites built on A (Aacute, ...) follow A's
new metrics in the host, as Glyphs' automatic composites do (calibrated on the
2026-10-16 round-4 run): only their Regular layer may change, and only in the
fields that follow the base glyph (components, width, anchors)."""

import re

from realuse_oracle import (
    Pt,
    close,
    contours,
    set_contours,
    sidebearings,
)

ADJ = -5


def check(o):
    l0, r0 = sidebearings(o.lb("A", "Light"))
    got = sidebearings(o.la("A", "Regular"))
    o.clause(
        f"A/Regular: LSB, RSB = A/Light's + ({ADJ}) = ({l0 + ADJ:g}, {r0 + ADJ:g})",
        got is not None and close(got[0], l0 + ADJ) and close(got[1], r0 + ADJ),
        got,
    )
    o.clause(
        "Output: adjustment -5.00 and the A line",
        "Adjustment for sidebearings and kerning: -5.00" in o.text
        and re.search(rf"Adjusted A: LSB={l0 + ADJ:.2f}, RSB={r0 + ADJ:.2f}", o.text)
        is not None,
        o.text[-400:],
    )
    o.only_layer_changed("A", "Regular")
    composites = o.composites_follow("A")
    o.nothing_else_changed({"A"} | composites, font={"masters"})


def example(o):
    l0, r0 = sidebearings(o.lb("A", "Light"))
    layer = o.edit_layer("A", "Regular")
    lb, _ = sidebearings(layer)
    pts = [p for c in contours(layer) for p in c]
    width = max(p.x for p in pts) - min(p.x for p in pts)
    set_contours(
        layer, [[Pt(p.x + l0 + ADJ - lb, p.y) for p in c] for c in contours(layer)]
    )
    layer["advanceWidth"] = l0 + ADJ + width + r0 + ADJ
    o.output = [
        f"Adjustment for sidebearings and kerning: -5.00\nAdjusted A: LSB={l0 + ADJ:.2f}, RSB={r0 + ADJ:.2f}\n"
    ]


def same_master_noop(o):  # defaults (Regular -> Regular): adjustment 0
    o.output = ["Adjustment for sidebearings and kerning: -0.00\n"]


COUNTEREXAMPLES = [same_master_noop]
