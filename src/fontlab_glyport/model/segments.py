# this_file: src/fontlab_glyport/model/segments.py
"""Glyphs segments as detached points, including each segment's start point."""

from itertools import pairwise
from math import hypot, isfinite

from ..fonttools import fonttools_module
from ..foundation import NSArray
from ..ui.cocoa import NSPoint, unsupported


class GSPathSegment(NSArray):
    """A detached line/cubic segment, including its starting point."""

    @property
    def type(self):
        return "line" if len(self) == 2 else "curve"

    @property
    def countOfPoints(self):
        return len(self)

    def pointAtIndex_(self, index):
        return self[index]

    def pointAtTime_(self, time):
        points = list(self)
        t = float(time)
        while len(points) > 1:
            points = [
                NSPoint(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
                for a, b in pairwise(points)
            ]
        return points[0]

    def length(self):
        if len(self) == 2:
            return hypot(self[1].x - self[0].x, self[1].y - self[0].y)
        bezier = fonttools_module("misc.bezierTools", "GSPathSegment.length.dependency")
        return bezier.calcCubicArcLength(*(tuple(point) for point in self))


def path_segments(path):
    nodes = list(path.nodes)
    if not nodes:
        return NSArray()
    if path.closed:
        start = next(
            (i for i in range(len(nodes) - 1, -1, -1) if nodes[i].type != "offcurve"),
            None,
        )
        if start is None:
            raise unsupported("GSPath.segments.allOffcurve")
        ordered = nodes[start:] + nodes[: start + 1]
    else:
        ordered = nodes
    if ordered[0].type == "offcurve":
        raise unsupported("GSPath.segments.openOffcurveStart")
    result, controls, start = [], [], NSPoint(*ordered[0].position)
    for node in ordered[1:]:
        end = NSPoint(*node.position)
        if node.type == "offcurve":
            controls.append(end)
            continue
        if node.type == "qcurve":
            for i, control in enumerate(controls):
                finish = (
                    end
                    if i == len(controls) - 1
                    else NSPoint(
                        (control.x + controls[i + 1].x) / 2,
                        (control.y + controls[i + 1].y) / 2,
                    )
                )
                # Exact quadratic-to-cubic conversion: segments have 4 points.
                c1 = NSPoint(
                    start.x + (control.x - start.x) * 2 / 3,
                    start.y + (control.y - start.y) * 2 / 3,
                )
                c2 = NSPoint(
                    finish.x + (control.x - finish.x) * 2 / 3,
                    finish.y + (control.y - finish.y) * 2 / 3,
                )
                result.append([start, c1, c2, finish])
                start = finish
            if not controls:
                result.append([start, end])
        elif node.type == "curve" and len(controls) == 2:
            result.append([start, *controls, end])
        elif not controls:
            result.append([start, end])
        else:
            raise unsupported("GSPath.segments.invalidControls")
        start, controls = end, []
    if controls:
        raise unsupported("GSPath.segments.trailingControls")
    return NSArray(GSPathSegment(segment) for segment in result)


def _segment_point(point):
    """Unbox Cocoa points and detach x/y into finite Python coordinates."""
    point_value = getattr(point, "pointValue", None)
    if callable(point_value):
        point = point_value()
    if hasattr(point, "x") and hasattr(point, "y"):
        point = (point.x, point.y)
    if isinstance(point, (str, bytes, bytearray)):
        raise TypeError("Segment points require two numeric coordinates")
    try:
        x, y = point
        x, y = float(x), float(y)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Segment points require two numeric coordinates") from error
    if not (isfinite(x) and isfinite(y)):
        raise ValueError("Segment coordinates must be finite")
    return x, y


def _segment_nodes(values, closed):
    """Parse one continuous line/cubic contour before touching its old nodes."""
    from .backend import NodeInfo

    segments = [tuple(_segment_point(point) for point in segment) for segment in values]
    if not segments:
        raise ValueError("GSPath.segments requires a nonempty array")
    if any(len(segment) not in (2, 4) for segment in segments):
        raise ValueError("Segments require two line or four cubic points")
    if any(first[-1] != second[0] for first, second in pairwise(segments)):
        raise ValueError("Path segments must be continuous")
    if closed and segments[-1][-1] != segments[0][0]:
        raise ValueError("A closed path must end at its first segment's start")
    nodes = [] if closed else [NodeInfo("", *segments[0][0])]
    for segment in segments:
        nodes.extend(NodeInfo("", *point, "offcurve") for point in segment[1:-1])
        nodes.append(
            NodeInfo("", *segment[-1], "line" if len(segment) == 2 else "curve")
        )
    return tuple(nodes)


def set_path_segments(path, values):
    """Rebuild sharp nodes in place, retaining path metadata and Undo machinery."""
    from .proxies import GSNode

    closed = path.closed  # Also reject a stale live path before parsing inputs.
    nodes = _segment_nodes(values, closed)
    if "_draft" in path.__dict__:
        replacement = [GSNode((node.x, node.y), node.type) for node in nodes]
        for node in path._draft_nodes:
            node._path = None
        path._draft_nodes = replacement
        for node in replacement:
            node._path = path
        return
    with path._font.undo_group("Replace path segments"):
        path._font._model._backend.set_path_nodes(path._id, nodes, closed)


def _signed_path_area(path, capability):
    """Integrate supported segments, closing open contours without editing them."""
    segments = path.segments
    if not segments:
        return 0
    module = fonttools_module("pens.areaPen", capability)
    pen = module.AreaPen()
    pen.moveTo(tuple(segments[0][0]))
    for segment in segments:
        if len(segment) == 2:
            pen.lineTo(tuple(segment[-1]))
        else:
            pen.curveTo(*(tuple(point) for point in segment[1:]))
    pen.closePath()
    return pen.value


def path_area(path):
    """Unsigned analytic area; curved results can differ from Glyphs' flattening."""
    return abs(_signed_path_area(path, "GSPath.area.dependency"))


def path_direction(path):
    """Glyphs uses +1 for clockwise and -1 for counterclockwise contours."""
    return -1 if _signed_path_area(path, "GSPath.direction.dependency") > 0 else 1
