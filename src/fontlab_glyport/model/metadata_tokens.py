# this_file: src/fontlab_glyport/model/metadata_tokens.py
"""Retained string-to-byte metadata decoders on owned str/None input only.

The prefix rules are distinct from public enum constants. This does not emulate
PyObjC coercion, native object messages, or out-of-range scalar conversion.
"""

from .production_metadata import _utf16_length


def direction_from_string(value: str | None) -> int:
    """Decode the retained parser's first/third UTF16 characters, including 12."""
    if value is None or _utf16_length(value) < 3:
        return 0
    units = value.encode("utf-16-le", errors="surrogatepass")
    first, third = (
        int.from_bytes(units[:2], "little"),
        int.from_bytes(units[4:6], "little"),
    )
    if first == ord("V"):
        return 12 if third == ord("R") else 4
    return {ord("R"): 2, ord("B"): 1}.get(first, 0)


def case_from_string(value: str | None) -> int:
    """The retained ten-entry table uses only the first character l through u."""
    if not value:
        return 0
    return {"l": 2, "m": 4, "o": 5, "s": 3, "u": 1}.get(value[0], 0)
