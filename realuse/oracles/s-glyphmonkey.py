# this_file: realuse/oracles/s-glyphmonkey.py
"""glyphmonkey (simoncozens--GlyphsScripts/glyphmonkey.py) is a helper library,
not an action: running it only adds methods to GlyphsApp classes (path
segments, node/path rotate, reflect, centres, node sets) for other scripts. In
Glyphs it prints nothing and changes no font data. Expected: the run raises
nothing (every patched class and imported name exists), the Output stays empty
and the font is unchanged."""


def check(o):
    run = o.extra.get("run", {})
    o.clause(
        "the library loads: no exception",
        "error" not in run,
        {k: run.get(k) for k in ("error", "message")},
    )
    o.clause("no Output", not o.text.strip(), o.text[-200:])
    o.unchanged()


def example(o):
    o.extra = {"run": {"state": "active"}}


def import_failed(o):
    o.extra = {"run": {"error": "ImportError", "message": "cannot import name 'Proxy'"}}


COUNTEREXAMPLES = [import_failed]
