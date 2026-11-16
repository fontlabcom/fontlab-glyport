# this_file: src/fontlab_glyport/glyphsapp/info_hangul.py
"""Source-derived queued Hangul component linking for explicit owned records.

Matches the retained uint16 primitive and complete 0xAC00/0x2BA4 enumeration.
This is a scalar/record contract, not an arbitrary Objective-C pointer bridge.
"""

from collections.abc import Callable
from typing import Protocol

from ..model.info_hex import hex_u32
from .info_runtime import InfoNativeException

_HANGUL_FIRST = 0xAC00
_HANGUL_END = 0xD7A4
_NO_TRAILING = 0xFFFF
_VOWEL_COUNT = 21
_TRAILING_COUNT = 28


class _Queue(Protocol):
    def addOperationWithBlock_(self, callback: Callable[[], None]) -> None: ...


def decompose_hangul(code: int) -> tuple[int, int, int] | None:
    """Return leading/vowel/trailing uint16 values, or None outside Hangul.

    A missing trailing consonant is 0xFFFF. Python input must already be a
    uint16 integer; raw bridge conversions and pointer outputs are unqualified.
    """
    if type(code) is not int:
        raise TypeError("Hangul decomposition requires a qualified uint16 integer")
    if not 0 <= code <= 0xFFFF:
        raise ValueError("Hangul decomposition requires an integer in 0..0xFFFF")
    if not _HANGUL_FIRST <= code < _HANGUL_END:
        return None
    leading, remainder = divmod(code - _HANGUL_FIRST, _VOWEL_COUNT * _TRAILING_COUNT)
    vowel, trailing = divmod(remainder, _TRAILING_COUNT)
    return (
        0x1100 + leading,
        0x1161 + vowel,
        0x11A7 + trailing if trailing else _NO_TRAILING,
    )


def link_hangul(
    lookup: Callable[[str], object | None],
    assign: Callable[[object, tuple[object, ...]], None],
) -> None:
    """Link all syllables using then-current lookups in retained source order.

    NSArray rejects nil members after all part lookups, even for a nil target.
    The marked exception models that boundary only; completed writes survive.
    """
    for code in range(_HANGUL_FIRST, _HANGUL_END):
        leading, vowel, trailing = decompose_hangul(code)
        target = lookup(hex_u32(code))
        parts = (lookup(hex_u32(leading)), lookup(hex_u32(vowel)))
        if trailing != _NO_TRAILING:
            parts += (lookup(hex_u32(trailing)),)
        if any(part is None for part in parts):
            raise InfoNativeException(
                f"Hangul {hex_u32(code)} component array contains nil"
            )
        if target is not None:
            assign(target, parts)


def queue_hangul(
    queue: _Queue,
    lookup: Callable[[str], object | None],
    assign: Callable[[object, tuple[object, ...]], None],
) -> None:
    """Enqueue exactly one complete operation; execution and waits belong to caller."""
    queue.addOperationWithBlock_(lambda: link_hangul(lookup, assign))
