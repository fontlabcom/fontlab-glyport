# this_file: src/fontlab_glyport/model/public_joining.py
"""Public-derived names for the retained positional helper's binary R predicate.

The complete R-set is independently calibrated against build4108. Non-R here
does not expose or approximate the native connectionType API's other values.
"""

import hashlib
import json
from functools import lru_cache
from importlib import resources

from ..errors import UnsupportedCapability


@lru_cache(maxsize=1)
def _right_names() -> frozenset[str]:
    try:
        raw = (
            resources.files("fontlab_glyport")
            .joinpath("data", "unicode17_positional_right.json")
            .read_bytes()
        )
        # Exact pinned public resource; partial/mismatched installs must fail.
        if hashlib.sha256(raw).hexdigest() != RESOURCE_SHA256:
            raise ValueError("Positional-name resource hash mismatch")
        return frozenset(json.loads(raw)["right_joining_names"])
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
        raise UnsupportedCapability(
            f"Packaged positional-name calibration is unavailable: {error}",
            capability="GSGlyphInfo.compound.joiningData",
            recovery_action="Install an intact matching fontlab-glyport distribution.",
        ) from error


def positional_kind(name: str) -> str:
    """Return R or non-R D for the internal retained positional branch only."""
    if not isinstance(name, str):
        raise TypeError("A positional component name must be a string")
    return "R" if name.split(".", 1)[0] in _right_names() else "D"


RESOURCE_SHA256 = "d0b7fd6f63730aa89e7707e59f572f815719dd38dbacd8562d48ed21e8fe7758"
