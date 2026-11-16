# this_file: src/fontlab_glyport/model/proxies.py
"""Explicit Glyphs 3 subset, pinned to docu.glyphsapp.com on 2026-10-14."""

import math
import re
import unicodedata
import weakref
from collections import namedtuple
from collections.abc import MutableMapping, Sequence
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from functools import partial
from itertools import count
from typing import Any, Never
from uuid import uuid4

from .._strict import caller_location, guard_properties
from ..errors import (
    PartialFailure,
    StaleNativeObject,
    UnsupportedAttribute,
    UnsupportedCapability,
)
from .backend import (
    AnchorInfo,
    AxisInfo,
    ComponentInfo,
    GlyphInfo,
    GuideInfo,
    HintInfo,
    InstanceInfo,
    ModelBackend,
    NodeInfo,
    PathInfo,
)


def _mapped_positions(
    items: Sequence[Any], transform: Sequence[float]
) -> list[tuple[Any, tuple[float, float]]]:
    """Preflight positions in occurrence order, including repeated draft objects."""
    from ..drawing.context import apply

    positions, moves = {}, []
    for item in items:
        key = id(item)
        if key not in positions:
            positions[key] = item.position
        previous = positions[key]
        position = apply(transform, *previous)
        positions[key] = position
        moves.append((item, position))
    return moves


Point = namedtuple("Point", "x y")
Size = namedtuple("Size", "width height")
Rect = namedtuple("Rect", "origin size")

# glyphsLib's UFO lib keys (glyphsLib 6.16.0 builder/constants.py), so that data
# written here reads back the way glyphsLib maps a UFO lib to a Glyphs font.
FONT_USER_DATA_KEY = "com.schriftgestaltung.Glyphs.fontUserData"
CUSTOM_PARAMETER_PREFIX = "com.schriftgestaltung.customParameter.GSFont."

# Glyphs hint type constants (GlyphsApp: TOPGHOST, STEM, BOTTOMGHOST).
TOPGHOST, STEM, BOTTOMGHOST = -1, 0, 1
# FontLab ghost hint widths (FontLab chat appendix, layer_hints): -20 top, 21 bottom.
GHOST_WIDTH_TOP = -20
GSLTR = 0
# Glyphs SDK node connections (distinct from the string-valued node types).
GSSHARP, GSSMOOTH = 0, 100
CORNER, CAP = 16, 17
# Glyph metadata FontLab has no native field for (probe_glyph_export.json):
# the UFO skip-export list in the font lib, glyphsLib-style keys in the glyph lib.
SKIP_EXPORT_KEY = "public.skipExportGlyphs"
SCRIPT_KEY = "com.schriftgestaltung.Glyphs.script"
STORE_SCRIPT_KEY = "com.schriftgestaltung.Glyphs.storeScript"
CATEGORY_KEY = "com.schriftgestaltung.Glyphs.category"
STORE_CATEGORY_KEY = "com.schriftgestaltung.Glyphs.storeCategory"
SUBCATEGORY_KEY = "com.schriftgestaltung.Glyphs.subCategory"
STORE_SUBCATEGORY_KEY = "com.schriftgestaltung.Glyphs.storeSubCategory"
# Keep the compatibility case snapshot separate from native Unicode metadata.
CASE_KEY = "com.fontlab.glyport.case"
STORE_CASE_KEY = "com.fontlab.glyport.storeCase"
LEFT_GROUP, RIGHT_GROUP = "@MMK_L_", "@MMK_R_"
NO_KERNING_VALUE = float(2**63)  # Native kerning returns a double, not NSInteger.
KERNING_NONE_THRESHOLD = 1_000_000  # Glyphs 3 Python wrapper conversion.


def _ltr_only(direction):
    if direction != GSLTR:
        _unsupported("GSFont.kerning.direction")


def _kerning_key(key, side):
    """Glyphs pair keys are glyph names or @MMK groups of the matching side."""
    if not isinstance(key, str) or not key:
        raise TypeError("Kerning keys must be nonempty strings")
    wrong = RIGHT_GROUP if side == LEFT_GROUP else LEFT_GROUP
    if key.startswith(wrong):
        raise ValueError(f"{key!r} is a group key for the other side of the pair")
    return key


# Unicode script name prefixes -> Glyphs script names.
_SCRIPTS = {
    "LATIN": "latin",
    "GREEK": "greek",
    "CYRILLIC": "cyrillic",
    "ARABIC": "arabic",
    "HEBREW": "hebrew",
    "CJK": "han",
    "HIRAGANA": "kana",
    "KATAKANA": "kana",
    "HANGUL": "hangul",
    "DEVANAGARI": "devanagari",
    "GURMUKHI": "gurmukhi",
    "THAI": "thai",
}
_CATEGORIES = {
    "L": "Letter",
    "M": "Mark",
    "N": "Number",
    "P": "Punctuation",
    "S": "Symbol",
    "Z": "Separator",
}
_CASES = {"Lu": ("Uppercase", 1), "Ll": ("Lowercase", 2)}  # GSUppercase, GSLowercase


# Glyphs label colours (index order of GSGlyph/GSLayer.color) as FontLab mark
# hues of their system colours; FontLab marks are hues with 0 meaning none, so
# the two grays (10, 11) have no FontLab mark. Brown and orange share a hue.
LABEL_HUES = (3, 35, 34, 48, 135, 173, 199, 211, 280, 349)


def _label_to_mark(index) -> int:
    if index is None or index == NSNOTFOUND:
        return 0
    if not 0 <= int(index) < len(LABEL_HUES):
        _unsupported(f"label color {index} (FontLab marks are hues; no grays)")
    return LABEL_HUES[int(index)]


def _mark_to_label(hue: int):
    if not hue:
        return None
    distance = [min(abs(hue - h), 360 - abs(hue - h)) for h in LABEL_HUES]
    return distance.index(min(distance))


NSNOTFOUND = 0x7FFFFFFFFFFFFFFF


def unicode_facts(code: str | None) -> tuple:
    """``(category, subCategory, case, script)`` from Unicode data.

    These Unicode facts supply case/script fallbacks. GSGlyph category and
    subCategory are read separately from GlyphData, whose categories differ.
    """
    if not code:
        return (None, None, 0, None)
    char = chr(int(code, 16))
    general = unicodedata.category(char)
    sub, case = _CASES.get(general, (None, 0))
    from ..fonttools import fonttools_module

    try:
        database = fonttools_module("unicodedata", "GSGlyph.script")
    except UnsupportedCapability:
        # Basic metadata remains available without the optional geometry extra.
        words = unicodedata.name(char, "").split()
        script = _SCRIPTS.get(words[0]) if words else None
    else:
        code = database.script(char)
        name = database.script_name(code)
        script = (
            None
            if code in ("Zyyy", "Zinh", "Zzzz")
            else _SCRIPTS.get(name.upper(), name.replace(" ", "").lower())
        )
    return (
        _CATEGORIES.get(general[0]),
        sub,
        case,
        script,
    )


def _unsupported(
    name: str, error: type[UnsupportedCapability] = UnsupportedCapability
) -> Never:
    raise error(
        f"Unsupported model member: {name}",
        capability=name,
        location=caller_location(),
    )


class _Explicit:
    """Missing members fail explicitly; they never forward into a native object.

    Unknown public reads raise ``UnsupportedAttribute`` so ``hasattr`` and
    ``getattr(obj, name, default)`` probes work; writes raise plain
    ``UnsupportedCapability``. Subclass properties are guarded: an
    AttributeError inside a body surfaces as ``UnsupportedCapability`` naming
    the inner capability, never as a probe-visible miss of the property.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        guard_properties(cls)

    def isKindOfClass_(self, cls):
        return isinstance(cls, type) and isinstance(self, cls)

    def className(self):
        return type(self).__name__

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        # Only expose selectors for properties explicitly implemented here.
        if re.fullmatch(r"set[A-Z][A-Za-z0-9]*_", name):
            stem = name[3:-1]
            for key in (stem[0].lower() + stem[1:], stem):
                descriptor = getattr(type(self), key, None)
                if isinstance(descriptor, property) and descriptor.fset:
                    return partial(setattr, self, key)
        _unsupported(f"{type(self).__name__}.{name}", UnsupportedAttribute)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        descriptor = getattr(type(self), name, None)
        if isinstance(descriptor, property) and descriptor.fset:
            descriptor.fset(self, value)
            return
        _unsupported(f"{type(self).__name__}.{name}")


class ProxySequence(_Explicit, Sequence):
    """Refresh on access; string misses return None as Glyphs keyed proxies do."""

    def __init__(
        self,
        values,
        keys=lambda item: (),
        append=None,
        remove=None,
        set_item=None,
        insert=None,
    ):
        self._values, self._keys = values, keys
        self._append, self._remove = append, remove
        self._set_item, self._insert = set_item, insert

    def __len__(self):
        return len(self._values())

    def __iter__(self):
        return iter(self._values())

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        from copy import deepcopy

        result = []
        memo[id(self)] = result
        result.extend(deepcopy(value, memo) for value in self)
        return result

    def copy(self):
        return self.__deepcopy__({})

    def __getitem__(self, key):
        values = self._values()
        if isinstance(key, (int, slice)):
            return values[key]
        if isinstance(key, str):
            primary = next(
                (v for v in values if self._keys(v) and key == self._keys(v)[0]), None
            )
            if primary is not None:
                return primary
            return next((v for v in values if key in self._keys(v)), None)
        raise TypeError("Expected an index, slice or string key")

    def __setitem__(self, key, value):
        if self._set_item is None:
            _unsupported("collection.assignment")
        self._set_item(key, value)

    def __delitem__(self, key):
        if self._remove is None:
            _unsupported("collection.remove")
        values = self[key]
        for value in reversed(values) if isinstance(key, slice) else (values,):
            self.remove(value)

    def __contains__(self, value):
        if isinstance(value, str):
            return self[value] is not None
        return any(v is value for v in self._values())

    def append(self, value):
        if self._append is None:
            _unsupported("collection.append")
        return self._append(value)

    def insert(self, index, value):
        if self._insert is None:
            _unsupported("collection.insert")
        return self._insert(index, value)

    def clear(self):
        if self._remove is None:
            _unsupported("collection.clear")
        for value in reversed(tuple(self)):
            self.remove(value)

    def remove(self, value):
        if self._remove is None:
            _unsupported("collection.remove")
        if value not in self:
            raise ValueError("Object does not belong to this collection")
        return self._remove(value)


class UserData(_Explicit, MutableMapping):
    """Glyphs userData over a native lib: reads are copies, writes replace the lib."""

    def __init__(self, read, write):
        self._read, self._write = read, write

    def __getitem__(self, key):
        """None for a missing key, as Glyphs' userData answers."""
        return self._read().get(key)

    def __contains__(self, key):
        return key in self._read()

    def get(self, key, default=None):
        return self._read().get(key, default)

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError("userData keys must be strings")
        data = self._read()
        data[key] = value
        self._write(data)

    def __delitem__(self, key):
        data = self._read()
        del data[key]
        self._write(data)

    def __iter__(self):
        return iter(self._read())

    def __len__(self):
        return len(self._read())


def _parameter_equal(left, right):
    return left == right or (
        type(left) is float
        and type(right) is float
        and math.isnan(left)
        and math.isnan(right)
    )


def _parameter_value(name, value):
    if name == "Use Arabic Presentation Form Unicodes":
        from .parameter_numbers import normalize

        return normalize(value)
    return value


def _parameter_rows(rows):
    for row in rows:
        if row["active"]:
            row["value"] = _parameter_value(row["name"], row["value"])
    return rows


class GSCustomParameter(_Explicit):
    """Mutable ordered parameter; attached objects write through their owner."""

    def __init__(self, name, value):
        self._binding, self._parent = None, None
        self._data = {"name": name, "value": value, "active": True}
        self.name = name

    def _get(self, field):
        data = (
            self._data
            if self._binding is None
            else self._binding[0]._record(self._binding[1])
        )
        return (
            _parameter_value(data["name"], data[field])
            if field == "value"
            else data[field]
        )

    def _set(self, field, value):
        if self._binding is None:
            data = {**self._data, field: value}
            data["value"] = _parameter_value(data["name"], data["value"])
            self._data = data
        else:
            self._binding[0]._change(self._binding[1], field, value)

    @property
    def parent(self):
        return self._parent

    @property
    def name(self) -> str:
        return self._get("name")

    @name.setter
    def name(self, value: str) -> None:
        if value is not None and not isinstance(value, str):
            raise TypeError("Custom parameter names must be strings or None")
        self._set(
            "name",
            ("" if value is None else value).translate(str.maketrans("‘’“”", "''\"\"")),
        )

    @property
    def value(self):
        return self._get("value")

    @value.setter
    def value(self, value) -> None:
        self._set("value", value)

    @property
    def active(self) -> bool:
        return self._get("active")

    @active.setter
    def active(self, value: bool) -> None:
        self._set("active", bool(value))

    def __copy__(self):
        from copy import deepcopy

        result = GSCustomParameter(self.name, deepcopy(self.value))
        result.active, result._parent = self.active, self.parent
        return result


class CustomParameters(_Explicit, Sequence):
    """Ordered records plus glyphsLib-compatible effective-value mirrors.

    Historical flat keys have no order/active information; import them in their
    former sorted order on first write. An owned sidecar then preserves IDs,
    duplicates and active flags. Unrelated lib entries are never reconstructed.
    Reads select fresh records instead of maintaining a second value cache.
    """

    def __init__(
        self, font, prefix=CUSTOM_PARAMETER_PREFIX, owner_id=None, parent=None
    ):
        self._font, self._prefix = font, prefix
        self._owner_id = font._id if owner_id is None else owner_id
        self._parent = font if parent is None else parent
        self._key = "com.fontlab.glyport.orderedParameters." + prefix
        if not hasattr(font, "_parameter_objects"):
            font._parameter_objects = {}
        self._objects = font._parameter_objects.setdefault((self._owner_id, prefix), {})

    def _lib(self):
        self._parent._check()
        return self._font._model._backend.lib(self._owner_id)

    def _records(self):
        from copy import deepcopy

        lib = self._lib()
        if self._key in lib:
            records = deepcopy(lib[self._key])
            if (
                not isinstance(records, list)
                or any(
                    not isinstance(row, dict)
                    or set(row) != {"id", "name", "value", "active"}
                    or not isinstance(row["id"], str)
                    or not isinstance(row["name"], str)
                    or type(row["active"]) is not bool
                    for row in records
                )
                or len({row["id"] for row in records}) != len(records)
            ):
                raise ValueError("Invalid ordered custom-parameter data")
            actual = {
                key[len(self._prefix) :]: value
                for key, value in lib.items()
                if key.startswith(self._prefix)
            }
            names = {row["name"] for row in records}
            # The flat keys are the effective values other tools read and write;
            # when they drift from the sidecar they win: a deleted key drops that
            # name's active rows, a changed one updates its effective row.
            effective, repaired, drift = set(), [], False
            for row in records:
                name = row["name"]
                if row["active"] and name not in actual:
                    drift = True
                    continue
                if row["active"] and name not in effective:
                    effective.add(name)
                    if not _parameter_equal(actual[name], row["value"]):
                        row["value"], drift = deepcopy(actual[name]), True
                repaired.append(row)
            records = repaired
            drift = drift or bool((actual.keys() - effective) & names)
            if drift:
                self._note_drift()
            identities = {row["id"] for row in records}
            for name in sorted(actual.keys() - effective):
                identity = "legacy:" + self._prefix + name
                while identity in identities:
                    identity += ":"
                identities.add(identity)
                records.append(
                    {
                        'id': identity,
                        'name': name,
                        'value': deepcopy(actual[name]),
                        'active': True,
                    }
                )
            return records
        return [
            {
                'id': "legacy:" + key,
                'name': key[len(self._prefix) :],
                'value': deepcopy(lib[key]),
                'active': True,
            }
            for key in sorted(lib)
            if key.startswith(self._prefix)
        ]

    def _note_drift(self):
        """Queue one warning per drift (until the next write) for the execution
        boundary; reads do not persist the repair."""
        from ..receipt import ReceiptDiagnostic

        font, key = self._font, (self._key, self._owner_id)
        if not hasattr(font, "_noted_drift"):
            font._noted_drift = set()
        if key in font._noted_drift:
            return
        font._noted_drift.add(key)
        font.__dict__.setdefault("_pending_diagnostics", {})[key] = ReceiptDiagnostic(
            "CUSTOM_PARAMETERS_REBUILT",
            "warning",
            f"Custom parameters ({self._prefix}) were changed outside glyport; "
            "the collection follows the flat keys (the values other tools see).",
            capability="GSFont.customParameters",
        )

    def _record(self, identity):
        for row in self._records():
            if row["id"] == identity:
                return row
        raise StaleNativeObject("Custom parameter was removed outside this collection")

    def _write(self, rows):
        from copy import deepcopy

        rows = _parameter_rows(deepcopy(rows))
        lib = self._lib()
        for key in list(lib):
            if key.startswith(self._prefix):
                del lib[key]
        seen = set()
        for row in rows:
            if row["active"] and row["name"] not in seen:
                lib[self._prefix + row["name"]] = deepcopy(row["value"])
                seen.add(row["name"])
        lib[self._key] = deepcopy(rows)
        self._font._model._backend.set_lib(self._owner_id, lib)
        getattr(self._font, "_noted_drift", set()).discard((self._key, self._owner_id))

    def _change(self, identity, field, value):
        rows = self._records()
        row = next((row for row in rows if row["id"] == identity), None)
        if row is None:
            raise StaleNativeObject(
                "Custom parameter was removed outside this collection"
            )
        if not _parameter_equal(row[field], value):
            row[field] = value
            if field != "active":
                row["value"] = _parameter_value(row["name"], row["value"])
            self._write(rows)

    def _object(self, row):
        identity = row["id"]
        if identity not in self._objects:
            obj = GSCustomParameter.__new__(GSCustomParameter)
            obj._data = {key: row[key] for key in ("name", "value", "active")}
            obj._binding, obj._parent = (self, identity), self._parent
            self._objects[identity] = obj
        return self._objects[identity]

    @staticmethod
    def _index(index, length, inserting=False):
        if not isinstance(index, int):
            raise TypeError("Expected a parameter name or integer index")
        if index < 0:
            index += length
        if not 0 <= index < length + int(inserting):
            raise IndexError("Custom parameter index out of range")
        return index

    def __len__(self):
        return len(self._records())

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def __getitem__(self, key):
        rows = self._records()
        if isinstance(key, str):
            if not key:
                return None
            effective = {}
            for row in rows:
                if row["active"]:
                    value = _parameter_value(row["name"], row["value"])
                    effective.setdefault(row["name"], value)
            return effective.get(key)
        if isinstance(key, slice):
            return [self._object(row) for row in rows[key]]
        return self._object(rows[self._index(key, len(rows))])

    def __contains__(self, key):
        if isinstance(key, str):
            if not key:
                return False
            for row in self._records():
                if row["name"] == key:
                    _parameter_value(row["name"], row["value"])
                    return True
            return False
        return any(self[index] is key for index in range(len(self)))

    def __setitem__(self, key, value):
        if isinstance(key, str):
            if value is None:
                del self[key]
                return
            for row in self._records():
                if key and row["name"] == key:
                    self._change(row["id"], "value", value)
                    return
            self.append(GSCustomParameter(key, value))
            return
        rows = self._records()
        index = self._index(key, len(rows))
        self._insert(index, value, replace=True)

    def __delitem__(self, key):
        rows = self._records()
        if isinstance(key, str):
            indices = [i for i, row in enumerate(rows) if key and row["name"] == key][
                :1
            ]
        elif isinstance(key, slice):
            indices = list(range(len(rows)))[key]
        else:
            indices = [self._index(key, len(rows))]
        removed = [rows[i] for i in indices]
        if not removed:
            return
        for index in sorted(indices, reverse=True):
            del rows[index]
        self._write(rows)
        for row in removed:
            self._detach(row)

    def _detach(self, row):
        obj = self._objects.pop(row["id"], None)
        if obj is not None:
            obj._data = {key: row[key] for key in ("name", "value", "active")}
            obj._binding, obj._parent = None, None

    def _insert(self, index, parameter, replace=False):
        if not isinstance(parameter, GSCustomParameter):
            raise TypeError("Expected GSCustomParameter")
        if parameter._binding is not None:
            _unsupported("GSCustomParameter.repeated_or_cross_owner_insertion")
        rows = self._records()
        row = {
            'id': str(uuid4()),
            'name': parameter.name,
            'value': parameter.value,
            'active': parameter.active,
        }
        old = rows[index] if replace else None
        if replace:
            rows[index] = row
        else:
            rows.insert(index, row)
        self._write(rows)
        if old is not None:
            self._detach(old)
        parameter._binding, parameter._parent = (self, row["id"]), self._parent
        self._objects[row["id"]] = parameter

    def insert(self, index, parameter):
        self._insert(self._index(index, len(self), inserting=True), parameter)

    def append(self, parameter):
        self._insert(len(self), parameter)

    def extend(self, parameters):
        for parameter in parameters:
            self.append(parameter)

    def remove(self, parameter):
        """Remove ``parameter`` itself (Glyphs' ``removeObject_``), not the first
        parameter with its name; ValueError when it is not in this collection."""
        if not isinstance(parameter, GSCustomParameter):
            raise TypeError("Expected GSCustomParameter")
        identity = parameter._binding[1] if parameter._binding is not None else None
        if identity is not None and self._objects.get(identity) is parameter:
            for index, row in enumerate(self._records()):
                if row["id"] == identity:
                    del self[index]
                    return
        raise ValueError("CustomParameters.remove(x): x not in the collection")


