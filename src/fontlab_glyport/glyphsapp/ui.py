# this_file: src/fontlab_glyport/glyphsapp/ui.py
"""``GlyphsApp.UI``: ``GlyphView``, a vanilla control that shows one layer.

Built over a session's vanilla module: a ``VanillaBaseObject`` hosting an
NSView whose ``drawRect_`` fills the background and the layer's
``completeBezierPath``, scaled so the master's ascender..descender fills the
height, centred horizontally. Referenced by glyphsapp/fontlab_session.py.
"""

from types import ModuleType
from typing import Any

from ..ui.cocoa_menu import NSMenuItem


class MenuItem(NSMenuItem):
    """Legacy UI constructor: a title, selector/callable action and target."""

    def __init__(self, title, action=None, target=None):
        self.initWithTitle_action_keyEquivalent_(title, action, "")
        self.setTarget_(target)


def _glyph_ns_view(ns_view: type) -> type:
    """The NSView subclass that draws a ``GlyphView``'s layer."""
    from ..drawing.cocoa_drawing import NSAffineTransform, NSColor, NSRectFill

    class _GlyphNSView(ns_view):
        def drawRect_(self, rect) -> None:
            owner = self._glyph_view
            if owner._background is not None:
                owner._background.set()
                NSRectFill(rect)
            layer = owner._layer
            if layer is None:
                return
            (_, _), (width, height) = self.bounds()
            metrics = layer.master._metrics()
            span = metrics.ascender - metrics.descender
            if span <= 0 or height <= 0:
                return
            scale = height / span
            path = layer.completeBezierPath
            transform = NSAffineTransform.transform()
            transform.translateXBy_yBy_(
                (width - layer.width * scale) / 2, -metrics.descender * scale
            )
            transform.scaleBy_(scale)
            path.transformUsingAffineTransform_(transform)
            (owner._color or NSColor.blackColor()).set()
            path.fill()

    return _GlyphNSView


def make_ui_module(vanilla: ModuleType) -> ModuleType:
    """Return a ``GlyphsApp.UI`` module bound to ``vanilla``'s environment."""
    base = vanilla.VanillaBaseObject
    views: list[type] = []  # the NSView subclass, built on first use (needs Qt)

    def view_class() -> type:
        if not views:
            views.append(_glyph_ns_view(base._env.appkit["NSView"]))
        return views[0]

    class GlyphView(base):
        """``GlyphView(posSize, layer=None, backgroundColor=None)``."""

        def __init__(self, posSize, layer=None, backgroundColor=None, **kwargs: Any):
            self._layer, self._background = layer, backgroundColor
            self._color = kwargs.get("color")
            self._setupView(view_class(), posSize)
            self._nsObject._glyph_view = self

        @property
        def layer(self):
            return self._layer

        @layer.setter
        def layer(self, value) -> None:
            self._layer = value
            self._nsObject.setNeedsDisplay_(True)

        def setLayer_(self, value) -> None:
            self.layer = value

    module = ModuleType("GlyphsApp.UI", "glyport GlyphsApp.UI views")
    module.GlyphView = GlyphView
    module.MenuItem = MenuItem
    module.__all__ = ["GlyphView", "MenuItem"]
    return module
