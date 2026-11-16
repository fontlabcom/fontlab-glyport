# this_file: src/fontlab_glyport/assessment.py
"""Immutable discovery facts, separate from native execution receipts."""

from dataclasses import asdict, dataclass
from typing import Literal

Profile = Literal["auto", "glyphs2", "glyphs3", "glyphs4"]


@dataclass(frozen=True)
class Diagnostic:
    """A source-relative limitation or malformed input with a stable code."""

    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class Dependency:
    """A lexical import, not proof of resolution or successful import."""

    module: str
    path: str
    line: int


@dataclass(frozen=True)
class SourceFile:
    """Bundle-relative file identity; symlink content is never dereferenced."""

    path: str
    kind: Literal["file", "symlink"]
    sha256: str | None
    bytes: int | None
    link_target: str | None = None


@dataclass(frozen=True)
class Assessment:
    """Static observations; required capabilities are unverified requirements."""

    source_id: str
    profile: Profile
    entrypoints: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    adaptations: tuple
    dependencies: tuple[Dependency, ...]
    diagnostics: tuple[Diagnostic, ...]
    files: tuple[SourceFile, ...]
    principal_class: str | None = None
    schema_version: int = 1
    runtime_status: Literal["unexecuted"] = "unexecuted"

    def to_dict(self) -> dict:
        """Return JSON-ready arrays without mutable references to this record."""
        result = asdict(self)
        for key in (
            "entrypoints",
            "required_capabilities",
            "adaptations",
            "dependencies",
            "diagnostics",
            "files",
        ):
            result[key] = list(result[key])
        return result
