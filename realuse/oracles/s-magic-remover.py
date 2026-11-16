# this_file: realuse/oracles/s-magic-remover.py
"""Magic Remover script (RezaBohloul--RezaBohloul/Edit/Magic Remover.py), with
every node of A/Regular selected in an edit tab: the selected nodes are removed
from every compatible master layer (A's Light, Regular and Bold share one
structure), and paths left empty are deleted. Anchors were not selected and
stay; widths stay. Expected: A has no paths in any master, anchors and widths
unchanged, nothing else changes."""

from realuse_oracle import anchors, contours, layers


def check(o):
    for name in sorted(layers(o.before, "A")):
        lb, la = o.lb("A", name), o.la("A", name)
        o.clause(
            f"A/{name}: all paths removed",
            contours(lb) and not contours(la),
            len(contours(la)),
        )
        o.clause(
            f"A/{name}: anchors and width kept",
            anchors(la) == anchors(lb)
            and la.get("advanceWidth") == lb.get("advanceWidth"),
        )
    o.nothing_else_changed({"A"})


def example(o):
    for name in layers(o.after, "A"):
        o.edit_layer("A", name)["elements"] = []


def unchanged(o):
    pass


def current_only(o):
    o.edit_layer("A")["elements"] = []


COUNTEREXAMPLES = [unchanged, current_only]
