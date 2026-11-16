# this_file: realuse/oracles/p-epsexport.py
"""EPS Export file format plugin (mekkablue--PSExport/EPSExport.glyphsFileFormat/
.../plugin.py:121-160), run from File > Export with EPS Export; the folder dialog
is answered with the run's scratch "out" folder. Defaults: outline (stroke), remove
overlap, only glyphs with shapes, no metrics markers, all glyphs. For every active
instance it writes one "<instance file name>-<glyph>.eps" per exported glyph that
has shapes, with a BoundingBox 30 units outside the glyph's bounds and one moveto
... closepath per path, ending "stroke" and "showpage". plum-var's instances
(Light, Regular, Bold) sit exactly on its masters, so each instance's A must have
the matching master's bounds. macOS file names are case-insensitive, so "A.eps"
and "a.eps" are one file (the later glyph wins, in Glyphs too): the count is of
case-insensitively distinct names and the content check uses "seven" (straight
lines only, no case twin). The font is unchanged."""

import re

from realuse_oracle import (
    bounds,
    contours,
    has_shapes,
    instances,
    layers,
    master_at,
    points,
)

PROBE = "seven"


def shaped(o, master):
    return sorted(
        g["name"]
        for g in o.before["font"]["glyphs"]
        if has_shapes(layers(o.before, g["name"]).get(master))
    )


def eps_files(o):
    return {n: size for n, size in o.files.items() if n.endswith(".eps")}


def check(o):
    found = eps_files(o)
    o.clause(
        "EPS files written into the chosen folder", bool(found), sorted(o.files)[:10]
    )
    for name, where in instances(o.before):
        master = master_at(o.before, where)
        mine = sorted(n for n in found if f"-{name}-" in n.rsplit("/", 1)[-1])
        want = len({g.lower() for g in shaped(o, master)})
        o.clause(
            f"instance {name}: one EPS per glyph with shapes ({want})",
            len(mine) == want,
            {"found": len(mine), "sample": mine[:3]},
        )
        a_file = next((n for n in mine if n.endswith(f"-{name}-{PROBE}.eps")), None)
        if not o.clause(f"instance {name}: {PROBE} exported", a_file is not None):
            continue
        text = o.read(a_file)
        x0, y0, x1, y1 = bounds(points(layers(o.before, PROBE)[master]))
        box = re.search(r"%%BoundingBox: (-?\d+) (-?\d+) (-?\d+) (-?\d+)", text)
        got = tuple(int(v) for v in box.groups()) if box else None
        want_box = (int(x0 - 30), int(y0 - 30), int(x1 + 30), int(y1 + 30))
        o.clause(
            f"instance {name}: {PROBE}'s BoundingBox = {master} bounds + 30",
            got == want_box,
            {"got": got, "want": want_box},
        )
        n_paths = len(contours(layers(o.before, PROBE)[master]))
        o.clause(
            f"instance {name}: {PROBE} drawn as {n_paths} closed paths, stroked, one page",
            text.count("moveto") == n_paths
            and text.count("closepath") == n_paths
            and "stroke" in text
            and "showpage" in text
            and f"%% {PROBE}" in text,
            text[:300],
        )
    o.unchanged()


def example(o):
    import tempfile
    from pathlib import Path

    o.scratch = Path(tempfile.mkdtemp(prefix="eps-oracle-"))
    (o.scratch / "out").mkdir()
    for name, where in instances(o.before):
        master = master_at(o.before, where)
        for glyph in shaped(o, master):
            rel = f"out/GGPlum-{name}-{glyph}.eps"
            layer = layers(o.before, glyph)[master]
            text = "%!PS-Adobe-3.1 EPSF-3.0\n"
            box = bounds(points(layer))
            if box:
                text += f"%%BoundingBox: {box[0] - 30:.0f} {box[1] - 30:.0f} {box[2] + 30:.0f} {box[3] + 30:.0f}\n"
            text += (
                f"%% {glyph}\n"
                + "0 0 moveto\nclosepath\n" * len(contours(layer))
                + "stroke\nshowpage\n"
            )
            (o.scratch / rel).write_text(text)
    o.files = {
        str(p.relative_to(o.scratch)): p.stat().st_size
        for p in o.scratch.rglob("*.eps")
    }


def nothing_written(o):  # round 3 recorded only the folder dialog
    pass


def one_instance_only(o):
    example(o)
    for n in [n for n in o.files if "-Bold-" in n]:
        del o.files[n]


COUNTEREXAMPLES = [nothing_written, one_instance_only]
