# this_file: realuse/oracles/p-smartplumblines.py
"""Smart Plumblines (Mark2Mark--Show-Smart-Plumblines/SmartPlumblines.glyphsReporter/
.../plugin.py: background): draws plumb lines through the selected nodes of the
current layer. The harness selects an on-curve node of O/Regular.
Expected: it draws while switched on, nothing after it is switched off, and the
font is unchanged."""

from reporter_oracle import check_reporter, example_reporter, silent, sticky


def check(o):
    check_reporter(o, "plumb lines through the selected node")


def example(o):
    example_reporter(o)


COUNTEREXAMPLES = [silent, sticky]
