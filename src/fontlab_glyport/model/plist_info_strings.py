# this_file: src/fontlab_glyport/model/plist_info_strings.py
"""Bounded normal-file quoted strings and whitespace for custom GlyphData.

Qualified from retained QP/QT/WS source: this is neither XML entity decoding nor
standard Unicode-escape decoding. Alternate escaped-input mode, unsafe native
lookahead and Foundation conversion edge cases remain unqualified.
"""

from ..errors import UnsupportedCapability
from .custom_info_errors import GlyphDataParseError

_ASCII_SPACE = b"\t\n\v\f\r "
_LINE_SEPARATORS = (b"\xe2\x80\xa8", b"\xe2\x80\xa9")
_CONTROLS = dict(zip(b"abfnrtv", (7, 8, 12, 10, 13, 9, 11)))
_OCTAL = {byte: byte - 48 for byte in b"01234567"}
_HEX = {byte: value for value, byte in enumerate(b"0123456789abcdef")}
_HEX.update({byte: value + 10 for value, byte in enumerate(b"ABCDEF")})


def _check_offset(data: bytes, offset: int) -> None:
    """Reject invalid cursors instead of accepting Python negative indexing."""
    if not 0 <= offset <= len(data):
        raise GlyphDataParseError("offset outside quoted-text buffer", offset)


def _read_number(
    data: bytes, offset: int, digits: dict[int, int], radix: int, limit: int
) -> tuple[int, int]:
    """Consume bounded digits, preserving the retained eight-bit accumulator."""
    value = 0
    for _ in range(limit):
        if offset == len(data) or data[offset] not in digits:
            break
        value = (value * radix + digits[data[offset]]) & 0xFF
        offset += 1
    return value, offset


def _read_escape(data: bytes, offset: int) -> tuple[bytes, int]:
    """Decode one escape following a slash, including source-specific U values."""
    if offset == len(data):
        raise GlyphDataParseError("unterminated quoted escape", offset)
    byte = data[offset]
    if byte in _OCTAL:
        value, offset = _read_number(data, offset, _OCTAL, 8, 3)
    elif byte == ord("U"):
        value, offset = _read_number(data, offset + 1, _HEX, 16, 4)
    else:
        value, offset = _CONTROLS.get(byte, byte), offset + 1
    return chr(value).encode("utf-8"), offset


def _decode_text(data: bytearray, escaped: bool) -> str:
    """Refuse unqualified CF conversion edges rather than repairing the input."""
    if data.startswith(b"\xef\xbb\xbf"):
        edge = "externalRepresentation" if escaped else "byteOrderMark"
        raise UnsupportedCapability(
            "Leading UTF8 BOM conversion is not qualified",
            capability=f"GSGlyphsInfo.customData.UTF8.{edge}",
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UnsupportedCapability(
            "Foundation conversion of invalid custom GlyphData UTF8 is unqualified",
            capability="GSGlyphsInfo.customData.UTF8",
        ) from error


def read_quoted(data: bytes, offset: int) -> tuple[str, int]:
    """Read at an opening quote and return its text and cursor after the close."""
    _check_offset(data, offset)
    if offset == len(data) or data[offset] not in b"\"'":
        raise GlyphDataParseError("expected a quoted value", offset)
    quote = data[offset]
    offset += 1
    decoded = bytearray()
    escaped = False
    while offset < len(data):
        byte = data[offset]
        offset += 1
        if byte == quote:
            return _decode_text(decoded, escaped), offset
        if byte == ord("\\"):
            segment, offset = _read_escape(data, offset)
            decoded.extend(segment)
            escaped = True
        else:
            decoded.append(byte)
    raise GlyphDataParseError("unterminated quoted value", offset)


def _skip_line(data: bytes, offset: int) -> int:
    """Stop at the source line separators, leaving them for whitespace skipping."""
    while offset < len(data):
        if data[offset] in b"\r\n" or data.startswith(_LINE_SEPARATORS, offset):
            break
        offset += 1
    return offset


def skip_space(data: bytes, offset: int) -> int:
    """Skip normal-file separators and C comments; unfinished comments reach EOF."""
    _check_offset(data, offset)
    while offset < len(data):
        if data[offset] in _ASCII_SPACE:
            offset += 1
        elif data.startswith(_LINE_SEPARATORS, offset):
            offset += 3
        elif data.startswith(b"/*", offset):
            close = data.find(b"*/", offset + 2)
            offset = len(data) if close == -1 else close + 2
        elif data.startswith(b"//", offset):
            offset = _skip_line(data, offset + 2)
        else:
            break
    return offset