# FontLab stores each feature as a whole "feature tag { ... } tag;" block, while
# Glyphs' GSFeature.code is the body (native fact: glyport-r020/probe-font-writes-run3).
# Text that is not exactly one such block (a comment before it, several blocks)
# reads verbatim (native: glyport-r020/probe-review-fixes-run1).
_FEATURE_BLOCK = re.compile(
    r"\s*feature\s+(\S+?)\s*\{\n?(.*?)\n?\}\s*(\S+?)\s*;\s*", re.DOTALL
)


_FEATURE_START = re.compile(r"\bfeature\s+\S+?\s*\{")
# FEA comments run from # to the end of the line; strings are double-quoted.
_FEA_NOISE = re.compile(r'"[^"]*"|#[^\r\n]*')  # CR, LF and CRLF end a comment


def _fea_code_only(text):
    """FEA text with comments and strings blanked, so that block starts
    mentioned in them are not counted (RR2-r020)."""
    return _FEA_NOISE.sub(" ", text)


def _feature_parts(name, text):
    """The match of a text that is exactly one block of feature ``name``.

    Text with several blocks (even of the same tag) is not one block: the lazy
    body would otherwise span from the first block's body to the last's.
    """
    text = text or ""
    if len(_FEATURE_START.findall(_fea_code_only(text))) != 1:
        return None
    match = _FEATURE_BLOCK.fullmatch(text)
    if match and match.group(1) == match.group(3) == name:
        return match
    return None


def _feature_body(name, text):
    match = _feature_parts(name, text)
    return match.group(2) if match else text


def _feature_text(name, current, code):
    """The FontLab text that makes ``code`` the feature's Glyphs code.

    ``code`` that is itself FontLab text for this feature is stored verbatim,
    so a verbatim read assigns back unchanged; a body replaces the body of a
    single block in place (byte-exact elsewhere) or is wrapped for a new
    feature. A body for text that is not one block is refused.
    """
    if _feature_parts(name, code) or re.search(
        rf"\bfeature\s+{re.escape(name)}\s*\{{", _fea_code_only(code)
    ):
        return code
    if current is None:
        return f"feature {name} {{\n{code}\n}} {name};\n"
    match = _feature_parts(name, current)
    if match is None:
        _unsupported(
            f"GSFeature.code ({name}'s FontLab text is not one feature block; "
            "assign its full text)"
        )
    return current[: match.start(2)] + code + current[match.end(2) :]


def _text(value, what):
    if not isinstance(value, str):
        raise TypeError(f"{what} must be a string")
    return value


# FontLab OpenType classes are lists of glyph names (fgGroup), so class code that
# is more than whitespace-separated names cannot be stored faithfully.
_CLASS_SYNTAX = re.compile(r"[#@\[\]{}();,<>'\"\\]")


def _class_members(code):
    code = _text(code, "code")
    if _CLASS_SYNTAX.search(code):
        _unsupported(
            "GSClass.code (FontLab classes hold glyph names only: no comments, "
            "class references or other feature syntax)"
        )
    return tuple(code.split())


_TOKENS = count(1)


class _Bound(_Explicit):
    """A font-level record a script builds detached and the font binds.

    Detached it holds its own ``_values``. Bound it holds the font and a token
    the font issues: identity (and the cached wrapper the font hands out for
    the token) survives edits, and a removed or externally replaced record's
    token stops resolving, so its proxy raises StaleNativeObject.
    """

    _key = ""

    def __init__(self, **values):
        self._font = self._token = None
        self._values = values

    @classmethod
    def _bind(cls, font, token):
        record = cls()
        record._font, record._token = font, token
        return record

    def _live(self):
        self._font._check()
        return self._font._model._backend


class _NamedRecord(_Bound):
    """A record FontLab keys by name: features, classes, the prefix."""

    def __init__(self, name="", code=""):
        super().__init__(name=name, code=code)

    def _name(self):
        names = self._font._named(self._key)
        name = next((n for n, t in names.items() if t == self._token), None)
        if name is None:
            raise StaleNativeObject(f"{self._key} {self._token}")
        return name

    @property
    def name(self) -> str:
        return self._values["name"] if self._font is None else self._name()

    @name.setter
    def name(self, value):
        value = _text(value, "name")
        if self._font is None:
            self._values["name"] = value
            return
        old = self._name()
        if value == old:
            return
        if not hasattr(self, "_rename"):
            _unsupported(f"{type(self).__name__}.name (rename)")
        if not value:
            raise ValueError(f"A {self._key} needs a name")
        if value in self._font._named(self._key):
            _unsupported(
                f"{type(self).__name__}.name (a {self._key} named {value} exists)"
            )
        self._rename(old, value)
        self._font._named_refresh(self._key, old, value)

    @property
    def code(self) -> str:
        if self._font is None:
            return self._values["code"]
        return self._read_code(self._name())

    @code.setter
    def code(self, value):
        value = _text(value, "code")
        if self._font is None:
            self._values["code"] = value
        else:
            name = self._name()
            self._write_code(name, value)
            self._font._named_refresh(self._key, name)


class GSFeature(_NamedRecord):
    """OpenType feature; ``code`` is the body inside FontLab's feature block."""

    _key = "feature"

    def _native_text(self, name):
        features = self._font._features_info().features
        return next((f.code for f in features if f.name == name), None)

    def _read_code(self, name):
        return _feature_body(name, self._native_text(name))

    def _write_code(self, name, value):
        text = _feature_text(name, self._native_text(name), value)
        self._live().set_feature(self._font._id, name, text)


class GSClass(_NamedRecord):
    """OpenType glyph class; ``code`` is the space-separated glyph names."""

    _key = "class"

    @property
    def automatic(self) -> bool:
        return False

    @automatic.setter
    def automatic(self, value):
        if value:
            _unsupported("GSClass.automatic (FontLab classes are not automatic)")

    def _read_code(self, name):
        glyphs = next(c.glyphs for c in self._font._classes_info() if c.name == name)
        return " ".join(glyphs)

    def _write_code(self, name, value):
        members = _class_members(value)
        self._live().set_class(self._font._id, name, members)

    def _rename(self, old, new):
        self._live().rename_class(self._font._id, old, new)


class GSFeaturePrefix(_NamedRecord):
    """The feature prefix; FontLab keeps exactly one per font."""

    _key = "prefix"

    def _read_code(self, name):
        return self._font._features_info().prefix

    def _write_code(self, name, value):
        self._live().set_feature_prefix(self._font._id, value)
        self._font._prefix_pending = True  # the record exists even with empty code


class _ListRecord(_Bound):
    """A record FontLab keeps by position: axes, instances, hints."""

    def _slot_key(self):
        return (self._key,)

    def _infos(self):
        raise NotImplementedError

    def _index(self):
        return self._font._slot(self._slot_key(), self._token)

    def _info(self):
        return self._infos()[self._index()]

    def _get(self, key, field):
        return self._values[key] if self._font is None else getattr(self._info(), field)


class GSAxis(_ListRecord):
    """Font axis; ``id`` is a glyport identity that survives name and tag edits."""

    _key = "axes"

    def __init__(self, name="", axisTag="", hidden=False):
        super().__init__(name=name, axisTag=axisTag, hidden=hidden)
        self._axis_uuid = str(uuid4()).upper()

    def _infos(self):
        if "axes" in getattr(self._font._model._backend, "volatile_collections", ()):
            return self._font._data().axes
        return self._font._layer_info(("axis-infos",), lambda: self._font._data().axes)

    def _set(self, key, field, value):
        if self._font is None:
            self._values[key] = value
            return
        index = self._index()
        axes = self._infos()
        info = replace(axes[index], **{field: value})
        others = [a for i, a in enumerate(axes) if i != index]
        if any(a.name == info.name or a.tag == info.tag for a in others):
            _unsupported(f"GSAxis.{key} (another axis has this name or tag)")
        self._live().set_axis(self._font._id, index, info)
        self._font._slot_refresh(self._slot_key())

    @property
    def name(self) -> str:
        return self._get("name", "name")

    @name.setter
    def name(self, value):
        value = _text(value, "name")
        if not value:
            raise ValueError("An axis needs a name")
        self._set("name", "name", value)

    @property
    def axisTag(self) -> str:
        return self._get("axisTag", "tag")

    @axisTag.setter
    def axisTag(self, value):
        self._set("axisTag", "tag", _axis_tag(value))

    @property
    def id(self) -> str:
        return self._token or self._axis_uuid

    @property
    def axisId(self) -> str:
        return self.id

    @property
    def hidden(self) -> bool:
        return self._get("hidden", "hidden")

    @hidden.setter
    def hidden(self, value):
        self._set("hidden", "hidden", bool(value))


def _axis_tag(value):
    value = _text(value, "axisTag")
    if not 1 <= len(value) <= 4:
        raise ValueError("An axis tag has one to four characters")
    return value


def _coordinates(values, count):
    values = list(values)
    if len(values) != count:
        raise ValueError(f"Expected {count} axis coordinates, got {len(values)}")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        raise TypeError("Axis coordinates must be numbers")
    return tuple(float(v) for v in values)


class GSInstance(_ListRecord):
    """Font instance. A new instance without coordinates takes the first master's;
    edits change only the field set (other native data is kept)."""

    _key = "instances"

    def __init__(self, name="Regular", exports=True, axes=()):
        super().__init__(
            name=name,
            exports=exports,
            axes=tuple(axes),
            weight="Regular",
            weightValue=100.0,
            width="Normal",
        )

    @property
    def active(self):
        return self.exports

    @active.setter
    def active(self, value):
        self.exports = value

    @property
    def type(self):
        # FontLab's named flInstance records are single static instances.
        return 0

    @property
    def weight(self):
        return self._get("weight", "weight")

    @property
    def weightValue(self):
        if self._font is not None:
            for axis, value in zip(self._font._data().axes, self.axes):
                if axis.tag == "wght":
                    return value
        return self._get("weightValue", "weightValue")

    @property
    def width(self):
        return self._get("width", "width")

    @property
    def widthValue(self):
        if self._font is not None:
            for axis, value in zip(self._font._data().axes, self.axes):
                if axis.tag == "wdth":
                    return value
        _unsupported("GSInstance.widthValue")

    @property
    def interpolatedFont(self):
        # Native interpolateInstance yields an unregistered package whose
        # fgPackage getter is unsafe. Do not expose a half-valid GSFont.
        raise UnsupportedCapability(
            "FontLab interpolation returns an unregistered package whose fgPackage "
            "getter is unsafe; a safe interpolated GSFont is unavailable",
            capability="GSInstance.interpolatedFont",
            location=caller_location(),
        )

    def fileName(self, format=None):
        # Glyphs applies naming/custom-parameter tokens and export format.
        # A FontLab style name alone cannot faithfully produce that filename.
        raise UnsupportedCapability(
            "Glyphs instance export filenames require custom-parameter/token "
            "expansion not provided by FontLab style names",
            capability="GSInstance.fileName",
            location=caller_location(),
        )

    def _infos(self):
        return self._font._model._backend.instances(self._font._id)

    def _set(self, key, value):
        if self._font is None:
            self._values[key] = value
            return
        index = self._index()
        self._live().set_instance(self._font._id, index, {key: value})
        self._font._slot_refresh(self._slot_key())

    @property
    def name(self) -> str:
        return self._get("name", "name")

    @name.setter
    def name(self, value):
        value = _text(value, "name")
        if self._font is not None and not value:
            raise ValueError("An instance needs a name")
        self._set("name", value)

    @property
    def exports(self) -> bool:
        return self._get("exports", "exports")

    @exports.setter
    def exports(self, value):
        self._set("exports", bool(value))

    @property
    def axes(self) -> list:
        return list(self._get("axes", "axes"))

    @axes.setter
    def axes(self, values):
        if self._font is None:
            self._values["axes"] = tuple(values)
            return
        self._set("axes", _coordinates(values, len(self._font._data().axes)))

    @property
    def internalAxesValues(self) -> list:
        return self.axes

    @internalAxesValues.setter
    def internalAxesValues(self, values):
        self.axes = values


GHOST_WIDTH_BOTTOM = 21
_GHOST_WIDTHS = {TOPGHOST: GHOST_WIDTH_TOP, BOTTOMGHOST: GHOST_WIDTH_BOTTOM}


