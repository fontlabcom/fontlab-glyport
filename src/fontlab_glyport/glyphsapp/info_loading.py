# this_file: src/fontlab_glyport/glyphsapp/info_loading.py
"""Qualified URL and raw-pointer arguments for the public Glyph Info loaders."""

import sys
from types import ModuleType

from ..errors import UnsupportedCapability


def _require_null_error(value):
    """Qualified raw ^@ default-PyObjC profile; no output slot or tuple."""
    from ..ui.objc_bridge import NULL

    if value is None or value is NULL:
        return
    bridge = sys.modules.get("objc")
    if isinstance(bridge, ModuleType) and value is vars(bridge).get("NULL"):
        return
    raise UnsupportedCapability(
        "Unqualified custom GlyphData error pointer; supply None or objc.NULL",
        capability="GSGlyphsInfo.customData.errorPointer",
    )


def _url_path(url):
    """Accept the qualified NSURL.path() protocol without importing a framework."""
    path = getattr(url, "path", None)
    if callable(path):
        value = path()
        if type(value) is str:
            return value
    raise UnsupportedCapability(
        "Custom GlyphData requires a URL with a qualified string path()",
        capability="GSGlyphsInfo.customData.URL",
    )
