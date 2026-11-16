# this_file: realuse/oracles/s-chequemetricas.py
"""Cheque as Metricas (diegommaldo--Glyphs-Scripts/Metricas/ChequeMetricas.py:
check_master, process_script), button "Cheque!" with the defaults: current master
(Regular), x-height and ascender checks, overshoot zones considered. It analyses
the letters named in its x-height list (a c e m n o r s u v w x z ae oe dotlessi
dotlessj) and ascender list (b d f h k l t thorn germandbls) that have shapes,
flags those whose top differs from the metric by more than the zone at that
height (plum-var has no alignment zones, so any difference counts), prints the
analysed list and opens a tab with the flagged glyphs. Expected on plum-var
Regular (x-height 478, ascender 765): 24 analysed; u v w x dotlessi sit exactly
on 478 and pass; the other 19 are flagged and shown in the new tab. The font is
unchanged."""

from realuse_oracle import bounds, has_shapes, layers, points, tab_glyphs, tab_text

ASC = ["b", "d", "f", "h", "k", "l", "t", "thorn", "germandbls"]
XH = [
    "a",
    "c",
    "e",
    "m",
    "n",
    "o",
    "r",
    "s",
    "u",
    "v",
    "w",
    "x",
    "z",
    "ae",
    "oe",
    "dotlessi",
    "dotlessj",
]


def expected(o):
    master = next(
        m["fontMaster"]
        for m in o.before["font"]["masters"]
        if m["fontMaster"]["name"] == o.layer
    )
    analysed, flagged = [], []
    for names, metric in ((ASC, master["ascender"]), (XH, master["xHeight"])):
        for name in names:
            layer = layers(o.before, name).get(o.layer)
            if not has_shapes(layer):
                continue
            analysed.append(name)
            if bounds(points(layer))[3] != metric:
                flagged.append(name)
    return sorted(analysed), sorted(flagged)


def check(o):
    analysed, flagged = expected(o)
    o.clause(
        f"Output lists the {len(analysed)} analysed glyphs",
        f"ANALISADOS ({len(analysed)}):\n{', '.join(analysed)}" in o.text,
        o.text[-600:],
    )
    o.clause(
        f"the new tab shows the {len(flagged)} flagged glyphs",
        sorted(tab_glyphs(o.before, o.tab)) == flagged,
        {"tab": o.tab[:200], "want": flagged},
    )
    o.unchanged()


def example(o):
    analysed, flagged = expected(o)
    o.output = [
        f"Relatório\n\n✅ ANALISADOS ({len(analysed)}):\n{', '.join(analysed)}\n\nValeu!\n"
    ]
    o.tab = tab_text(o.before, flagged)


def nothing_run(o):
    pass


def all_flagged(o):
    analysed, _ = expected(o)
    o.output = [f"✅ ANALISADOS ({len(analysed)}):\n{', '.join(analysed)}\n"]
    o.tab = tab_text(o.before, analysed)


COUNTEREXAMPLES = [nothing_run, all_flagged]
