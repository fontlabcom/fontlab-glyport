# this_file: realuse/oracles/s-report-glyphs-with-acute-node.py
"""Report Glyphs with Acute Node (Tosche--Glyphs-Scripts/Path/Report Glyphs with
Acute Node.py:17): the script calls the layer's selection as a method (a Glyphs 2
API). In Glyphs 3 and 4 the selection is a list property, so Glyphs itself stops
at that line with a TypeError before printing anything (controller ruling:
corpus defect). The faithful result is therefore that TypeError at line 17, no
report line and an unchanged font."""


def check(o):
    run = o.extra.get("run", {})
    o.clause(
        "stops like Glyphs: TypeError at the script's line 17 (selection called)",
        run.get("error") == "TypeError"
        and any(
            "Report Glyphs with Acute Node.py:17" in f for f in run.get("frames", [])
        ),
        {k: run.get(k) for k in ("error", "message", "frames")},
    )
    o.clause("no report printed", "very acute corner" not in o.text, o.text[-300:])
    o.unchanged()


def example(o):
    o.extra = {
        "run": {
            "error": "TypeError",
            "message": "object is not callable",
            "frames": ["Report Glyphs with Acute Node.py:17 in <module>"],
        }
    }


def ran_through(o):  # a shim that made selection callable would hide the defect
    o.extra = {"run": {}}
    o.output = [
        "Following glyphs have a very acute corner point, at less than 15 degrees:\n"
    ]


COUNTEREXAMPLES = [ran_through]
