# this_file: realuse/oracles/s-change-weight.py
"""Change Weight (Reset-Type-Studio--Glyphs-Scripts/Paths/Change Weight.py:
102-110, 498-520): "Apply Offset" looks up Glyphs' built-in Offset Curve filter
(GlyphsFilterOffsetCurve, compiled into Glyphs). Under the existing controller
ruling FontLab has no equivalent, so the faithful result here is the script's own
precise report: a "Offset Curve filter not found" Message and no change to the
font (the target is classified, out of scope)."""


def check(o):
    o.clause(
        "the script reports the missing Offset Curve filter itself",
        any("Offset Curve filter not found" in d for d in o.dialogs),
        o.dialogs,
    )
    o.unchanged()


def example(o):
    o.dialogs = ["message: Error: Offset Curve filter not found."]


def silent(o):
    pass


def changed_anyway(o):
    example(o)
    o.edit_layer("A")["advanceWidth"] += 30


COUNTEREXAMPLES = [silent, changed_anyway]
