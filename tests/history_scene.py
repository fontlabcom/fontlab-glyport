# this_file: tests/history_scene.py
"""Explicit offline Font-window and queue surfaces for native backend doubles."""

import sys
from types import SimpleNamespace as NS


def install_font_window(monkeypatch, module, package):
    """Extend a fixture's capabilities; keep the actual App guards operational."""
    package.isNull = False
    frame = NS(inherits=lambda name: name == "YFrameWindow")
    panel = NS(inherits=lambda name: name == "FontWindow", parentWidget=lambda: frame)
    if module.flWorkspace is None:
        module.flWorkspace = NS(instance=lambda: NS(packages=lambda: [package]))
    instance = module.flWorkspace.instance

    def workspace():
        value = instance()
        if not hasattr(value, "getActiveCanvas"):
            value.getActiveCanvas = lambda: None
        if not hasattr(value, "activeFontPanel"):
            value.activeFontPanel = panel
        if not hasattr(value, "currentPackage"):
            value.currentPackage = package
        return value

    monkeypatch.setattr(module.flWorkspace, "instance", workspace)
    if not hasattr(module, "flGlyph"):
        module.flGlyph = NS()
    monkeypatch.setattr(module.flGlyph, "updatedFgGlyphs", lambda: (), raising=False)
    monkeypatch.setitem(sys.modules, "fontlab", module)


def register_history_owner(backend, package, glyph, layers=()):
    """Give manually retained test batches the same parent maps as live reads."""
    fid = backend._font_id(package)
    glyph.isValid = True
    gid = backend._register((fid, "glyph", glyph.id), glyph, fid)
    backend._glyph_names[gid] = glyph.name
    for layer in layers:
        layer.isValid = True
        backend._register((fid, "layer", gid, layer.name), layer, gid)
