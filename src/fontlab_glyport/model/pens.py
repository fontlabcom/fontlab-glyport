# this_file: src/fontlab_glyport/model/pens.py
"""fontlab_pens point/segment protocols over layer snapshots and existing writes."""

from weakref import proxy

from fontlab_pens import PointToSegmentPen, SegmentToPointPen

from .backend import PathInfo


def draw_path_points(path: PathInfo, pen) -> None:
    """Emit a contour's point order, node names and smoothness."""
    if not path.nodes:
        return
    pen.beginPath()
    for index, node in enumerate(path.nodes):
        kind = None if node.type == "offcurve" else node.type
        if not path.closed and index == 0:
            kind = "move"
        pen.addPoint(
            (node.x, node.y), segmentType=kind, smooth=node.smooth, name=node.name
        )
    pen.endPath()


def draw_info(info, pen, *, points=False, contours=True, components=True) -> None:
    """Draw outlines and components without decomposing or changing the model."""
    target = pen
    if not points:
        target = PointToSegmentPen(pen)
    if contours:
        for path in info.paths:
            draw_path_points(path, target)
    if components:
        for component in info.components:
            target.addComponent(component.componentName, component.transform)


class LayerPen:
    """A writing pen supporting both Glyphs point and segment protocols.

    A contour is staged until endPath/closePath, then appended through the
    layer's existing collection route. Components append through that route too.
    """

    def __init__(self, layer):
        self.layer = layer
        self._nodes = None
        self._closed = True
        self._font = None
        self._segments = SegmentToPointPen(proxy(self))

    def __enter__(self):
        """Retain one history scope for all contours/components in this session."""
        return self

    def __exit__(self, *exc):
        self.doneDrawing()

    def __del__(self):
        # Legacy callers do not explicitly finish pens. Prefer doneDrawing()
        # or a with block; finalization only balances a still-owned Undo scope.
        try:
            self.doneDrawing()
        except Exception as error:  # noqa: BLE001 -- finalizers cannot propagate.
            import warnings

            warnings.warn(
                f"LayerPen cleanup failed: {error}", RuntimeWarning, stacklevel=2
            )

    def _append(self, field, value):
        if self._font is None and "_font" in self.layer.__dict__:
            font = self.layer._font
            font._begin_undo("Draw layer")
            self._font = font
        try:
            getattr(self.layer, field).append(value)
        except BaseException:
            self.doneDrawing()
            raise

    def doneDrawing(self):
        """Finish this pen's history step; repeated calls are harmless."""
        if self._font is not None:
            self._font._end_undo()
            self._font = None

    def close(self):
        """Explicitly finish the drawing session, like doneDrawing()."""
        self.doneDrawing()

    def beginPath(self, identifier=None, **kwargs):
        """Begin a staged contour; identifiers have no native counterpart."""
        if self._nodes is not None:
            raise ValueError("A contour is already open")
        self._nodes, self._closed = [], True

    def addPoint(
        self, pt, segmentType=None, smooth=False, name=None, identifier=None, **kwargs
    ):
        """Append a point, preserving quadratic/cubic type and smoothness."""
        from .proxies import GSNode

        if self._nodes is None:
            raise ValueError("beginPath must precede addPoint")
        if segmentType == "move":
            if self._nodes:
                raise ValueError("move is only valid at the start of an open contour")
            self._closed = False
        kind = "line" if segmentType == "move" else segmentType or "offcurve"
        node = GSNode(pt, kind, smooth)
        if name is not None:
            node.name = name
        self._nodes.append(node)

    def endPath(self):
        """Finish a point contour, or the active open segment contour."""
        if self._nodes is None:
            return self._segments.endPath()
        from .proxies import GSPath

        nodes, closed = self._nodes, self._closed
        self._nodes = None
        if nodes:
            self._append("paths", GSPath(nodes, closed=closed))

    def addComponent(self, glyphName, transformation, identifier=None, **kwargs):
        """Append an affine component using the existing backend contract."""
        from .proxies import GSComponent

        component = GSComponent(glyphName)
        from dataclasses import replace

        component._draft = replace(component._draft, transform=tuple(transformation))
        self._append("components", component)

    def moveTo(self, pt):
        """Begin a segment contour."""
        self._segments.moveTo(pt)

    def lineTo(self, pt):
        """Append a straight segment."""
        self._segments.lineTo(pt)

    def curveTo(self, *points):
        """Append cubic control points and endpoint."""
        self._segments.curveTo(*points)

    def qCurveTo(self, *points):
        """Append quadratic controls, including implied closing points."""
        self._segments.qCurveTo(*points)

    def closePath(self):
        """Finish and append a closed segment contour."""
        self._segments.closePath()


def path_info(path) -> PathInfo:
    """Snapshot a draft or live path, including its draft node collection."""
    from dataclasses import replace

    return replace(path._data(), nodes=tuple(node._data() for node in path.nodes))
