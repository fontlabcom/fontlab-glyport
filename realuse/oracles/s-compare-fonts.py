# this_file: realuse/oracles/s-compare-fonts.py
"""Compare Fonts (weiweihuanghuang--wei-glyphs-scripts/Compare Fonts.py): compares
the first two open fonts master by master (paths, components, anchors, width;
composites with automatically aligned components skipped), prints each master's
"Different Glyphs" as a /-joined list and opens a tab with them in both fonts.
The other font is an untouched copy of plum-var; the harness changed the owned
copy first: A/Regular width +10 and one node of B/Light. Expected Output: Light
lists /B, Regular lists /A, Bold lists nothing; the owned font is not changed by
the script (copyToBackground is off)."""

import re


def listed(text, master):
    m = re.search(rf"{master}\n\tDifferent Glyphs\n(/[^\n]*)", text)
    return None if m is None else [g for g in m.group(1).split("/") if g]


def check(o):
    for master, want in (("Light", ["B"]), ("Regular", ["A"]), ("Bold", [])):
        got = listed(o.text, master)
        o.clause(f"{master}: Different Glyphs = {want}", got == want, got)
    o.unchanged()


def example(o):
    o.output = [
        "\nLight\n\tDifferent Glyphs\n/B\n\nRegular\n\tDifferent Glyphs\n/A\n\nBold\n\tDifferent Glyphs\n/\n"
    ]


def nothing_found(o):  # what an unprepared identical pair gives
    o.output = [
        "\nLight\n\tDifferent Glyphs\n/\n\nRegular\n\tDifferent Glyphs\n/\n\nBold\n\tDifferent Glyphs\n/\n"
    ]


def everything_found(o):
    o.output = [
        "\nLight\n\tDifferent Glyphs\n/A/B\n\nRegular\n\tDifferent Glyphs\n/A/B\n\nBold\n\tDifferent Glyphs\n/A/B\n"
    ]


COUNTEREXAMPLES = [nothing_found, everything_found]