class GSHint(_ListRecord):
    """FontLab PostScript hint (stem or ghost); FontLab hints are not node-linked.

    A new hint takes either ``position``/``width`` (FontLab's edge and
    thickness) or Glyphs' ``originNode``/``targetNode``, whose coordinates are
    read once when it is appended. A stored hint edits one field at a time, so
    FontLab keeps links and expressions it does not have to change.
    """

    _key = "hints"

    def __init__(self):
        super().__init__(
            horizontal=True,
            type=STEM,
            name="",
            position=None,
            width=None,
            originNode=None,
            targetNode=None,
        )
        self._layer = None

    def copy(self):
        info = self._resolve() if self._font is None else self._info()
        result = GSHint()
        result.horizontal, result.name = info.horizontal, info.name
        result.type = (
            (TOPGHOST if info.width == -20 else BOTTOMGHOST) if info.ghost else STEM
        )
        result.position, result.width = info.position, info.width
        return result

    def __deepcopy__(self, memo):
        result = self.copy()
        memo[id(self)] = result
        return result

    @classmethod
    def _bind_layer(cls, layer, token):
        hint = cls._bind(layer._font, token)
        hint._layer = layer
        return hint

    def _slot_key(self):
        return (self._key, self._layer._id)

    def _infos(self):
        self._layer._check()
        return self._font._model._backend.hints(self._layer._id)

    def _set(self, key, value):
        if self._font is None:
            self._values[key] = value
            return
        index = self._index()
        self._live().set_hint(self._layer._id, index, {key: value})
        self._font._slot_refresh(self._slot_key())

    @property
    def horizontal(self) -> bool:
        return self._get("horizontal", "horizontal")

    @horizontal.setter
    def horizontal(self, value):
        if self._font is not None and self._info().ghost:
            _unsupported("GSHint.horizontal (FontLab ghost hints are horizontal)")
        self._set("horizontal", bool(value))

    @property
    def type(self) -> int:
        if self._font is None:
            return self._values["type"]
        info = self._info()
        if not info.ghost:
            return STEM
        return TOPGHOST if info.width == GHOST_WIDTH_TOP else BOTTOMGHOST

    @type.setter
    def type(self, value):
        if value not in (STEM, TOPGHOST, BOTTOMGHOST):
            _unsupported(
                f"GSHint.type {value!r} (FontLab stores PostScript stems and ghosts)"
            )
        if self._font is not None:
            _unsupported("GSHint.type (change the type of a stored hint)")
        self._values["type"] = value

    @property
    def name(self) -> str:
        return self._get("name", "name")

    @name.setter
    def name(self, value):
        self._set("name", _text(value, "name"))

    @property
    def position(self) -> float | None:
        return self._get("position", "position")

    @position.setter
    def position(self, value):
        self._set("position", float(value))

    @property
    def width(self) -> float | None:
        return self._get("width", "width")

    @width.setter
    def width(self, value):
        if self._font is not None and self._info().ghost:
            _unsupported("GSHint.width (ghost widths are fixed)")
        self._set("width", float(value))

    def _node(self, name):
        if self._font is not None:
            _unsupported(f"GSHint.{name} (FontLab hints are not node-linked)")
        return self._values[name]

    @property
    def originNode(self):
        return self._node("originNode")

    @originNode.setter
    def originNode(self, node):
        self._node("originNode")
        self._values["originNode"] = node

    @property
    def targetNode(self):
        return self._node("targetNode")

    @targetNode.setter
    def targetNode(self, node):
        self._node("targetNode")
        self._values["targetNode"] = node

    @property
    def isPostScript(self) -> bool:
        return True

    @property
    def isTrueType(self) -> bool:
        return False

    def _resolve(self):
        """The HintInfo this new hint describes (FontLab position and width)."""
        v = self._values
        axis = 1 if v["horizontal"] else 0
        origin, target = v["originNode"], v["targetNode"]
        position = v["position"]
        if position is None and origin is not None:
            position = tuple(origin.position)[axis]
        if position is None:
            raise ValueError("A hint needs a position or an originNode")
        if v["type"] != STEM:
            if not v["horizontal"]:
                _unsupported("GSHint (FontLab ghost hints are horizontal)")
            width = _GHOST_WIDTHS[v["type"]]
            return HintInfo(True, float(position), width, v["name"], True)
        width = v["width"]
        if width is None and target is not None:
            width = tuple(target.position)[axis] - position
        if not width:
            raise ValueError("A stem hint needs a nonzero width or a targetNode")
        if width < 0:
            position, width = position + width, -width
        return HintInfo(v["horizontal"], float(position), float(width), v["name"])


class GSEditViewController(_Explicit):
    """FontLab's active glyph tab of a font (``font.currentTab``/``newTab``).

    ``text`` uses characters for encoded glyphs and ``/name `` for the others,
    built from the tab's glyphs (FontLab's own string form does not round-trip).
    """

    def __init__(self, font, tab_id):
        self._font, self._tab_id = font, tab_id

    def __call__(self):
        self._view()
        return self

    def className(self):
        return "GSEditViewController"

    def _view(self):
        self._font._check()
        view = self._font._model._backend.edit_view(self._font._id)
        if view is None or view.id != self._tab_id:
            raise StaleNativeObject("The glyph tab is no longer the font's active tab")
        return view

    @property
    def text(self) -> str:
        glyphs = self._font.glyphs

        def char(name):
            unicode = glyphs[name].unicode if name in glyphs else None
            return chr(int(unicode, 16)) if unicode else None

        def line_text(names):
            # "/name" needs a delimiting space only before a following character
            # (the parser consumes exactly one); glyph characters, spaces
            # included, are never trimmed.
            chars = [char(n) for n in names]
            parts = []
            for index, (name, c) in enumerate(zip(names, chars, strict=True)):
                if c is not None:
                    parts.append(c)
                    continue
                parts.append(f"/{name}")
                if index + 1 < len(names) and chars[index + 1] is not None:
                    parts.append(" ")
            return "".join(parts)

        return "\n".join(line_text(line) for line in self._view().lines)

    @text.setter
    def text(self, value):
        self._view()
        lines = self._glyph_lines(str(value))
        self._font._model._backend.set_edit_glyphs(self._font._id, lines)

    def _glyph_lines(self, text):
        """Glyphs text -> glyph names per line; unknown names/characters raise."""

        glyphs = self._font.glyphs
        lines, line, i = [], [], 0
        while i < len(text):
            char = text[i]
            if char == "\n":
                lines.append(tuple(line))
                line, i = [], i + 1
            elif char == "/":
                end = i + 1
                while end < len(text) and text[end] not in " /\n":
                    end += 1
                name = text[i + 1 : end]
                if name:
                    token = glyphs.token_for_key(name)
                    if token is None or glyphs.info(token).name != name:
                        raise ValueError(f"No glyph named {name!r} in the font")
                    line.append(name)
                i = end + (end < len(text) and text[end] == " ")
            else:
                token = glyphs.token_for_key(f"{ord(char):04X}", unicode=True)
                if token is None:
                    raise ValueError(f"No glyph for character {char!r} in the font")
                line.append(glyphs.info(token).name)
                i += 1
        lines.append(tuple(line))
        return tuple(lines)

    def view(self):
        """Only ``view().window().windowController()`` (reporters' tool check);
        every other editor-view member is unsupported."""
        self._view()
        return _EditorView(self)

    def windowController(self):
        self._view()
        return _EditorWindowController(self._font)

    def graphicView(self):
        """Editor refresh is always available; paint coordinates require a painter."""
        self._view()
        from ..drawing.context import optional_current

        context = optional_current()
        if context is None:
            return _EditorGraphicView(self._font)
        return _GraphicView(context, self._font._model._backend.dark_mode)

    @property
    def textCursor(self) -> int | None:
        """Index of FontLab's active glyph in the text (one slot per glyph and
        per line break). FontLab's cursor is always on a glyph, so an index
        past the last glyph of a line reads back as that glyph's."""
        return self._view().cursor

    @textCursor.setter
    def textCursor(self, value):
        self._view()
        index = int(value)
        if index < 0:
            raise ValueError("textCursor must not be negative")
        self._font._model._backend.set_edit_cursor(self._font._id, index)

    @property
    def layers(self) -> list:
        view = self._view()
        master = next((m for m in self._font.masters if m.name == view.master), None)
        master = master or self._font.masters[0]
        return [
            self._font.glyphs[name].layers[master.id]
            for line in view.lines
            for name in line
        ]

    @layers.setter
    def layers(self, values):
        self._view()
        current_master = self.layers[0].associatedMasterId if self.layers else None
        lines = _tab_layer_lines(self._font, values, current_master)
        self._font._model._backend.set_edit_glyphs(self._font._id, lines)

    @property
    def composedLayers(self) -> list:
        """Deprecated read-only alias of ``layers`` (Glyphs SDK TabLayersProxy).

        Shares the current FontLab edit-view/master-layer subset; this does not
        add feature control, mixed-master or general shaping compatibility.
        """
        return self.layers

    @property
    def selectedLayers(self) -> list:
        """The layer of the tab's active glyph in the tab's master (FontLab
        has one active glyph per tab; Glyphs' text selection is not modelled)."""
        view = self._view()
        if view.active is None:
            return []
        master = next((m for m in self._font.masters if m.name == view.master), None)
        master = master or self._font.masters[0]
        return [self._font.glyphs[view.active].layers[master.id]]


def _tab_layer_lines(font, values, current_master=None):
    """Stage exactly representable layers before changing an editor tab."""
    from ..glyphsapp import GSControlLayer

    lines, line = [], []
    for layer in values:
        if isinstance(layer, GSControlLayer) and layer.char == 10:
            lines.append(tuple(line))
            line = []
            continue
        if not isinstance(layer, GSLayer):
            raise TypeError("Expected GSLayer or newline GSControlLayer")
        layer._check()
        if "_draft" in layer.__dict__ or layer._font is not font:
            _unsupported("GSEditViewController.layers.detachedOrForeignLayer")
        if type(layer) is not GSLayer or not layer.isMasterLayer:
            _unsupported("GSEditViewController.layers.unsupportedLayerKind")
        if current_master is None:
            current_master = font.selectedFontMaster.id
        if layer.associatedMasterId != current_master:
            raise UnsupportedCapability(
                "FontLab tabs display one master; mixed-master layer lists cannot be represented",
                capability="GSEditViewController.layers.mixedMasters",
                location=caller_location(),
            )
        line.append(layer.parent.name)
    return (*lines, tuple(line))


def _append_path_segments(target, path) -> None:
    """Glyphs path nodes -> NSBezierPath elements (offcurves are the controls
    of the following curve node; a closed path starts at its last node)."""
    nodes = list(path.nodes)
    if not nodes:
        return
    if path.closed:
        start, rest = nodes[-1], nodes
    else:
        start, rest = nodes[0], nodes[1:]
    target.moveToPoint_((start.x, start.y))
    controls = []
    for node in rest:
        point = (node.x, node.y)
        if node.type == "offcurve":
            controls.append(point)
        elif node.type == "curve" and len(controls) == 2:
            target.curveToPoint_controlPoint1_controlPoint2_(point, *controls)
            controls = []
        elif node.type in ("curve", "qcurve") and controls:
            raise UnsupportedCapability(
                "Quadratic segments in bezierPath", capability="GSLayer.bezierPath"
            )
        else:
            target.lineToPoint_(point)
            controls = []
    if path.closed:
        target.closePath()


class _EditorGraphicView(_Explicit):
    def __init__(self, font):
        self._font = font

    def setNeedsDisplay_(self, flag):
        if flag:
            self._font._model._backend.redraw_edit_view(self._font._id)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        _unsupported("GSEditViewController.graphicView." + name, UnsupportedAttribute)


class _GraphicView(_Explicit):
    """``graphicView()`` values from the current paint context."""

    def __init__(self, context, dark_mode=None):
        self._dark_mode = dark_mode
        base = context.glyph_base or context.base
        a, b = base[0], base[1]
        self._scale = (a * a + b * b) ** 0.5
        device = context.painter.device()
        w, h = float(device.width()), float(device.height())
        self._active_position = (base[4], h - base[5])
        self._view_size = (w, h)
        self._base, self._qt, self._device = base, context.qt, device

    def getActiveLocation_(self, event):
        """Mouse location in glyph units: a tool event's, else the live cursor's."""
        from ..drawing.context import apply, invert
        from ..drawing.native_painters import paint_widget
        from ..ui.cocoa import NSMakePoint

        pixel = getattr(event, "_widget", None)  # tool events carry view pixels
        if pixel is None:
            widget = paint_widget() or self._device
            if not hasattr(widget, "mapFromGlobal"):
                _unsupported("_GraphicView.getActiveLocation_ outside a canvas")
            point = widget.mapFromGlobal(self._qt.QtGui.QCursor.pos())
            pixel = (point.x(), point.y())
        return NSMakePoint(*apply(invert(self._base), *pixel))

    def drawDark(self):
        if self._dark_mode is None:
            _unsupported("GSEditViewController.graphicView.drawDark")
        return bool(self._dark_mode())

    def visibleRect(self):
        from ..ui.cocoa import NSMakeRect

        return NSMakeRect(0, 0, *self._view_size)

    def activePosition(self):
        from ..ui.cocoa import NSMakePoint

        return NSMakePoint(*self._active_position)

    def scale(self) -> float:
        return self._scale


class _EditorView(_Explicit):
    """``GSEditViewController.view()``: only the path to the window controller."""

    def __init__(self, controller):
        self._controller = controller

    def window(self):
        return self

    def windowController(self):
        return self._controller.windowController()


class GlyphsToolSelect:
    """``NSClassFromString("GlyphsToolSelect")``: a marker for ``isKindOfClass_``."""


class _EditorTool(_Explicit):
    """``toolDrawDelegate()``/``toolEventHandler()``. FontLab's active tool is
    not readable from Python, so this is always Glyphs' select tool: reporters
    that skip drawing for the text or hand tool always draw."""

    def className(self):
        return "GlyphsToolSelect"

    def isKindOfClass_(self, cls):
        return getattr(cls, "__name__", cls) == "GlyphsToolSelect"

    def dragging(self) -> bool:
        return False


class _EditorWindowController(_Explicit):
    """The font window controller as reporters use it: tool and document."""

    def __init__(self, font):
        self._font = font

    def toolDrawDelegate(self):
        return _EditorTool()

    toolEventHandler = toolDrawDelegate

    def document(self):
        return self._font.parent


class Model(_Explicit):
    """One model session owns one identity cache per open document."""

    def __init__(self, backend: ModelBackend):
        self._backend, self._fonts = backend, {}

    def _font(self, id):
        if not self._backend.is_valid(id):
            raise StaleNativeObject(id)
        if id not in self._fonts:
            font = GSFont(self, id)
            self._fonts[id] = font
        return self._fonts[id]

    @property
    def fonts(self) -> ProxySequence:
        return ProxySequence(
            lambda: [self._font(i) for i in self._backend.list_fonts()],
            lambda f: (f.familyName, f.id),
        )

    @property
    def font(self):
        id = self._backend.current_font_id()
        return self._font(id) if id is not None else None


class _Proxy(_Explicit):
    def __init__(self, font, id, read):
        self._font, self._id, self._read = font, id, read
        parent = getattr(font._model._backend, "proxy_parent", None)
        self._resolver_parent = parent(id) if parent else None

    def _lib_user_data(self, hidden_prefixes=()):
        """userData backed by this object's whole native lib (glyph, layer)."""
        self._check()
        backend = self._font._model._backend

        def read():
            self._check()
            return {
                key: value
                for key, value in backend.lib(self._id).items()
                if not key.startswith(hidden_prefixes)
            }

        def write(data):
            self._check()
            if any(key.startswith(hidden_prefixes) for key in data):
                raise ValueError("Reserved custom-parameter storage is not userData")
            retained = {
                key: value
                for key, value in backend.lib(self._id).items()
                if key.startswith(hidden_prefixes)
            }
            backend.set_lib(self._id, {**retained, **data})

        return UserData(read, write)

    def _check(self):
        backend = self._font._model._backend
        if not backend.is_valid(self._font._id) or not backend.is_valid(self._id):
            raise StaleNativeObject(self._id)
        parent = getattr(backend, "proxy_parent", None)
        current = parent(self._id) if parent else None
        if current != self._resolver_parent:
            self._font._rebind_proxy(self, current)

    def _data(self):
        self._check()
        return self._read()

    def copy(self):
        return self.__deepcopy__({})

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        from .copies import detached_copy

        return detached_copy(self, memo)

    @property
    def id(self) -> str:
        self._check()
        return self._id


