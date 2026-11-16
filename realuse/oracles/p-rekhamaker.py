# this_file: realuse/oracles/p-rekhamaker.py
"""RekhaMaker filter (mekkablue--Rekha/RekhaMaker.glyphsFilter/.../plugin.py:
filter, drawRekhaInLayer), Filter menu, "Insert" with the defaults: height 700,
thickness 100, overshoot 20, no decomposition (the master has no "Rekha"
parameter). It acts only on letters of Gurmukhi, Devanagari or Bengali, so the
target uses Zoto Sans Gurmukhi's ka-guru. ka-guru has no "rekha"/"rekha_stop"
anchors, so one closed counter-clockwise rectangle is added from x -20 to the
width + 20 (1293), y 700..800; no cap hints (the font has no _cap.rekha glyph).
Expected: ka-guru/Regular keeps its paths and gains exactly that rectangle;
composites built on ka-guru follow it in the host (FontLab drops their TrueType
hinting data, calibrated 2026-10-16); nothing else changes."""

from realuse_oracle import Pt, contours, same_cycle, set_contours

GLYPH = "ka-guru"
CONTEXT = {"current": [[GLYPH, "Regular"]], "tab": "/" + GLYPH}


def rekha(layer):
    w = float(layer["advanceWidth"])
    return [(-20.0, 700.0), (w + 20, 700.0), (w + 20, 800.0), (-20.0, 800.0)]


def check(o):
    before, after = contours(o.lb(GLYPH)), contours(o.la(GLYPH))
    o.clause(f"{GLYPH}: original paths kept", after[: len(before)] == before)
    added = after[len(before) :]
    want = rekha(o.lb(GLYPH))
    o.clause(
        f"{GLYPH}: one rekha rectangle added at y 700..800 from -20 to width+20",
        len(added) == 1
        and same_cycle(sorted([(p.x, p.y) for p in added[0]]), sorted(want)),
        [[(p.x, p.y) for p in c] for c in added],
    )
    o.only_layer_changed(GLYPH)
    o.nothing_else_changed({GLYPH} | o.composites_follow(GLYPH))


def example(o):
    layer = o.edit_layer(GLYPH)
    set_contours(
        layer, contours(layer) + [[Pt(x, y) for x, y in reversed(rekha(layer))]]
    )


def unchanged(o):  # glyph not recognised as Gurmukhi letter
    pass


def wrong_height(o):
    layer = o.edit_layer(GLYPH)
    set_contours(layer, contours(layer) + [[Pt(x, y + 574) for x, y in rekha(layer)]])


COUNTEREXAMPLES = [unchanged, wrong_height]
