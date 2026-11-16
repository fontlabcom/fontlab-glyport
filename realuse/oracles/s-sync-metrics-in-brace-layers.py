# this_file: realuse/oracles/s-sync-metrics-in-brace-layers.py
"""Sync metrics in brace layers (huertatipografica--huertatipografica-scripts/
Metrics/Sync metrics in brace layers.py:14-45). The harness gives A a brace layer
{550} (a copy of A/Regular, LSB +40) before the run. For each brace layer of the
selected glyph the script re-interpolates the layer, keeps only the interpolated
LSB/RSB and restores everything else (paths, anchors, hints, keys), then prints
"name: LSB <- -> RSB". Expected: A/{550} has the sidebearings interpolated at
weight 550 between Regular (400) and Bold (700), the same outline shape as before,
the masters are untouched and the Output line reports the new values."""

import re

from realuse_oracle import Pt, close, contours, location, set_contours, sidebearings

BRACE = "{550}"


def expected(o):
    lo, hi = location(o.before, "Regular")["wt"], location(o.before, "Bold")["wt"]
    t = (550 - lo) / (hi - lo)
    (l0, r0), (l1, r1) = (
        sidebearings(o.lb("A", "Regular")),
        sidebearings(o.lb("A", "Bold")),
    )
    return l0 + t * (l1 - l0), r0 + t * (r1 - r0)


def shape(layer):
    pts = [p for c in contours(layer) for p in c]
    x0 = min((p.x for p in pts), default=0)
    return [(p.x - x0, p.y, p.on) for p in pts]


def check(o):
    if not o.clause(
        "the prepared brace layer {550} exists before the run",
        o.lb("A", BRACE) is not None,
    ):
        return
    lsb, rsb = expected(o)
    got = sidebearings(o.la("A", BRACE))
    o.clause(
        f"A/{BRACE}: LSB, RSB = ({lsb:g}, {rsb:g}) +-1",
        got is not None and close(got[0], lsb, 1.0) and close(got[1], rsb, 1.0),
        {"before": sidebearings(o.lb("A", BRACE)), "after": got},
    )
    o.clause(
        f"A/{BRACE}: outline shape kept",
        shape(o.la("A", BRACE)) == shape(o.lb("A", BRACE)),
    )
    o.clause(
        "Output reports the brace layer's new sidebearings",
        re.search(rf"\{{550\}}:\s*{round(lsb)} <- -> {round(rsb)}", o.text) is not None,
        o.text[-300:],
    )
    o.only_layer_changed("A", BRACE)
    o.nothing_else_changed({"A"})


def prepared(o):  # what the harness does before the "before" save
    for vfj in (o.before, o.after):
        glyph = next(g for g in vfj["font"]["glyphs"] if g["name"] == "A")
        regular = next(layer for layer in glyph["layers"] if layer["name"] == "Regular")
        brace = __import__("copy").deepcopy(regular)
        brace["name"] = BRACE
        set_contours(
            brace, [[Pt(p.x + 40, p.y, p.on) for p in c] for c in contours(brace)]
        )
        brace["advanceWidth"] += 40
        glyph["layers"].append(brace)


def example(o):
    prepared(o)
    lsb, rsb = expected(o)
    layer = o.edit_layer("A", BRACE)
    l0, _ = sidebearings(layer)
    pts = [p for c in contours(layer) for p in c]
    width = max(p.x for p in pts) - min(p.x for p in pts)
    set_contours(
        layer, [[Pt(p.x + lsb - l0, p.y, p.on) for p in c] for c in contours(layer)]
    )
    layer["advanceWidth"] = lsb + width + rsb
    o.output = [f"{BRACE}:\t{round(lsb)} <- -> {round(rsb)}\n"]


def unchanged(o):
    prepared(o)


def no_brace(o):  # prepare failed: a no-op on A must not pass
    pass


def masters_resynced(o):
    example(o)
    o.edit_layer("A", "Regular")["advanceWidth"] += 4


COUNTEREXAMPLES = [unchanged, no_brace, masters_resynced]
