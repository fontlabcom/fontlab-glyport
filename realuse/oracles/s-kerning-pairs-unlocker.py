# this_file: realuse/oracles/s-kerning-pairs-unlocker.py
"""Kerning pairs Unlocker (lexislav--Kerning-pair-unlocker/kerning pairs
unlocker.py: AppWorker.unlockKerning), driven with the pair "A C", lock side Left,
correction 0, all masters. A C is kerned class to class in plum-var (A's first-
side class L_A against C's second-side class R_C). Locking the left side keeps
A's class and writes an exception against the glyph C with the current value.
Expected in every master: an entry from A's left class to the glyph C holding
the value the pair had before; the effective A C kerning is unchanged; no glyph
changes.

Ruled point (controller, round 32 a8d57f1): in Glyphs 3, kerningForPair returns None
for a missing pair, so unlockKerning's `> int` comparison raises TypeError before any
exception is written. When that traceback is in the Output, the faithful Glyphs 3 result
up to the ruled point is: no kerning and no glyph changed (the classify_if rule then
classifies the run)."""

from realuse_oracle import kern_value, kerning, kerning_classes, masters

RULED_ERROR = "TypeError: '>' not supported between instances of 'NoneType' and 'int'"


def check(o):
    if RULED_ERROR in o.text:
        for m in masters(o.before):
            o.clause(
                f"{m}: kerning unchanged up to the ruled TypeError",
                kerning(o.after, m) == kerning(o.before, m),
            )
        o.clause("no glyph changed", not o.touched(), sorted(o.touched())[:10])
        return
    for m in masters(o.before):
        before = kern_value(o.before, m, "A", "C")
        classes = [
            k
            for k, (first, names) in kerning_classes(o.after, m).items()
            if first and "A" in names
        ]
        pairs = kerning(o.after, m)
        got = [float(pairs[k]["C"]) for k in classes if "C" in pairs.get(k, {})]
        o.clause(
            f"{m}: A's left class -> C exception = {before:g}",
            got == [before],
            {"got": got, "classes": classes},
        )
        o.clause(
            f"{m}: effective A C kerning unchanged",
            kern_value(o.after, m, "A", "C") == before,
        )
    o.clause("no glyph changed", not o.touched(), sorted(o.touched())[:10])


def example(o):
    for m in o.after["font"]["masters"]:
        name = m["fontMaster"]["name"]
        m["fontMaster"]["kerning"]["pairs"]["@L_A"]["C"] = str(
            int(kern_value(o.before, name, "A", "C"))
        )


def unchanged(o):
    pass


def current_master_only(o):
    m = next(
        m for m in o.after["font"]["masters"] if m["fontMaster"]["name"] == "Regular"
    )
    m["fontMaster"]["kerning"]["pairs"]["@L_A"]["C"] = str(
        int(kern_value(o.before, "Regular", "A", "C"))
    )


def ruled_error_after_partial_write(o):
    """The ruled TypeError, but an exception was written before it: rejected."""
    current_master_only(o)
    o.output = ["Traceback ...\n" + RULED_ERROR]


COUNTEREXAMPLES = [unchanged, current_master_only, ruled_error_after_partial_write]