class GSFont(_Proxy):
    def save(self, path: str | None = None, formatVersion=None, makeCopy=False) -> None:
        """Save a native document or copy; Glyphs serialization versions are unsupported."""
        if formatVersion is not None:
            raise UnsupportedCapability("formatVersion is unsupported for native FontLab saves", capability="GSFont.save.formatVersion")
        self._check()
        if self._undo_depth or self._undo_pending:
            raise UnsupportedCapability("End pending changes before saving", capability="GSFont.save")
        self._model._backend.save_font(self._id, path, make_copy=makeCopy)

    def close(self, ignoreChanges: bool | None = None) -> None:
        """Close; unsaved edits require an explicit ignoreChanges=True argument."""
        self._check()
        if self._undo_depth or self._undo_pending:
            raise UnsupportedCapability("End pending changes before closing", capability="GSFont.close")
        self._model._backend.close_font(self._id, ignore_changes=ignoreChanges is True)

    @property
    def formatVersion(self):
        raise UnsupportedCapability(
            "FontLab cannot select a Glyphs file format serialization version",
            capability="GSFont.formatVersion",
            location=caller_location(),
        )

    @formatVersion.setter
    def formatVersion(self, value):
        _ = self.formatVersion

    @property
    def tool(self):
        raise UnsupportedCapability(
            "FontLab does not expose the Glyphs editor tool identity or selection",
            capability="GSFont.tool",
            location=caller_location(),
        )

    @tool.setter
    def tool(self, value):
        _ = self.tool

    @property
    def parent(self):
        from ..glyphsapp.application import GSDocument

        self._check()
        if "_document" not in self.__dict__:
            self._document = GSDocument(self)
        return self._document

    def glyphsInfo(self):
        self._check()
        from ..glyphsapp.info_manager import GSGlyphsInfo

        value = self.parent.valueForKey_("glyphsInfo")
        return GSGlyphsInfo.sharedManager() if value is None else value

    @property
    def filepath(self) -> str | None:
        self._check()
        from ..glyphsapp import NSPath

        path = self._model._backend.font_path(self._id)
        return None if path is None else NSPath(path)

    def __init__(self, model=None, id=None):
        if model is None:
            # Explicit detached storage, never a fallback for a missing host.
            from .backend import FontInfo
            from .fake_backend import FakeBackend

            backend = FakeBackend()
            backend.fonts = {"font": FontInfo("font", "", 1000, ())}
            backend.glyph_lists = {"font": ()}
            backend.layers = {}
            model, id = Model(backend), "font"
            model._fonts[id] = self
        self._model, self._cache, self._undo_depth = model, {}, 0
        self._undo_pending = False
        self._undo_glyphs = {}
        self._undo_label = ""
        self._names, self._slot_tokens = {}, {}
        self._slot_versions, self._slot_positions, self._slot_order = {}, {}, {}
        self._records = weakref.WeakValueDictionary()
        self._prefix_pending = False
        self._indexes, self._layer_snapshots = {}, {}
        self._copy_owner = uuid4().hex
        super().__init__(self, id, lambda: model._backend.font_info(id))

    def _revision(self, key=()):
        self._check()
        backend = self._model._backend
        scoped = getattr(backend, "cache_revision", None)
        return scoped(self._id, key) if scoped else backend.revision(self._id)

    def _indexed(
        self,
        key,
        records,
        make,
        keys=lambda info: (info.id,),
        *,
        sequence_type=None,
        **kw,
    ):
        from .indexes import IndexedSequence

        if key not in self._indexes:
            self._indexes[key] = (sequence_type or IndexedSequence)(
                lambda: self._revision(key), records, make, keys, **kw
            )
        sequence = self._indexes[key]
        backend = self._model._backend
        if key == "glyphs" and hasattr(backend, "glyph_info"):
            sequence._validator = (
                lambda token: backend.cache_revision(self._id, (token,)),
                backend.glyph_info,
            )
            lookup = getattr(backend, "glyph_lookup", None)
            if lookup is not None:
                sequence._native_lookup = lambda value, **kw: lookup(
                    self._id, value, **kw
                )
        return sequence

    def _layer_info(self, key, read):
        version = self._revision(key)
        cached = self._layer_snapshots.get(key)
        if cached is None or cached[0] != version:
            cached = self._layer_snapshots[key] = version, read()
        return cached[1]

    def _proxy(self, cls, id, read):
        self._check()
        key = (cls, id)
        if key not in self._cache:
            obj = object.__new__(cls)
            _Proxy.__init__(obj, self, id, read)
            self._cache[key] = obj
        else:
            self._cache[key]._read = read
        return self._cache[key]

    def _native_layer(self, layer_id):
        glyph, master, background = self._model._backend.layer_location(layer_id)
        layer = self.glyphs._make(glyph).layers[master]
        return layer.background if background else layer

    def _rebind_proxy(self, proxy, parent):
        """Retained children follow their current parent's indexed reader."""
        backend = self._model._backend
        if isinstance(proxy, GSNode):
            layer = self._native_layer(backend.proxy_parent(parent))
            path = layer.paths._make(parent)
            sequence = path.nodes
            proxy._path = path
        else:
            layer = self._native_layer(parent)
            field = {
                GSPath: "paths",
                GSComponent: "components",
                GSAnchor: "anchors",
                GSGuide: "guides",
            }[type(proxy)]
            sequence = layer._children(field, type(proxy))
        proxy._read = lambda: sequence.info(proxy._id)
        proxy._resolver_parent = parent

    @property
    def familyName(self) -> str:
        return self._data().familyName

    @familyName.setter
    def familyName(self, value):
        value = _text(value, "familyName")
        with self.undo_group("Set font familyName"):
            self._model._backend.set_font_info(self._id, familyName=value)

    @property
    def unitsPerEm(self) -> int:
        return self._data().unitsPerEm

    @unitsPerEm.setter
    def unitsPerEm(self, value):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("unitsPerEm must be a positive integer")
        with self.undo_group("Set font unitsPerEm"):
            self._model._backend.set_font_info(self._id, unitsPerEm=value)

    @property
    def upm(self) -> int:
        return self.unitsPerEm

    @upm.setter
    def upm(self, value):
        self.unitsPerEm = value

    def _append_master(self, master):
        if not isinstance(master, GSFontMaster):
            raise TypeError("Expected GSFontMaster")
        if "_draft" not in master.__dict__:
            raise ValueError("Master already belongs to a font")
        append = getattr(self._model._backend, "append_master", None)
        if append is None:
            _unsupported("GSFont.masters.append: backend cannot create masters")
        data, metrics = master._data(), master._metrics()
        with self.undo_group("Append master"):
            token = append(self._id, data, metrics)
        del master._draft, master._draft_metrics
        _Proxy.__init__(master, self, token, lambda: self.masters.info(token))
        self._cache[GSFontMaster, token] = master
        return master

    @property
    def masters(self) -> ProxySequence:
        def make(token):
            return self._proxy(GSFontMaster, token, lambda: self.masters.info(token))

        return self._indexed(
            "masters", lambda: self._data().masters, make, lambda m: (m.id, m.name),
            append=self._append_master
        )

    def fontMasterForId_(self, master_id):
        return self.masters[master_id]

    def _glyph_data(self):
        self._check()
        return self._model._backend.glyphs(self._id)

    @property
    def glyphs(self) -> ProxySequence:
        def make(token):
            return self._proxy(GSGlyph, token, lambda: self.glyphs.info(token))

        return self._indexed(
            "glyphs",
            self._glyph_data,
            make,
            lambda g: (
                g.name,
                *g.unicodes,
                *(chr(int(u, 16)) for u in g.unicodes),
                g.id,
            ),
            append=self._append_glyph,
            remove=self._remove_glyph,
        )

    def glyphForUnicode_(self, code):
        wanted = str(code).upper()
        token = self.glyphs.token_for_key(wanted, unicode=True)
        if token is None or wanted not in self.glyphs.info(token).unicodes:
            return None
        return self.glyphs._make(token)

    def _remove_glyph(self, glyph):
        self._model._backend.remove_glyph(self._id, glyph._id)

    def _append_glyph(self, glyph):
        self._check()
        if not isinstance(glyph, GSGlyph):
            raise TypeError("Expected a GSGlyph")
        if "_draft" not in glyph.__dict__:
            _unsupported("font.glyphs.append(existing glyph)")
        from .copies import DetachedGlyph

        data = glyph._draft
        layers = list(glyph.layers) if isinstance(glyph, DetachedGlyph) else []
        user_data = dict(glyph.userData) if isinstance(glyph, DetachedGlyph) else {}
        if layers:
            from .attachment import target_master

            for layer in layers:
                target_master(self, layer)
        scope = (
            self.undo_group("Append glyph")
            if layers or user_data or data.unicodes or glyph._case_state()
            else nullcontext()
        )
        from .attachment import attach

        with scope:
            return attach(self, glyph, data, layers, user_data)

    @property
    def userData(self) -> UserData:
        self._check()
        backend = self._model._backend

        def read():
            self._check()
            return dict(backend.lib(self._id).get(FONT_USER_DATA_KEY, {}))

        def write(data):
            lib = backend.lib(self._id)
            if data:
                lib[FONT_USER_DATA_KEY] = data
            else:
                lib.pop(FONT_USER_DATA_KEY, None)
            backend.set_lib(self._id, lib)

        return UserData(read, write)

    @property
    def customParameters(self) -> CustomParameters:
        self._check()
        return CustomParameters(self)

    # Record identity (R020 review): tokens the font issues for records FontLab
    # keeps by name or by position, each paired with a fingerprint of the
    # record's native content. A record that changed outside glyport (replaced,
    # recreated, edited) gets a new token, so held proxies of the old one turn
    # stale instead of writing into the replacement; glyport's own writes
    # refresh the fingerprint. Wrappers are cached weakly and retired with
    # their token.

    def _new_token(self):
        return f"glyport-{next(_TOKENS)}"

    def _retire(self, token):
        self._records.pop(token, None)

    def _live_named(self, key):
        """Name -> fingerprint of the live records of ``key``."""
        if key == "feature":
            return {f.name: f.code for f in self._features_info().features}
        if key == "class":
            return {c.name: tuple(c.glyphs) for c in self._classes_info()}
        prefix = self._features_info().prefix
        return {"Prefix": prefix} if prefix or self._prefix_pending else {}

    def _named(self, key):
        """Name -> token for the live records of ``key``."""
        live = self._live_named(key)
        entries = self._names.setdefault(key, {})
        for name in list(entries):
            if name not in live or entries[name][1] != live[name]:
                self._retire(entries.pop(name)[0])
        for name, fingerprint in live.items():
            if name not in entries:
                entries[name] = [self._new_token(), fingerprint]
        return {name: entries[name][0] for name in live}  # native order

    def _named_refresh(self, key, name, new_name=None):
        """After glyport changed record ``name`` (renamed to ``new_name``)."""
        new_name = name if new_name is None else new_name
        fingerprint = self._live_named(key).get(new_name)
        # Rebuilt in place: the edited record keeps its position (RR2-r020).
        self._names[key] = {
            (new_name if n == name else n): ([e[0], fingerprint] if n == name else e)
            for n, e in self._names[key].items()
        }

    def _fingerprints(self, key):
        backend = self._model._backend
        if key[0] == "axes":
            return [(a.name, a.tag, a.hidden) for a in self._data().axes]
        if key[0] == "instances":
            # The backend id is part of it: a backend that issues a new id for
            # a recreated instance makes identical content distinguishable.
            return [
                (i.id, i.name, tuple(i.axes), i.exports)
                for i in backend.instances(self._id)
            ]
        return list(backend.hints(key[1]))

    def _slots(self, key):
        """Tokens of a positional list; entries whose content changed outside
        glyport, or a length glyport did not make, get new tokens."""
        version = self._revision(key)
        volatile = getattr(self._model._backend, "volatile_collections", ())
        if key[0] not in volatile and self._slot_versions.get(key) == version:
            return self._slot_order[key]
        fingerprints = self._fingerprints(key)
        entries = self._slot_tokens.get(key)
        if entries is None or len(entries) != len(fingerprints):
            for token, _ in entries or ():
                self._retire(token)
            entries = [[self._new_token(), f] for f in fingerprints]
            self._slot_tokens[key] = entries
        for entry, fingerprint in zip(entries, fingerprints, strict=True):
            if entry[1] != fingerprint:
                self._retire(entry[0])
                entry[0], entry[1] = self._new_token(), fingerprint
        self._slot_positions[key] = {entry[0]: i for i, entry in enumerate(entries)}
        self._slot_versions[key] = version
        self._slot_order[key] = tuple(self._slot_positions[key])
        return self._slot_order[key]

    def _slot(self, key, token):
        volatile = getattr(self._model._backend, "volatile_collections", ())
        if key[0] in volatile or self._slot_versions.get(key) != self._revision(key):
            self._slots(key)
        try:
            return self._slot_positions[key][token]
        except KeyError:
            raise StaleNativeObject(f"{key[0]} {token}") from None

    def _slot_refresh(self, key):
        """After a glyport write that kept the list length: take the new content."""
        entries = self._slot_tokens.get(key)
        fingerprints = self._fingerprints(key)
        if entries is not None and len(entries) == len(fingerprints):
            for entry, fingerprint in zip(entries, fingerprints, strict=True):
                entry[1] = fingerprint

    def _slot_append(self, key, record):
        """After glyport appended ``record`` at the end of the list."""
        token = record._axis_uuid if isinstance(record, GSAxis) else self._new_token()
        self._slot_tokens[key].append([token, self._fingerprints(key)[-1]])
        self._adopt(record, token)

    def _slot_pop(self, key, index):
        """After glyport removed the record at ``index``; positional backend
        ids of the records after it may have shifted, so take the new content."""
        token, _ = self._slot_tokens[key].pop(index)
        self._retire(token)
        self._slot_refresh(key)

    def _wrapper(self, cls, token, bind=None):
        record = self._records.get(token)
        if record is None:
            record = bind(token) if bind else cls._bind(self, token)
            self._records[token] = record
        return record

    def _adopt(self, record, token):
        record._font, record._token = self, token
        self._records[token] = record

    def _features_info(self):
        self._check()
        return self._model._backend.features(self._id)

    def _classes_info(self):
        self._check()
        return self._model._backend.classes(self._id)

    def _named_values(self, cls):
        tokens = self._named(cls._key)
        return [self._wrapper(cls, tokens[name]) for name in tokens]

    def _named_remove(self, record):
        name = record._name()
        backend = self._model._backend
        if record._key == "feature":
            backend.set_feature(self._id, name, None)
        elif record._key == "class":
            backend.set_class(self._id, name, None)
        else:
            backend.set_feature_prefix(self._id, "")
            self._prefix_pending = False
        self._retire(self._names[record._key].pop(name)[0])

    def _check_new(self, record, cls, what):
        if not isinstance(record, cls):
            raise TypeError(f"Expected {cls.__name__}")
        if record._font is not None:
            _unsupported(f"{what}.append ({cls.__name__} already in a font)")

    @property
    def features(self) -> ProxySequence:
        self._check()

        def append(feature):
            self._check_new(feature, GSFeature, "GSFont.features")
            name = _text(feature._values["name"], "name")
            code = _text(feature._values["code"], "code")
            if not name:
                raise ValueError("A feature needs a tag name")
            if name in self._named("feature"):
                _unsupported(
                    f"GSFont.features.append (FontLab keys features by tag: {name})"
                )
            self._check()
            self._model._backend.set_feature(
                self._id, name, _feature_text(name, None, code)
            )
            self._adopt(feature, self._named("feature")[name])

        return ProxySequence(
            lambda: self._named_values(GSFeature),
            lambda f: (f.name,),
            append=append,
            remove=self._named_remove,
        )

    @property
    def classes(self) -> ProxySequence:
        self._check()

        def append(cls):
            self._check_new(cls, GSClass, "GSFont.classes")
            name = _text(cls._values["name"], "name")
            members = _class_members(cls._values["code"])
            if not name:
                raise ValueError("A class needs a name")
            if name in self._named("class"):
                _unsupported(f"GSFont.classes.append (a class named {name} exists)")
            self._check()
            self._model._backend.set_class(self._id, name, members)
            self._adopt(cls, self._named("class")[name])

        return ProxySequence(
            lambda: self._named_values(GSClass),
            lambda c: (c.name,),
            append=append,
            remove=self._named_remove,
        )

    @property
    def featurePrefixes(self) -> ProxySequence:
        self._check()

        def append(prefix):
            self._check_new(prefix, GSFeaturePrefix, "GSFont.featurePrefixes")
            code = _text(prefix._values["code"], "code")
            if self._named("prefix"):
                _unsupported(
                    "GSFont.featurePrefixes.append (FontLab keeps one prefix; set its code)"
                )
            self._check()
            self._model._backend.set_feature_prefix(self._id, code)
            self._prefix_pending = True  # an empty prefix is a record too
            self._adopt(prefix, self._named("prefix")["Prefix"])

        return ProxySequence(
            lambda: self._named_values(GSFeaturePrefix),
            lambda f: (f.name,),
            append=append,
            remove=self._named_remove,
        )

    @property
    def axes(self) -> ProxySequence:
        self._check()
        backend = self._model._backend
        key = ("axes",)

        def records():
            tokens = self._slots(key)
            return tuple(
                replace(info, id=token)
                for token, info in zip(tokens, self._data().axes, strict=True)
            )

        def append(axis):
            self._check_new(axis, GSAxis, "GSFont.axes")
            name = _text(axis._values["name"], "name")
            tag = _axis_tag(axis._values["axisTag"])
            if not name:
                raise ValueError("An axis needs a name")
            axes = self._data().axes
            if any(a.name == name or a.tag == tag for a in axes):
                _unsupported(f"GSFont.axes.append (axis {name}/{tag} exists)")
            self._slots(key)
            self._slots(("instances",))
            self._check()
            backend.add_axis(
                self._id, AxisInfo("", name, tag, bool(axis._values["hidden"]))
            )
            self._slot_append(key, axis)
            self._slot_refresh(("instances",))  # instances gained a coordinate

        def remove(axis):
            index = self._slot(key, axis._token)
            self._slots(("instances",))
            self._check()
            backend.remove_axis(self._id, index)
            self._slot_pop(key, index)
            self._slot_refresh(("instances",))  # instances lost a coordinate

        return self._indexed(
            "axes",
            records,
            lambda token: self._wrapper(GSAxis, token),
            lambda info: (info.id, info.name, info.tag),
            append=append,
            remove=remove,
        )

    @property
    def instances(self) -> ProxySequence:
        self._check()
        backend = self._model._backend
        key = ("instances",)

        def values():
            return [self._wrapper(GSInstance, token) for token in self._slots(key)]

        def append(instance):
            self._check_new(instance, GSInstance, "GSFont.instances")
            name = _text(instance._values["name"], "name")
            if not name:
                raise ValueError("An instance needs a name")
            data = self._data()
            coordinates = instance._values["axes"]
            if not coordinates and data.masters:
                coordinates = data.masters[0].axes
            coordinates = _coordinates(coordinates, len(data.axes))
            self._slots(key)
            info = InstanceInfo(
                "", name, coordinates, bool(instance._values["exports"])
            )
            self._check()
            backend.add_instance(self._id, info)
            self._slot_append(key, instance)

        def remove(instance):
            index = self._slot(key, instance._token)
            self._check()
            backend.remove_instance(self._id, index)
            self._slot_pop(key, index)

        return ProxySequence(values, lambda i: (i.name,), append=append, remove=remove)

    def _glyph_ids(self):
        return {g.name: g.id for g in self._glyph_data()}

    @property
    def kerning(self):
        """LTR master writeback mapping; nested pair mappings are read-only."""
        from .kerning import KerningMapping

        self._check()
        return KerningMapping(self)

    def kerningDict(self):
        return self.kerning

    def kerningForPair(self, fontMasterId, leftKey, rightKey, direction=GSLTR):
        """Explicit pair only; Glyphs' Python wrapper converts large values to None."""
        value = self._kerning_for_pair(fontMasterId, leftKey, rightKey, direction)
        return None if value > KERNING_NONE_THRESHOLD else value

    def _kerning_for_pair(self, fontMasterId, leftKey, rightKey, direction=GSLTR):
        """Native direct-key value, before the Python wrapper's None conversion."""
        self._check()
        _ltr_only(direction)
        left, right = (
            _kerning_key(leftKey, LEFT_GROUP),
            _kerning_key(rightKey, RIGHT_GROUP),
        )
        pairs = self._model._backend.kerning(self._id, fontMasterId)
        return next(
            (float(p.value) for p in pairs if (p.left, p.right) == (left, right)),
            NO_KERNING_VALUE,
        )

    def setKerningForPair(
        self, fontMasterId, leftKey, rightKey, value, direction=GSLTR
    ):
        self._check()
        _ltr_only(direction)
        left, right = (
            _kerning_key(leftKey, LEFT_GROUP),
            _kerning_key(rightKey, RIGHT_GROUP),
        )
        self._model._backend.set_kerning(
            self._id, fontMasterId, left, right, float(value)
        )

    def removeKerningForPair(self, fontMasterId, leftKey, rightKey, direction=GSLTR):
        self._check()
        _ltr_only(direction)
        left, right = (
            _kerning_key(leftKey, LEFT_GROUP),
            _kerning_key(rightKey, RIGHT_GROUP),
        )
        self._model._backend.set_kerning(self._id, fontMasterId, left, right, None)

    @property
    def currentTab(self) -> GSEditViewController | None:
        self._check()
        view = self._model._backend.edit_view(self._id)
        return None if view is None else GSEditViewController(self, view.id)

    @currentTab.setter
    def currentTab(self, tab):
        self._check()
        current = self.currentTab
        if not isinstance(tab, GSEditViewController) or tab._font is not self:
            raise ValueError("Tab does not belong to this font")
        if current is None or current._tab_id != tab._tab_id:
            _unsupported("GSFont.currentTab.activateInactiveTab")
        tab._view()

    @property
    def tabs(self) -> ProxySequence:
        """The current native edit tab (other FontLab canvases are not exposed)."""
        return ProxySequence(lambda: [tab] if (tab := self.currentTab) else [])

    def newTab(self, tabText=""):
        """Open a FontLab glyph tab for this font (it becomes the active font)."""
        self._check()
        if isinstance(tabText, (list, tuple)):
            _tab_layer_lines(self, tabText)
        self._model._backend.open_edit_view(self._id)
        tab = self.currentTab
        if tab is None:
            _unsupported("GSFont.newTab (FontLab opened no glyph tab for this font)")
        if isinstance(tabText, (list, tuple)):
            tab.layers = tabText
        elif tabText:
            tab.text = tabText
        return tab

    @property
    def selectedLayers(self) -> list:
        """FontLab's current glyphs of this font (glyph tab or font window)."""
        self._check()
        masters = {m.name: m.id for m in self.masters}
        default = next(iter(masters.values()))
        return [
            self.glyphs[name].layers[masters.get(layer, default)]
            for name, layer in self._model._backend.current_layers(self._id)
        ]

    @property
    def selection(self) -> list:
        return list(dict.fromkeys(layer.parent for layer in self.selectedLayers))

    @selection.setter
    def selection(self, glyphs):
        self._check()
        if not isinstance(glyphs, (list, tuple)):
            raise TypeError("Font selection requires a list or tuple of glyphs")
        for glyph in glyphs:
            if not isinstance(glyph, GSGlyph):
                raise TypeError("Font selection requires glyphs")
            if glyph.parent != self:
                raise ValueError("Selected glyph belongs to a different font")
            glyph._check()
        ids = tuple(dict.fromkeys(glyph.id for glyph in glyphs))
        self._model._backend.set_font_selection(self._id, ids)

    @property
    def metrics(self):
        from .metrics import font_metrics

        self._check()
        return font_metrics(self)

    @property
    def selectedFontMaster(self):
        """FontLab's current master of this font."""
        self._check()
        id = self._model._backend.current_master(self._id)
        return next((m for m in self.masters if m.id == id), None)

    @selectedFontMaster.setter
    def selectedFontMaster(self, master):
        if master not in self.masters:
            raise ValueError("Master does not belong to this font")
        self._model._backend.set_current_master(self._id, master.id)

    @property
    def masterIndex(self):
        master = self.selectedFontMaster
        return next((i for i, item in enumerate(self.masters) if item is master), None)

    @masterIndex.setter
    def masterIndex(self, index):
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError("masterIndex must be an integer")
        if not 0 <= index < len(self.masters):
            raise IndexError(index)
        self.selectedFontMaster = self.masters[index]

    def disableUpdateInterface(self) -> None:
        """No-op: glyport publishes edits per undo group, not per UI refresh."""
        self._check()

    def enableUpdateInterface(self) -> None:
        """No-op counterpart of disableUpdateInterface."""
        self._check()

    @contextmanager
    def undo_group(self, name):
        self._begin_undo(name)
        try:
            yield self
        except BaseException as error:
            try:
                self._end_undo()
            except Exception as end_error:  # noqa: BLE001 - keep the body's error
                error.add_note(f"glyport: closing the undo group failed: {end_error!r}")
            raise
        else:
            self._end_undo()

    def _begin_undo(self, name):
        self._check()
        if self._undo_pending:
            raise RuntimeError(
                "Previous undo publication failed; close the pending Undo step first"
            )
        if self._undo_depth == 0:
            self._model._backend.begin_undo(name)
            self._undo_label = name
        self._undo_depth += 1

    def _end_undo(self):
        if self._undo_depth:
            self._undo_depth -= 1
            if self._undo_depth:
                return
            self._undo_pending = True
        if self._undo_pending:
            self._model._backend.end_undo()
            self._undo_pending = False
            self._undo_glyphs.clear()

    def _finish_undo(self, diagnostic_sink):
        """Publish abandoned edits; failed publication remains explicitly pending."""
        for diagnostic in self.__dict__.pop("_pending_diagnostics", {}).values():
            diagnostic_sink(diagnostic)
        if not self._undo_depth and not self._undo_pending:
            return
        from ..receipt import ReceiptDiagnostic

        names = ", ".join(name for _, name in self._undo_glyphs.values())
        owner = f"glyph {names}" if names else self._undo_label
        self._undo_depth = 0
        self._undo_pending = True
        for glyph, _ in self._undo_glyphs.values():
            glyph._undo_count = 0
        try:
            validation_error = None
            try:
                valid = self._model._backend.can_publish_undo(self._id)
                reason = "font/package is closed or unregistered, or a changed object is stale"
            except Exception as error:  # noqa: BLE001 - never publish unverified native objects
                valid, reason = False, f"could not verify native validity: {error!r}"
                validation_error = error
            if not valid:
                self._model._backend.discard_undo()
                self._undo_pending = False
                self._undo_glyphs.clear()
                diagnostic_sink(
                    ReceiptDiagnostic(
                        "UNBALANCED_UNDO_DISCARDED",
                        "warning",
                        f"Discarded pending Undo for {owner}: {reason}.",
                        capability="GSGlyph.endUndo",
                    )
                )
                if validation_error is not None:
                    raise validation_error
                return
            self._end_undo()
        except BaseException as error:
            diagnostic_sink(
                ReceiptDiagnostic(
                    "UNDO_CLOSE_FAILED",
                    "error",
                    f"Closing Undo for {owner} failed: {error!r}",
                    capability="GSGlyph.endUndo",
                )
            )
            raise
        diagnostic_sink(
            ReceiptDiagnostic(
                "UNBALANCED_UNDO_CLOSED",
                "warning",
                f"Published an unbalanced Undo step for {owner} at the execution boundary.",
                capability="GSGlyph.endUndo",
            )
        )


