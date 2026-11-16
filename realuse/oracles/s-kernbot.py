# this_file: realuse/oracles/s-kernbot.py
"""KernBot (joeygrable94--KernBot.io/KernBot.py: _adjustLeftGlyphRightMetric).
The script reads its word list from ./resources relative to the working
directory, which Glyphs sets to the script's folder before running it. The first
"+" button (left glyph, right metric) raises the active left glyph's RSB on the
current master by the metric unit 4 (plum-var has no metrics keys), then syncs
metrics. Expected: exactly one glyph changes, only on Regular: width +4, outline
unchanged (RSB grows, LSB stays); no kerning or other change."""

from realuse_oracle import contours, layers


def check(o):
    touched = sorted(o.touched())
    o.clause("exactly one glyph changed", len(touched) == 1, touched[:10])
    if len(touched) != 1:
        return
    name = touched[0]
    lb, la = o.lb(name), o.la(name)
    o.clause(
        f"{name}: only the shown layer changed",
        o.changed_layers(name) == {o.layer},
        sorted(o.changed_layers(name)),
    )
    o.clause(
        f"{name}/{o.layer}: width +4, outline unchanged (RSB +4)",
        la is not None
        and la.get("advanceWidth") == lb.get("advanceWidth") + 4
        and contours(la) == contours(lb),
        {
            "before": lb.get("advanceWidth"),
            "after": None if la is None else la.get("advanceWidth"),
        },
    )
    o.clause(
        "no font-level change (kerning untouched)",
        not o.font_keys_changed(),
        sorted(o.font_keys_changed()),
    )


def example(o):
    o.edit_layer("H")["advanceWidth"] += 4


def unchanged(o):
    pass


def all_masters(o):
    for name in layers(o.after, "H"):
        o.edit_layer("H", name)["advanceWidth"] += 4


COUNTEREXAMPLES = [unchanged, all_masters]
