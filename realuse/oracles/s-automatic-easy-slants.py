# this_file: realuse/oracles/s-automatic-easy-slants.py
"""Automatic Easy Slants (usted--Glyphs-Scripts/Automatic Easy Slants.py): adds
an "Italic" axis (tag ital), and for every master a copy named "<master>
Italic" at ital 1 with all glyphs and kerning copied, italic angle 9.5; the
copies' layers with paths are slanted by 9.5 degrees around half the x-height
(with Glyphs' slant correction); every instance gets an italic twin. Expected on
plum-var: an ital axis, six masters (Light, Regular, Bold and their Italic
copies), each italic A has its base master's node structure, the same y values
and x slanted by tan(9.5 deg) * (y - 239) (+-4 for the correction), the base
masters' glyphs unchanged; the Output says it completed."""

import math

from realuse_oracle import contours, layers, masters

T = math.tan(math.radians(9.5))


def check(o):
    o.clause(
        "an 'ital' axis was added",
        any(a.get("tag") == "ital" for a in o.after["font"].get("axes", [])),
        [a.get("tag") for a in o.after["font"].get("axes", [])],
    )
    names = masters(o.after)
    want = ["Light", "Regular", "Bold", "Light Italic", "Regular Italic", "Bold Italic"]
    o.clause(
        "six masters: the three and their Italic copies",
        sorted(names) == sorted(want),
        names,
    )
    for base in ("Light", "Regular", "Bold"):
        src, ital = (
            layers(o.before, "A").get(base),
            layers(o.after, "A").get(base + " Italic"),
        )
        ok = ital is not None and [[p.on for p in c] for c in contours(ital)] == [
            [p.on for p in c] for c in contours(src)
        ]
        ok = ok and all(
            q.y == p.y and abs(q.x - (p.x + T * (p.y - 239))) <= 4
            for c, d in zip(contours(src), contours(ital))
            for p, q in zip(c, d)
        )
        o.clause(f"A/{base} Italic: A/{base} slanted 9.5 deg around y 239", ok)
    o.clause(
        "base masters' glyph layers unchanged",
        all(
            o.changed_layers(g) <= {m + " Italic" for m in ("Light", "Regular", "Bold")}
            for g in o.touched()
        ),
    )
    o.clause(
        "Output: completed",
        "Easy Slants completed successfully." in o.text,
        o.text[-200:],
    )


def example(o):
    import copy

    from realuse_oracle import Pt, set_contours

    font = o.after["font"]
    font["axes"].append({"name": "Italic", "tag": "ital", "shortName": "it"})
    for m in list(font["masters"]):
        new = copy.deepcopy(m)
        new["fontMaster"]["name"] += " Italic"
        font["masters"].append(new)
    for g in font["glyphs"]:
        for layer in list(g.get("layers", [])):
            if layer.get("name") in ("Light", "Regular", "Bold"):
                new = copy.deepcopy(layer)
                new["name"] += " Italic"
                if contours(new):
                    set_contours(
                        new,
                        [
                            [Pt(p.x + T * (p.y - 239), p.y, p.on) for p in c]
                            for c in contours(new)
                        ],
                    )
                g["layers"].append(new)
    o.output = ["Easy Slants completed successfully.\n"]


def masters_only(o):  # copies without slant
    example(o)
    for g in o.after["font"]["glyphs"]:
        for layer in g["layers"]:
            if layer["name"].endswith(" Italic"):
                src = next(
                    la
                    for la in g["layers"]
                    if la["name"] == layer["name"][: -len(" Italic")]
                )
                layer["elements"] = src.get("elements", [])


def nothing(o):
    pass


COUNTEREXAMPLES = [masters_only, nothing]
