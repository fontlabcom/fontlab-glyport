# this_file: realuse/oracles/p-showinterpolation.py
"""Show Interpolation (mekkablue--ShowInterpolations/ShowInterpolation.glyphsReporter/
.../plugin.py: background): draws the glyph as interpolated for every active
instance behind the current layer. plum-var has three instances, so A's
instance outlines are drawn.
Expected: it draws while switched on, nothing after it is switched off, and the
font is unchanged."""

from reporter_oracle import check_reporter, example_reporter, silent, sticky


def check(o):
    check_reporter(o, "A's instance outlines")


def example(o):
    example_reporter(o)


COUNTEREXAMPLES = [silent, sticky]