class GSFontMaster(_Proxy):
    def __init__(self):
        from .backend import MasterInfo, MasterMetrics

        self._id = uuid4().hex
        self._draft = MasterInfo(self._id, "Regular")
        self._draft_metrics = MasterMetrics(800, 700, -200, 500, 0)

    def _check(self):
        if "_draft" not in self.__dict__:
            super()._check()

    def _data(self):
        return self._draft if "_draft" in self.__dict__ else super()._data()

    def _set_value(self, field, value):
        if field != "name":
            value = float(value)
            if not math.isfinite(value):
                raise ValueError("Master metrics must be finite")
        else:
            value = _text(value, "master name")
            if not value:
                raise ValueError("Master name must not be empty")
        if "_draft" in self.__dict__:
            if field == "name":
                self._draft = replace(self._draft, name=value)
            else:
                self._draft_metrics = replace(self._draft_metrics, **{field: value})
            return
        self._check()
        with self._font.undo_group("Set master " + field):
            self._font._model._backend.set_master_info(self._id, **{field: value})

    @property
    def font(self):
        self._check()
        return self.__dict__.get("_font")

    @property
    def userData(self):
        return self._lib_user_data(
            (
                "com.schriftgestaltung.customParameter.GSFontMaster.",
                "com.fontlab.glyport.orderedParameters.",
            )
        )

    @property
    def customParameters(self):
        import json

        self._check()
        # Names are native persistent master identifiers; proxy tokens are not.
        prefix = (
            "com.schriftgestaltung.customParameter.GSFontMaster."
            + json.dumps(self.name)
            + "."
        )
        return CustomParameters(self._font, prefix, self._id, parent=self)

    @property
    def guides(self):
        def make(token):
            return self._font._proxy(GSGuide, token, lambda: sequence.info(token))

        sequence = self._font._indexed(
            (self._id, "master-guides"),
            lambda: self._font._model._backend.master_guides(self._id),
            make,
            lambda info: (info.name, info.id),
        )

        def append(guide):
            if not isinstance(guide, GSGuide):
                raise TypeError("Expected GSGuide")
            self._check()
            token = self._font._model._backend.append_master_guide(
                self._id, guide._data()
            )
            return make(token)

        sequence._append = append
        return sequence

    @property
    def alignmentZones(self):
        from .zones import GSAlignmentZone

        backend = self._font._model._backend

        def infos():
            return self._font._layer_info(
                (self._id, "zones"), lambda: backend.master_zones(self._id)
            )

        def values():
            result = []
            for index in range(len(infos())):
                zone = GSAlignmentZone()
                zone._read = lambda index=index: infos()[index]
                zone._write = lambda pos, size, index=index: backend.set_master_zone(
                    self._id, index, pos, size
                )
                result.append(zone)
            return result

        return ProxySequence(values)

    @property
    def name(self) -> str:
        return self._data().name

    @name.setter
    def name(self, value):
        self._set_value("name", value)

    @property
    def axes(self) -> list[float]:
        return list(self._data().axes)

    @axes.setter
    def axes(self, values):
        coords = _coordinates(values, len(self._font._data().axes))
        self._check()
        self._font._model._backend.set_master_axes(self._id, coords)

    @property
    def internalAxesValues(self):
        from .axis_values import AxisValues

        return AxisValues(self)

    @internalAxesValues.setter
    def internalAxesValues(self, values):
        self.axes = values

    def _metrics(self):
        if "_draft" in self.__dict__:
            return self._draft_metrics
        self._check()
        return self._font._model._backend.master_metrics(self._id)

    @property
    def metrics(self):
        from .metrics import master_metrics

        self._check()
        return master_metrics(self)

    metricValues = metrics

    @property
    def ascender(self) -> float:
        return self._metrics().ascender

    @ascender.setter
    def ascender(self, value):
        self._set_value("ascender", value)

    @property
    def capHeight(self) -> float:
        return self._metrics().capHeight

    @capHeight.setter
    def capHeight(self, value):
        self._set_value("capHeight", value)

    @property
    def descender(self) -> float:
        return self._metrics().descender

    @descender.setter
    def descender(self, value):
        self._set_value("descender", value)

    @property
    def xHeight(self) -> float:
        return self._metrics().xHeight

    @xHeight.setter
    def xHeight(self, value):
        self._set_value("xHeight", value)

    def slantHeightForLayer_(self, layer):
        """GlyphsCore slant metric, falling back to half the master's x-height."""
        value = layer.metricForType_(3)
        if value is None or value > 10000:
            value = self.xHeight / 2
        return float(value) if value <= 10000 else 0.0

    @property
    def italicAngle(self) -> float:
        return self._metrics().italicAngle

    @italicAngle.setter
    def italicAngle(self, value):
        self._set_value("italicAngle", value)


class _Draft(_Proxy):
    @property
    def parent(self):
        if "_draft" in self.__dict__:
            return self.__dict__.get("_parent")
        self._check()
        parent = getattr(self._font._model._backend, "proxy_parent", None)
        token = parent(self._id) if parent else None
        return self._font._native_layer(token) if token is not None else None

    def _data(self):
        return self._draft if "_draft" in self.__dict__ else super()._data()


