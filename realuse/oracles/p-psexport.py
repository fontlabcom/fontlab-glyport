# this_file: realuse/oracles/p-psexport.py
"""PS Export file format plugin (mekkablue--PSExport/PSExport.glyphsFileFormat/
.../plugin.py, export): like EPS Export but one PostScript file per active
instance, "<instance file name>.ps", starting with "%!PS" and a page-device
setup, then one page per exported glyph with shapes ("%% name" comment, its
closed paths, "stroke", "showpage"). plum-var's instances (Light, Regular, Bold)
sit on its masters, so each file has one page per glyph with shapes in that
master, and the "seven" page draws seven's paths. The font is unchanged."""

from realuse_oracle import contours, has_shapes, instances, layers, master_at

PROBE = "seven"


def shaped(o, master):
    return [
        g["name"]
        for g in o.before["font"]["glyphs"]
        if has_shapes(layers(o.before, g["name"]).get(master))
    ]


def page(text, glyph):
    start = text.find(f"%% {glyph}\n")
    return text[start : text.find("showpage", start)] if start != -1 else ""


def check(o):
    found = sorted(n for n in o.files if n.endswith(".ps"))
    want = instances(o.before)
    o.clause(f"one .ps file per instance ({len(want)})", len(found) == len(want), found)
    for name, where in want:
        master = master_at(o.before, where)
        path = next(
            (n for n in found if n.rsplit("/", 1)[-1].endswith(f"-{name}.ps")), None
        )
        if not o.clause(
            f"instance {name}: PostScript file written", path is not None, found
        ):
            continue
        text = o.read(path)
        glyphs = shaped(o, master)
        o.clause(
            f"instance {name}: PostScript header and one page per glyph with shapes ({len(glyphs)})",
            text.startswith("%!PS") and text.count("showpage") == len(glyphs),
            {"pages": text.count("showpage")},
        )
        n_paths = len(contours(layers(o.before, PROBE)[master]))
        drawn = page(text, PROBE)
        o.clause(
            f"instance {name}: the {PROBE} page draws {n_paths} closed paths, stroked",
            drawn.count("moveto") == n_paths
            and drawn.count("closepath") == n_paths
            and "stroke" in drawn,
            drawn[:200],
        )
    o.unchanged()


def example(o):
    import tempfile
    from pathlib import Path

    o.scratch = Path(tempfile.mkdtemp(prefix="ps-oracle-"))
    (o.scratch / "out").mkdir()
    for name, where in instances(o.before):
        master = master_at(o.before, where)
        text = "%!PS\n<</Install { 100 300 translate .4 .4 scale } bind >> setpagedevice\n\n"
        for glyph in shaped(o, master):
            n = len(contours(layers(o.before, glyph)[master]))
            text += (
                f"%% {glyph}\n" + "0 0 moveto\nclosepath\n" * n + "stroke\nshowpage\n\n"
            )
        (o.scratch / f"out/GGPlum-{name}.ps").write_text(text)
    o.files = {
        str(p.relative_to(o.scratch)): p.stat().st_size for p in o.scratch.rglob("*.ps")
    }


def nothing_written(o):
    pass


def pages_missing(o):
    example(o)
    for rel in o.files:
        text = o.read(rel)
        (o.scratch / rel).write_text(text[: len(text) // 2])


COUNTEREXAMPLES = [nothing_written, pages_missing]
