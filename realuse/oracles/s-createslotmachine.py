# this_file: realuse/oracles/s-createslotmachine.py
"""Create Slot Machine (kylewaynebenson--Glyphs-Scripts/Paths/CreateSlotMachine.py:
SlotMachineMain), defaults: top crop Cap Height (688), bottom Baseline, Y shift
100, gap 20, current master only. For A/Regular the outline is moved up by 100,
cut at 678 and 698; the lower part moves up by 10 (now 110..688) and the part
above 698 wraps to the bottom (0..90). Expected: A/Regular spans y 0..688 with a
20-unit empty band between 90 and 110, at least one node on each cut line, the
base keeps A's x extent (13..585), width and anchors unchanged; Light and Bold
and all other glyphs unchanged; Output names A."""

from realuse_oracle import Pt, anchors, bounds, close, contours, points, set_contours


def check(o):
    pts = points(o.la("A"))
    box = bounds([p for p in pts if p.on])
    o.clause(
        "A/Regular: outline spans y 0..688",
        box is not None and close(box[1], 0, 1) and close(box[3], 688, 1),
        box,
    )
    o.clause(
        "A/Regular: empty band between y 90 and 110 (the gap)",
        bool(pts) and not any(90.5 < p.y < 109.5 for p in pts),
        sorted({p.y for p in pts}),
    )
    o.clause(
        "A/Regular: nodes on both cut lines (y 90 and y 110)",
        any(close(p.y, 90) for p in pts) and any(close(p.y, 110) for p in pts),
    )
    base = [p for p in pts if p.on and p.y >= 109.5]
    o.clause(
        "A/Regular: shifted base keeps A's x extent 13..585",
        bool(base)
        and close(min(p.x for p in base), 13, 1)
        and close(max(p.x for p in base), 585, 1),
        bounds(base),
    )
    o.clause(
        "A/Regular: width and anchors unchanged",
        o.la("A").get("advanceWidth") == o.lb("A").get("advanceWidth")
        and anchors(o.la("A")) == anchors(o.lb("A")),
    )
    o.clause(
        "Output names A", "Created slot machine effect for: A" in o.text, o.text[-200:]
    )
    o.only_layer_changed("A")
    o.nothing_else_changed({"A"})


def example(o):
    # A/Regular after the effect, drawn by hand: base 0..578 lifted to 110..688,
    # apex 598..688 wrapped to 0..90 (A's sides cut at those heights).
    base = [
        Pt(13, 110),
        Pt(100, 110),
        Pt(173, 337),
        Pt(422, 337),
        Pt(495, 110),
        Pt(585, 110),
        Pt(550, 688),
        Pt(48, 688),
    ]
    counter = [Pt(196, 409), Pt(297, 688), Pt(399, 409)]
    apex = [Pt(275, 0), Pt(323, 0), Pt(352, 90), Pt(246, 90)]
    set_contours(o.edit_layer("A"), [base, counter, apex])
    o.output = ["Created slot machine effect for: A\n"]


def unchanged(o):
    pass


def shifted_only(o):
    layer = o.edit_layer("A")
    set_contours(
        layer, [[Pt(p.x, p.y + 100, p.on) for p in c] for c in contours(layer)]
    )
    o.output = ["Created slot machine effect for: A\n"]


COUNTEREXAMPLES = [unchanged, shifted_only]
