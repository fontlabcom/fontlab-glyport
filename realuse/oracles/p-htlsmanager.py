# this_file: realuse/oracles/p-htlsmanager.py
"""HT Letterspacer Manager (eweracs--HTLSManager/HTLSManager.glyphsPlugin/.../
plugin.py: start, showWindow_): Glyph > HT Letterspacer Manager opens the
"HT LetterSpacer Manager" window: it reads every master's spacing parameters
(defaults 400/10 when absent), every glyph's master sidebearings and the
glyph categories, and builds its rule, parameter and inspector tabs. Opening it
writes nothing. Expected: that window is open after the menu action, no
traceback, and the font is unchanged."""


def check(o):
    opened = o.windows + o.extra.get("trigger", {}).get("windows", [])
    o.clause(
        "the 'HT LetterSpacer Manager' window opened",
        any("HT LetterSpacer Manager" in w for w in opened),
        opened,
    )
    o.unchanged()


def example(o):
    o.windows = ["QWidget:HT LetterSpacer Manager"]


def no_window(o):
    pass


COUNTEREXAMPLES = [no_window]
