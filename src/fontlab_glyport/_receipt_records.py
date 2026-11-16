# this_file: src/fontlab_glyport/_receipt_records.py
"""Immutable receipt facts keep execution evidence independent of any host API."""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from types import MappingProxyType
from typing import Literal, cast

Status = Literal["unexecuted", "passed", "failed", "blocked", "not_applicable"]
Severity = Literal["info", "warning", "error"]


def _json_value(value: object) -> object:
    """Copy typed records into JSON containers without sharing mutable state."""
    if is_dataclass(value):
        return {
            item.name: _json_value(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


class _Record:
    """Freeze collection inputs and export fresh JSON-compatible containers."""

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, Mapping):
                object.__setattr__(self, item.name, MappingProxyType(dict(value)))
            elif isinstance(value, list):
                object.__setattr__(self, item.name, tuple(value))

    def to_dict(self) -> dict:
        """Return an independent JSON record; validation is an explicit boundary."""
        return cast(dict, _json_value(self))


@dataclass(frozen=True)
class ReceiptSource(_Record):
    """Identify original source; dirty paths remain relative to its repository."""

    repository: str | None
    revision: str | None
    relative_path: str
    sha256: str | None
    dirty_files: Mapping[str, str]


@dataclass(frozen=True)
class ReceiptEnvironment(_Record):
    """Record observed host facts, using explained nulls for unavailable facts."""

    host: str | None
    host_build: str | None
    python: str | None
    qt: str | None
    os: str | None
    arch: str | None


@dataclass(frozen=True)
class ReceiptAdapter(_Record):
    """Pin the adapter and transformation pipeline independently of the host."""

    version: str
    profile: str | None
    pipeline_version: str


@dataclass(frozen=True)
class SourceMap(_Record):
    """Identify a file containing generated-to-original line/column span mappings."""

    path: str
    sha256: str


@dataclass(frozen=True)
class Adaptation(_Record):
    """Bind an ordered transformation and its reason to both byte identities."""

    id: str
    reason: str
    input_sha256: str
    output_sha256: str
    source_map: SourceMap | None


@dataclass(frozen=True)
class RoleReason(_Record):
    """Explain non-applicability through the source's role, never missing support."""

    role: str
    reason: str


@dataclass(frozen=True)
class Capability(_Record):
    """Report evidence for a capability; requested features cannot be exempted."""

    id: str
    status: Status
    evidence: tuple[str, ...]
    requested: bool = field(default=True, metadata={"optional": True})
    reason: RoleReason | None = field(default=None, metadata={"optional": True})


@dataclass(frozen=True)
class Stage(_Record):
    """Describe a stage and UTC times without inventing execution timestamps."""

    name: str
    status: Status
    started_at: str | None
    finished_at: str | None
    evidence: tuple[str, ...]
    requested: bool = field(default=True, metadata={"optional": True})
    reason: RoleReason | None = field(default=None, metadata={"optional": True})


@dataclass(frozen=True)
class Artifact(_Record):
    """Bind an output kind and path to its content hash when available."""

    kind: str
    path: str
    sha256: str | None


@dataclass(frozen=True)
class SourceLocation(_Record):
    """Locate original source using one-based lines and columns when known."""

    path: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class ReceiptDiagnostic(_Record):
    """Preserve failure context; field identifies an unavailable receipt fact."""

    code: str
    severity: Severity
    message: str
    location: SourceLocation | None = None
    capability: str | None = None
    recovery_action: str | None = None
    field: str | None = field(default=None, metadata={"optional": True})
