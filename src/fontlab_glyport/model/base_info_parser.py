# this_file: src/fontlab_glyport/model/base_info_parser.py
"""Independent retained base-file scanner and owned parser containers.

Qualified normal byte/UTF8 inputs use the row helper's prefix dispatch, rather
than custom-file merge or XML semantics. Unsafe native lookahead, arbitrary
Foundation conversion, mmap/fstat failures and NSError ABI remain unqualified.
"""

import logging
from pathlib import Path
from types import SimpleNamespace

from ..errors import UnsupportedCapability
from .base_info_commit import (
    BaseParseError as BaseParseError,  # noqa: PLC0414 - explicit public re-export
)
from .base_info_commit import (
    BaseParseResult as BaseParseResult,  # noqa: PLC0414 - explicit public re-export
)
from .base_info_commit import (
    commit_base as commit_base,  # noqa: PLC0414 - explicit public re-export
)
from .custom_info_errors import GlyphDataParseError
from .info_records import GlyphInfoIndex, add_unicode, new_record
from .metadata_tokens import case_from_string, direction_from_string
from .plist_info_strings import read_quoted, skip_space
from .production_metadata import _utf16_length

_LOG = logging.getLogger(__name__)
_STRINGS = {
    key: key
    for key in ["name", "category", "subCategory", "group", "script", "sortNameKeep", "sortName", "mirror"]
}
_STRINGS["description"] = "desc"
_ARRAYS = {
    "altNames": "altNames",
    "anchors": "anchors",
    "accents": "marks",
    "marks": "marks",
    "decompose": "_component_names",
}
# Longest prefixes preserve groupIdx/group, sortNameKeep/sortName and Unicode
# dispatch. Unknown prefixes with unqualified native progress remain unavailable.
_KEYS = tuple(
    sorted(
        [
            *_STRINGS,
            *_ARRAYS,
            "production",
            "legacy",
            "case",
            "direction",
            "unicodeLegacy",
            "unicodes",
            "unicode2",
            "unicode",
            "groupIdx",
            "deprecated",
        ],
        key=len,
        reverse=True,
    )
)


def _read_group_index(data: bytes, offset: int) -> tuple[int, int]:
    """Read the bounded readInt grammar and retain signed-short stored bits."""
    while offset < len(data) and data[offset] in b" \t":
        offset += 1
    if offset < len(data) and data[offset] == ord('"'):
        offset += 1
    if offset < len(data) and data[offset] == ord("+"):
        offset += 1
    negative = offset < len(data) and data[offset] == ord("-")
    offset += negative
    value = 0
    while offset < len(data) and ord("0") <= data[offset] <= ord("9"):
        value = (value * 10 + data[offset] - ord("0")) & 0xFFFF
        offset += 1
    if offset < len(data) and data[offset] == ord('"'):
        offset += 1
    value = (-value if negative else value) & 0xFFFF
    return (value if value < 0x8000 else value - 0x10000), offset


def _store_value(row: SimpleNamespace, key: str, value: str) -> None:
    """Preserve base-only fields, direct arrays, and parameter order."""
    if key in _STRINGS:
        setattr(row, _STRINGS[key], value)
    elif key in _ARRAYS:
        setattr(row, _ARRAYS[key], value.split(", "))
    elif key in {"production", "legacy"}:
        row._production_state.value = value
    elif key == "case":
        row.case = case_from_string(value)
    elif key == "direction":
        row.direction = direction_from_string(value)
    elif key == "unicodes":
        row.unicodes = tuple(value.split(", "))
        row.unicode = row.unicodes[0]
    elif key == "unicodeLegacy":
        if _utf16_length(value) > 2:
            row.unicodeLegacy = value
    else:
        codes = (
            value.split(", ")
            if key == "unicode" and _utf16_length(value) > 9
            else [value]
        )
        for code in codes:
            add_unicode(row, code)


def _read_row(data: bytes, offset: int) -> tuple[SimpleNamespace | None, int]:
    """Decode the qualified fixed attribute spellings without XML normalization."""
    row = new_record()
    while (offset := skip_space(data, offset)) < len(data):
        if data[offset] in b"/\0":
            row._locked = True
            return row, offset + (2 if data[offset] == ord("/") else 0)
        key = next(
            (
                key
                for key in _KEYS
                if data.startswith(
                    key.encode() + (b"=" if key == "unicode" else b""), offset
                )
            ),
            None,
        )
        if key is None:
            if data[offset] in b"acdglmnpsu":
                raise UnsupportedCapability(
                    "Unknown base GlyphData row prefix has unqualified native progress",
                    capability="GSGlyphsInfo.baseData.rowPrefix",
                )
            offset += 1
            continue
        offset += len(key) + 1
        if key == "groupIdx":
            row.groupIdx, offset = _read_group_index(data, offset)
        elif key == "deprecated":
            row.deprecated = True
            offset += 3
        else:
            try:
                value, offset = read_quoted(data, offset)
            except GlyphDataParseError as error:
                if error.offset < len(data) and (
                    row.name is not None or data[error.offset] not in b"/\0"
                ):
                    raise UnsupportedCapability(
                        "Malformed base GlyphData attribute recovery is unqualified",
                        capability="GSGlyphsInfo.baseData.rowRecovery",
                    ) from error
                raise
            _store_value(row, key, value)
    return None, offset


def _append_row(index: GlyphInfoIndex, row: SimpleNamespace) -> None:
    """Base aliases log overlap but use ordinary last-write index semantics."""
    index.records.append(row)
    index.names[row.name] = row
    production = row._production_state.value
    if production is not None and not production.startswith("uni"):
        index.names[production] = row
    for alias in row.altNames or ():
        if alias in index.names:
            _LOG.warning(
                "Overlapping altName %r in glyph data for glyph %r", alias, row.name
            )
        index.names[alias] = row
    for code in row.unicodes:
        index.unicodes[code] = row
    if row.unicodeLegacy is not None:
        index.unicodes[row.unicodeLegacy] = row


def parse_base_bytes(data: bytes) -> BaseParseResult:
    """Scan exact '<glyph ' bytes; failed private parses never commit a manager."""
    result = BaseParseResult(False, GlyphInfoIndex(), {})
    if len(data) <= 9:
        return result
    offset = 0
    try:
        while (offset := data.find(b"<glyph ", offset)) != -1:
            row, offset = _read_row(data, offset + 7)
            if row is None or row.name is None:
                return result
            _append_row(result.index, row)
    except GlyphDataParseError as error:
        result.error = BaseParseError(str(error), error.offset)
        return result
    result.success = True
    return result


def parse_base_file(path: str | Path) -> BaseParseResult:
    """Normal open failure is false/nil; later I/O failures remain explicit."""
    try:
        stream = Path(path).open("rb")  # noqa: SIM115 - only open failures return nil; read failures must propagate
    except OSError:
        return BaseParseResult(False, GlyphInfoIndex(), {})
    with stream:
        return parse_base_bytes(stream.read())
