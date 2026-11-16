# this_file: src/fontlab_glyport/model/unicode_casing.py
"""Retained Foundation name casing from licensed public Unicode17 facts."""

import gzip
import hashlib
import json
from bisect import bisect_right
from functools import lru_cache
from importlib import resources

from ..errors import UnsupportedCapability
from .unicode_case import lowercase_scalar

_RESOURCE_SHA256 = "005cde63f97724ede155cd13d787fc5fe33b4455e694eaa3c79b8c9431903c84"


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        raw = (
            resources.files("fontlab_glyport")
            .joinpath("data", "unicode17_casing.json.gz")
            .read_bytes()
        )
        if hashlib.sha256(raw).hexdigest() != _RESOURCE_SHA256:
            raise ValueError("Unicode17 casing resource checksum mismatch")
        data = json.loads(gzip.decompress(raw))
        data["uppercase"] = {
            int(key, 16): tuple(int(c, 16) for c in values)
            for key, values in data["uppercase"].items()
        }
        for key in ("cased_ranges", "ignorable_ranges"):
            data[key] = tuple(tuple(pair) for pair in data[key])
        return data
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise UnsupportedCapability(
            f"Packaged Unicode17 casing data is unavailable: {error}",
            capability="GSGlyphInfo.smallCaps.casingData",
            recovery_action="Install an intact fontlab-glyport distribution.",
        ) from error


def uppercase_scalar(value: int) -> tuple[int, ...]:
    """Return full uppercase independently of Python's Unicode version."""
    if type(value) is not int:
        raise TypeError("Code point must be an integer")
    if not 0 <= value <= 0x10FFFF:
        raise ValueError("Code point must be in 0..10FFFF")
    return _data()["uppercase"].get(value, (value,))


def _has(value: int, key: str) -> bool:
    ranges = _data()[key]
    index = bisect_right(ranges, (value, 0x110000)) - 1
    return index >= 0 and value <= ranges[index][1]


def _neighbor(values: list[int], index: int, step: int) -> bool | None:
    index += step
    while 0 <= index < len(values):
        value = values[index]
        if not _has(value, "ignorable_ranges"):
            return _has(value, "cased_ranges")
        index += step
    return None


def _final_sigma(values: list[int], index: int) -> bool:
    # Retained scan accepts a wholly ignorable prefix; index zero never qualifies.
    return (
        index > 0
        and _neighbor(values, index, -1) is not False
        and _neighbor(values, index, 1) is not True
    )


def lowercase_text(text: str) -> str:
    """Match the qualified nonlocalized Foundation scan, preserving UTF16 data."""
    text = text.encode("utf-16-le", "surrogatepass").decode(
        "utf-16-le", "surrogatepass"
    )
    values = list(map(ord, text))
    result = []
    for index, value in enumerate(values):
        mapped = (
            (0x03C2,)
            if value == 0x03A3 and _final_sigma(values, index)
            else lowercase_scalar(value)
        )
        result.extend(mapped)
    return "".join(map(chr, result))
