# this_file: src/fontlab_glyport/profile_versions.py
"""Compatibility metadata shared by guard evaluation and runtime adapters."""

from types import MappingProxyType
from typing import NamedTuple


class ProfileVersion(NamedTuple):
    # The first two fields retain the legacy bridge's (number, build) order.
    number: float
    build: float
    string: str


PROFILE_VERSIONS = MappingProxyType(
    {
        # Older profiles retain the existing synthetic compatibility values.
        "glyphs2": ProfileVersion(2.0, 2000.0, "2.0"),
        "glyphs3": ProfileVersion(3.0, 3000.0, "3.0"),
        # analysis/01-glyphs4/REPORT.md and the supplied bundle's Info.plist.
        "glyphs4": ProfileVersion(4.1, 4108.0, "4.1.1"),
    }
)
