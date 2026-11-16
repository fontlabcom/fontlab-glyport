# this_file: realuse/oracles/s-postino.py
"""Postino (rsztype--Scripts/Postino.py: deliver, copyGlyph), Deliver with the
defaults: every other open font ticked, replace existing glyphs. The other font
is an untouched plum-var copy; the harness first changed A/Regular in the owned
copy (nodes +15, width +30). For the selected glyph A, every master of the other
font (matched by name) receives the source's shapes, anchors, hints and width.
Expected: in the other font, A's Light, Regular and Bold equal the owned copy's
(so its Regular carries the +15/+30 change); the owned copy is unchanged."""

import copy

from realuse_oracle import Pt, anchors, contours, layers, set_contours


def check(o):
    others = o.extra.get("others") or []
    if not o.clause(
        "the other font was saved after the run", len(others) == 1, len(others)
    ):
        return
    for name in ("Light", "Regular", "Bold"):
        src, dst = layers(o.before, "A")[name], layers(others[0], "A").get(name)
        o.clause(
            f"other font A/{name} = owned copy's (paths, anchors, width)",
            dst is not None
            and contours(dst) == contours(src)
            and anchors(dst) == anchors(src)
            and dst.get("advanceWidth") == src.get("advanceWidth"),
        )
    o.unchanged()


def prepared(o):
    for vfj in (o.before, o.after):
        layer = layers(vfj, "A")["Regular"]
        set_contours(layer, [[Pt(p.x + 15, p.y) for p in c] for c in contours(layer)])
        layer["advanceWidth"] += 30


def example(o):
    other = copy.deepcopy(o.before)  # unprepared copy + delivered A
    prepared(o)
    for name in ("Light", "Regular", "Bold"):
        layers(other, "A")[name].update(copy.deepcopy(layers(o.before, "A")[name]))
    o.extra = {"others": [other]}


def not_delivered(o):
    other = copy.deepcopy(o.before)
    prepared(o)
    o.extra = {"others": [other]}


COUNTEREXAMPLES = [not_delivered]
