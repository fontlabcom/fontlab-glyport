# this_file: src/fontlab_glyport/inspection.py
"""Read-only inspection of an original Python script or Glyphs plugin bundle."""

import hashlib
import json
import os
import plistlib
from pathlib import Path
from xml.parsers.expat import ExpatError

from .assessment import Assessment, Diagnostic, Profile, SourceFile
from .profiles import select_profile
from .source_analysis import analyze_python

BUNDLE_SUFFIXES = frozenset(
    {
        ".glyphsReporter",
        ".glyphsFilter",
        ".glyphsPlugin",
        ".glyphsPalette",
        ".glyphsFileFormat",
        ".glyphsTool",
    }
)
RESOURCE_CAPABILITIES = {
    ".xib": "ui:xib",
    ".nib": "ui:nib",
    ".car": "ui:asset-catalog",
    ".svg": "drawing:svg",
    ".pdf": "drawing:pdf",
    ".pyc": "python:bytecode",
    ".zip": "dependency:archive",
}
MACH_O_MAGIC = {
    bytes.fromhex(x)
    for x in (
        "feedface",
        "cefaedfe",
        "feedfacf",
        "cffaedfe",
        "cafebabe",
        "bebafeca",
        "cafebabf",
        "bfbafeca",
    )
}


def _paths(root: Path) -> list[Path]:
    """Enumerate deterministically without following directory symlinks."""
    found = []
    for base, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories):
            path = Path(base) / name
            if path.is_symlink():
                found.append(path)
        found.extend(Path(base) / name for name in sorted(files))
    return sorted(found, key=lambda path: path.relative_to(root).as_posix())


def _metadata(data: bytes, path: str, diagnostics: list) -> dict:
    try:
        metadata = plistlib.loads(data)
    except (plistlib.InvalidFileException, ValueError, TypeError, ExpatError) as error:
        diagnostics.append(Diagnostic("BUNDLE_PLIST_ERROR", "error", str(error), path))
        return {}
    if not isinstance(metadata, dict):
        diagnostics.append(
            Diagnostic(
                "BUNDLE_PLIST_ERROR", "error", "Expected a plist dictionary.", path
            )
        )
        return {}
    return metadata


def inspect_source(path: str | Path, *, profile: Profile = "auto") -> Assessment:
    """Assess requirements without native imports, mutation or execution.

    Profiles select intended compatibility from metadata and source evidence.
    Discovery does not certify import, adaptation, UI or semantic outcomes.
    """
    if profile not in {"auto", "glyphs2", "glyphs3", "glyphs4"}:
        raise ValueError(f"Unknown Glyphs profile: {profile!r}")
    source = Path(path).expanduser().absolute()
    if not source.exists():
        raise FileNotFoundError(source)
    bundle = source.is_dir() and source.suffix in BUNDLE_SUFFIXES
    if not bundle and not (
        source.is_file() and source.suffix in {".py", ".pyc", ".zip"}
    ):
        raise ValueError("Expected a Python script or Glyphs bundle.")
    if source.is_symlink():
        raise ValueError(
            "Resolve the source root symlink explicitly before inspection."
        )
    root = source if bundle else source.parent
    candidates = _paths(source) if bundle else [source]
    files, dependencies, diagnostics, capabilities, entrypoints = (
        [],
        [],
        [],
        set(),
        set(),
    )
    metadata, script_hash, sources = {}, None, {}
    for candidate in candidates:
        relative = candidate.relative_to(root).as_posix()
        if candidate.is_symlink():
            files.append(
                SourceFile(relative, "symlink", None, None, os.readlink(candidate))
            )
            diagnostics.append(
                Diagnostic(
                    "SYMLINK_UNRESOLVED",
                    "warning",
                    "Link target not inspected.",
                    relative,
                )
            )
            continue
        data = candidate.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        files.append(SourceFile(relative, "file", digest, len(data)))
        if not bundle:
            script_hash = digest
        for part in Path(relative).parts:
            capability = RESOURCE_CAPABILITIES.get(Path(part).suffix)
            if capability:
                capabilities.add(capability)
        if data[:4] in MACH_O_MAGIC:
            capabilities.add("native:mach-o")
        if relative == "Contents/Info.plist":
            metadata = _metadata(data, relative, diagnostics)
        if candidate.suffix == ".py":
            sources[relative] = data
            imports, required, issues, classes = analyze_python(data, relative)
            dependencies.extend(imports)
            capabilities.update(required)
            diagnostics.extend(issues)
            if not bundle or classes:
                entrypoints.add(relative)
        elif candidate.suffix == ".pyc":
            from .adaptation_entries import check_pyc
            from .errors import DependencyUnavailable

            try:
                check_pyc(data, relative)
            except DependencyUnavailable as error:
                diagnostics.append(
                    Diagnostic("PYC_VERSION_UNSUPPORTED", "error", str(error), relative)
                )
            if not bundle:
                entrypoints.add(relative)
        elif candidate.suffix == ".zip":
            from .adaptation_entries import archive_members
            from .errors import DependencyUnavailable

            try:
                members = archive_members(candidate)
                for name, raw in members:
                    if name.endswith(".py"):
                        sources[relative + "!/" + name] = raw
                    if name in {"__main__.py", "__main__.pyc"} and not bundle:
                        entrypoints.add(relative + "!/" + name)
            except DependencyUnavailable as error:
                diagnostics.append(
                    Diagnostic("ARCHIVE_UNSUPPORTED", "error", str(error), relative)
                )
    if bundle:
        _bundle_entrypoints(metadata, files, entrypoints, diagnostics, capabilities)
    diagnostics.append(
        Diagnostic(
            "STATIC_INSPECTION_ONLY",
            "info",
            "Imports and capabilities are observations; runtime behavior is unexecuted.",
        )
    )
    selection = select_profile(metadata=metadata, sources=sources, override=profile)
    profile = selection.profile
    diagnostics.extend(selection.diagnostics)
    payload = json.dumps(
        [file.__dict__ for file in files],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    source_id = (
        script_hash if not bundle else hashlib.sha256(payload.encode()).hexdigest()
    )
    principal = metadata.get("NSPrincipalClass")
    return Assessment(
        source_id,
        profile,
        tuple(sorted(entrypoints)),
        tuple(sorted(capabilities)),
        (),
        tuple(dependencies),
        tuple(diagnostics),
        tuple(files),
        principal if isinstance(principal, str) else None,
    )


def _bundle_entrypoints(
    metadata: dict, files: list, entries: set, diagnostics: list, capabilities: set
) -> None:
    names = metadata.get("PyMainFileNames", [])
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        diagnostics.append(
            Diagnostic(
                "BUNDLE_ENTRYPOINT_ERROR",
                "error",
                "PyMainFileNames must be an array of names.",
            )
        )
        names = []
    available = {file.path for file in files if file.kind == "file"}
    for name in names:
        path = "Contents/Resources/" + name
        if path in available and Path(name).suffix in {".py", ".pyc"}:
            entries.add(path)
        else:
            diagnostics.append(
                Diagnostic(
                    "BUNDLE_ENTRYPOINT_ERROR",
                    "error",
                    "Declared Python entrypoint is unavailable.",
                    path,
                )
            )
    if not any(
        file.path.endswith((".py", ".pyc")) and file.kind == "file" for file in files
    ):
        capabilities.add("native:bundle")
        diagnostics.append(
            Diagnostic(
                "NATIVE_ROUTE_REQUIRED",
                "warning",
                "No Python source is present; a native support route is required.",
            )
        )
