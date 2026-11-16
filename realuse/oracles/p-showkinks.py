# this_file: realuse/oracles/p-showkinks.py
"""Show Kinks (harbortype--ShowSmoothNodeAngleAndProportion/ShowKinks.glyphsReporter/.../plugin.py:
foregroundInViewCoords, backgroundInViewCoords): with one smooth node selected it
labels the handle proportions (and angle) of that node, and in the background it
marks smooth nodes whose handle proportions differ between masters (kink
risk). The harness selects a smooth node of O/Regular and lengthens its next
handle by 40, so both drawings apply.
Expected: it draws while switched on, nothing after it is switched off, and the
font is unchanged."""

from reporter_oracle import check_reporter, example_reporter, silent, sticky


def check(o):
    check_reporter(o, "the selected node's labels and the kink marks")


def example(o):
    example_reporter(o)


COUNTEREXAMPLES = [silent, sticky]
