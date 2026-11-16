# this_file: realuse/oracles/s-papyrify.py
"""Papyrify (mekkablue--Papyrify/Papyrify.py:548-630) needs exactly two masters;
the harness removes Bold from the owned plum-var copy, leaving Light and Regular.
For the selected glyph A the script moves the first master's outline (Light) into
its background, rebuilds Light's foreground as a subdivided copy of it (many short
segments, same overall shape), clears the second master (Regular), gives it
Light's width and fills it with a copy of the new Light paths whose nodes are
randomly pushed and bent. It prints a report header and "Done.".
Randomised, so the oracle checks properties: Light keeps its bounds but has more
nodes; the original Light outline is in Light's background (FontLab mask layer);
Regular is point-compatible with the new Light, differs from it and has Light's
width; nothing else changes."""

from realuse_oracle import (
    Pt,
    bounds,
    contours,
    layers,
    oncurves,
    points,
    same_cycle,
    set_contours,
)


def structure(layer):
    return [[p.on for p in c] for c in contours(layer)]


def key(c):
    return [(p.x, p.y, p.on) for p in c]


def check(o):
    o.clause(
        "two masters before the run (prepare removed Bold)",
        [m["fontMaster"]["name"] for m in o.before["font"]["masters"]]
        == ["Light", "Regular"],
    )
    old, light, regular = o.lb("A", "Light"), o.la("A", "Light"), o.la("A", "Regular")
    o.clause(
        "A/Light: subdivided (more on-curve nodes than before)",
        len(oncurves(light)) > len(oncurves(old)),
        {"before": len(oncurves(old)), "after": len(oncurves(light))},
    )
    b0, b1 = bounds(points(old)), bounds(points(light))
    o.clause(
        "A/Light: overall shape kept (bounds within 3 units)",
        b1 is not None and all(abs(a - b) <= 3 for a, b in zip(b0, b1)),
        {"before": b0, "after": b1},
    )
    masks = [n for n in layers(o.after, "A") if n.startswith("mask")]
    o.clause(
        "A/Light background holds the original Light outline",
        any(
            len(contours(layers(o.after, "A")[n])) == len(contours(old))
            and all(
                same_cycle(key(a), key(b))
                for a, b in zip(contours(old), contours(layers(o.after, "A")[n]))
            )
            for n in masks
        ),
        masks,
    )
    o.clause(
        "A/Regular: point-compatible with the new A/Light",
        bool(structure(regular)) and structure(regular) == structure(light),
    )
    o.clause(
        "A/Regular: randomly deformed (differs from A/Light)",
        points(regular) != points(light),
    )
    o.clause(
        "A/Regular: width = A/Light width",
        regular is not None
        and regular.get("advanceWidth") == light.get("advanceWidth"),
    )
    o.clause(
        "Output: report and 'Done.'",
        "Papyrify Report" in o.text and "Done." in o.text,
        o.text[-300:],
    )
    o.nothing_else_changed({"A"})


def two_masters(o):
    for vfj in (o.before, o.after):
        vfj["font"]["masters"] = [
            m for m in vfj["font"]["masters"] if m["fontMaster"]["name"] != "Bold"
        ]
        for g in vfj["font"]["glyphs"]:
            g["layers"] = [la for la in g.get("layers", []) if la.get("name") != "Bold"]


def subdivide(c):
    out = []
    for a, b in zip(c, c[1:] + c[:1]):
        out += [a, Pt((a.x + b.x) / 2, (a.y + b.y) / 2, True)]
    return out


def example(o):
    two_masters(o)
    glyph = o.after_glyph("A")
    light = o.edit_layer("A", "Light")
    original = contours(light)
    mask = {"name": "mask.Light", "elements": []}
    set_contours(mask, original)
    glyph["layers"].append(mask)
    new = [subdivide(c) for c in original]
    set_contours(light, new)
    regular = o.edit_layer("A", "Regular")
    set_contours(
        regular, [[Pt(p.x + (i % 3), p.y, p.on) for i, p in enumerate(c)] for c in new]
    )
    regular["advanceWidth"] = light["advanceWidth"]
    o.output = ["Papyrify Report for GG Plum\n\nDone.\n"]


def precondition_only(o):  # round 3: "Two masters required", nothing changed
    two_masters(o)
    o.dialogs = [
        "message: Two masters required: The script requires exactly 2 masters."
    ]


def regular_not_deformed(o):
    example(o)
    set_contours(o.edit_layer("A", "Regular"), contours(o.la("A", "Light")))


COUNTEREXAMPLES = [precondition_only, regular_not_deformed]
