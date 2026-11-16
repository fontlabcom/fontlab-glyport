# this_file: src/fontlab_glyport/ui/nib_archive.py
"""Read compiled NIBs (no Objective-C runtime) into plain Python objects (R031).

Two container formats occur in Glyphs plugin bundles: ``NIBArchive`` (the
default since macOS 10.13; a single file or ``keyedobjects-101300.nib``) and
``NSKeyedArchiver`` binary plists (``keyedobjects.nib``). Both decode to the
same shape: :class:`Archived` objects (class name plus fields) with strings,
numbers and collections already turned into Python values. A ``.nib``
directory is read through its keyed archive when present.

NIBArchive layout, all integers little-endian: magic, two format words, then
(count, offset) pairs for objects, keys, values and class names. Variable
integers keep 7 bits per byte, and a set high bit marks the *last* byte.
Value types: 0-3 signed ints of 1/2/4/8 bytes, 4 false, 5 true, 6 float,
7 double, 8 data (length-prefixed), 9 nil, 10 object reference (4 bytes).
Collections store their elements under the repeated key ``UINibEncoderEmptyKey``.

Hostile input is rejected with :class:`NibFormatError`, never expanded: files
over ``MAX_BYTES``, variable integers wider than 5 bytes (32 bits), table
counts larger than the file, offsets and references outside their tables,
reference chains deeper than ``MAX_DECODE_DEPTH``, and any malformed record.
Shared and cyclic references decode once (memoised by object index).
"""

import plistlib
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAGIC = b"NIBArchive"
_ELEMENT_KEY = "UINibEncoderEmptyKey"
_STRINGS = {"NSString", "NSMutableString", "NSLocalizableString"}
_LISTS = {"NSArray", "NSMutableArray", "NSSet", "NSMutableSet"}
_FIXED = {0: "<b", 1: "<h", 2: "<i", 3: "<q", 6: "<f", 7: "<d"}
MAX_BYTES = 32 * 1024 * 1024
MAX_VARINT_BYTES = 5
MAX_DECODE_DEPTH = 400


class NibFormatError(ValueError):
    """The file is not a NIB this decoder understands."""


@dataclass(eq=False)
class Archived:
    """One archived object: its class and fields (repeated keys become lists)."""

    cls: str
    fields: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)

    def __repr__(self) -> str:
        return f"Archived({self.cls}, {sorted(self.fields)})"


def read_nib(path: str | Path) -> Archived:
    """Return the root object (``NSIBObjectData``) of a ``.nib`` file or bundle."""
    path = Path(path)
    if path.is_dir():
        candidates = ("keyedobjects.nib", "keyedobjects-101300.nib")
        found = [path / name for name in candidates if (path / name).is_file()]
        if not found:
            raise NibFormatError(f"{path}: no keyedobjects*.nib inside")
        path = found[0]
    if path.stat().st_size > MAX_BYTES:
        raise NibFormatError(
            f"{path}: too large for a NIB ({path.stat().st_size} bytes)"
        )
    return read_nib_data(path.read_bytes(), path)


def read_nib_data(data: bytes, path: str | Path = "<nib data>") -> Archived:
    """The root of NIB bytes (a file's, or a table view's archived prototype
    cell views); ``path`` only names it in errors."""
    if len(data) > MAX_BYTES:
        raise NibFormatError(f"{path}: too large for a NIB ({len(data)} bytes)")
    try:
        if data.startswith(MAGIC):
            top = _NibArchive(data).decode()
        elif data.startswith(b"bplist00"):
            top = _KeyedArchive(plistlib.loads(data)).decode()
        else:
            raise NibFormatError(f"{path}: neither NIBArchive nor a keyed archive")
    except NibFormatError as error:
        raise NibFormatError(f"{path}: {error}") from error
    except (
        ValueError,
        IndexError,
        KeyError,
        TypeError,
        AttributeError,
        struct.error,
    ) as error:
        raise NibFormatError(f"{path}: malformed NIB ({error!r})") from error
    root = top.get("IB.objectdata") if isinstance(top, Archived) else top
    if not isinstance(root, Archived) or root.cls != "NSIBObjectData":
        raise NibFormatError(f"{path}: no NSIBObjectData root")
    return root


def _normalise(cls: str, fields: dict[str, Any]) -> Any:
    if cls in _STRINGS:
        raw = fields.get("NS.bytes", fields.get("NS.string", ""))
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    if cls in _LISTS:
        items = fields.get(_ELEMENT_KEY, fields.get("NS.objects", []))
        return list(items) if isinstance(items, list) else [items]
    if cls in ("NSNumber",):
        return fields.get("NS.intval", fields.get("NS.dblval", fields.get("NS.value")))
    return None


