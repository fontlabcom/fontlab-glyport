# this_file: realuse/oracles/s-export-trial-version.py
"""Export Trial Version (HugoJourdan--Glyph-Script/Export/Export Trial
Version.py: buttonGenerateCallback). "Select Save Folder" is answered with the
run's scratch "out" folder, then "Generate trials" with the default format TTF.
The script marks for export only glyphs whose name occurs in its trial glyph
set text (a substring test, as written), removes the features, generates every
active instance under the name "<instance>-Trial", then restores export flags,
features and classes. Expected: one TrueType file per instance (3) with "Trial"
in its name, each holding exactly that glyph subset, the "All exports are done"
message, and the font unchanged afterwards."""

from realuse_oracle import instances, sfnt_glyph_count

TRIAL = (
    "A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z, "
    "a, b, c, d, e, f, g, h, i, j, k, l, m, n, o, p, q, r, s, t, u, v ,w, x, y, z, "
    "zero, one, two, three, four, five, six, seven, eight, nine, space, comma, period, "
    "parenleft, parenright, exclam, question, at, ampersand, .notdef"
)


def subset(o):
    return [g["name"] for g in o.before["font"]["glyphs"] if g["name"] in TRIAL]


def check(o):
    fonts = sorted(
        n
        for n in o.files
        if n.lower().endswith((".ttf", ".otf")) and "trial" in n.lower()
    )
    want = len(instances(o.before))
    o.clause(
        f"one trial font per instance ({want})",
        len(fonts) == want,
        sorted(o.files)[:10],
    )
    n = len(subset(o))
    counts = {f: sfnt_glyph_count((o.scratch / f).read_bytes()) for f in fonts}
    o.clause(
        f"each trial font holds the {n} trial glyphs",
        bool(counts) and all(c == n for c in counts.values()),
        counts,
    )
    o.clause(
        "'All exports are done' message",
        any("All exports are done" in d for d in o.dialogs),
        o.dialogs,
    )
    o.unchanged()


def ttf(n):
    import struct

    maxp = struct.pack(">IH", 0x00005000, n)
    head = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 16, 0, 0)
    return head + struct.pack(">4sIII", b"maxp", 0, 28, len(maxp)) + maxp


def example(o):
    import tempfile
    from pathlib import Path

    o.scratch = Path(tempfile.mkdtemp(prefix="trial-oracle-"))
    (o.scratch / "out").mkdir()
    for name, _ in instances(o.before):
        (o.scratch / f"out/GGPlum-{name}-Trial.ttf").write_bytes(ttf(len(subset(o))))
    o.files = {
        str(p.relative_to(o.scratch)): p.stat().st_size
        for p in o.scratch.rglob("*.ttf")
    }
    o.dialogs = ["message: Trial Exports: All exports are done"]


def full_fonts(o):  # subset ignored
    example(o)
    for rel in o.files:
        (o.scratch / rel).write_bytes(ttf(205))


def nothing(o):
    pass


COUNTEREXAMPLES = [full_fonts, nothing]
