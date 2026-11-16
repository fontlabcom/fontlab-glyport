# this_file: realuse/oracles/s-axis-twister.py
"""Axis Twister (loweredcase--glyphs-tools/Drawing/Axis Twister.py: run), "Run"
with the defaults (random range mode, all smart components, chance 100%). It
changes the axis values of smart components in the selected layers. No GetGo
font has smart components (and FontLab has no Glyphs-style smart-component
axes), so on Aacute (plain components A + acute) the faithful Glyphs result is
its summary line reporting 0 axis values set, and no change to the font. The
Reset button (the round-3 default click) is not the action under test."""


def check(o):
    o.clause(
        "Output: the run summary with 0 axis values set",
        "✔ Axis Twister: set 0 axis value(s)" in o.text,
        o.text[-300:],
    )
    o.clause("the Reset path was not taken", "Reset failed" not in o.text)
    o.unchanged()


def example(o):
    o.output = [
        "✔ Axis Twister: set 0 axis value(s) on 0 component(s). Mode=Random range, ...\n"
    ]


def reset_clicked(o):  # round 3
    o.output = ["⚠️ Reset failed: Unsupported model member: GSFont.parent\n"]


COUNTEREXAMPLES = [reset_clicked]
