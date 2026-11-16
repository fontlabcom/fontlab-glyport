# this_file: realuse/oracles/p-rekha.py
"""Rekha plugin bundle, general plug-in part (mekkablue--Rekha/Rekha.glyphsPlugin/
.../plugin.py: RekhaCapMenu.addRekhaCap_, _drawRekhaCap): Glyph menu "Add Rekha
Cap", enabled only for fonts with Devanagari glyphs (the harness adds an empty
ka-deva). It creates the glyph _cap.rekha and gives each master layer one open
path (0, 5) (0, -10) (100, -10) (100, 5) (100 = the default rekha thickness),
then opens a tab with /_cap.rekha. Expected: _cap.rekha exists after (not
before) with that open path in Light, Regular and Bold; the tab shows it; no
other glyph changes."""

from realuse_oracle import contours, glyph_record, layers, tab_glyphs

CAP = [(0.0, 5.0), (0.0, -10.0), (100.0, -10.0), (100.0, 5.0)]


def check(o):
    o.clause(
        "_cap.rekha created",
        glyph_record(o.before, "_cap.rekha") is None
        and glyph_record(o.after, "_cap.rekha") is not None,
    )
    for m in ("Light", "Regular", "Bold"):
        paths = contours(layers(o.after, "_cap.rekha").get(m))
        o.clause(
            f"_cap.rekha/{m}: the open cap path",
            [[(p.x, p.y) for p in c] for c in paths] == [CAP],
            paths,
        )
    o.clause(
        "the new tab shows _cap.rekha",
        tab_glyphs(o.before, o.tab) == ["_cap.rekha"],
        o.tab,
    )
    o.nothing_else_changed({"_cap.rekha"})


def example(o):
    glyph = {"name": "_cap.rekha", "layers": []}
    for m in ("Light", "Regular", "Bold"):
        glyph["layers"].append(
            {
                "name": m,
                "advanceWidth": 600,
                "elements": [
                    {
                        "elementData": {
                            "contours": [
                                {
                                    "open": True,
                                    "nodes": [f"{x:g} {y:g}" for x, y in CAP],
                                }
                            ]
                        }
                    }
                ],
            }
        )
    o.after["font"]["glyphs"].append(glyph)
    o.tab = "/_cap.rekha"


def nothing(o):  # menu item disabled or missing
    pass


def closed_square(o):
    example(o)
    for layer in o.after_glyph("_cap.rekha")["layers"]:
        layer["elements"][0]["elementData"]["contours"][0]["nodes"] = [
            "0 0",
            "100 0",
            "100 100",
            "0 100",
        ]


COUNTEREXAMPLES = [nothing, closed_square]
