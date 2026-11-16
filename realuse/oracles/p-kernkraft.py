# this_file: realuse/oracles/p-kernkraft.py
"""Kernkraft bundle, Kernschmelze part (bBoxType--Kernkraft/Kernkraft.glyphsPlugin/
.../Kernschmelze.py: EQKerningPairs, buttonCallback): Glyph > Kernschmelze, then
"Schmelz!" with the defaults: source masters A = Light and B = Regular, no target
master ticked. The run always equalises the two sources: every pair kerned in
only one of them is added to the other with value 0. Expected: Light and Regular
end with the same set of pairs (the union of their pairs before), every value
that existed is unchanged, the added ones are 0; Bold's kerning and all glyphs
are unchanged."""

import copy

from realuse_oracle import kerning


def flat(pairs):
    return {
        (left, right): float(v)
        for left, rights in pairs.items()
        for right, v in rights.items()
    }


def check(o):
    light, regular = (
        flat(kerning(o.before, "Light")),
        flat(kerning(o.before, "Regular")),
    )
    union = light.keys() | regular.keys()
    for name, old in (("Light", light), ("Regular", regular)):
        new = flat(kerning(o.after, name))
        o.clause(
            f"{name}: kerned pairs = union of Light and Regular ({len(union)})",
            new.keys() == union,
            {
                "missing": sorted(union - new.keys())[:5],
                "extra": sorted(new.keys() - union)[:5],
            },
        )
        o.clause(
            f"{name}: old values kept, added pairs are 0",
            all(new.get(k) == old.get(k, 0.0) for k in union),
            [
                (k, old.get(k), new.get(k))
                for k in union
                if new.get(k) != old.get(k, 0.0)
            ][:5],
        )
    o.clause(
        "Bold kerning unchanged", kerning(o.after, "Bold") == kerning(o.before, "Bold")
    )
    o.clause("no glyph changed", not o.touched(), sorted(o.touched())[:5])


def example(o):
    light, regular = (
        flat(kerning(o.before, "Light")),
        flat(kerning(o.before, "Regular")),
    )
    for m in o.after["font"]["masters"]:
        name = m["fontMaster"]["name"]
        if name in ("Light", "Regular"):
            old = light if name == "Light" else regular
            pairs = m["fontMaster"]["kerning"]["pairs"]
            for left, right in light.keys() | regular.keys():
                if (left, right) not in old:
                    pairs.setdefault(left, {})[right] = "0"


def unchanged(o):
    pass


def bold_too(o):
    example(o)
    bold = next(
        m for m in o.after["font"]["masters"] if m["fontMaster"]["name"] == "Bold"
    )
    bold["fontMaster"]["kerning"] = copy.deepcopy(
        next(
            m for m in o.after["font"]["masters"] if m["fontMaster"]["name"] == "Light"
        )["fontMaster"]["kerning"]
    )


COUNTEREXAMPLES = [unchanged, bold_too]
