# this_file: realuse/oracles/s-import-images-by-unicode-code-point.py
"""Import Images by Unicode Code Point (dyyybek--Glyphs-Scripts/Import Images by
Unicode Code Point.py), driven: "Choose Path to Images" answered with an owned
folder holding A.jpeg and B.jpeg (1x1 images), method "By Glyph Name" and the
placeholder extension .jpeg (the defaults), then "Place Images": each glyph's
layer on the current master gets the background image "<folder><name>.jpeg".
Expected: A and B carry an image on the current master (FontLab keeps images as
image elements); no outline anywhere changes; glyphs without a file gain nothing
FontLab can store."""

from realuse_oracle import contours, layers


def images(vfj, glyph):
    return [
        n
        for n, layer in layers(vfj, glyph).items()
        for e in layer.get("elements", [])
        if "image" in (e.get("elementData") or {})
    ]


def check(o):
    for g in ("A", "B"):
        o.clause(
            f"{g}: an image was placed",
            len(images(o.after, g)) > len(images(o.before, g)),
            {"before": images(o.before, g), "after": images(o.after, g)},
        )
        o.clause(
            f"{g}: outlines unchanged",
            all(
                contours(layers(o.after, g).get(n)) == contours(la)
                for n, la in layers(o.before, g).items()
            ),
        )
    o.nothing_else_changed({"A", "B"})


def example(o):
    for g in ("A", "B"):
        o.edit_layer(g).setdefault("elements", []).append(
            {"elementData": {"image": {"PNG": "89504e47"}}}
        )


def nothing(o):
    pass


def only_a(o):
    o.edit_layer("A").setdefault("elements", []).append(
        {"elementData": {"image": {"PNG": "89504e47"}}}
    )


COUNTEREXAMPLES = [nothing, only_a]
