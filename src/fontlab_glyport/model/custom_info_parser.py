# this_file: src/fontlab_glyport/model/custom_info_parser.py
"""Retained normal-file glyph-token scan, with streamed custom mutations.

Only bounded byte/UTF8 semantics are qualified. No XML tree, whole-file rollback,
private resource data or arbitrary Foundation string conversion is substituted.
"""

from collections.abc import Iterator

from ..errors import UnsupportedCapability
from .custom_info import merge_custom
from .custom_info_errors import GlyphDataLoadError, GlyphDataParseError
from .info_records import GlyphInfoIndex
from .plist_info_strings import read_quoted, skip_space

_ASCII_SPACE = b"\t\n\v\f\r "
_KEY_END = _ASCII_SPACE + b"/=>"


def _read_key(data: bytes, offset: int) -> tuple[str, int]:
    start = offset
    while offset < len(data) and data[offset] not in _KEY_END:
        offset += 1
    if offset == start or offset == len(data):
        raise GlyphDataParseError("Expected an attribute key and equals sign", offset)
    try:
        return data[start:offset].decode("utf-8"), offset
    except UnicodeDecodeError as error:
        raise UnsupportedCapability(
            "Invalid custom GlyphData key UTF8 conversion is unqualified",
            capability="GSGlyphsInfo.customData.UTF8",
        ) from error


def _read_entry(data: bytes, offset: int) -> tuple[dict[str, str], int]:
    attributes = {}
    while True:
        offset = skip_space(data, offset)
        if offset == len(data):
            raise GlyphDataParseError("Unterminated glyph entry", offset)
        if data[offset] == ord(">"):
            return attributes, offset + 1
        if data[offset] == ord("/"):
            offset += 1
            if offset < len(data) and data[offset] == ord(">"):
                offset += 1
            return attributes, offset
        key, offset = _read_key(data, offset)
        offset = skip_space(data, offset)
        if offset == len(data) or data[offset] != ord("="):
            raise GlyphDataParseError("Expected equals after attribute key", offset)
        offset = skip_space(data, offset + 1)
        attributes[key], offset = read_quoted(data, offset)


def scan_entries(data: bytes) -> Iterator[dict[str, str]]:
    """Yield only completed glyph dictionaries, ignoring arbitrary outer text."""
    offset = 0
    while offset + 7 < len(data):
        if data.startswith(b"<!--", offset):
            end = data.find(b"-->", offset + 4)
            if end == -1:
                return
            offset = end + 3
        elif data.startswith(b"<glyph", offset) and data[offset + 6] in _ASCII_SPACE:
            attributes, offset = _read_entry(data, offset + 6)
            yield attributes
        else:
            offset += 1


def parse_into(index: GlyphInfoIndex, data: bytes) -> None:
    """Merge rows in order; syntax and post-scan duplicates preserve prior writes."""
    seen, duplicates = set(), set()
    prepared = False
    for attributes in scan_entries(data):
        if not prepared:
            index.prepare_custom_merge()
            prepared = True
        merge_custom(index, attributes, seen=seen, duplicates=duplicates)
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise GlyphDataLoadError(f"Duplicate custom production names: {names}", code=1)
