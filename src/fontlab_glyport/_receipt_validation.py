# this_file: src/fontlab_glyport/_receipt_validation.py
"""Validate the receipt records directly so field types have one authority."""

import re
from collections.abc import Iterator, Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import PureWindowsPath
from types import UnionType
from typing import Literal, get_args, get_origin, get_type_hints

_HASH = re.compile(r"[0-9a-f]{64}")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
_CODE = re.compile(r"[A-Z][A-Z0-9_]*")
_PRIVATE = re.compile(
    r"(?:^|[\s(=:,;\[\{\"'`])(?:/(?!/)(?=\S|$)|\\|[A-Za-z]:[/\\]|"
    r"~[^/\\\s]*(?:[/\\]|$)|\$HOME(?:[/\\]|$)|\$\{HOME\}|%USERPROFILE%)|"
    r"file://|(?<!:)//(?=\S)",
    re.IGNORECASE,
)


def _relative(value: str) -> bool:
    """Check portable relative provenance without resolving filesystem paths."""
    return bool(value.strip()) and not (
        value.startswith(("/", "\\", "~", "$", "%"))
        or PureWindowsPath(value).drive
        or ".." in value.replace("\\", "/").split("/")
        or "\x00" in value
    )


def _string(value: str, path: str, errors: list[str]) -> None:
    """Validate receipt-specific strings after their JSON type is established."""
    if not value.strip():
        errors.append(f"{path}: must be a nonempty string")
    if path.endswith("sha256") and not _HASH.fullmatch(value):
        errors.append(f"{path}: must be a lowercase 64-hex SHA-256")
    if path.endswith(".code") and not _CODE.fullmatch(value):
        errors.append(f"{path}: must be a stable uppercase code")
    if path == "source.relative_path" and not _relative(value):
        errors.append(f"{path}: must be a relative path without parent traversal")
    if path.endswith((".started_at", ".finished_at")):
        try:
            if not _TIME.fullmatch(value):
                raise ValueError
            datetime.fromisoformat(value)
        except ValueError:
            errors.append(f"{path}: must be a valid ISO 8601 UTC timestamp ending in Z")


def _record(value: object, kind: type, path: str, errors: list[str]) -> None:
    """Check every declared field and reject silent misspellings in version one."""
    if not isinstance(value, dict):
        errors.append(f"{path or 'receipt'}: must be an object")
        return
    hints = get_type_hints(kind)
    for key in value.keys() - hints.keys():
        errors.append(f"{path + '.' if path else ''}{key}: unknown field")
    for item in fields(kind):
        child = f"{path}.{item.name}" if path else item.name
        if item.name not in value:
            if not item.metadata.get("optional"):
                errors.append(f"{child}: required key is missing")
        else:
            _value(value[item.name], hints[item.name], child, errors)


def _value(value: object, kind: object, path: str, errors: list[str]) -> None:
    """Validate only JSON shapes used by the typed receipt, without coercion."""
    origin, args = get_origin(kind), get_args(kind)
    if origin is UnionType:
        if value is not None:
            _value(
                value, next(arg for arg in args if arg is not type(None)), path, errors
            )
    elif origin is Literal:
        if not any(type(value) is type(option) and value == option for option in args):
            errors.append(f"{path}: must be one of {args!r}")
    elif is_dataclass(kind):
        _record(value, kind, path, errors)
    elif origin is tuple:
        if not isinstance(value, list):
            errors.append(f"{path}: must be an array")
        else:
            for index, item in enumerate(value):
                _value(item, args[0], f"{path}[{index}]", errors)
    elif origin is Mapping:
        _dirty_files(value, path, errors)
    elif type(value) is not kind:
        errors.append(f"{path}: must be {kind.__name__}")
    elif kind is str:
        _string(value, path, errors)
    elif kind is int and value < 1:
        errors.append(f"{path}: must be a positive one-based integer")


def _dirty_files(value: object, path: str, errors: list[str]) -> None:
    """Validate relative-path/hash entries without mistaking them for records."""
    if not isinstance(value, dict):
        errors.append(f"{path}: must be an object mapping relative paths to hashes")
        return
    for key, digest in value.items():
        if not isinstance(key, str) or not _relative(key):
            errors.append(f"{path}[{key!r}]: key must be a relative path")
        if not isinstance(digest, str) or not _HASH.fullmatch(digest):
            errors.append(f"{path}[{key!r}]: must be a lowercase 64-hex SHA-256")


def _leaves(value: object, path: str = "") -> Iterator[tuple[str, object]]:
    """Walk JSON leaves with stable field references for diagnostics/privacy."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{path}[{index}]")
    else:
        yield path, value


def _records(data: dict, key: str) -> list[dict]:
    """Skip malformed containers already reported by structural validation."""
    value = data.get(key)
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _context(data: dict, errors: list[str]) -> None:
    """Require explanations for unknown facts and explicit role exemptions."""
    explained = [item.get("field") for item in _records(data, "diagnostics")]
    for path, value in _leaves(data):
        if (
            value is None
            and not path.startswith("diagnostics[")
            and not path.endswith(".reason")
            and path not in explained
        ):
            errors.append(
                f"{path}: null fact requires a diagnostic with this field reference"
            )
    for key in ("capabilities", "stages"):
        for index, item in enumerate(_records(data, key)):
            if item.get("status") == "not_applicable":
                path = f"{key}[{index}]"
                if not isinstance(item.get("reason"), dict):
                    errors.append(
                        f"{path}.reason: not_applicable requires a role-based reason"
                    )
                if item.get("requested", True) is not False:
                    errors.append(
                        f"{path}.requested: requested features cannot be not_applicable"
                    )


def validate(data: dict, kind: type, *, public: bool) -> list[str]:
    """Accumulate structural errors without reading files or claiming execution."""
    errors: list[str] = []
    _record(data, kind, "", errors)
    if not isinstance(data, dict):
        return errors
    _context(data, errors)
    if public:
        for path, value in _leaves(data):
            if isinstance(value, str) and (
                _PRIVATE.search(value)
                or (path.endswith(".path") and not _relative(value))
            ):
                errors.append(
                    f"{path}: public receipts require redacted, relative paths"
                )
    return errors
