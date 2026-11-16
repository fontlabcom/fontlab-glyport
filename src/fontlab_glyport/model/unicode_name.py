# this_file: src/fontlab_glyport/model/unicode_name.py
"""Decode retained uni/u grammar into ordered, unchanged raw records."""

from collections.abc import Callable
from types import SimpleNamespace

_UPPER_HEX = frozenset("0123456789ABCDEF")


def decode_unicode_name(
    name: str,
    lookup: Callable[[str], SimpleNamespace | None],
    fallback: Callable[[str], SimpleNamespace],
) -> list[SimpleNamespace] | None:
    """Apply the ordered decoder gates, delegating all record policy.

    Rejected grammar returns None; bare ``uni`` returns an empty list. Bare
    ``u`` preserves the helper's empty-payload IndexError. Accepted payloads
    are ASCII, so their Python lengths equal the retained UTF16-unit lengths.
    Indexed records retain identity; each miss calls fallback independently.
    """
    length = len(name)
    if name.startswith("uni") and length % 4 == 3:
        payload, width = name[3:], 4
    elif name.startswith("u") and length % 5 == 1:
        payload, width = name[1:], 5
    elif name.startswith("u1") and length == 7:
        payload, width = name[1:], 6
    elif name.startswith("u") and length == 5:
        payload, width = name[1:], 4
    else:
        return None

    if any(character not in _UPPER_HEX for character in payload):
        return None
    if width == 5 and payload[0] == "0":
        payload, width = payload[1:], 4

    records = []
    for start in range(0, len(payload) - width + 1, width):
        code = payload[start : start + width]
        record = lookup(code)
        records.append(fallback(code) if record is None else record)
    return records
