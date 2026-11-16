# this_file: src/fontlab_glyport/model/background.py
"""Mask-backed backgrounds and detached background snapshots."""

from .._strict import caller_location
from ..errors import UnsupportedCapability
from .copies import DetachedLayer
from .proxies import GSLayer


class GSBackgroundImage:
    def __init__(self, *args, **kwargs):
        raise UnsupportedCapability(
            "raster background attachment is not exposed by the model backend; "
            "no image was loaded or attached",
            capability="GlyphsApp.GSBackgroundImage",
            location=caller_location(),
        )


class GSBackgroundLayer(GSLayer):
    """A native mask proxy, or a detached empty background when constructed."""

    def __new__(cls, *args, **kwargs):
        if cls is GSBackgroundLayer and not args and not kwargs:
            return object.__new__(DetachedBackgroundLayer)
        return object.__new__(cls)

    def foreground(self):
        return self.__dict__.get("_foreground")

    isMasterLayer = property(lambda self: False)
    background = property(lambda self: None)
    # The Glyphs wrapper deliberately ignores writes to a background's width.
    width = property(GSLayer.width.fget, lambda self, value: None)


class DetachedBackgroundLayer(DetachedLayer, GSBackgroundLayer):
    background = property(lambda self: None)
    width = property(DetachedLayer.width.fget, lambda self, value: None)
