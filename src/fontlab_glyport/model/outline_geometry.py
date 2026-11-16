# this_file: src/fontlab_glyport/model/outline_geometry.py
"""Exact Python contour geometry shared by both model backends."""

from dataclasses import replace

from fontlab_pens import (
    AreaPen,
    PointInsidePen,
    PointToSegmentPen,
    ReverseContourPointPen,
)

from ..fonttools import fonttools_module
from .pens import draw_path_points, path_info


def _explicit_nodes(path):
    """Make implied quadratic endpoints explicit without changing geometry."""
    from .backend import NodeInfo

    nodes = list(path.nodes)
    if not nodes:
        return []
    if all(n.type == "offcurve" for n in nodes):
        if not path.closed:
            raise ValueError("An open path must start with an on-curve point")
        a, b = nodes[-1], nodes[0]
        nodes.insert(
            0,
            NodeInfo(
                "",
                (a.x + b.x) / 2,
                (a.y + b.y) / 2,
                "qcurve",
                True,
                selected=a.selected and b.selected,
            ),
        )
    if path.closed:
        # Glyphs can put outgoing controls first and the start on-curve last.
        # Traverse from that start, then restore the original node rotation.
        index = (
            0
            if nodes[0].type != "offcurve"
            else next(
                i for i in range(len(nodes) - 1, -1, -1) if nodes[i].type != "offcurve"
            )
        )
        nodes = nodes[index:] + nodes[:index] + [nodes[index]]
    if nodes[0].type == "offcurve":
        raise ValueError("An open path must start with an on-curve point")
    result, controls = [nodes[0]], []
    for node in nodes[1:]:
        if node.type == "offcurve":
            controls.append(node)
            continue
        for index, control in enumerate(controls):
            result.append(control)
            if node.type == "qcurve" and index + 1 < len(controls):
                other = controls[index + 1]
                result.append(
                    NodeInfo(
                        "",
                        (control.x + other.x) / 2,
                        (control.y + other.y) / 2,
                        "qcurve",
                        True,
                        selected=control.selected and other.selected,
                    )
                )
        result.append(node)
        controls = []
    if controls:
        raise ValueError("Unterminated Bezier segment")
    return result


def _draft(info):
    from .proxies import GSNode, GSPath

    path = GSPath(
        [GSNode((n.x, n.y), n.type, n.smooth) for n in info.nodes], info.closed
    )
    path._draft = replace(path._draft, attributes=info.attributes)
    for node, source in zip(path.nodes, info.nodes, strict=True):
        node._draft = replace(source, id="")
    return path


def _direction_paths(paths):
    """Analytic winding and containment; outer contours are counterclockwise.

    FontLab has no layer-scoped correction call in echopy's stubs. Use
    fontlab_pens AreaPen/PointInsidePen/ReverseContourPointPen in Python instead.
    """
    from .copies import DetachedLayer
    from .pens import LayerPen

    closed = [p for p in paths if p.closed and p.nodes]
    result = []
    for path in paths:
        if path not in closed:
            result.append(path)
            continue
        first = next((n for n in path.nodes if n.type != "offcurve"), path.nodes[0])
        depth = 0
        for other in closed:
            if other is path:
                continue
            inside = PointInsidePen(None, (first.x, first.y), evenOdd=True)
            draw_path_points(other, PointToSegmentPen(inside))
            depth += bool(inside.getResult())
        area = AreaPen(None)
        draw_path_points(path, PointToSegmentPen(area))
        if bool(area.value < 0) == bool(depth % 2):
            result.append(path)
            continue
        destination = DetachedLayer()
        draw_path_points(path, ReverseContourPointPen(LayerPen(destination)))
        result.append(
            replace(path_info(destination.paths[0]), attributes=path.attributes)
        )
    return tuple(result)


def _extreme_paths(paths, check_selection):
    """Split Beziers at derivative roots without flattening or approximating.

    There is no layer-scoped add-extremes call in echopy's stubs. Python's
    fontTools Bezier routines implement exact cubic and quadratic splitting.
    """
    from .backend import NodeInfo

    bezier = fonttools_module("misc.bezierTools", "GSLayer.addNodesAtExtremes")
    result = []
    for path in paths:
        nodes = _explicit_nodes(path)
        if not nodes:
            result.append(path)
            continue
        output, controls = [nodes[0]], []
        for node in nodes[1:]:
            if node.type == "offcurve":
                controls.append(node)
                continue
            start = output[-1]
            segment = [start, *controls, node]
            selected = not check_selection or all(n.selected for n in segment)
            if not controls or not selected:
                output.extend([*controls, node])
                controls = []
                continue
            points = [(n.x, n.y) for n in segment]
            if node.type == "curve" and len(controls) == 2:
                a, b, c, _ = bezier.calcCubicParameters(*points)
                roots = [
                    t
                    for dimension in range(2)
                    for t in bezier.solveQuadratic(
                        3 * a[dimension], 2 * b[dimension], c[dimension]
                    )
                ]
                splitter = bezier.splitCubicAtT
            elif node.type == "qcurve" and len(controls) == 1:
                roots = [
                    (points[0][i] - points[1][i])
                    / (points[0][i] - 2 * points[1][i] + points[2][i])
                    for i in range(2)
                    if points[0][i] - 2 * points[1][i] + points[2][i]
                ]
                splitter = bezier.splitQuadraticAtT
            else:
                raise ValueError("Unsupported Bezier control sequence for extrema")
            roots = sorted({round(t, 14) for t in roots if 1e-10 < t < 1 - 1e-10})
            if not roots:
                output.extend([*controls, node])
            else:
                pieces = splitter(*points, *roots)
                for i, piece in enumerate(pieces):
                    output.extend(NodeInfo("", *p, "offcurve") for p in piece[1:-1])
                    output.append(
                        node
                        if i == len(pieces) - 1
                        else NodeInfo(
                            "", *piece[-1], node.type, True, selected=node.selected
                        )
                    )
            controls = []
        if controls:
            raise ValueError("Unterminated Bezier segment")
        if path.closed:
            output[0] = replace(output[0], type=output[-1].type)
            output.pop()
            if len(output) == len(path.nodes):
                result.append(path)
                continue
            if path.nodes[0].type == "offcurve":
                start = (
                    next(
                        i
                        for i in range(len(path.nodes) - 1, -1, -1)
                        if path.nodes[i].type != "offcurve"
                    )
                    if any(n.type != "offcurve" for n in path.nodes)
                    else len(path.nodes) - 1
                )
                offset = len(path.nodes) - start
                output = output[offset:] + output[:offset]
        result.append(replace(path, nodes=tuple(output)))
    return tuple(result)