class GSGlyph(_Draft):
    @property
    def selected(self):
        if "_draft" in self.__dict__:
            return self.__dict__.get("_selected", False)
        self._check()
        return self._font._model._backend.glyph_selected(self._font._id, self._id)

    @selected.setter
    def selected(self, value):
        if "_draft" in self.__dict__:
            self._selected = bool(value)
        else:
            self._check()
            self._font._model._backend.set_glyph_selected(
                self._font._id, self._id, bool(value)
            )

    """A font's glyph; ``GSGlyph(name)`` is a new glyph until appended to
    ``font.glyphs``."""

    def __init__(self, name=None):
        from ..glyphsapp.glyph_info import creation_unicodes

        name = str(name or "")
        self._draft = GlyphInfo("", name, creation_unicodes(name) if name else ())

    def mastersCompatibleForLayerIds_(self, layer_ids):
        from .compatibility import compatible

        layer_ids = tuple(layer_ids)
        if "_draft" in self.__dict__:
            return compatible(self, layer_ids)
        return self._font._layer_info(
            ("master-compatibility", self._id, layer_ids),
            lambda: compatible(self, layer_ids),
        )

    def beginUndo(self):
        self._check()
        self._font._begin_undo(f"Edit {self.name}")
        self._font._undo_glyphs[id(self)] = (self, self.name)
        self._undo_count = self.__dict__.get("_undo_count", 0) + 1

    def endUndo(self):
        count = self.__dict__.get("_undo_count", 0)
        if count:
            try:
                self._font._end_undo()
            finally:
                self._undo_count = count - 1
                if self._undo_count == 0 and not self._font._undo_pending:
                    self._font._undo_glyphs.pop(id(self), None)
        elif self._font._undo_pending and id(self) in self._font._undo_glyphs:
            self._font._end_undo()

    @property
    def name(self) -> str:
        return self._data().name

    @name.setter
    def name(self, value):
        value = _text(value, "name")
        previous = self.name
        if value == previous:
            return
        from .glyph_metadata import FIELDS, private_use, resolve

        state = self._case_state()
        previous_values = {key: getattr(self, field) for field, key, _ in FIELDS}
        codes = self.unicodes
        if codes and not private_use(int(codes[0], 16)):
            codes = []
        record = resolve(self, name=value, unicodes=codes, state=state)
        if record is None:
            for key, current in previous_values.items():
                state.setdefault(key, current)
        else:
            state = self._refreshed_metadata(record, state)
            codes = list(
                getattr(record, "unicodes", (record.unicode,) if record.unicode else ())
            )
        self._write_metadata(value, codes, state, "GSGlyph.name.case.rollback")

    @property
    def parent(self):
        return None if "_draft" in self.__dict__ else self._font

    @property
    def glyphInfo(self):
        if "_draft" in self.__dict__:
            _unsupported("GSGlyph.glyphInfo.detached")
        self._check()
        return self.parent.glyphsInfo().glyphInfoForGlyph_(self)

    @property
    def unicodes(self) -> list[str]:
        return list(self._data().unicodes)

    @unicodes.setter
    def unicodes(self, values):
        codes = tuple(f"{int(value, 16):04X}" for value in values)
        if any(not 0 <= int(value, 16) <= 0x10FFFF for value in codes):
            raise ValueError("Unicode value is out of range")
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, unicodes=codes)
        else:
            self._check()
            self._font._model._backend.set_glyph_unicodes(self._id, codes)

    @property
    def unicode(self) -> str | None:
        return next(iter(self.unicodes), None)

    @unicode.setter
    def unicode(self, value):
        self.unicodes = [] if value is None else [value]

    @property
    def string(self) -> str | None:
        return chr(int(self.unicode, 16)) if self.unicode else None

    @property
    def color(self):
        """Glyphs label colour index from FontLab's mark hue (None = no mark)."""
        self._check()
        return _mark_to_label(self._font._model._backend.mark(self._id))

    @color.setter
    def color(self, value):
        self._check()
        self._font._model._backend.set_mark(self._id, _label_to_mark(value))

    @property
    def tags(self) -> ProxySequence:
        """Glyphs 3 glyph tags: a live list (append, remove, ``in``)."""
        self._check()
        backend = self._font._model._backend

        def append(tag):
            backend.set_glyph_tags(self._id, (*backend.glyph_tags(self._id), str(tag)))

        def remove(tag):
            tags = list(backend.glyph_tags(self._id))
            tags.remove(tag)
            backend.set_glyph_tags(self._id, tuple(tags))

        return ProxySequence(
            lambda: list(backend.glyph_tags(self._id)),
            keys=lambda tag: (tag,),
            append=append,
            remove=remove,
        )

    @tags.setter
    def tags(self, value):
        self._check()
        tags = tuple(str(t) for t in value or ())
        self._font._model._backend.set_glyph_tags(self._id, tags)

    def glyphId(self) -> int:
        """Index of this glyph in its font's glyph order."""
        return self._font.glyphs.ordinal(self._id)

    @property
    def export(self) -> bool:
        """No per-glyph export flag was found in FontLab 9's Python API or VFJ
        (glyport-matrix/probe_glyph_export.json), so the flag is the UFO font
        lib list ``public.skipExportGlyphs``. FontLab's own export does not
        read it; tools that read the lib (UFO export, fontmake) do."""
        self._check()
        lib = self._font._model._backend.lib(self._font._id)
        return self.name not in lib.get(SKIP_EXPORT_KEY, ())

    @export.setter
    def export(self, value) -> None:
        self._check()
        backend = self._font._model._backend
        lib = backend.lib(self._font._id)
        names = [n for n in lib.get(SKIP_EXPORT_KEY, ()) if n != self.name]
        if not value:
            names.append(self.name)
        if names == list(lib.get(SKIP_EXPORT_KEY, ())):
            return  # unchanged: no write (CJK Metrics sets it on every paint)
        lib[SKIP_EXPORT_KEY] = names
        backend.set_lib(self._font._id, lib)

    def _glyph_lib_value(self, key, default=None):
        self._check()
        return self._font._model._backend.lib(self._id).get(key, default)

    def _set_glyph_lib_value(self, key, value) -> None:
        self._check()
        backend = self._font._model._backend
        lib = backend.lib(self._id)
        if lib.get(key) == value:
            return  # unchanged: no write
        lib[key] = value
        backend.set_lib(self._id, lib)

    @property
    def storeScript(self) -> bool:
        return bool(self._case_state().get(STORE_SCRIPT_KEY, False))

    @storeScript.setter
    def storeScript(self, value) -> None:
        self._store_metadata("script", SCRIPT_KEY, STORE_SCRIPT_KEY, value)

    @property
    def group(self):
        from .stored_glyph_fields import raw_value

        return raw_value(self, "group")

    @group.setter
    def group(self, value):
        from .stored_glyph_fields import set_raw_value

        set_raw_value(self, "group", value)

    @property
    def groupIdx(self):
        from .stored_glyph_fields import raw_value

        return raw_value(self, "groupIdx")

    @groupIdx.setter
    def groupIdx(self, value):
        from .stored_glyph_fields import set_raw_value

        set_raw_value(self, "groupIdx", value)

    @property
    def direction(self):
        from .stored_glyph_fields import raw_value

        return raw_value(self, "direction")

    @direction.setter
    def direction(self, value):
        from .stored_glyph_fields import set_raw_value

        set_raw_value(self, "direction", value)

    @property
    def storeGroup(self):
        from .stored_glyph_fields import STORE_GROUP_KEY

        return bool(self._case_state().get(STORE_GROUP_KEY, False))

    @storeGroup.setter
    def storeGroup(self, value):
        from .stored_glyph_fields import set_store

        set_store(self, "group", value)

    @property
    def storeDirection(self):
        from .stored_glyph_fields import STORE_DIRECTION_KEY

        return bool(self._case_state().get(STORE_DIRECTION_KEY, False))

    @storeDirection.setter
    def storeDirection(self, value):
        from .stored_glyph_fields import set_store

        set_store(self, "direction", value)

    def _refreshed_metadata(self, record, state):
        from .glyph_metadata import FIELDS
        from .stored_glyph_fields import GROUP_IDX_KEY, STORE_GROUP_KEY, record_value

        state = state.copy()
        for field, key, flag in FIELDS:
            if state.get(flag, False):
                continue
            if record is None and field not in {"category", "subCategory"}:
                continue
            value = record_value(record, field) if record is not None else None
            if key in state or value != getattr(self, field):
                state[key] = value
        if record is not None and not state.get(STORE_GROUP_KEY, False):
            value = record_value(record, "groupIdx")
            if GROUP_IDX_KEY in state or value != self.groupIdx:
                state[GROUP_IDX_KEY] = value
        return state

    def _write_metadata(self, name, codes, state, capability):
        previous_name, previous_codes = self.name, self.unicodes
        previous_state = self._case_state()
        if "_draft" in self.__dict__:
            data = replace(self._draft, name=name, unicodes=tuple(codes))
            self._set_case_state(state)
            self._draft = data
            return
        backend = self._font._model._backend
        try:
            if name != previous_name:
                backend.rename_glyph(self._font._id, self._id, name)
            if list(codes) != self.unicodes:
                self.unicodes = codes
            if state != self._case_state():
                self._set_case_state(state)
        except BaseException as error:
            try:
                if self.name != previous_name:
                    backend.rename_glyph(self._font._id, self._id, previous_name)
                if self.unicodes != previous_codes:
                    self.unicodes = previous_codes
                if self._case_state() != previous_state:
                    self._set_case_state(previous_state)
            except BaseException as recovery:
                failure = PartialFailure(
                    "Metadata refresh failed and glyph state could not be reverted",
                    capability=capability,
                )
                failure.errors = (error, recovery)
                raise failure from recovery
            raise

    def updateGlyphInfo(self, changeName=True):
        from .glyph_metadata import resolve

        state = self._case_state()
        record = resolve(self, state=state)
        state = self._refreshed_metadata(record, state)
        name = self.name
        if record is not None and changeName and record.category != "Private Use":
            name = record.name
        codes = (
            list(
                getattr(record, "unicodes", (record.unicode,) if record.unicode else ())
            )
            if record is not None
            else []
        )
        self._write_metadata(
            name, codes, state, "GSGlyph.updateGlyphInfo.case.rollback"
        )

    def _metadata_value(self, field, key):
        state = self._case_state()
        if key in state:
            return state[key]
        from .glyph_metadata import raw_name_info

        record = raw_name_info(self.name)
        return getattr(record, field) if record is not None else None

    def _set_metadata_value(self, field, key, value):
        if getattr(self, field) == value:
            return
        state = self._case_state()
        state[key] = value
        self._set_case_state(state)

    def _store_metadata(self, field, key, flag, value):
        from .glyph_metadata import resolve

        value = bool(value)
        state = self._case_state()
        if bool(state.get(flag, False)) == value:
            return
        state[flag] = value
        if not value:
            if "_draft" in self.__dict__:
                _unsupported(
                    f"GSGlyph.store{field[0].upper() + field[1:]}.detachedReset"
                )
            record = resolve(self, state=state)
            if record is None:
                _unsupported(
                    f"GSGlyph.store{field[0].upper() + field[1:]}.missingMetadata"
                )
            state[key] = getattr(record, field)
        else:
            state[key] = getattr(self, field)
        self._set_case_state(state)

    @property
    def category(self) -> str | None:
        return self._metadata_value("category", CATEGORY_KEY)

    @category.setter
    def category(self, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("Category must be a string or None")
        self._set_metadata_value("category", CATEGORY_KEY, value)

    @property
    def subCategory(self) -> str | None:
        return self._metadata_value("subCategory", SUBCATEGORY_KEY)

    @subCategory.setter
    def subCategory(self, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("Subcategory must be a string or None")
        self._set_metadata_value("subCategory", SUBCATEGORY_KEY, value)

    @property
    def storeCategory(self) -> bool:
        return bool(self._case_state().get(STORE_CATEGORY_KEY, False))

    @storeCategory.setter
    def storeCategory(self, value):
        self._store_metadata("category", CATEGORY_KEY, STORE_CATEGORY_KEY, value)

    @property
    def storeSubCategory(self) -> bool:
        return bool(self._case_state().get(STORE_SUBCATEGORY_KEY, False))

    @storeSubCategory.setter
    def storeSubCategory(self, value):
        self._store_metadata(
            "subCategory", SUBCATEGORY_KEY, STORE_SUBCATEGORY_KEY, value
        )

    @staticmethod
    def _default_case(name):
        from .glyph_metadata import raw_name_info

        record = raw_name_info(name)
        return None if record is None else record.case

    def _case_state(self):
        # Metadata fields share one snapshot and one backend write.
        if "_draft" in self.__dict__:
            return self.__dict__.get("_case_metadata", {}).copy()
        self._check()
        return self._font._model._backend.lib(self._id)

    def _set_case_state(self, state):
        if "_draft" in self.__dict__:
            self._case_metadata = state.copy()
        else:
            self._check()
            self._font._model._backend.set_lib(self._id, state)

    @property
    def case(self) -> int:
        state = self._case_state()
        if CASE_KEY in state:
            return state[CASE_KEY]
        return self._default_case(self.name) or 0

    @case.setter
    def case(self, value):
        if not isinstance(value, int):
            raise TypeError("Case must be an integer")
        if not 0 <= value <= 255:
            raise ValueError("Case must fit an unsigned byte")
        if self.case == value:
            return
        state = self._case_state()
        state[CASE_KEY] = value
        self._set_case_state(state)

    @property
    def storeCase(self) -> bool:
        return bool(self._case_state().get(STORE_CASE_KEY, False))

    @storeCase.setter
    def storeCase(self, value):
        self._store_metadata("case", CASE_KEY, STORE_CASE_KEY, value)

    @staticmethod
    def _default_script(name):
        from .glyph_metadata import raw_name_info

        record = raw_name_info(name)
        return record is not None, None if record is None else record.script

    @property
    def script(self) -> str | None:
        """Effective script metadata; an explicit None remains a value."""
        state = self._case_state()
        return (
            state[SCRIPT_KEY]
            if SCRIPT_KEY in state
            else self._default_script(self.name)[1]
        )

    @script.setter
    def script(self, value) -> None:
        value = None if value is None else str(value)
        if self.script == value:
            return
        state = self._case_state()
        state[SCRIPT_KEY] = value
        self._set_case_state(state)

    @property
    def note(self) -> str:
        self._check()
        return self._font._model._backend.glyph_note(self._id)

    @property
    def lastChange(self) -> str | None:
        self._check()
        return self._font._model._backend.glyph_last_change(self._id)

    def charString(self) -> str:
        code = self.unicode
        return chr(int(code, 16)) if code else ""

    @property
    def userData(self) -> UserData:
        return self._lib_user_data()

    def _glyph_metrics_key(self, side):
        if "_draft" in self.__dict__:
            return self.__dict__.get("_glyph_metrics_keys", {}).get(side)
        return self._glyph_lib_value(
            "com.schriftgestaltung.Glyphs." + side + "MetricsKey"
        )

    def _set_glyph_metrics_key(self, side, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("A metrics key must be a string or None")
        if "_draft" in self.__dict__:
            self.__dict__.setdefault("_glyph_metrics_keys", {})[side] = value
            return
        self._set_glyph_lib_value(
            "com.schriftgestaltung.Glyphs." + side + "MetricsKey", value
        )

    leftMetricsKey = property(
        lambda self: self._glyph_metrics_key("left"),
        lambda self, value: self._set_glyph_metrics_key("left", value),
    )
    rightMetricsKey = property(
        lambda self: self._glyph_metrics_key("right"),
        lambda self, value: self._set_glyph_metrics_key("right", value),
    )
    widthMetricsKey = property(
        lambda self: self._glyph_metrics_key("width"),
        lambda self, value: self._set_glyph_metrics_key("width", value),
    )

    def _kerning_group(self, side):
        name = self.name

        def read():
            groups = {}
            for group in self._font._model._backend.kerning_classes(self._font._id):
                if getattr(group, side):
                    for member in group.glyphs:
                        groups.setdefault(member, group.name)
            return groups

        # The map covers every glyph, but native classes follow the current
        # master, whose selection need not advance the font's history revision.
        master = self._font._model._backend.current_master(self._font._id)
        return self._font._layer_info(("kerning-groups", side, master), read).get(name)

    @property
    def rightKerningGroup(self) -> str | None:
        """Glyphs: the group used when this glyph is on the pair's left (@MMK_L_)."""
        return self._kerning_group("left")

    @property
    def leftKerningGroup(self) -> str | None:
        """Glyphs: the group used when this glyph is on the pair's right (@MMK_R_)."""
        return self._kerning_group("right")

    def _set_kerning_group(self, side, value):
        from .kerning import group_name

        self._check()
        value = group_name(value)
        self._font._model._backend.set_kerning_group(
            self._font._id, self._id, side, value
        )

    @rightKerningGroup.setter
    def rightKerningGroup(self, value):
        self._set_kerning_group("left", value)

    @leftKerningGroup.setter
    def leftKerningGroup(self, value):
        self._set_kerning_group("right", value)

    @property
    def leftKerningKey(self):
        group = self.leftKerningGroup
        return RIGHT_GROUP + group if group else self.name

    @property
    def rightKerningKey(self):
        group = self.rightKerningGroup
        return LEFT_GROUP + group if group else self.name

    @property
    def layers(self) -> ProxySequence:
        from .indexes import LayerSequence
        from .layer_attachment import append_layer

        def make(layer_id):
            def read():
                return self._font._layer_info(
                    (self._id, layer_id),
                    lambda: self._font._model._backend.layer(self._id, layer_id),
                )
            info = read()
            layer = self._font._proxy(GSLayer, info.id, read)
            layer._glyph = self
            return layer

        return self._font._indexed(
            (self._id, "layers"),
            lambda: self._font._model._backend.glyph_layers(self._id),
            make,
            lambda info: (info.id,),
            sequence_type=LayerSequence,
            masters=lambda: list(self._font.masters),
            append=lambda layer: append_layer(self, layer),
        )


class GSLayer(_Proxy):
    def _outline_edit(self, method, **options):
        self._check()
        if method in {"add_layer_extrema", "remove_layer_overlap"}:
            return getattr(self._font._model._backend, method)(
                self._id, **options,
                undo_group=lambda: self._font.undo_group("Change layer"),
            )
        with self._font.undo_group("Change layer"):
            getattr(self._font._model._backend, method)(self._id, **options)

    def removeOverlap(self, checkSelection=False) -> None:
        """Join closed paths, optionally considering only selected contours."""
        self._outline_edit("remove_layer_overlap", check_selection=checkSelection)

    def decomposeComponents(self) -> None:
        """Recursively replace components with transformed outlines in one Undo group."""
        self._outline_edit("decompose_layer_components")

    def correctPathDirection(self) -> None:
        """Orient outer closed paths counterclockwise and counters clockwise."""
        if "_draft" in self.__dict__:
            from .outline_geometry import _direction_paths, _draft
            from .pens import path_info

            self.paths = [_draft(p) for p in _direction_paths(tuple(path_info(p) for p in self.paths))]
            return
        self._outline_edit("correct_layer_direction")

    def addNodesAtExtremes(self, force=False, checkSelection=False) -> None:
        """Insert exact cubic/quadratic extrema; preserve the curve's geometry."""
        if "_draft" in self.__dict__:
            from .outline_ops import _draft, _extreme_paths
            from .pens import path_info

            self.paths = [_draft(p) for p in _extreme_paths(tuple(path_info(p) for p in self.paths), checkSelection)]
            return
        self._outline_edit("add_layer_extrema", force=force, check_selection=checkSelection)

    def getPen(self):
        """Return a writing pen accepting fontTools segment and point commands."""
        from .pens import LayerPen

        self._check()
        return LayerPen(self)

    def getPointPen(self):
        """Return a writing point pen (the same dual protocol as getPen)."""
        return self.getPen()

    def draw(self, pen, contours=True, components=True) -> None:
        """Draw to a fontTools segment pen without changing the layer."""
        self._draw_to_pen(pen, False, contours, components)

    def drawPoints(self, pointPen, contours=True, components=True) -> None:
        """Draw node types, smoothness, names and components to a point pen."""
        self._draw_to_pen(pointPen, True, contours, components)

    def _draw_to_pen(self, pen, points, contours, components):
        self._check()
        if "_draft" in self.__dict__:
            from dataclasses import replace

            from .pens import draw_info, path_info

            info = replace(self._data(), paths=tuple(path_info(p) for p in self.paths),
                           components=tuple(c._data() for c in self.components))
            draw_info(info, pen, points=points, contours=contours, components=components)
        else:
            self._font._model._backend.draw_layer(self._id, pen, points=points,
                                                 contours=contours, components=components)

    def compareString(self):
        from .compatibility import compare_string

        return compare_string(self)

    def beginChanges(self):
        """Group live edits in the existing document Undo scope."""
        # Keep the font token, not a generator context manager: __exit__
        # exhausts that generator even when publishing Undo raises.
        font = None if "_draft" in self.__dict__ else self._font
        if font is not None:
            font._begin_undo("Change layer")
        self.__dict__.setdefault("_change_scopes", []).append(font)

    def endChanges(self):
        scopes = self.__dict__.get("_change_scopes", [])
        if not scopes:
            raise RuntimeError("endChanges requires a matching beginChanges")
        font = scopes[-1]
        if font is not None:
            font._end_undo()
        scopes.pop()

    def anchorForName_(self, name):
        return self.anchors[name]

    def removeShape_(self, shape):
        self.shapes.remove(shape)

    def indexOfObjectInShapes_(self, shape):
        return list(self.shapes).index(shape) if shape in self.shapes else NSNOTFOUND

    def indexOfPath_(self, path):
        return list(self.paths).index(path) if path in self.paths else NSNOTFOUND

    @property
    def isBracketLayer(self):
        return False if self.isMasterLayer else bool(self.attributes["axisRules"])

    @property
    def isBraceLayer(self):
        return False if self.isMasterLayer else bool(self.attributes["coordinates"])

    @property
    def italicAngle(self):
        return self.master.italicAngle

    @property
    def slantHeight(self):
        return self.master.slantHeightForLayer_(self)

    def updateMetrics(self):
        self._check()
        from .metrics_keys import update

        if not update(self):
            self._font._model._backend.update_layer_metrics(self._id)

    def transform_checkForSelection_doComponents_(
        self, transform, selection, components
    ):
        if hasattr(transform, "transformStruct"):
            transform = transform.transformStruct()
        values = tuple(float(value) for value in transform)
        if len(values) != 6:
            raise ValueError("transform needs six values")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Affine transform values must be finite")
        if not selection and components:
            return self.applyTransform(values)
        if selection and components and self.components:
            _unsupported("GSLayer.transform.componentSelection")
        # Resolve selection before editing: unsupported native anchor selection
        # must not leave half a transform applied to the outline.
        nodes = [
            node
            for path in self.paths
            for node in path.nodes
            if not selection or node.selected
        ]
        anchors = [
            anchor for anchor in self.anchors if not selection or anchor.selected
        ]
        moves = _mapped_positions([*nodes, *anchors], values)
        group = (
            self._font.undo_group("Transform layer")
            if "_font" in self.__dict__
            else nullcontext()
        )
        with group:
            for item, position in moves:
                item.position = position

    def indexPathOfNode_(self, node):
        from ..foundation import NSIndexPath

        if not isinstance(node, GSNode) or node.parent not in self.shapes:
            return None
        shapes = self.shapes
        index = (
            shapes.ordinal(node.parent.id)
            if hasattr(shapes, "ordinal")
            else list(shapes).index(node.parent)
        )
        return NSIndexPath((index, node.index))

    def nodeAtIndexPath_(self, index):
        if index is None or len(index) != 2 or any(i < 0 for i in index):
            return None
        try:
            shape = self.shapes[index[0]]
            return shape.nodes[index[1]] if isinstance(shape, GSPath) else None
        except IndexError:
            return None

    def clear(self):
        self._check()
        backend = self._font._model._backend
        state = backend.snapshot_collection(self._id)
        with self._font.undo_group("Glyport clear layer"):
            try:
                self.shapes = None
                self.anchors = None
                for hint in list(self.hints):
                    self.hints.remove(hint)
            except BaseException:
                backend.restore_collection(self._id, state)
                raise

    def __new__(cls, *args, **kwargs):
        if cls is GSLayer and not args and not kwargs:
            from .copies import DetachedLayer

            return object.__new__(DetachedLayer)
        return object.__new__(cls)

    @property
    def background(self):
        self._check()
        from .background import GSBackgroundLayer

        backend = self._font._model._backend
        def read():
            return self._font._layer_info(
                ("background", self._id), lambda: backend.background_layer(self._id)
            )
        result = self._font._proxy(GSBackgroundLayer, read().id, read)
        result._glyph = self.__dict__.get("_glyph")
        result._foreground = self
        return result

    @background.setter
    def background(self, value):
        self._check()
        if value is not None and not isinstance(value, GSLayer):
            raise TypeError("background must be a GSLayer or None")
        from .attachment import require_supported_attributes

        if value is not None:
            require_supported_attributes(value)
        source = None if value is None else value.copy()
        with self._font.undo_group("Glyport background"):
            if source is None:
                self._font._model._backend.clear_background_layer(self._id)
                return
            target = self.background
            target.shapes = source.shapes
            target.anchors = source.anchors
            target.guides = source.guides
            target.userData.clear()
            target.userData.update(dict(source.userData))
            for side in ("left", "right", "width"):
                setattr(
                    target, side + "MetricsKey", getattr(source, side + "MetricsKey")
                )

    def foreground(self):
        if "_foreground" not in self.__dict__:
            _unsupported("GSLayer.foreground")
        return self._foreground

    def _metrics_key(self, side):
        self._check()
        return self._font._model._backend.layer_metrics_key(self._id, side)

    def _set_metrics_key(self, side, value):
        self._check()
        if value is not None and not isinstance(value, str):
            raise TypeError("A metrics key must be a string or None")
        self._font._model._backend.set_layer_metrics_key(self._id, side, value)

    leftMetricsKey = property(
        lambda self: self._metrics_key("left"),
        lambda self, value: self._set_metrics_key("left", value),
    )
    rightMetricsKey = property(
        lambda self: self._metrics_key("right"),
        lambda self, value: self._set_metrics_key("right", value),
    )
    widthMetricsKey = property(
        lambda self: self._metrics_key("width"),
        lambda self, value: self._set_metrics_key("width", value),
    )

    @property
    def layerId(self) -> str:
        info = self._data()
        return info.layerId or info.masterId

    @property
    def associatedMasterId(self) -> str:
        """The connected master's ID, independent of an auxiliary's own ID."""
        return self._data().masterId

    @property
    def width(self) -> float:
        return self._data().width

    @width.setter
    def width(self, value):
        self._check()
        self._font._model._backend.set_layer_width(self._id, float(value))

    @property
    def userData(self) -> UserData:
        return self._lib_user_data()

    @property
    def name(self) -> str | None:
        """Preserve auxiliary names, including empty or absent values."""
        info = self._data()
        if (
            "_foreground" not in self.__dict__
            and info.layerId
            and info.layerId != info.masterId
        ):
            return info.name
        return info.name or self.master.name

    @property
    def parent(self):
        """The ``GSGlyph`` this layer belongs to."""
        self._check()
        glyph = self.__dict__.get("_glyph")
        if glyph is None:
            _unsupported("GSLayer.parent of a layer not reached through its glyph")
        return glyph

    @property
    def master(self) -> GSFontMaster:
        layer_id = self.associatedMasterId
        return next(m for m in self._font.masters if m.id == layer_id)

    @property
    def vertWidth(self) -> float | None:
        """FontLab's advance height; None when the layer has none set."""
        self._check()
        return self._font._model._backend.layer_vertical_width(self._id)

    def _vertical(self) -> tuple[float, float]:
        """Glyphs' vertical origin (the ascender) and vertical width (default
        ascender - descender)."""
        m = self.master._metrics()
        width = self.vertWidth
        return m.ascender, width if width is not None else m.ascender - m.descender

    @property
    def TSB(self) -> float:
        bounds = self._bounds()
        return 0.0 if bounds is None else self._vertical()[0] - (bounds[1] + bounds[3])

    @property
    def BSB(self) -> float:
        bounds = self._bounds()
        if bounds is None:
            return 0.0
        origin, width = self._vertical()
        return bounds[1] - (origin - width)

    def glyph(self):
        """Glyphs' ``layer.glyph()``: the parent glyph."""
        return self.parent

    @property
    def isMasterLayer(self) -> bool:
        return (
            bool(self.associatedMasterId)
            and self.layerId == self.associatedMasterId
            and "_foreground" not in self.__dict__
        )

    @property
    def isSpecialLayer(self) -> bool:
        return False

    def associatedFontMaster(self):
        return self.master

    def metricForType_(self, kind):
        """GSMetricsType values from the master; types FontLab has no
        counterpart for (slant, mid, body height) read None."""
        m = self.master._metrics()
        values = {
            1: m.ascender,
            2: m.capHeight,
            4: m.xHeight,
            7: m.descender,
            8: 0,
            9: m.italicAngle,
        }
        return values.get(int(kind))

    def copyDecomposedLayer(self):
        """A detached copy (paths with components decomposed, anchors,
        width); edits to it never reach the font."""
        result = self.copy()
        result.decomposeComponents()
        return result

    def nextKerningForLayer_direction_(self, layer, direction=GSLTR):
        """Kerning between this layer and the following one: the glyph pair
        first, then glyph/group, group/glyph and group/group (Glyphs' order);
        NSNotFound when the pair is not kerned."""
        _ltr_only(direction)
        left, right = self.parent, layer.parent
        lefts = [left.name] + (
            [LEFT_GROUP + left.rightKerningGroup] if left.rightKerningGroup else []
        )
        rights = [right.name] + (
            [RIGHT_GROUP + right.leftKerningGroup] if right.leftKerningGroup else []
        )
        for a in lefts:
            for b in rights:
                value = self._font._kerning_for_pair(self.layerId, a, b)
                if value != NO_KERNING_VALUE:
                    return value
        return NO_KERNING_VALUE

    def rightKerningForLayer_(self, layer):
        """Glyphs 2 name of ``nextKerningForLayer_direction_`` (LTR)."""
        return self.nextKerningForLayer_direction_(layer, GSLTR)

    @property
    def bezierPath(self):
        """The layer's paths as an NSBezierPath (drawing.cocoa_drawing), or
        None without paths. Closed paths start at their last node, as Glyphs
        lists the start node last."""
        paths = list(self.paths)
        if not paths:
            return None
        from ..drawing.cocoa_drawing import NSBezierPath

        result = NSBezierPath.bezierPath()
        for path in paths:
            _append_path_segments(result, path)
        return result

    @property
    def completeBezierPath(self):
        """Paths plus decomposed components (each through its transform)."""
        return self._complete_path(frozenset())

    def _complete_path(self, seen):
        from ..drawing.cocoa_drawing import NSAffineTransform, NSBezierPath

        glyph_name = self.parent.name
        if glyph_name in seen:
            raise ValueError(f"Component cycle through glyph {glyph_name!r}")
        result = self.bezierPath or NSBezierPath.bezierPath()
        master_id = self.layerId
        for component in self.components:
            base = self._font.glyphs[component.componentName]
            if base is None:
                continue
            path = base.layers[master_id]._complete_path(seen | {glyph_name})
            transform = NSAffineTransform.transform()
            transform._m = tuple(float(v) for v in component.transform)
            path.transformUsingAffineTransform_(transform)
            result.appendBezierPath_(path)
        return result

    @property
    def ascender(self) -> float:
        """The master's ascender (Glyphs layers have no own metrics here)."""
        return self.master._metrics().ascender

    @property
    def descender(self) -> float:
        return self.master._metrics().descender

    def glyphMetrics(self) -> tuple:
        """Glyphs' ``(width, ascender, capHeight, descender, xHeight,
        italicAngle, vertWidth)``; vertical width is not modelled (None)."""
        m = self.master._metrics()  # one native read
        return (
            self.width,
            m.ascender,
            m.capHeight,
            m.descender,
            m.xHeight,
            m.italicAngle,
            None,
        )

    def _bounds(self):
        self._check()
        return self._font._model._backend.layer_bounds(self._id)

    @property
    def bounds(self) -> Rect:
        """Outline bounds; an empty layer has a zero rect at the origin."""
        x, y, w, h = self._bounds() or (0.0, 0.0, 0.0, 0.0)
        return Rect(Point(x, y), Size(w, h))

    def _spacing_bounds(self):
        from .sidebearings import spacing_bounds

        return spacing_bounds(self)

    @property
    def LSB(self) -> float:
        bounds = self._spacing_bounds()
        return 0.0 if bounds is None else bounds[0]

    @LSB.setter
    def LSB(self, value):
        bounds = self._spacing_bounds()
        if bounds is None:
            float(value)
            return
        delta = float(value) - bounds[0]
        with self._font.undo_group("Glyport LSB"):
            self._font._model._backend.transform_layer(
                self._id, (1.0, 0.0, 0.0, 1.0, delta, 0.0)
            )
            self.width = self.width + delta

    @property
    def RSB(self) -> float:
        bounds = self._spacing_bounds()
        width = self.width
        return width if bounds is None else width - (bounds[0] + bounds[2])

    @RSB.setter
    def RSB(self, value):
        bounds = self._spacing_bounds()
        if bounds is None:
            self.width = float(value)
            return
        self.width = bounds[0] + bounds[2] + float(value)

    def applyTransform(self, transform):
        """Affine (a, b, c, d, tx, ty) applied to the layer's outlines natively."""
        values = tuple(float(v) for v in transform)
        if len(values) != 6:
            raise ValueError("applyTransform needs six values")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Affine transform values must be finite")
        self._check()
        self._font._model._backend.transform_layer(self._id, values)

    def hasAlignedWidth(self) -> bool:
        """Plain outlines have no width inherited by automatic alignment.

        FontLab component positioning does not expose Glyphs' alignment state.
        """
        if len(self.components):
            _unsupported("GSLayer.hasAlignedWidth")
        return False

    def _children(self, field, cls):
        def make(token):
            return self._font._proxy(cls, token, lambda: sequence.info(token))

        sequence = self._font._indexed(
            (self._id, field),
            lambda: getattr(self._data(), field),
            make,
            lambda info: (
                (info.name, info.id) if field in ("anchors", "guides") else (info.id,)
            ),
        )
        return sequence

    def _append_path(self, path):
        self._check()
        data = path._data() if isinstance(path, GSPath) else path
        if not isinstance(data, PathInfo):
            raise TypeError("Expected GSPath or PathInfo")
        id = self._font._model._backend.append_path(self._id, data)
        return self._children("paths", GSPath)._make(id)

    def _remove_path(self, path):
        self._check()
        self._font._model._backend.remove_path(self._id, path.id)

    @property
    def paths(self) -> ProxySequence:
        self._check()
        sequence = self._children("paths", GSPath)
        sequence._append, sequence._remove = self._append_path, self._remove_path
        return sequence

    @paths.setter
    def paths(self, values):
        from .bulk import replace_collection

        replace_collection(self, "paths", values)

    @property
    def color(self):
        """Glyphs label colour index from FontLab's layer mark (None = no mark)."""
        self._check()
        return _mark_to_label(self._font._model._backend.mark(self._id))

    @color.setter
    def color(self, value):
        self._check()
        self._font._model._backend.set_mark(self._id, _label_to_mark(value))

    @property
    def components(self) -> ProxySequence:
        self._check()
        sequence = self._children("components", GSComponent)
        sequence._append, sequence._remove = self._append_component, self._remove_shape
        return sequence

    @components.setter
    def components(self, values):
        from .bulk import replace_collection

        replace_collection(self, "components", values)

    @property
    def shapes(self) -> ProxySequence:
        def records():
            data = self._data()
            items = {v.id: v for v in (*data.paths, *data.components)}
            return tuple(items[key] for key in data.shape_ids)

        def make(token):
            info = sequence.info(token)
            cls = GSPath if isinstance(info, PathInfo) else GSComponent
            return self._font._proxy(cls, token, lambda: sequence.info(token))

        sequence = self._font._indexed(
            (self._id, "shapes"),
            records,
            make,
            append=self._append_shape,
            remove=self._remove_shape,
        )
        return sequence

    @shapes.setter
    def shapes(self, values):
        from .bulk import replace_collection

        replace_collection(self, "shapes", values)

    def _append_shape(self, shape):
        if isinstance(shape, GSComponent):
            return self._append_component(shape)
        return self._append_path(shape)

    def decomposeComponent_(self, component: "GSComponent") -> None:
        """Replace exactly one owned component with its transformed base shapes."""
        from .component_edits import decompose_proxy

        decompose_proxy(self, component)

    def _append_component(self, component):
        self._check()
        if "_draft" not in component.__dict__:
            raise TypeError("Expected a new GSComponent")
        id = self._font._model._backend.append_component(self._id, component._draft)
        return self._children("components", GSComponent)._make(id)

    def _remove_shape(self, shape):
        if isinstance(shape, GSComponent):
            self._check()
            self._font._model._backend.remove_component(self._id, shape.id)
        else:
            self._remove_path(shape)

    def _add_anchor(self, anchor):
        self._check()
        data = anchor._data() if isinstance(anchor, GSAnchor) else anchor
        if not isinstance(data, AnchorInfo):
            raise TypeError("Expected GSAnchor or AnchorInfo")
        id = self._font._model._backend.add_anchor(self._id, data)
        return self._children("anchors", GSAnchor)._make(id)

    @property
    def anchors(self) -> ProxySequence:
        self._check()
        from .anchor_assignment import assign_anchor

        sequence = self._children("anchors", GSAnchor)
        sequence._set_item = partial(assign_anchor, self)
        sequence._append, sequence._remove = self._add_anchor, self._remove_anchor
        return sequence

    @anchors.setter
    def anchors(self, values):
        from .bulk import replace_collection

        replace_collection(self, "anchors", values)

    def _remove_anchor(self, anchor):
        self._check()
        self._font._model._backend.remove_anchor(self._id, anchor.id)

    def _add_guide(self, guide):
        self._check()
        if not isinstance(guide, GSGuide):
            raise TypeError("Expected GSGuide")
        id = self._font._model._backend.append_guide(self._id, guide._data())
        return self._children("guides", GSGuide)._make(id)

    @property
    def guides(self) -> ProxySequence:
        self._check()
        sequence = self._children("guides", GSGuide)
        sequence._append, sequence._remove = self._add_guide, self._remove_guide
        return sequence

    @guides.setter
    def guides(self, values):
        from .bulk import replace_collection

        replace_collection(self, "guides", values)

    def _remove_guide(self, guide):
        self._check()
        self._font._model._backend.remove_guide(self._id, guide.id)

    @property
    def selectionBounds(self):
        positions = [item.position for item in self.selection]
        if not positions:
            return Rect(Point(0, 0), Size(0, 0))
        xs, ys = zip(*positions, strict=True)
        return Rect(Point(min(xs), min(ys)), Size(max(xs) - min(xs), max(ys) - min(ys)))

    def _selection_members(self):
        self._check()
        return ([n for p in self.paths for n in p.nodes]
                + list(self.anchors) + list(self.components) + list(self.guides))

    def _check_selection_kind(self, element):
        if "_draft" in self.__dict__:
            return
        backend = self._font._model._backend
        for cls, kind in ((GSAnchor, "anchor"), (GSComponent, "component"), (GSGuide, "guide")):
            if isinstance(element, cls) and not getattr(backend, "supports_" + kind + "_selection", False):
                _unsupported("GSLayer.selection." + kind + "Selection")

    @property
    def selection(self) -> ProxySequence:
        """Nodes, anchors, components and guides in collection order."""
        def selected():
            result = []
            for item in self._selection_members():
                try:
                    self._check_selection_kind(item)
                except UnsupportedCapability:
                    continue  # Reads expose the subset the host can observe.
                if item.selected:
                    result.append(item)
            return result
        return ProxySequence(selected)

    @selection.setter
    def selection(self, values):
        members, values = self._selection_members(), list(values)
        for item in values:
            if not isinstance(item, (GSNode, GSAnchor, GSComponent, GSGuide)):
                _unsupported("GSLayer.selection.elementKind")
            if "_draft" not in item.__dict__:
                item._check()
            if not any(item is member for member in members):
                raise ValueError("Selected element does not belong to this layer")
        for item in values:
            self._check_selection_kind(item)
        for item in list(self.selection):
            if not any(item is value for value in values):
                item.selected = False
        for item in values:
            item.selected = True

    def addSelection_(self, element):
        """Add one owned selectable object without replacing other selection."""
        if not isinstance(element, (GSNode, GSAnchor, GSComponent, GSGuide)):
            _unsupported("GSLayer.addSelection_.elementKind")
        if "_draft" not in element.__dict__:
            element._check()
        if not any(element is member for member in self._selection_members()):
            raise ValueError("Selected element does not belong to this layer")
        self._check_selection_kind(element)
        if not element.selected:
            element.selected = True

    def clearSelection(self):
        """Clear observable selection; unsupported kinds cannot be changed."""
        self.selection = []

    @property
    def hints(self) -> ProxySequence:
        """PostScript hints, written through FontLab's edit_layer_hints tool."""
        self._check()
        backend = self._font._model._backend
        font, key = self._font, ("hints", self._id)

        def values():
            return [
                font._wrapper(GSHint, t, lambda t: GSHint._bind_layer(self, t))
                for t in font._slots(key)
            ]

        def append(hint):
            font._check_new(hint, GSHint, "GSLayer.hints")
            info = hint._resolve()
            font._slots(key)
            self._check()
            backend.add_hint(self._id, info)
            hint._layer = self
            font._slot_append(key, hint)

        def remove(hint):
            index = font._slot(key, hint._token)
            self._check()
            backend.remove_hint(self._id, index)
            font._slot_pop(key, index)

        return ProxySequence(values, append=append, remove=remove)

    @hints.setter
    def hints(self, values):
        values = list(values or ())
        if not all(isinstance(value, GSHint) for value in values):
            raise TypeError("Expected GSHint values")
        copies = [value.copy() for value in values]
        previous = [value.copy() for value in self.hints]
        with self._font.undo_group("Glyport hints"):
            try:
                for value in list(self.hints):
                    self.hints.remove(value)
                for value in copies:
                    self.hints.append(value)
            except BaseException:
                for value in list(self.hints):
                    self.hints.remove(value)
                for value in previous:
                    self.hints.append(value)
                raise


class GSPath(_Draft):
    def reverse(self):
        """Reverse winding and incoming segment types, retaining node metadata."""
        data = self._data()
        if not data.nodes:
            return
        oncurves = [i for i, node in enumerate(data.nodes) if node.type != "offcurve"]
        replacements = list(data.nodes)
        for position, index in enumerate(oncurves):
            following = oncurves[(position + 1) % len(oncurves)]
            kind = data.nodes[following].type
            if not data.closed and position == len(oncurves) - 1:
                kind = "line"
            replacements[index] = replace(data.nodes[index], type=kind)
        nodes = tuple(reversed(replacements))
        if data.closed:
            nodes = nodes[1:] + nodes[:1]
        if "_draft" in self.__dict__:
            original = list(reversed(self._draft_nodes))
            if data.closed:
                original = original[1:] + original[:1]
            self._draft_nodes = original
            for node, info in zip(original, nodes, strict=True):
                node._draft = info
        else:
            with self._font.undo_group("Reverse path"):
                self._font._model._backend.set_path_nodes(self._id, nodes, data.closed)

    def area(self):
        """Return unsigned analytic area, closing open paths only for integration.

        Uses current live or detached geometry without mutation. Glyphs flattens
        curves for this calculation, so its curved-path approximation may differ.
        """
        from .segments import path_area

        return path_area(self)

    def addNode_(self, node):
        """Objective-C spelling of nodes.append; returns void."""
        self.nodes.append(node)

    @property
    def direction(self):
        from .segments import path_direction

        return path_direction(self)

    def setSmooth_withCenterNode_oppositeNode_(self, node, center, opposite):
        """Align one handle opposite its neighbour, retaining its length."""
        from math import hypot

        if not all(
            any(value is n for n in self.nodes) for value in (node, center, opposite)
        ):
            raise ValueError("All three nodes must belong to this path")
        dx, dy = center.x - opposite.x, center.y - opposite.y
        distance = hypot(dx, dy)
        if not distance:
            raise ValueError("The opposite node must differ from the center")
        length = hypot(node.x - center.x, node.y - center.y)
        node.position = (
            center.x + dx * length / distance,
            center.y + dy * length / distance,
        )

    @property
    def bezierPath(self):
        from ..drawing.cocoa_drawing import NSBezierPath

        result = NSBezierPath.bezierPath()
        for segment in self.segments:
            if result.isEmpty():
                result.moveToPoint_(segment[0])
            if len(segment) == 2:
                result.lineToPoint_(segment[-1])
            else:
                result.curveToPoint_controlPoint1_controlPoint2_(
                    segment[-1], *segment[1:3]
                )
        if self.closed and not result.isEmpty():
            result.closePath()
        return result

    @property
    def bounds(self):
        from .copies import DetachedLayer

        layer = DetachedLayer()
        layer.shapes = [self.copy()]
        return layer.bounds

    @property
    def attributes(self):
        if "_draft" in self.__dict__:
            return UserData(
                lambda: dict(self._draft.attributes),
                lambda data: setattr(
                    self, "_draft", replace(self._draft, attributes=dict(data))
                ),
            )
        backend = self._font._model._backend
        return UserData(
            lambda: backend.path_attributes(self._id),
            lambda data: backend.set_path_attributes(self._id, data),
        )

    def __init__(self, nodes=(), closed=True):
        self._draft_nodes = [
            n if isinstance(n, GSNode) else GSNode((n.x, n.y), n.type, n.smooth)
            for n in nodes
        ]
        self._draft = PathInfo("", (), closed)
        for node in self._draft_nodes:
            node._path = self

    def _data(self):
        if "_draft" in self.__dict__:
            return replace(
                self._draft, nodes=tuple(n._data() for n in self._draft_nodes)
            )
        return super()._data()

    @property
    def closed(self) -> bool:
        return self._data().closed

    @closed.setter
    def closed(self, value):
        if "_draft" not in self.__dict__:
            _unsupported("GSPath.closed write")
        self._draft = replace(self._draft, closed=bool(value))

    @property
    def nodes(self) -> ProxySequence:
        self._data()
        if "_draft" in self.__dict__:
            for node in self._draft_nodes:
                node._path = self
            return ProxySequence(
                lambda: list(self._draft_nodes),
                append=self._append_node,
                insert=self._insert_node,
                remove=self._remove_node,
            )

        def make(token):
            node = self._font._proxy(GSNode, token, lambda: sequence.info(token))
            node._path = self
            return node

        sequence = self._font._indexed(
            (self._id, "nodes"),
            lambda: self._data().nodes,
            make,
            append=self._append_node,
            insert=self._insert_node,
        )
        return sequence

    def _remove_node(self, node):
        self._draft_nodes.remove(node)
        node._path = None

    def _append_node(self, node: "GSNode") -> None:
        self._insert_node(len(self.nodes), node)

    def _insert_node(self, index: int, node: "GSNode") -> None:
        """Attach an unparented draft; relocation requires an explicit copy().

        Glyphs 3 wrapper indices are strict, including negative indices. Native
        insertion preserves old nodes; whole-path assignment must not be used.
        """
        from .node_insert import insertion_index, insertion_node

        index = insertion_index(index, len(self.nodes))
        if not isinstance(node, GSNode):
            raise TypeError("Expected GSNode")
        data = insertion_node(node._data())  # stale handles fail before relocation
        if "_draft" not in node.__dict__ or node.parent is not None:
            _unsupported("GSPath.nodes.insert relocation; use node.copy()")
        if "_draft" in self.__dict__:
            node._draft = data
            self._draft_nodes.insert(index, node)
            node._path = self
            return

        def attached(token: str) -> None:
            del node._draft
            _Proxy.__init__(node, self._font, token, lambda: self.nodes.info(token))
            node._path = self
            self._font._cache[GSNode, token] = node

        self._font._model._backend.insert_path_node(
            self._id, index, data, on_attach=attached
        )

    @property
    def selected(self):
        return all(n.selected for n in self.nodes)

    @selected.setter
    def selected(self, value):
        for node in self.nodes:
            node.selected = bool(value)

    def applyTransform(self, transform):
        transform = tuple(map(float, transform))
        if len(transform) != 6:
            raise ValueError("Expected six affine transform values")
        if not all(math.isfinite(value) for value in transform):
            raise ValueError("Affine transform values must be finite")
        moves = _mapped_positions(list(self.nodes), transform)
        scope = (
            nullcontext()
            if "_draft" in self.__dict__
            else self._font.undo_group("Transform path")
        )
        with scope:
            for node, position in moves:
                node.position = position

    @property
    def segments(self):
        from .segments import path_segments

        return path_segments(self)

    @segments.setter
    def segments(self, values):
        from .segments import set_path_segments

        set_path_segments(self, values)


class GSNode(_Draft):
    @property
    def name(self):
        if "_draft" in self.__dict__:
            return self._draft.name
        return self._font._model._backend.node_name(self._id)

    @name.setter
    def name(self, value):
        value = str(value)
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, name=value)
        else:
            self._check()
            self._font._model._backend.set_node_name(self._id, value)

    @property
    def parent(self):
        if "_draft" not in self.__dict__:
            self._check()
        return self.__dict__.get("_path")

    @property
    def index(self):
        if self.parent is None:
            return None
        nodes = self.parent.nodes
        return (
            nodes.ordinal(self.id)
            if "_draft" not in self.__dict__
            else list(nodes).index(self)
        )

    def _neighbor(self, offset):
        if self.parent is None:
            return None
        nodes = self.parent.nodes
        return nodes[(self.index + offset) % len(nodes)]

    nextNode = property(lambda self: self._neighbor(1))
    prevNode = property(lambda self: self._neighbor(-1))

    def __init__(self, position=(0, 0), type="line", smooth=False):
        self._draft = NodeInfo("", *position, type, smooth is True)

    @property
    def position(self) -> Point:
        data = self._data()
        return Point(data.x, data.y)

    @position.setter
    def position(self, value):
        x, y = map(float, value)
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, x=x, y=y)
        else:
            self._check()
            self._font._model._backend.set_node_position(self._id, x, y)

    @property
    def x(self) -> float:
        return self.position[0]

    @x.setter
    def x(self, value):
        self.position = (value, self.y)

    @property
    def y(self) -> float:
        return self.position[1]

    @y.setter
    def y(self, value):
        self.position = (self.x, value)

    @property
    def type(self) -> str:
        return self._data().type

    def makeNodeFirst(self) -> None:
        """Make this node the path's start node (Glyphs lists it last)."""
        if "_draft" in self.__dict__:
            _unsupported("GSNode.makeNodeFirst on a node not yet in a path")
        self._check()
        self._font._model._backend.make_node_first(self._id)

    @type.setter
    def type(self, value):
        if value not in ("line", "curve", "qcurve", "offcurve"):
            raise ValueError(f"Invalid node type: {value}")
        data = replace(self._data(), type=value)
        if "_draft" in self.__dict__:
            self._draft = data
        else:
            with self._font.undo_group("Set node type"):
                self._font._model._backend.set_node_type(self._id, value)

    @property
    def smooth(self) -> bool:
        return self._data().smooth

    @smooth.setter
    def smooth(self, value):
        # The Glyphs wrapper accepts literal True here; connection accepts ints.
        smooth = value is True
        if "_draft" in self.__dict__:
            self._draft = replace(
                self._draft, smooth=smooth, connection=GSSMOOTH if smooth else GSSHARP
            )
        else:
            self._check()
            self._font._model._backend.set_node_smooth(self._id, smooth)

    @property
    def connection(self) -> int:
        data = self._data()
        return (
            data.connection
            if data.connection is not None
            else (GSSMOOTH if data.smooth else GSSHARP)
        )

    @connection.setter
    def connection(self, value):
        if not isinstance(value, int):
            raise TypeError("Node connection must be an integer")
        if "_draft" in self.__dict__:
            self._draft = replace(
                self._draft, connection=value, smooth=value == GSSMOOTH
            )
        else:
            self._check()
            self._font._model._backend.set_node_connection(self._id, value)

    @property
    def selected(self) -> bool:
        if "_draft" in self.__dict__:
            return self._draft.selected
        self._check()
        return self._font._model._backend.node_selected(self._id)

    @selected.setter
    def selected(self, value):
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, selected=bool(value))
        else:
            self._check()
            self._font._model._backend.set_node_selected(self._id, bool(value))


