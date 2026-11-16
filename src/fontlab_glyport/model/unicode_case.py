# this_file: src/fontlab_glyport/model/unicode_case.py
"""Versioned scalar casing and owned additional-encoding resolution.

Unicode17 matches the independently measured macOS27.2 NSString scalar results;
this is not a qualification of every native host or custom glyph-info manager.
"""

import json
from functools import lru_cache
from importlib import resources
from types import SimpleNamespace

from ..errors import UnsupportedCapability


def _code(value):
    if not isinstance(value, str):
        raise ValueError("Unicode data must contain hexadecimal strings")  # noqa: TRY004 - preserve the existing ValueError contract for malformed data
    code = int(value, 16)
    if not 0 <= code <= 0x10FFFF or f"{code:04X}" != value:
        raise ValueError("Unicode data contains a noncanonical code point")
    return code


@lru_cache(maxsize=1)
def _mapping():
    try:
        raw = json.loads(
            resources.files("fontlab_glyport")
            .joinpath("data", "unicode17_lowercase.json")
            .read_text("utf-8")
        )
        if not isinstance(raw, dict) or raw.get("unicode_version") != "17.0.0":
            raise ValueError("Expected Unicode17 lowercase data")
        mapping = raw.get("lowercase")
        if not isinstance(mapping, dict) or len(mapping) != 1488:
            raise ValueError("Incomplete Unicode17 lowercase mapping")
        result = {}
        for code, values in mapping.items():
            if not isinstance(values, list) or not values:
                raise ValueError("A lowercase mapping must be a nonempty list")
            result[_code(code)] = tuple(_code(value) for value in values)
        return result
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        raise UnsupportedCapability(
            f"Packaged Unicode17 lowercase data is unavailable: {error}",
            capability="GSGlyph.metadata.lowercaseData",
            recovery_action="Install an intact fontlab-glyport distribution.",
        ) from error


def lowercase_scalar(value: int) -> tuple[int, ...]:
    """Return the full scalar lowercase mapping, independent of Python Unicode."""
    if type(value) is not int:
        raise TypeError("Code point must be an integer")
    if not 0 <= value <= 0x10FFFF:
        raise ValueError("Code point must be in 0..10FFFF")
    return _mapping().get(value, (value,))


def _append(info, code):
    from .glyph_metadata import _copy_production
    from .info_records import add_unicode

    if getattr(info, "_locked", True):
        info = SimpleNamespace(**_copy_production(vars(info).copy()))
    if not hasattr(info, "unicodes"):
        info.unicodes = (info.unicode,) if info.unicode else ()
    add_unicode(info, code)
    return info


def _available(font, glyph, value):
    owner = font.glyphForUnicode_(f"{value:04X}")
    return owner is None or owner._id == glyph._id


def additional_unicode(glyph, info, name, codes):
    """Apply audited helper gates using staged names/codes and prior fields."""
    if info is None or not codes:
        return info
    parent = glyph.parent
    if glyph.case == 1:
        if parent is None:
            return info
        if glyph.script == "greek" and any(
            parent.glyphForUnicode_(code) is None for code in ("03A6", "03A3")
        ):
            return info
        value = int(codes[0], 16)
        if value == 0x0130 or value > 0x10FFFE:
            return info
        lowered = lowercase_scalar(value)
        if lowered != (value,) and _available(parent, glyph, lowered[0]):
            info = _append(info, f"{lowered[0]:04X}")
        if value == 0x0049 and _available(parent, glyph, 0x0131):
            info = _append(info, "0131")
    if glyph.script == "arabic":
        if parent is None:
            return None
        isolated = name + ".isol"
        if parent.glyphs[isolated] is None:
            record = parent.glyphsInfo().glyphInfoForName_(isolated)
            if record is not None:
                info = _append(info, record.unicode)
    return info


def presentation_unicode(glyph, info):
    """Append audited Arabic presentation metadata before stored-field overlays."""
    if info is None or info.script != "arabic" or glyph.parent is None:
        return info
    value = glyph.parent.customParameters["Use Arabic Presentation Form Unicodes"]
    if value is None:
        return info
    from .parameter_numbers import normalize

    if not normalize(value):
        return info
    legacy = getattr(info, "unicodeLegacy", None)
    if legacy is None:
        from .glyph_metadata import _direct

        isolated = _direct(info.name + ".isol")
        legacy = None if isolated is None else isolated.unicodeLegacy
    return _append(info, legacy)
