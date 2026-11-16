# this_file: src/fontlab_glyport/model/production_metadata.py
"""Nullable stored production and the separate audited GSGlyphInfo helper.

Slots adapt immutable public records; filling one never changes dependency data.
The helper computes an output only, leaving name/Unicode producer policy to callers.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from glyphsLib.glyphdata import GlyphData


@dataclass
class StoredProduction:
    """One mutable stored field, shared by canonical database-record handles."""

    value: str | None = None


@lru_cache(maxsize=1)
def _slots(data: "GlyphData") -> dict[str, StoredProduction]:
    """Keep a lazy adapter for the actual hashable immutable dataset identity."""
    return {}


def slot_for(data: "GlyphData", attributes: dict[str, str]) -> StoredProduction:
    """Return the canonical record's raw nullable slot, without name-lookup fill."""
    slots = _slots(data)
    name = attributes["name"]
    if name not in slots:
        slots[name] = StoredProduction(attributes.get("production"))
    return slots[name]


def _utf16_length(value: str) -> int:
    """Match NSString length, preserving lone surrogate code units."""
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def production_name(
    name: str, stored: str | None, unicode: str | None, script: str | None
) -> str | None:
    """Compute retained Glyphs4 GSGlyphInfo helper output, never the raw getter.

    The separate GSGlyph/font-local helper branches remain outside this contract.
    Unicode spelling and the audited additive hex parsing are preserved.
    """
    if stored:
        if (
            _utf16_length(stored) == 7
            and stored.startswith("uni")
            and unicode
            and _utf16_length(unicode) == 4
        ):
            return "uni" + unicode
        return stored
    if unicode:
        from .glyph_metadata import _hex_value, private_use

        if private_use(_hex_value(unicode)) or (
            script == "latin" and ("-" in name or "." in name)
        ):
            return ("uni" if _utf16_length(unicode) <= 4 else "u") + unicode
        return name
    return name.replace("-", "") or name