class GSComponent(_Draft):
    """A component; ``GSComponent(glyph or name, offset)`` is new until it is
    appended to a layer's shapes."""

    @property
    def selected(self):
        if "_draft" in self.__dict__:
            return self._draft.selected
        self._check()
        return self._font._model._backend.component_selected(self._id)

    @selected.setter
    def selected(self, value):
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, selected=bool(value))
        else:
            self._check()
            self._font._model._backend.set_component_selected(self._id, bool(value))

    @property
    def alignment(self):
        raise UnsupportedCapability(
            "FontLab has no Glyphs automatic alignment mode for components",
            capability="GSComponent.alignment",
            location=caller_location(),
        )

    @alignment.setter
    def alignment(self, value):
        _ = self.alignment

    def __init__(self, glyph=None, offset=(0, 0), scale=(1, 1), transform=None):
        name = glyph.name if isinstance(glyph, GSGlyph) else str(glyph or "")
        self._draft = ComponentInfo("", name, (1, 0, 0, 1, 0, 0))
        sx, sy = scale
        x, y = offset
        self.transform = transform if transform is not None else (sx, 0, 0, sy, x, y)

    @property
    def component(self):
        if "_draft" in self.__dict__:
            return None
        return self._font.glyphs[self.componentName]

    @property
    def componentName(self) -> str:
        return self._data().componentName

    @componentName.setter
    def componentName(self, value: str) -> None:
        value = _text(value, "componentName")
        if not value:
            raise ValueError("A component name must not be empty")
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, componentName=value)
        else:
            self._check()
            self._font._model._backend.set_component_name(self._id, value)

    name = property(
        lambda self: self.componentName,
        lambda self, value: setattr(self, "componentName", value),
    )

    def decompose(self) -> None:
        """Decompose one level, retaining this object as a detached snapshot."""
        parent = self.parent
        if parent is None:
            raise ValueError("A detached component has no containing layer")
        parent.decomposeComponent_(self)

    @property
    def transform(self):
        return self._data().transform

    @transform.setter
    def transform(self, value):
        value = tuple(map(float, value))
        if len(value) != 6 or not all(map(math.isfinite, value)):
            raise ValueError("Expected six finite affine transform values")
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, transform=value)
        else:
            self._check()
            with self._font.undo_group("Set component transform"):
                self._font._model._backend.set_component_transform(self._id, value)

    @property
    def scale(self):
        a, b, c, d, _, _ = self.transform
        sx = math.hypot(a, b)
        sy = math.hypot(c, d)
        if a * d - b * c < 0:
            # Prefer the reflected representation with rotation nearest zero.
            return Point(-sx, sy) if a < 0 else Point(sx, -sy)
        return Point(sx, sy)

    @scale.setter
    def scale(self, value):
        sx, sy = map(float, value)
        a, b, c, d, x, y = self.transform
        oldx, oldy = self.scale
        angle = math.radians(self.rotation)
        self.transform = (
            a / oldx * sx if oldx else math.cos(angle) * sx,
            b / oldx * sx if oldx else math.sin(angle) * sx,
            c / oldy * sy if oldy else -math.sin(angle) * sy,
            d / oldy * sy if oldy else math.cos(angle) * sy, x, y,
        )

    @property
    def rotation(self):
        a, b, c, d, _, _ = self.transform
        if self.scale.x < 0:
            a, b = -a, -b
        return math.degrees(math.atan2(b, a) if a or b else math.atan2(-c, d))

    @rotation.setter
    def rotation(self, value):
        angle = math.radians(float(value) - self.rotation)
        cosine, sine = math.cos(angle), math.sin(angle)
        a, b, c, d, x, y = self.transform
        self.transform = (a*cosine-b*sine, a*sine+b*cosine,
                          c*cosine-d*sine, c*sine+d*cosine, x, y)

    @property
    def position(self) -> Point:
        return Point(*self.transform[4:])

    @position.setter
    def position(self, value):
        x, y = map(float, value)
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, transform=(*self.transform[:4], x, y))
        else:
            self._check()
            self._font._model._backend.set_component_position(self._id, x, y)

    @property
    def bounds(self) -> Rect:
        if "_draft" in self.__dict__:
            _unsupported("GSComponent.bounds.detached")
        self._check()
        bounds = self._font._model._backend.component_bounds(self._id)
        x, y, width, height = bounds or (0.0, 0.0, 0.0, 0.0)
        return Rect(Point(x, y), Size(width, height))


