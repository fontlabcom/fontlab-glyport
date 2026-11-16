# this_file: src/fontlab_glyport/model/compound_scripts.py
"""Ordered Indic name filtering from the retained compound call path."""

import hashlib
import json
from functools import lru_cache
from importlib import resources

from ..errors import UnsupportedCapability

INDIC_SCRIPTS = frozenset(
    ["devanagari", "dev2", "deva", "oriya", "ory2", "kannada", "knd2", "knda", "malayalam", "mlm2", "gujarati", "gujr", "telugu", "telu", "gurmukhi", "guru", "gur2", "tamil", "taml", "tml2", "khmer", "khmr", "bengali", "beng", "cham", "chakma", "cakm", "sharada", "shrd"]
)


@lru_cache(maxsize=1)
def _script_suffixes() -> dict[str, str]:
    try:
        raw = (
            resources.files("fontlab_glyport")
            .joinpath("data", "public_script_suffixes.json")
            .read_bytes()
        )
        if (
            hashlib.sha256(raw).hexdigest()
            != "a26412f27770364f2dec9ca2f3f38e40a9d947ed510662d18249375316bb8801"
        ):
            raise ValueError("Public script-suffix resource hash mismatch")
        return json.loads(raw)["script_suffixes"]
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        raise UnsupportedCapability(
            "Public script-suffix data is unavailable",
            capability="GSGlyphInfo.compound.scriptData",
        ) from error


def script_for_tag(tag: str | None) -> str | None:
    """Return an independently qualified public mapping; private-only tags remain unqualified."""
    return _script_suffixes().get(tag) if tag else None


def filter_halant(names: list[str]) -> list[str]:
    """Retain the native index-changing scan, including its shifted-entry skip."""
    result = list(names)
    previous_halant = previous_ra = a_index = current_halant = -10
    halant_text = a_text = ""
    index = 0
    while index < len(result):
        name = result[index]
        current_halant = -10
        inspect_a = True
        if name.startswith("halant-"):
            halant_text, current_halant = name, index
            if previous_ra == index - 1:
                result[index] = name.replace("halant", "reph")
                del result[previous_ra]
                previous_ra = current_halant = -10
                inspect_a = False
        elif name.startswith("ra-") and not name.endswith("-kannada"):
            if previous_halant == index - 1:
                result[previous_halant] = halant_text.replace("halant", "rakar")
                del result[previous_halant + 1]
                index = previous_halant
                previous_ra = -10
                inspect_a = False
            else:
                previous_ra = index
        else:
            if index > 1 and previous_halant == index - 1 and a_index >= 0:
                result[a_index] = a_text.replace("a-", "-")
                del result[previous_halant]
                a_index = -10
                index = previous_halant
            previous_ra = -10
        if inspect_a and 0 <= name.find("a-") < 4:
            a_index, a_text = index, name
        previous_halant = current_halant
        index += 1
    if current_halant > 0 and previous_ra < 0 and a_index >= 0:
        result[a_index] = a_text.replace("a-", "-")
        del result[current_halant]
    return result
