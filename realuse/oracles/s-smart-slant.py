# this_file: realuse/oracles/s-smart-slant.py
"""Smart Slant / Simple Slant (Reset-Type-Studio--Glyphs-Scripts/Paths/Smart
Slant.py: _slant_one_layer), "Apply to selection" with the defaults: angle 9,
write the italic angle into the master, skip red glyphs. For A/Regular every node
and anchor moves by tan(9 deg) * (y - yRef), yRef at 33.5% of the layer's
height (230.48), the result is re-centred and the original LSB (13) and RSB (11)
are restored. The script first writes the italic angle 9 into the master, and
Glyphs measures LSB/RSB of a master with an italic angle on the slanted metrics
(points un-sheared around half the x-height), so the restored 13/11 are italic
sidebearings (calibrated 2026-10-16: the earlier upright 13/11 expectation was
wrong). Expected: master Regular italic angle 9; A/Regular = the sheared outline
up to one horizontal shift with italic LSB 13 and RSB 11; anchors sheared with
the same shift; composites built on A follow it; nothing else changes."""

import math

from realuse_oracle import (
    Pt,
    anchors,
    close,
    contours,
    points,
    set_contours,
    sidebearings,
)

SHEAR = math.tan(math.radians(9))


def sheared(layer):
    pts = points(layer)
    y0 = min(p.y for p in pts)
    y_ref = y0 + (max(p.y for p in pts) - y0) * 0.335
    return y_ref, [
        [(p.x + SHEAR * (p.y - y_ref), p.y) for p in c] for c in contours(layer)
    ]


def regular_master(vfj):
    return next(
        m["fontMaster"]
        for m in vfj["font"]["masters"]
        if m["fontMaster"].get("name") == "Regular"
    )


def italic_sidebearings(layer, master, angle=9.0):
    pts = points(layer)
    if not pts:
        return None
    origin = float(master.get("xHeight") or 0) / 2
    shear = math.tan(math.radians(angle))
    xs = [p.x - shear * (p.y - origin) for p in pts]
    return min(xs), float(layer.get("advanceWidth", 0)) - max(xs)


def check(o):
    master = regular_master(o.after)
    o.clause(
        "master Regular: italic angle 9 written",
        master.get("italic_angle") is not None
        and close(float(master["italic_angle"]), 9, 0.01),
        master.get("italic_angle"),
    )
    y_ref, want = sheared(o.lb("A"))
    got = [[(p.x, p.y) for p in c] for c in contours(o.la("A"))]
    shift = got[0][0][0] - want[0][0][0] if got and got[0] and want else 0.0
    o.clause(
        "A/Regular: outline sheared by tan(9 deg) around y 230.5 (up to a horizontal shift)",
        len(got) == len(want)
        and all(
            len(a) == len(b)
            and all(close(x - shift, u, 1) and y == v for (x, y), (u, v) in zip(a, b))
            for a, b in zip(got, want)
        ),
        {"shift": shift, "got": got},
    )
    italic = italic_sidebearings(o.la("A"), master)
    o.clause(
        "A/Regular: original LSB 13 and RSB 11 kept as italic sidebearings (9 deg, origin x-height/2)",
        italic is not None and all(close(a, b, 1) for a, b in zip(italic, (13, 11))),
        {"italic": italic, "upright": sidebearings(o.la("A"))},
    )
    ab, aa = anchors(o.lb("A")), anchors(o.la("A"))
    o.clause(
        "A/Regular: anchors sheared with the same shift",
        ab.keys() == aa.keys()
        and all(
            close(aa[k][0], ab[k][0] + SHEAR * (ab[k][1] - y_ref) + shift, 1)
            for k in ab
        ),
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"} | o.composites_follow("A"), font={"masters"})


def example(o):
    master = regular_master(o.after)
    master["italic_angle"] = 9  # FontLab VFJ key
    origin = float(master.get("xHeight") or 0) / 2
    layer = o.edit_layer("A")
    y_ref, new = sheared(layer)
    unsheared = [x - SHEAR * (y - origin) for c in new for x, y in c]
    shift = 13 - min(unsheared)
    set_contours(layer, [[Pt(x + shift, y) for x, y in c] for c in new])
    layer["advanceWidth"] = max(unsheared) + shift + 11
    for a in layer["anchors"]:
        x, y = (float(v) for v in a["point"].split())
        a["point"] = f"{x + SHEAR * (y - y_ref) + shift:.2f} {y:g}"


def unchanged(o):
    pass


def shifted_only(o):
    layer = o.edit_layer("A")
    set_contours(layer, [[Pt(p.x + 30, p.y) for p in c] for c in contours(layer)])


def upright_sidebearings_only(o):  # what glyport did on 2026-10-16: no italic angle
    example(o)
    regular_master(o.after).pop("italic_angle", None)


COUNTEREXAMPLES = [unchanged, shifted_only, upright_sidebearings_only]