class GSGuide(_Draft):
    """Glyphs guide with writable position and angle."""

    @property
    def selected(self):
        if "_draft" in self.__dict__:
            return self._draft.selected
        self._check()
        return self._font._model._backend.guide_selected(self._id)

    @selected.setter
    def selected(self, value):
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, selected=bool(value))
        else:
            self._check()
            self._font._model._backend.set_guide_selected(self._id, bool(value))

    def __init__(self, position=(0, 0), angle=0.0, name=""):
        self._draft = GuideInfo("", *position, angle, name)

    @property
    def position(self) -> Point:
        data = self._data()
        return Point(data.x, data.y)

    @position.setter
    def position(self, value):
        x, y = map(float, value)
        self._set_values(x=x, y=y)

    def _set_values(self, **changes):
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, **changes)
        else:
            self._check()
            self._font._model._backend.set_guide(self._id, **changes)

    @property
    def angle(self) -> float:
        return self._data().angle

    @angle.setter
    def angle(self, value):
        self._set_values(angle=float(value))

    @property
    def name(self) -> str:
        return self._data().name

    @name.setter
    def name(self, value):
        self._set_values(name=str(value))


class GSAnchor(_Draft):
    @property
    def selected(self):
        if "_draft" in self.__dict__:
            return self._draft.selected
        self._check()
        return self._font._model._backend.anchor_selected(self._id)

    @selected.setter
    def selected(self, value):
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, selected=bool(value))
        else:
            self._check()
            self._font._model._backend.set_anchor_selected(self._id, bool(value))

    def __init__(self, name="", position=(0, 0)):
        self._draft = AnchorInfo("", name, *position)

    @property
    def name(self) -> str:
        return self._data().name

    @name.setter
    def name(self, value):
        value = _text(value, "anchor name")
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, name=value)
        else:
            self._check()
            with self._font.undo_group("Set anchor name"):
                self._font._model._backend.set_anchor_name(self._id, value)

    @property
    def position(self) -> Point:
        data = self._data()
        return Point(data.x, data.y)

    @position.setter
    def position(self, value):
        x, y = map(float, value)
        if "_draft" in self.__dict__:
            self._draft = replace(self._draft, x=x, y=y)
        else:
            self._check()
            self._font._model._backend.set_anchor_position(self._id, x, y)

    @property
    def x(self) -> float:
        return self.position[0]

    @x.setter
    def x(self, value):
        self.position = (value, self.y)

    @property
    def y(self) -> float:
        return self.position[1]

    @y.setter
    def y(self, value):
        self.position = (self.x, value)
