# this_file: tests/test_plist_info_strings.py
"""Owned byte fixtures for the normal-file retained QP/QT/WS contract."""

from collections.abc import Callable

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.custom_info_errors import GlyphDataParseError
from fontlab_glyport.model.plist_info_strings import read_quoted, skip_space


@pytest.mark.parametrize("quote", [b'"', b"'"])
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", ""),
        (b"Owned", "Owned"),
        ("Zażółć\u2028\u2029".encode(), "Zażółć\u2028\u2029"),
        (b"&amp;&quot;&#65;&#x41;>/", "&amp;&quot;&#65;&#x41;>/"),
        (b"\x00", "\x00"),
        (rb"\a\b\f\n\r\t\v", "\a\b\f\n\r\t\v"),
        (rb"\q\x41\u0041", "qx41u0041"),
        (b"\\\n", "\n"),
        (rb"\0", "\x00"),
        (rb"\07", "\x07"),
        (rb"\101", "A"),
        (rb"\777", "ÿ"),
        (rb"\400", "\x00"),
        (rb"\1012", "A2"),
        (rb"\078", "\x078"),
        (rb"\8\9", "89"),
        (rb"\U0041", "A"),
        (rb"\U03A9", "©"),
        (rb"\U0100", "\x00"),
        (rb"\U1F600", "`0"),
        (rb"\U0A", "\n"),
        (rb"\U00ff", "ÿ"),
        (rb"\U", "\x00"),
        (rb"\UGGGG", "\x00GGGG"),
        (rb"\U1G23", "\x01G23"),
        (rb"\UFFFF", "ÿ"),
        (b"\\\xff", "ÿ"),
        ("前".encode() + rb"\U03A9" + "後".encode(), "前©後"),
    ],
)
def test_read_quoted_when_finite_source_case_then_exact_text_and_cursor(
    quote: bytes, content: bytes, expected: str
) -> None:
    data = b"prefix" + quote + content + quote + b"suffix"
    assert read_quoted(data, 6) == (expected, len(data) - 6)


@pytest.mark.parametrize("quote", [b'"', b"'"])
def test_read_quoted_when_quote_or_slash_escaped_then_decodes_once(
    quote: bytes,
) -> None:
    opposite = b"'" if quote == b'"' else b'"'
    content = opposite + b"\\" + quote + b"\\\\"
    assert read_quoted(quote + content + quote, 0) == (
        (opposite + quote + b"\\").decode(),
        len(content) + 2,
    )


@pytest.mark.parametrize("data", [b"", b"x", b'"', b'"abc', b'"abc\\', b'"\\U'])
def test_read_quoted_when_bad_open_or_truncated_then_parse_error(data: bytes) -> None:
    with pytest.raises(GlyphDataParseError) as caught:
        read_quoted(data, 0)
    assert 0 <= caught.value.offset <= len(data)


@pytest.mark.parametrize("offset", [-1, 4])
@pytest.mark.parametrize("reader", [read_quoted, skip_space])
def test_readers_when_offset_outside_buffer_then_parse_error(
    reader: Callable[[bytes, int], int | tuple[str, int]], offset: int
) -> None:
    with pytest.raises(GlyphDataParseError, match="offset"):
        reader(b'"a"', offset)


@pytest.mark.parametrize(
    "content", [b"\xff", b"\xc0\xaf", b"\xe2\x80", b"\xed\xa0\x80"]
)
@pytest.mark.parametrize("escaped", [b"", rb"\n"])
def test_read_quoted_when_raw_utf8_unqualified_then_refuses(
    content: bytes, escaped: bytes
) -> None:
    with pytest.raises(UnsupportedCapability) as caught:
        read_quoted(b'"' + escaped + content + b'"', 0)
    assert caught.value.capability == "GSGlyphsInfo.customData.UTF8"


@pytest.mark.parametrize(
    ("suffix", "edge"), [(b"", "byteOrderMark"), (rb"\n", "externalRepresentation")]
)
def test_read_quoted_when_leading_bom_unqualified_then_narrow_refusal(
    suffix: bytes, edge: str
) -> None:
    with pytest.raises(UnsupportedCapability) as caught:
        read_quoted(b'"\xef\xbb\xbf' + suffix + b'"', 0)
    assert caught.value.capability == f"GSGlyphsInfo.customData.UTF8.{edge}"


@pytest.mark.parametrize(
    "space",
    [b"", b"\t", b"\n", b"\v", b"\f", b"\r", b" ", b"\xe2\x80\xa8", b"\xe2\x80\xa9"],
)
def test_skip_space_when_qualified_separator_then_returns_next_byte(
    space: bytes,
) -> None:
    assert skip_space(b"p" + space + b"key", 1) == len(space) + 1
    assert skip_space(space, 0) == len(space)


@pytest.mark.parametrize(
    "prefix",
    [
        b"/**/",
        b"/*glyph name='Owned'*/",
        b"/* outer /* inner */",
        b"// until newline\n",
        b"// until carriage return\r",
        b"// tab\tand formfeed\fremain\n",
        b"// before separator\xe2\x80\xa8",
        b"// before separator\xe2\x80\xa9",
        b"\t/*one*/ //two\r\n\xe2\x80\xa8/*three*/ ",
    ],
)
def test_skip_space_when_comment_sequence_then_returns_next_token(
    prefix: bytes,
) -> None:
    assert skip_space(prefix + b"name", 0) == len(prefix)


@pytest.mark.parametrize(
    "data", [b"/*", b"/*x", b"/*x*", b"/*unterminated", b"//", b"//x"]
)
def test_skip_space_when_comment_unterminated_then_reaches_end(data: bytes) -> None:
    assert skip_space(data, 0) == len(data)


@pytest.mark.parametrize(
    "data",
    [
        rb"\n",
        rb"\t",
        b"/",
        b"/x",
        b"<!--x-->",
        b"\xc2\xa0",
        b"\xe2\x80",
        b"\xe2\x80\xa7",
        b"\0",
    ],
)
def test_skip_space_when_not_normal_file_space_then_leaves_byte(data: bytes) -> None:
    assert skip_space(data, 0) == 0


def test_skip_space_when_cursor_at_end_then_remains_at_end() -> None:
    assert skip_space(b"name", 4) == 4
