# this_file: realuse/oracles/s-gposreport.py
"""gposreport (m4rc1e--mf-glyphs-scripts/Reports/gposreport.py), a Glyphs 2
script adapted by glyport, run on cafe (one open font). It collects anchors per
layer name (names truncated at the first dot): base anchors ("top"), mark
anchors ("_top"); then for every layer name writes a section "\\n<layer>\\n" and,
for every base glyph x mark glyph whose anchors match, the two glyphs' strings
followed by a space; the text goes to "<font file path>_gpos_strings.txt" (the
path has no .ttf/.otf to strip, so next to the owned copy) and a "Done" message
is shown. Classified as a corpus defect (see check()): it stops with TypeError at
line 106. If it ran past that point, the expected result is that file with
exactly the computed base+mark pairs in the Regular section and no pairs
elsewhere, and the font unchanged."""

from collections import Counter

from realuse_oracle import layers


def expected(vfj):
    base, mark, chars = {}, {}, {}
    for g in vfj["font"]["glyphs"]:
        code = str(g.get("unicode", "")).split(",")[0].strip()
        chars[g["name"]] = chr(int(code, 16)) if code else "None"
        for lname, layer in layers(vfj, g["name"]).items():
            for a in layer.get("anchors", []):
                gname, aname = g["name"].split(".")[0], a["name"].split(".")[0]
                target = mark if a["name"].startswith("_") else base
                target.setdefault(lname, {}).setdefault(gname, set()).add(aname)
    pairs = Counter()
    for lname, glyphs in base.items():
        for b, banchors in glyphs.items():
            for m, manchors in mark.get(lname, {}).items():
                for ba in banchors:
                    for ma in manchors:
                        if ba == ma[1:]:
                            pairs[
                                (lname, chars.get(b, "None") + chars.get(m, "None"))
                            ] += 1
    return pairs


def parse(text):
    got, section = Counter(), None
    for line in text.split("\n"):
        tokens = line.split()
        if len(tokens) == 1 and not line.endswith(" ") and line.strip() == line:
            section = line
            continue
        for t in tokens:
            got[(section, t)] += 1
    return got


def check(o):
    """Ruled corpus defect (controller, 2026-10-16): the report is opened in text
    mode and receives bytes, so Glyphs 3/4 (Python 3) stop with TypeError in main
    at line 106 as well. The faithful result is that stop, before any report text
    and before the "Done" message, with the font unchanged. If a future run gets
    past it (glyport adapting the bytes), the full report expectations apply."""
    run = o.extra.get("run", {})
    stopped = run.get("error") == "TypeError" and any(
        "gposreport.py:106" in f for f in run.get("frames", [])
    )
    if stopped:
        o.clause(
            "stops like Glyphs 3/4: TypeError writing bytes to the text-mode report (line 106)",
            True,
            {k: run.get(k) for k in ("error", "message", "frames")},
        )
        o.clause(
            "no 'Done' message", not any("Done" in d for d in o.dialogs), o.dialogs
        )
        o.unchanged()
        return
    report(o)


def report(o):
    reports = [n for n in o.files if n.endswith("_gpos_strings.txt")]
    if not o.clause(
        "the _gpos_strings.txt report was written",
        len(reports) == 1,
        sorted(o.files)[:10],
    ):
        o.unchanged()
        return
    want, got = expected(o.before), parse(o.read(reports[0]))
    o.clause(
        f"the report lists exactly the {sum(want.values())} base+mark pairs",
        got == want,
        {
            "missing": list((want - got).items())[:5],
            "extra": list((got - want).items())[:5],
        },
    )
    o.clause("'Done' message", any("Done" in d for d in o.dialogs), o.dialogs)
    o.unchanged()


def stopped_like_glyphs(o):  # the ruled outcome (example of the classified path)
    o.extra = {
        "run": {
            "error": "TypeError",
            "message": "write() argument must be str, not bytes",
            "frames": ["gposreport.py:116 in <module>", "gposreport.py:106 in main"],
        }
    }


def example(o):
    import tempfile
    from pathlib import Path

    o.scratch = Path(tempfile.mkdtemp(prefix="gpos-oracle-"))
    text = (
        "\nRegular\n"
        + "".join(f"{s} " * n for (_, s), n in expected(o.before).items())
        + "\nimg\n"
    )
    (o.scratch / "cafe.vfj_gpos_strings.txt").write_text(text)
    o.files = {"cafe.vfj_gpos_strings.txt": len(text)}
    o.dialogs = ["message: Done: Strings saved to ..."]


def empty_file(o):  # bytes written to a text file (Python 3) leave it empty
    example(o)
    (o.scratch / "cafe.vfj_gpos_strings.txt").write_text("")


def nothing(o):
    pass


def other_error(o):  # a glyport failure elsewhere is not the ruled stop
    o.extra = {"run": {"error": "TypeError", "frames": ["gposreport.py:40 in main"]}}


COUNTEREXAMPLES = [empty_file, nothing, other_error]
