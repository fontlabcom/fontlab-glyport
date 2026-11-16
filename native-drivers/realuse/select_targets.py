#!/usr/bin/env python3
# this_file: native-drivers/realuse/select_targets.py
"""Rank real-use candidates in the Glyphs corpus (issue 106, lane G1).

Static and read-only: corpus files are parsed, never executed or copied. Prints
JSON ranked candidates; ``realuse/manifest.json`` records the curated selection
and the rule (this script is its first, mechanical stage).

Rule
1. Scripts: ``.py`` files outside bundles with a ``MenuTitle`` header that use
   GlyphsApp. Plugins: ``.glyphs*`` bundles whose ``PyMainFileNames`` entry
   defines a class based on one of the seven SDK protocol classes.
2. Pure Python only (D8): no compiled extension (``.so``/``.dylib``) or ``.pyc``
   next to the code, no ``objc.lookUpClass``/``NSClassFromString`` of private
   classes, no imports outside the standard library, GlyphsApp, vanilla,
   AppKit/Foundation/Cocoa/objc/Quartz and the repository's own modules.
   No effects outside FontLab that glyport does not scope: ``os.system``,
   ``os.popen``, ``subprocess``, ``webbrowser``, NSWorkspace, sockets/HTTP.
3. Score: the sum of ``log(1 + corpus frequency)`` over the distinct Glyphs API
   names the code reads (attribute names defined on GS* classes in Glyphs 4's
   shipped GlyphsApp wrapper, counted corpus-wide in corpus-capabilities.json).
4. Diversity: candidates are taken round-robin by author (the GitHub owner in
   the corpus folder name ``owner--repo``), best score first, at most two per
   author; scripts and each protocol are filled to the counts in
   realuse/curation.json. The 32 regression-matrix targets are excluded (they
   are re-run separately); curated exclusions (with reasons) are skipped and
   the next candidate fills in.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import plistlib
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

# The workspace (worktree or main checkout) holds the static corpus evidence.
EVIDENCE = next(
    (
        p / "verification/issue-101-ecosystem/evidence"
        for p in Path(__file__).resolve().parents
        if (p / "verification/issue-101-ecosystem/evidence").is_dir()
    ),
    None,
)
CORPUS = (
    Path(os.environ["GLYPORT_ORIGINAL_CORPUS"])
    if "GLYPORT_ORIGINAL_CORPUS" in os.environ
    else (EVIDENCE.parents[2] / "reference-glyphs-plugins" if EVIDENCE else None)
)
WRAPPER = os.environ.get("GLYPORT_GLYPHS_WRAPPER")
PROTOCOLS = (
    "GeneralPlugin",
    "FilterWithoutDialog",
    "FilterWithDialog",
    "ReporterPlugin",
    "PalettePlugin",
    "SelectTool",
    "FileFormatPlugin",
)
HOST_MODULES = {
    "GlyphsApp",
    "vanilla",
    "AppKit",
    "Foundation",
    "Cocoa",
    "objc",
    "Quartz",
    "PyObjCTools",
}
PRIVATE = re.compile(r"lookUpClass|NSClassFromString|loadBundle|ctypes")
SIDE_EFFECTS = re.compile(
    r"os\.system|os\.popen|\bsubprocess\b|\bwebbrowser\b|NSWorkspace|\burllib\b|\bsocket\b|\brequests\b"
)
MENU_TITLE = re.compile(r"^#\s?MenuTitle\s*:", re.MULTILINE)


def vocabulary() -> set[str]:
    """Attribute names Glyphs 4's GlyphsApp wrapper defines on GS* classes."""
    if WRAPPER is None:
        raise ValueError(
            "Set GLYPORT_GLYPHS_WRAPPER to the retained upstream Python wrapper"
        )
    text = Path(WRAPPER).read_text(encoding="utf-8", errors="replace")
    return set(
        re.findall(r"^(?:GS\w+|GlyphsApplication)\.(\w+)\s*=", text, re.MULTILINE)
    ) - {"__init__"}