class _NibArchive:
    def __init__(self, data: bytes):
        self.data, self.depth = data, 0
        words = struct.unpack_from("<10I", data, len(MAGIC))
        _, _, *tables = words
        for count, offset in zip(tables[::2], tables[1::2], strict=True):
            if count > len(data) or offset > len(data):
                raise NibFormatError("NIBArchive table exceeds the file")
        self.objects = self._table(tables[0], tables[1], self._object)
        self.keys = self._table(tables[2], tables[3], self._key)
        self.values = self._table(tables[4], tables[5], self._value)
        self.classes = self._table(tables[6], tables[7], self._class)
        self.decoded: dict[int, Any] = {}

    def _varint(self, i: int) -> tuple[int, int]:
        result = 0
        for shift in range(0, 7 * MAX_VARINT_BYTES, 7):
            byte = self.data[i]
            i += 1
            result |= (byte & 0x7F) << shift
            if byte & 0x80:
                return result, i
        raise NibFormatError("NIBArchive varint wider than 5 bytes")

    def _table(self, count: int, offset: int, read) -> list:
        items, i = [], offset
        for _ in range(count):
            item, i = read(i)
            items.append(item)
        return items

    def _object(self, i: int):
        cls, i = self._varint(i)
        start, i = self._varint(i)
        count, i = self._varint(i)
        return (cls, start, count), i

    def _key(self, i: int):
        size, i = self._varint(i)
        return self.data[i : i + size].decode("utf-8"), i + size

    def _class(self, i: int):
        size, i = self._varint(i)
        extra, i = self._varint(i)
        i += 4 * extra
        return self.data[i : i + size].rstrip(b"\0").decode("utf-8"), i + size

    def _value(self, i: int):
        key, i = self._varint(i)
        kind = self.data[i]
        i += 1
        if kind in _FIXED:
            fmt = _FIXED[kind]
            return (key, struct.unpack_from(fmt, self.data, i)[0]), i + struct.calcsize(
                fmt
            )
        if kind in (4, 5):
            return (key, kind == 5), i
        if kind == 8:
            size, i = self._varint(i)
            return (key, self.data[i : i + size]), i + size
        if kind == 9:
            return (key, None), i
        if kind == 10:
            return (key, _Ref(struct.unpack_from("<I", self.data, i)[0])), i + 4
        raise NibFormatError(f"unknown NIBArchive value type {kind}")

    def decode(self, index: int = 0) -> Any:
        if index in self.decoded:
            return self.decoded[index]
        if not 0 <= index < len(self.objects):
            raise NibFormatError(f"NIBArchive reference {index} out of range")
        cls_index, start, count = self.objects[index]
        if start + count > len(self.values):
            raise NibFormatError("NIBArchive object values exceed the value table")
        cls = self.classes[cls_index]
        obj = Archived(cls)
        self.decoded[index] = obj  # cycles (superview <-> subviews) resolve to it
        self.depth += 1
        if self.depth > MAX_DECODE_DEPTH:
            raise NibFormatError("NIBArchive references nest too deep")
        try:
            for key_index, raw in self.values[start : start + count]:
                value = self.decode(raw.index) if isinstance(raw, _Ref) else raw
                _store(obj.fields, self.keys[key_index], value)
        finally:
            self.depth -= 1
        plain = _normalise(cls, obj.fields)
        if plain is not None or cls in _STRINGS | _LISTS:
            self.decoded[index] = plain
        return self.decoded[index]


@dataclass(frozen=True)
class _Ref:
    index: int


def _store(fields: dict, key: str, value: Any) -> None:
    if key != _ELEMENT_KEY:
        fields[key] = value
        return
    fields.setdefault(key, []).append(value)


class _KeyedArchive:
    def __init__(self, plist: dict):
        if plist.get("$archiver") != "NSKeyedArchiver":
            raise NibFormatError("not an NSKeyedArchiver archive")
        self.objects, self.top = plist["$objects"], plist["$top"]
        self.decoded: dict[int, Any] = {}
        self.depth = 0

    def decode(self) -> Archived:
        top = Archived("$top")
        for key, value in self.top.items():
            top.fields[key] = self._value(value)
        return top

    def _value(self, value: Any) -> Any:
        if isinstance(value, plistlib.UID):
            return self._object(value.data)
        if isinstance(value, list):
            return [self._value(v) for v in value]
        return value

    def _object(self, index: int) -> Any:
        if index in self.decoded:
            return self.decoded[index]
        if not 0 <= index < len(self.objects):
            raise NibFormatError(f"keyed archive reference {index} out of range")
        raw = self.objects[index]
        if raw == "$null":
            return None
        if not isinstance(raw, dict) or "$class" not in raw:
            self.decoded[index] = raw
            return raw
        cls = self.objects[raw["$class"].data]["$classname"]
        obj = Archived(cls)
        self.decoded[index] = obj
        self.depth += 1
        if self.depth > MAX_DECODE_DEPTH:
            raise NibFormatError("keyed archive references nest too deep")
        try:
            for key, value in raw.items():
                if key != "$class":
                    obj.fields[key] = self._value(value)
        finally:
            self.depth -= 1
        plain = _normalise(cls, obj.fields)
        if plain is not None or cls in _STRINGS | _LISTS:
            self.decoded[index] = plain
        return self.decoded[index]
