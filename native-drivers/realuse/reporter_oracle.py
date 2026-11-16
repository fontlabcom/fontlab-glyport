# this_file: native-drivers/realuse/reporter_oracle.py
"""Shared check for reporter targets: the reporter is switched on from the View
menu, the harness paints the glyph editor and counts non-transparent overlay
pixels, switches it off and paints again. A reporter whose drawing condition
holds for the prepared glyph must draw (ink on) and stop drawing when switched
off (no ink); it never changes the font."""


def check_reporter(o, what: str) -> None:
    on, off = o.extra.get("paint") or {}, o.extra.get("paint_off") or {}
    o.clause(
        "the reporter's painter is registered while on", on.get("painters", 0) >= 1, on
    )
    o.clause(
        f"it draws {what} (ink while on)", sum(on.get("ink") or []) > 0, on.get("ink")
    )
    o.clause(
        "no drawing after it is switched off",
        bool(off) and sum(off.get("ink") or []) == 0,
        off.get("ink"),
    )
    o.unchanged()


def example_reporter(o) -> None:
    o.extra = {
        "paint": {"painters": 1, "ink": [120]},
        "paint_off": {"painters": 0, "ink": [0]},
    }


def silent(o) -> None:
    o.extra = {
        "paint": {"painters": 1, "ink": [0]},
        "paint_off": {"painters": 0, "ink": [0]},
    }


def sticky(o) -> None:
    o.extra = {
        "paint": {"painters": 1, "ink": [120]},
        "paint_off": {"painters": 1, "ink": [120]},
    }