def names_used(source: str) -> tuple[set[str], set[str], bool]:
    """(attribute names, top-level imported modules, parsed as Python 3)."""
    try:
        with warnings.catch_warnings():  # corpus regex literals with invalid escapes
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source)
    except (SyntaxError, ValueError):  # Python 2 source: token-level fallback
        attrs = set(re.findall(r"\.([A-Za-z_]\w*)", source))
        imports = set(
            re.findall(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", source, re.MULTILINE)
        )
        return attrs, imports, False
    attrs, imports = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attrs.add(node.attr)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imports.add(node.module.split(".")[0])
    return attrs, imports, True


def foreign_imports(imports: set[str], local: set[str]) -> list[str]:
    return sorted(
        m
        for m in imports
        if m not in HOST_MODULES | local and m not in sys.stdlib_module_names
    )


def local_modules(root: Path) -> set[str]:
    """Module names a repository provides itself (files and packages anywhere in it)."""
    names = {p.stem for p in root.rglob("*.py")}
    names |= {p.parent.name for p in root.rglob("__init__.py")}
    return names | {root.name.split("--")[-1]}


def score(
    attrs: set[str], vocab: set[str], freq: dict[str, int]
) -> tuple[float, list[str]]:
    api = sorted(a for a in attrs if a in vocab)
    return round(sum(math.log1p(freq.get(a, 0)) for a in api), 2), api


def protocol_of(source: str) -> str | None:
    for base in PROTOCOLS:
        if re.search(rf"^class\s+\w+\s*\([^)]*\b{base}\b[^)]*\)", source, re.MULTILINE):
            return base
    return None


def candidates(excluded: set[str]):
    vocab = vocabulary()
    freq = json.loads((EVIDENCE / "corpus-capabilities.json").read_text())[
        "attribute_frequency"
    ]
    for repo in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        local = local_modules(repo)
        for path in sorted(repo.rglob("*")):
            rel = str(path.relative_to(CORPUS))
            if rel in excluded or ".git/" in rel:
                continue
            if path.suffix == ".py" and ".glyphs" not in rel and path.is_file():
                source = path.read_text(encoding="utf-8", errors="replace")
                if not MENU_TITLE.search(source[:2000]) or "GlyphsApp" not in source:
                    continue
                yield _row("script", None, rel, path, source, local, vocab, freq)
            elif (
                path.is_dir()
                and path.suffix.startswith(".glyphs")
                and path.suffix != ".glyphsPackage"
            ):
                row = _bundle(path, rel, local, vocab, freq, excluded)
                if row:
                    yield row


def _bundle(path, rel, local, vocab, freq, excluded):
    info = path / "Contents/Info.plist"
    if not info.is_file():
        return None
    try:
        mains = plistlib.loads(info.read_bytes()).get("PyMainFileNames") or []
    except Exception:  # noqa: BLE001 - malformed plist: not a candidate
        return None
    resources = path / "Contents/Resources"
    main = resources / mains[0] if mains else None
    if main is None or not main.is_file():
        return None
    if str(main.relative_to(CORPUS)) in excluded:
        return None
    sources = [
        p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(resources.rglob("*.py"))
    ]
    source = "\n".join(sources)
    protocol = protocol_of(source)
    if protocol is None:
        return None
    row = _row(
        "plugin",
        protocol,
        str(path.relative_to(CORPUS)),
        main,
        source,
        local,
        vocab,
        freq,
    )
    compiled = [
        p.name for p in resources.rglob("*") if p.suffix in (".so", ".dylib", ".pyc")
    ]
    if compiled:
        row["excluded"].append(
            "compiled code in bundle (D8): " + ", ".join(sorted(compiled)[:3])
        )
    return row


def _row(kind, protocol, rel, path, source, local, vocab, freq):
    attrs, imports, py3 = names_used(source)
    value, api = score(attrs, vocab, freq)
    reasons = []
    foreign = foreign_imports(imports, local)
    if foreign:
        reasons.append("third-party imports: " + ", ".join(foreign))
    if PRIVATE.search(source):
        reasons.append("private native class lookup or ctypes")
    effects = sorted(set(SIDE_EFFECTS.findall(source)))
    if effects:
        reasons.append("unscoped effects outside FontLab: " + ", ".join(effects))
    return {
        "kind": kind,
        "protocol": protocol,
        "path": rel,
        "repository": rel.split("/")[0],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "python3_syntax": py3,
        "score": value,
        "api": api,
        "uses_vanilla": "vanilla" in imports,
        "excluded": reasons,
    }


def author(row: dict) -> str:
    return row["repository"].split("--")[0]


def round_robin(rows: list[dict], per_author: int) -> list[dict]:
    """Best-scoring candidate of every author, then every author's second, ..."""
    by_author = defaultdict(list)
    for row in sorted(rows, key=lambda r: (-r["score"], r["path"])):
        by_author[author(row)].append(row)
    ordered = []
    for rank in range(per_author):
        layer = [rows[rank] for rows in by_author.values() if len(rows) > rank]
        ordered.extend(sorted(layer, key=lambda r: (-r["score"], r["path"])))
    return ordered


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def pick(ordered: list[dict], count: int, excluded: dict[str, str]) -> list[dict]:
    return [r for r in ordered if r["path"] not in excluded][:count]


def coverage(selected: list[dict], eligible: list[dict], top: int = 50) -> dict:
    """Share of the ``top`` most-used Glyphs API names (by eligible files using
    them) that the selection exercises at least once."""
    usage = defaultdict(int)
    for row in eligible:
        for name in row["api"]:
            usage[name] += 1
    ranked = [n for n, _ in sorted(usage.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]
    used = {n for row in selected for n in row["api"]}
    missing = [n for n in ranked if n not in used]
    return {"top": top, "covered": top - len(missing), "missing": missing}


def build_manifest(rows: list[dict], curation: dict) -> dict:
    eligible = [r for r in rows if not r["excluded"]]
    excluded = curation.get("exclude", {})
    scripts = pick(
        round_robin([r for r in eligible if r["kind"] == "script"], 2),
        curation["counts"]["scripts"],
        excluded,
    )
    plugins = []
    for protocol, count in curation["counts"]["plugins"].items():
        ordered = round_robin([r for r in eligible if r["protocol"] == protocol], 2)
        plugins += pick(ordered, count, excluded)
    targets, seen = [], set()
    for row in scripts + plugins:
        name = Path(row["path"]).stem
        base = ("s-" if row["kind"] == "script" else "p-") + slug(name)
        ident = base
        while ident in seen:
            ident = f"{base}-{len(seen)}"
        seen.add(ident)
        entry = {
            "id": ident,
            "kind": row["kind"],
            "protocol": row["protocol"],
            "path": row["path"],
            "sha256": row["sha256"],
            "score": row["score"],
            "python3_syntax": row["python3_syntax"],
            "fixture": "plum-var",
            "tab": "A",
        }
        if row["kind"] == "script" and row["uses_vanilla"]:
            entry["drive"] = [{"click": None}]  # the window's default/primary button
        entry.update(curation.get("targets", {}).get(row["path"], {}))
        targets.append(entry)
    return {
        "schema_version": 1,
        "issue": 106,
        "lane": "G1",
        "corpus": "reference-glyphs-plugins",
        "selection_rule": __doc__.split("Rule\n", 1)[1].strip(),
        "selection_parameters": {
            "per_author": 2,
            "counts": curation["counts"],
            "python": sys.version.split()[0],
            "vocabulary": "glyphs-wrapper-vocabulary",
        },
        "curated_exclusions": excluded,
        "coverage": coverage(scripts + plugins, eligible),
        "candidate_counts": {
            "scripts": sum(r["kind"] == "script" for r in rows),
            "eligible_scripts": sum(r["kind"] == "script" for r in eligible),
            "eligible_plugins": {
                p: sum(r["protocol"] == p for r in eligible) for p in PROTOCOLS
            },
        },
        "targets": targets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--curation", type=Path, required=True, help="realuse/curation.json"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="realuse/manifest.json"
    )
    parser.add_argument(
        "--candidates", type=Path, help="also write every ranked candidate here"
    )
    args = parser.parse_args(argv)
    if EVIDENCE is None or CORPUS is None:
        raise RuntimeError("Target selection requires the retained corpus workspace")
    matrix = json.loads((EVIDENCE / "corpus-regression-matrix.json").read_text())[
        "regression_targets"
    ]
    rows = list(candidates({row["path"] for row in matrix}))
    manifest = build_manifest(rows, json.loads(args.curation.read_text()))
    args.output.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    if args.candidates:
        args.candidates.write_text(json.dumps(rows, indent=1) + "\n")
    print(
        f"{len(manifest['targets'])} targets; coverage {manifest['coverage']['covered']}/50"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
