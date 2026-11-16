# this_file: realuse/oracles/p-highlightimpreciseitalicangle.py
"""Highlight Imprecise Italic Angle (michaelrafailyk--HighlightImpreciseItalicAngle/
.../plugin.py: foreground): with the select or draw tool active it highlights
path segments within 10 degrees of the italic angle that do not match it
exactly. The harness moves one top node of I/Regular by 3 units, so I's stem
is 0.25 degrees off upright (italic angle 0).
Expected: it draws while switched on, nothing after it is switched off, and the
font is unchanged."""

from reporter_oracle import check_reporter, example_reporter, silent, sticky


def check(o):
    check_reporter(o, "the imprecise stem highlight")


def example(o):
    example_reporter(o)


COUNTEREXAMPLES = [silent, sticky]
