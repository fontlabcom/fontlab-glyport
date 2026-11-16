# this_file: realuse/oracles/p-htletterspacerpreview.py
"""HT Letterspacer Preview (huertatipografica--HTLetterspacer/
HTLetterspacerPreview.glyphsReporter/.../plugin.py: foreground): draws the
spacing areas HT Letterspacer would use for the current layer (default
parameters when the master has none) - here for A.
Expected: it draws while switched on, nothing after it is switched off, and the
font is unchanged."""

from reporter_oracle import check_reporter, example_reporter, silent, sticky


def check(o):
    check_reporter(o, "A's spacing areas")


def example(o):
    example_reporter(o)


COUNTEREXAMPLES = [silent, sticky]
