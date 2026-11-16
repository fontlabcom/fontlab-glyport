# this_file: realuse/oracles/s-latindiacriticsgeneratorpro.py
"""Latin Diacritics Glyph Generator Pro (diegommaldo--Glyphs-Scripts/Production/
LatinDiacriticsGeneratorPro.py: generate_diacritics, ensure_combining_mark),
"Generate Accented Glyphs" with the defaults: scope = selected glyphs (A),
upper- and lowercase, region Portuguese (its diacritics ticked), missing
combining marks generated (with .case marks), existing glyphs kept. plum-var
already has A's Portuguese composites, so A's composites are skipped; the
missing combining marks (e.g. acutecomb, acutecomb.case) are created as new,
empty glyphs named and encoded from Glyphs' glyph data, each logged as "Mark
created: <name>". Expected: the new glyphs are exactly the logged marks (at
least one), the plain marks carry their combining code point, any new composite
of A uses A as its first component, and no existing glyph changes."""

import re

from realuse_oracle import components, glyph_record, layers

CODES = {
    "gravecomb": "0300",
    "acutecomb": "0301",
    "circumflexcomb": "0302",
    "tildecomb": "0303",
    "dieresiscomb": "0308",
    "cedillacomb": "0327",
    "caroncomb": "030c",
    "ringcomb": "030a",
}


def added(o):
    names = {g["name"] for g in o.before["font"]["glyphs"]}
    return sorted(
        g["name"] for g in o.after["font"]["glyphs"] if g["name"] not in names
    )


def check(o):
    logged = sorted(set(re.findall(r"Mark created: (\S+)", o.text)))
    new = added(o)
    marks = [n for n in new if "comb" in n]
    o.clause(
        "missing combining marks were created and logged",
        bool(logged) and sorted(marks) == logged,
        {"logged": logged, "new": new[:20]},
    )
    o.clause(
        "plain marks carry their combining code point",
        all(
            str(glyph_record(o.after, n).get("unicode", "")).lower() == CODES[n]
            for n in marks
            if n in CODES
        ),
        {n: glyph_record(o.after, n).get("unicode") for n in marks if n in CODES},
    )
    composites = [n for n in new if "comb" not in n]
    o.clause(
        "any new composite of A starts with component A",
        all(
            components(la)[:1] == ["A"]
            for n in composites
            for la in layers(o.after, n).values()
        ),
        composites,
    )
    # new glyphs change the font's glyphsCount (calibrated 2026-10-16, as s-interpolate...)
    o.nothing_else_changed(set(new), font={"glyphsCount"} if new else frozenset())


def example(o):
    for name in ("acutecomb", "acutecomb.case", "tildecomb", "tildecomb.case"):
        record = {
            "name": name,
            "layers": [
                {"name": m, "advanceWidth": 0} for m in ("Light", "Regular", "Bold")
            ],
        }
        if name in CODES:
            record["unicode"] = CODES[name]
        o.after["font"]["glyphs"].append(record)
    log = ["acutecomb", "acutecomb.case", "tildecomb", "tildecomb.case"]
    o.output = ["".join(f"Mark created: {n}\n" for n in log) + "\n–––> STEP 2 <––––\n"]


def nothing(o):
    pass


def unlogged_extra(o):
    example(o)
    o.after["font"]["glyphs"].append({"name": "gravecomb", "layers": []})


COUNTEREXAMPLES = [nothing, unlogged_extra]
