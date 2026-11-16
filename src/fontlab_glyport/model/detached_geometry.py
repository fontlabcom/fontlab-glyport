# this_file: src/fontlab_glyport/model/detached_geometry.py
"""Exact, host-free bounds and component expansion for detached layer copies."""

from copy import deepcopy

from ..errors import UnsupportedCapability
from ..fonttools import fonttools_module
from .proxies import GSPath, _unsupported


def decomposed_paths(layer, operation, seen=frozenset()):
    capability = f"DetachedLayer.{operation}"
    if id(layer) in seen:
        _unsupported(capability + ".cyclicComponent")
    seen = seen | {id(layer)}
    paths = []
    for shape in layer.shapes:
        if isinstance(shape, GSPath):
            paths.append(deepcopy(shape))
            continue
        name = shape.componentName
        source = layer._component_layers.get(name)
        if source is None:
            _unsupported(capability + ".component." + name)
        # Stage every expanded path before changing the destination layer.
        from .copies import DetachedLayer

        transformed = DetachedLayer()
        transformed.shapes = decomposed_paths(source, operation, seen)
        transformed.applyTransform(shape.transform)
        paths.extend(transformed.paths)
    return paths


def layer_bounds(layer):
    paths = decomposed_paths(layer, "bounds")
    if not any(path.nodes for path in paths):
        return None
    module = fonttools_module("pens.boundsPen", "DetachedLayer.bounds.dependency")
    pen = module.BoundsPen(None)
    for path in paths:
        if not path.nodes:
            continue
        try:
            segments = path.segments
        except UnsupportedCapability as error:
            _unsupported("DetachedLayer.bounds." + error.capability.rsplit(".", 1)[-1])
        pen.moveTo(tuple(segments[0][0] if segments else path.nodes[0].position))
        for segment in segments:
            if len(segment) == 2:
                pen.lineTo(tuple(segment[-1]))
            else:
                pen.curveTo(*(tuple(point) for point in segment[1:]))
        if path.closed:
            pen.closePath()
        else:
            pen.endPath()
    if pen.bounds is None:
        return None
    x, y, right, top = pen.bounds
    return x, y, right - x, top - y


def remove_overlap(layer):
    """Skia's winding-aware boolean simplification; publish only complete output."""
    paths = decomposed_paths(layer, "removeOverlap")
    if not paths:
        return []
    try:
        import pathops
    except ImportError as error:
        raise UnsupportedCapability(
            "DetachedLayer.removeOverlap requires skia-pathops (the boolean extra)",
            capability="DetachedLayer.removeOverlap.dependency",
        ) from error
    from .proxies import GSNode

    closed = [path for path in paths if path.closed]
    if any(path.attributes for path in closed):
        _unsupported("DetachedLayer.removeOverlap.styledPaths")
    combined = pathops.Path()
    pen = combined.getPen()
    for path in closed:
        if not path.nodes:
            continue
        segments = path.segments
        pen.moveTo(tuple(segments[0][0] if segments else path.nodes[0].position))
        for segment in segments:
            if len(segment) == 2:
                pen.lineTo(tuple(segment[-1]))
            else:
                pen.curveTo(*(tuple(point) for point in segment[1:]))
        pen.closePath()
    combined.simplify(fix_winding=True, keep_starting_points=True)

    class Output:
        def __init__(self):
            self.paths, self.nodes = [], []

        def moveTo(self, point):
            self.nodes = [GSNode(point)]

        def lineTo(self, point):
            self.nodes.append(GSNode(point))

        def curveTo(self, a, b, end):
            self.nodes.extend(
                (GSNode(a, "offcurve"), GSNode(b, "offcurve"), GSNode(end, "curve"))
            )

        def closePath(self):
            if (
                len(self.nodes) > 1
                and self.nodes[-1].type != "offcurve"
                and self.nodes[-1].position == self.nodes[0].position
            ):
                # Retain the incoming closing segment type, not moveTo's line.
                self.nodes[0] = self.nodes.pop()
            # Glyphs lists the start on-curve node last in a closed contour.
            self.paths.append(GSPath(self.nodes[1:] + self.nodes[:1], closed=True))

        def endPath(self):
            self.paths.append(GSPath(self.nodes, closed=False))

    output = Output()
    combined.draw(output)
    return output.paths + [path for path in paths if not path.closed]
