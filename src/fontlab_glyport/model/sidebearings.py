# this_file: src/fontlab_glyport/model/sidebearings.py
"""Glyphs spacing is measured after removing the master's italic shear."""

from math import radians, tan

from ..drawing.cocoa_drawing import NSBezierPath
from ..fonttools import fonttools_module


def spacing_bounds(layer):
    angle = layer.italicAngle
    if not angle:
        return layer._bounds()
    from .copies import DetachedLayer
    from .detached_geometry import decomposed_paths
    from .proxies import _append_path_segments

    if isinstance(layer, DetachedLayer):
        outline = NSBezierPath.bezierPath()
        for path in decomposed_paths(layer, "sidebearings"):
            _append_path_segments(outline, path)
    else:
        outline = layer.completeBezierPath
    module = fonttools_module("pens.boundsPen", "GSLayer.sidebearings")
    pen = module.BoundsPen(None)
    shear = tan(radians(angle))
    center = layer.slantHeight
    for kind, *points in outline._elements:
        points = [(x - shear * (y - center), y) for x, y in points]
        if kind == "move":
            pen.moveTo(points[0])
        elif kind == "line":
            pen.lineTo(points[0])
        elif kind == "curve":
            pen.curveTo(*points)
        else:
            pen.closePath()
    if pen.bounds is None:
        return None
    left, bottom, right, top = pen.bounds
    return left, bottom, right - left, top - bottom
