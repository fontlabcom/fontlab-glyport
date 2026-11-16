# this_file: src/fontlab_glyport/profiles.py
"""Conservative profile evidence; a compatibility minimum is not native proof."""

import ast
import io
import re
import tokenize
from collections.abc import Mapping
from dataclasses import dataclass

from .assessment import Diagnostic
from .profile_guards import guard_versions

PROFILES = ("auto", "glyphs2", "glyphs3", "glyphs4")


@dataclass(frozen=True)
class ProfileSelection:
    profile: str
    evidence: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]


def _source_evidence(
    raw: bytes, path: str, diagnostics: list[Diagnostic]
) -> tuple[set[int], int, bool, list[str], set[int]]:
    declared, minimum, guarded, evidence = set(), 2, False, []
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        text = raw.decode(encoding)
    except (SyntaxError, UnicodeError, LookupError) as error:
        diagnostics.append(
            Diagnostic("PROFILE_ENCODING_ERROR", "error", str(error), path, 1, 1)
        )
        return declared, minimum, guarded, evidence, {2, 3, 4}
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                match = re.search(r"\bGLYPHS_VERSION\s*[:=]\s*([234])\b", token.string)
                if match:
                    declared.add(int(match[1]))
                    evidence.append(
                        f"{path}:{token.start[0]} declared Glyphs {match[1]}"
                    )
        tree = ast.parse(text)
    except SyntaxError:
        if re.search(r"(?m)^\s*print\s+[^\s(]", text):
            declared.add(2)
            evidence.append(
                f"{path}: Python 2 print syntax suggests Glyphs 2-era source"
            )
        return declared, minimum, guarded, evidence, {2, 3, 4}
    except (UnicodeError, LookupError, tokenize.TokenError):
        return declared, minimum, guarded, evidence, {2, 3, 4}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "versionNumber":
            guarded = True
        # GSMetric/GSAxis and the unified shapes collection were introduced
        # in Glyphs 3 (docu.glyphsapp.com). This does not identify Glyphs 4.
        if (isinstance(node, ast.Attribute) and node.attr == "shapes") or (
            isinstance(node, ast.ImportFrom)
            and node.module == "GlyphsApp"
            and any(a.name in {"GSMetric", "GSAxis"} for a in node.names)
        ):
            minimum = max(minimum, 3)
            evidence.append(f"{path}:{node.lineno} Glyphs 3+ API")
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "GlyphsApp"
            and any(a.name == "GSNameParticle" for a in node.names)
        ):
            minimum = 4
            evidence.append(f"{path}:{node.lineno} Glyphs 4+ GSNameParticle API")
    allowed = guard_versions(tree)
    if guarded:
        evidence.append(f"{path}: recognized version guards allow {sorted(allowed)}")
    return declared, minimum, guarded, evidence, allowed


def select_profile(
    *,
    metadata: Mapping | None = None,
    sources: Mapping[str, bytes] | None = None,
    override: str = "auto",
) -> ProfileSelection:
    """Select a declared generation or observed minimum; retain uncertainty.

    GlyphsVersion/GSVersion declare a major version. CFBundleVersion is the
    plugin version and GSMinVersion is a build number, never a major version.
    Unknown sources remain auto in inspection; runtime defaults them to glyphs4.
    Conflicting declarations or impossible recognized guards require an override.
    """
    if override not in PROFILES:
        raise ValueError(f"Unknown Glyphs profile: {override!r}")
    declared, minimum, guarded, evidence = set(), 2, False, []
    allowed = {2, 3, 4}
    diagnostics = []
    for key in ("GlyphsVersion", "GSVersion"):
        value = (metadata or {}).get(key)
        match = re.fullmatch(r"([234])(?:\.\d+)*", str(value))
        if match:
            declared.add(int(match[1]))
            evidence.append(f"Info.plist {key}={value}")
    for path, raw in sorted((sources or {}).items()):
        versions, required, guard, facts, candidates = _source_evidence(
            raw, path, diagnostics
        )
        declared.update(versions)
        minimum = max(minimum, required)
        guarded |= guard
        evidence.extend(facts)
        allowed &= candidates
    if any("Python 2 print syntax" in fact for fact in evidence):
        diagnostics.append(
            Diagnostic(
                "PROFILE_LEGACY_SYNTAX",
                "warning",
                "Python 2 syntax suggests glyphs2; this is an era heuristic, not a declared app version.",
            )
        )
    if override != "auto":
        selected = override
        diagnostics.append(
            Diagnostic(
                "PROFILE_OVERRIDE",
                "info",
                f"Explicit profile {override}; observed evidence: {evidence!r}",
            )
        )
    elif (
        len(declared) == 1
        and next(iter(declared)) >= minimum
        and next(iter(declared)) in allowed
    ):
        selected = f"glyphs{next(iter(declared))}"
    elif declared or not any(major >= minimum for major in allowed):
        selected = "auto"
        diagnostics.append(
            Diagnostic(
                "PROFILE_AMBIGUOUS",
                "warning",
                "Conflicting declarations or version-dependent behavior; select an explicit profile.",
            )
        )
    elif guarded:
        selected = f"glyphs{max(major for major in allowed if major >= minimum)}"
        diagnostics.append(
            Diagnostic(
                "PROFILE_VERSION_GUARD",
                "info",
                f"Version guards select {selected}; prefer the Glyphs 4 reference when permitted. Explicit profiles take precedence.",
            )
        )
    elif minimum > 2:
        selected = f"glyphs{minimum}"
        diagnostics.append(
            Diagnostic(
                "PROFILE_MINIMUM",
                "warning",
                f"Glyphs {minimum}+ API selects glyphs{minimum} as a minimum; newer semantics are not inferred.",
            )
        )
    else:
        selected = "auto"
        diagnostics.append(
            Diagnostic(
                "PROFILE_UNRESOLVED",
                "warning",
                "No generation-specific evidence; runtime defaults to glyphs4 unless a profile is specified explicitly.",
            )
        )
    return ProfileSelection(selected, tuple(evidence), tuple(diagnostics))
