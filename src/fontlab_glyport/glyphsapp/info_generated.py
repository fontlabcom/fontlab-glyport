# this_file: src/fontlab_glyport/glyphsapp/info_generated.py
"""Adapt real queued generation to source-qualified metadata record views.

The component setter replaces only its storage. No FontLab
objects, native pointer conversions or shared resource installation are involved.
"""

from types import SimpleNamespace

from ..errors import UnsupportedCapability
from .glyph_info import GSGlyphInfo
from .info_hangul import queue_hangul
from .info_runtime import state_for


def _record(view: GSGlyphInfo) -> SimpleNamespace:
    if isinstance(view, GSGlyphInfo):
        record = vars(view).get("_resolved_record")
        if isinstance(record, SimpleNamespace):
            return record
    raise UnsupportedCapability(
        "Generated components require source-qualified record views",
        capability="GSGlyphsInfo.generatedComponents.recordSource",
    )


def assign_components(
    target: GSGlyphInfo | None, parts: tuple[GSGlyphInfo, ...]
) -> None:
    """Replace component storage, retaining raw identities and unrelated state."""
    if target is None:
        return
    record = _record(target)
    records = tuple(_record(part) for part in parts)
    record._component_records = records
    record._component_names = None
    record._unavailable_fields = frozenset(
        getattr(record, "_unavailable_fields", ())
    ) - {"components"}


def add_hangul(manager: object) -> None:
    """Capture the receiver; resolve its method and records at each later call."""
    queue_hangul(
        state_for(manager).queue,
        lambda code: manager.glyphInfoForUnicode_(code),
        assign_components,
    )
