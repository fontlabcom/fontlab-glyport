# this_file: src/fontlab_glyport/glyphsapp/defaults.py
"""``Glyphs.defaults``/``boolDefaults``/``intDefaults`` over an injected mapping.

Coercion mirrors NSUserDefaults ``boolForKey:``/``integerForKey:`` as used by the
Glyphs SDK wrapper (GlyphsApp/__init__.py ``BoolDefaultsProxy``/``IntDefaultsProxy``):

- bool: missing/None -> False; bool as is; int/float -> nonzero; str -> True when,
  after leading whitespace, an optional sign and leading zeros, it starts with
  Y, y, T, t or a digit 1-9 (NSString ``boolValue``); anything else -> False.
- int: missing/None -> 0; bool -> 0/1; int as is; finite float -> truncated
  toward zero; non-finite float -> 0; str -> its leading optionally signed
  digits (``"3.7"`` -> 3, ``"x1"`` -> 0, NSString ``integerValue``); else 0.
"""

import json
import math
import os
import re
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

Store = MutableMapping[str, Any]
_LEADING_INT = re.compile(r"\s*([+-]?[0-9]+)")


def _key(key: object) -> str:
    if not isinstance(key, str):
        raise TypeError(f"defaults key must be str, not {type(key).__name__}")
    return key


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.lstrip().lstrip("+-").lstrip("0")
        return bool(text) and text[0] in "YyTt123456789"
    return False


def as_int(value: object) -> int:
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else 0
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        match = _LEADING_INT.match(value)
        return int(match.group(1)) if match else 0
    return 0


class Defaults:
    """Untyped access: a missing key reads None; assigning None deletes."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def _read(self, value: object) -> object:
        return value

    def _write(self, value: object) -> object:
        return value

    def __getitem__(self, key: str) -> Any:
        return self._read(self._store.get(_key(key)))

    def __setitem__(self, key: str, value: Any) -> None:
        if value is None:
            self._store.pop(_key(key), None)
        else:
            self._store[_key(key)] = self._write(value)

    def __delitem__(self, key: str) -> None:
        self._store.pop(_key(key), None)

    def get(self, key: str, default: Any = None) -> Any:
        value = self._store.get(_key(key))
        return default if value is None else self._read(value)

    def __repr__(self) -> str:
        return "<Userdefaults>"


class BoolDefaults(Defaults):
    """``Glyphs.boolDefaults``: reads coerce to bool; writes accept bool or None."""

    def _read(self, value: object) -> bool:
        return as_bool(value)

    def _write(self, value: object) -> bool:
        if not isinstance(value, bool):
            raise TypeError(
                f"boolDefaults accepts bool or None, not {type(value).__name__}"
            )
        return value


class IntDefaults(Defaults):
    """``Glyphs.intDefaults``: reads coerce to int; writes accept int/float or None."""

    def _read(self, value: object) -> int:
        return as_int(value)

    def _write(self, value: object) -> int:
        if not isinstance(value, (int, float)):
            raise TypeError(
                f"intDefaults accepts int, float or None, not {type(value).__name__}"
            )
        return int(value)


class ColorDefaults(Defaults):
    """``Glyphs.colorDefaults``: NSColor values stored as ``[r, g, b, a]``."""

    def _read(self, value: object) -> Any:
        from ..drawing.cocoa_drawing import NSColor

        if isinstance(value, (list, tuple)) and len(value) == 4:
            return NSColor(*value)
        return None

    def _write(self, value: object) -> list:
        rgba = getattr(value, "rgba", None)
        if rgba is None:
            raise TypeError(
                f"colorDefaults expects an NSColor, not {type(value).__name__}"
            )
        return list(rgba)


def register_default(store: Store, key: str, value: Any) -> None:
    """Set ``key`` only when absent (simplified registration; see README)."""
    if key is None or value is None or len(key) <= 2:
        raise KeyError("Invalid key or value for registerDefault")
    store.setdefault(_key(key), value)


# Owner ruling (issue 104): outside the FontLab 9 user folder; GLYPORT_DEFAULTS
# overrides it. The file and its folder are created on the first write only.
DEFAULTS_ENV = "GLYPORT_DEFAULTS"
DEFAULTS_PATH = "Library/Application Support/FontLab/Glyport/defaults.json"


def default_defaults_path() -> Path:
    """Where persisted ``Glyphs.defaults`` live unless the caller picks a store."""
    override = os.environ.get(DEFAULTS_ENV)
    return Path(override) if override else Path.home() / DEFAULTS_PATH


def _json_value(value: object) -> object:
    """Plain JSON value: tuples become lists; anything else non-JSON raises."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("defaults cannot store non-finite floats")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("defaults dict keys must be str")
        return {k: _json_value(v) for k, v in value.items()}
    raise TypeError(f"defaults cannot store {type(value).__name__}")


class JsonFileStore(MutableMapping[str, Any]):
    """Persisted defaults: one JSON object in a file the integrator chooses.

    Values are JSON (str, int, float, bool, None, lists, str-keyed dicts);
    tuples are stored as lists and other values raise ``TypeError`` before
    anything is written. Each write replaces the file atomically. A missing
    file reads as empty and is created on the first write; an unreadable or
    non-object file raises ``ValueError``.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        self._path = Path(path)
        self._data: dict[str, Any] = {}
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError(f"Unreadable defaults file {self._path}") from error
            if not isinstance(data, dict):
                raise ValueError(f"Defaults file {self._path} is not a JSON object")
            self._data = data

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._data, indent=1), encoding="utf-8")
        os.replace(temporary, self._path)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[_key(key)] = _json_value(value)
        self._save()

    def __delitem__(self, key: str) -> None:
        del self._data[key]
        self._save()

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)
