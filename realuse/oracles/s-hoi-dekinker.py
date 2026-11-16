# this_file: realuse/oracles/s-hoi-dekinker.py
"""HOI Dekinker (mekkablue--Glyphs-Scripts/Interpolation/HOI Dekinker.py:160-230):
a Glyphs 4 script (it refuses to run below version 4). With glyph A selected it
looks for kinks of smooth nodes between neighbouring key layers along every axis.
plum-var has three masters on its weight axis (two spans) and A has only corner
nodes, so the Glyphs 4 result is a report: the Macro window says no intermediate
point was added in the one selected glyph, and a Message says there were no kinks
above the threshold (not "no pair of neighbouring key layers", which would mean
the spans were not found). No outline changes. The "requires Glyphs 4" refusal is
not the script's result."""

import re


def check(o):
    shown = " ".join(o.dialogs)
    o.clause(
        "script ran (no 'requires Glyphs 4' refusal)",
        "requires Glyphs" not in shown,
        o.dialogs,
    )
    o.clause(
        "Output: report header and 'added 0 intermediate points in 0 of 1 glyph'",
        "Report for HOI Dekinker" in o.text
        and re.search(r"added 0 intermediate points? in 0 of 1 glyph\b", o.text)
        is not None,
        o.text[-600:],
    )
    o.clause(
        "Message: spans found, no kinks above the threshold",
        "no kinks larger than the threshold" in shown,
        o.dialogs,
    )
    o.unchanged()


def example(o):
    o.output = [
        "Report for HOI Dekinker\n\nSummary: added 0 intermediate points in 0 of 1 glyph.\n"
    ]
    o.dialogs = [
        (
            "message: HOI Dekinker: In the 1 selected glyph of 205 total glyphs in font "
            "'GG Plum', there were no kinks larger than the threshold 1.0u."
        )
    ]


def refused(o):  # what glyport did in round 3
    o.dialogs = ["message: HOI Dekinker: This script requires Glyphs 4 or later."]


def no_spans(o):
    example(o)
    o.dialogs = [
        (
            "message: HOI Dekinker: In the 1 selected glyph ..., no pair of neighboring "
            "key layers (masters or brace layers) was found along any axis"
        )
    ]


def changed_outline(o):
    example(o)
    o.edit_layer("A")["advanceWidth"] += 1


COUNTEREXAMPLES = [refused, no_spans, changed_outline]
