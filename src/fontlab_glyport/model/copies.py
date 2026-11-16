# this_file: src/fontlab_glyport/model/copies.py
"""Detached geometry snapshots: never traverse model caches or native handles."""

import math
from copy import deepcopy
from dataclasses import replace
from functools import partial

from .backend import LayerInfo
from .proxies import (
    GSAnchor,
    GSComponent,
    GSGlyph,
    GSGuide,
    GSHint,
    GSLayer,
    GSNode,
    GSPath,
    ProxySequence,
    UserData,
    _mapped_positions,
    _unsupported,
)


def detached_copy(source, memo):
    """Capture the native carrier only for an explicitly copied foreground.

    Recursive component/background projections remain value-only. In particular
    deepcopy never follows a backend, source font or native wrapper graph.
    """
    root = "glyport.layer-copy-root" not in memo
    if root:
        memo["glyport.layer-copy-root"] = True
    try:
        result = _detached_copy(source, memo)
        if root and isinstance(result, DetachedLayer):
            from .background import GSBackgroundLayer
            from .layer_attachment import copy_state

            if not isinstance(result, GSBackgroundLayer):
                if isinstance(source, DetachedLayer):
                    if "_copy_snapshot" in source.__dict__:
                        result._copy_snapshot = source._copy_snapshot
                        result._copy_state = source._copy_state
                        result._copy_association = source._copy_association
                else:
                    result._copy_snapshot = source._font._model._backend.snapshot_layer(
                        source.id
                    )
                    result._copy_state = copy_state(result)
                    result._copy_association = source.associatedMasterId
        return result
    finally:
        if root:
            memo.pop("glyport.layer-copy-root")


def _detached_copy(source, memo):
    if id(source) in memo:
        return memo[id(source)]
    if isinstance(source, GSPath):
        result = GSPath([], source.closed)
        result._draft = replace(
            result._draft, attributes=deepcopy(source._data().attributes, memo)
        )
        memo[id(source)] = result
        result._draft_nodes = [deepcopy(n, memo) for n in source.nodes]
    elif isinstance(source, (GSNode, GSAnchor, GSComponent, GSGuide)):
        result = type(source).__new__(type(source))
        # Editor selection changes need not advance the font's Undo history.
        selected = source.selected if isinstance(source, GSNode) else None
        data = source._data()
        result._draft = (
            replace(data, id="", selected=selected)
            if isinstance(source, GSNode)
            else replace(data, id="")
        )
    elif isinstance(source, GSLayer):
        from .background import DetachedBackgroundLayer, GSBackgroundLayer

        if isinstance(source, DetachedLayer):
            cls = type(source)
        elif isinstance(source, GSBackgroundLayer):
            cls = DetachedBackgroundLayer
        else:
            cls = DetachedLayer
        result = cls.__new__(cls)
        DetachedLayer.__init__(result, source, memo)
    elif isinstance(source, GSGlyph):
        result = DetachedGlyph(source, memo)
    else:
        _unsupported(f"{type(source).__name__}.copy")
    memo[id(source)] = result
    return result


class DetachedLayer(GSLayer):
    """An unattached GSLayer retaining its shape order, anchors and user data."""

    def __init__(self, source=None, memo=None):
        if source is None:
            self._draft = LayerInfo("", "", 0)
            self._name, self._glyph = "", None
            self._spacing_italic_angle = 0.0
            self._shapes, self._anchors, self._guides = [], [], []
            self._hints = []
            self._attributes = {}
            self._user_data = {}
            self._component_layers = {}
            self._metrics_keys = {}
            self._background = None
            return
        memo[id(source)] = self
        self._draft = replace(source._data(), id="")
        self._name = source.name
        self._spacing_italic_angle = source.italicAngle
        self._spacing_slant_height = source.slantHeight
        if isinstance(source, DetachedLayer):
            for key in ("_master_owner", "_master_name"):
                if key in source.__dict__:
                    self.__dict__[key] = source.__dict__[key]
        else:
            self._master_owner = source._font._copy_owner
            self._master_name = source.master.name
        self._associated_master_id = source.associatedMasterId
        self._metrics_keys = {
            side: getattr(source, side + "MetricsKey")
            for side in ("left", "right", "width")
        }
        self._attributes = (
            deepcopy(dict(source.attributes), memo)
            if isinstance(source, DetachedLayer)
            else {}
        )
        self._glyph = None
        self._shapes = deepcopy(list(source.shapes), memo)
        self._anchors = deepcopy(list(source.anchors), memo)
        self._guides = deepcopy(list(source.guides), memo)
        self._hints = [hint.copy() for hint in source.hints]
        self._user_data = deepcopy(dict(source.userData), memo)
        self._component_layers = self._snapshot_components(source, memo)
        from .background import GSBackgroundLayer

        self._background = (
            None
            if isinstance(source, GSBackgroundLayer)
            else deepcopy(source.background, memo)
        )

    italicAngle = property(lambda self: self._spacing_italic_angle)
    slantHeight = property(lambda self: self.__dict__.get("_spacing_slant_height", 0.0))

    @property
    def associatedMasterId(self):
        return self.__dict__.get("_associated_master_id", self._draft.masterId)

    @associatedMasterId.setter
    def associatedMasterId(self, value):
        if not isinstance(value, str):
            raise TypeError("associatedMasterId must be a string")
        self._associated_master_id = value

    @staticmethod
    def _snapshot_components(source, memo):
        if isinstance(source, DetachedLayer):
            return deepcopy(source._component_layers, memo)
        # Snapshot only referenced component layers; copies never retain the
        # source font. The memo terminates recursive component references.
        layers = {}
        for component in source.components:
            name = component.componentName
            glyph = source._font.glyphs[name]
            layer = None if glyph is None else glyph.layers[source.layerId]
            if layer is None and glyph is not None:
                layer = glyph.layers[source.associatedMasterId]
            layers[name] = None if layer is None else deepcopy(layer, memo)
        return layers

    @property
    def background(self):
        from .background import GSBackgroundLayer

        if self._background is None:
            self._background = GSBackgroundLayer()
        self._background._foreground = self
        self._background._glyph = self.parent
        return self._background

    @background.setter
    def background(self, value):
        from .background import DetachedBackgroundLayer

        if value is not None and not isinstance(value, GSLayer):
            raise TypeError("background must be a GSLayer or None")
        self._background = None if value is None else DetachedBackgroundLayer(value, {})

    @property
    def hints(self):
        def append(value):
            if not isinstance(value, GSHint):
                raise TypeError("Expected GSHint")
            self._hints.append(value.copy())

        return ProxySequence(
            lambda: list(self._hints), append=append, remove=self._hints.remove
        )

    @hints.setter
    def hints(self, values):
        values = list(values or ())
        if not all(isinstance(value, GSHint) for value in values):
            raise TypeError("Expected GSHint values")
        self._hints = [value.copy() for value in values]

    def _metrics_key(self, side):
        return self._metrics_keys.get(side) or None

    def _set_metrics_key(self, side, value):
        if value is not None and not isinstance(value, str):
            raise TypeError("A metrics key must be a string or None")
        self._metrics_keys[side] = value

    def _check(self):
        pass

    def _data(self):
        return replace(
            self._draft,
            paths=tuple(p._data() for p in self.paths),
            components=tuple(c._data() for c in self.components),
            anchors=tuple(a._data() for a in self._anchors),
            guides=tuple(g._data() for g in self._guides),
        )

    id = property(lambda self: "")

    @property
    def parent(self):
        return self._glyph

    @parent.setter
    def parent(self, value):
        if value is not None and not isinstance(value, GSGlyph):
            raise TypeError("parent must be a GSGlyph or None")
        self._glyph = value

    name = property(
        lambda self: self._name, lambda self, value: setattr(self, "_name", str(value))
    )
    width = property(
        lambda self: self._draft.width,
        lambda self, value: setattr(
            self, "_draft", replace(self._draft, width=float(value))
        ),
    )

    @property
    def attributes(self):
        return UserData(
            lambda: self._attributes, lambda value: setattr(self, "_attributes", value)
        )

    userData = property(lambda self: self._user_data)

    @property
    def shapes(self):
        return ProxySequence(
            lambda: list(self._shapes),
            append=self._shapes.append,
            remove=self._shapes.remove,
        )

    @shapes.setter
    def shapes(self, values):
        self._shapes = list(values or ())

    @property
    def paths(self):
        return ProxySequence(
            lambda: [s for s in self._shapes if isinstance(s, GSPath)],
            append=self._shapes.append,
            remove=self._shapes.remove,
        )

    @paths.setter
    def paths(self, values):
        self._shapes = [s for s in self._shapes if not isinstance(s, GSPath)] + list(
            values or ()
        )

    @property
    def components(self):
        return ProxySequence(
            lambda: [s for s in self._shapes if isinstance(s, GSComponent)],
            append=self._shapes.append,
            remove=self._shapes.remove,
        )

    @components.setter
    def components(self, values):
        self._shapes = [
            s for s in self._shapes if not isinstance(s, GSComponent)
        ] + list(values or ())

    @property
    def anchors(self):
        from .anchor_assignment import assign_anchor

        return ProxySequence(
            lambda: list(self._anchors),
            lambda a: (a.name,),
            append=self._anchors.append,
            remove=self._anchors.remove,
            set_item=partial(assign_anchor, self),
        )

    @anchors.setter
    def anchors(self, values):
        self._anchors = list(values or ())

    @property
    def guides(self):
        return ProxySequence(
            lambda: list(self._guides),
            append=self._guides.append,
            remove=self._guides.remove,
        )

    @guides.setter
    def guides(self, values):
        self._guides = list(values or ())

    def applyTransform(self, transform):
        from ..drawing.context import concat

        a, b, c, d, e, f = map(float, transform)
        values = a, b, c, d, e, f
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Affine transform values must be finite")
        points = [n for p in self.paths for n in p.nodes] + list(self.anchors)
        moves = _mapped_positions(points, values)
        transforms, components = {}, []
        for component in self.components:
            key = id(component)
            previous = transforms[key] if key in transforms else component.transform  # noqa: SIM401 - fallback property must stay lazy when the key exists
            mapped = concat(previous, values)
            transforms[key] = mapped
            components.append((component, replace(component._draft, transform=mapped)))
        for point, position in moves:
            point.position = position
        for component, draft in components:
            component._draft = draft

    def _bounds(self):
        from .detached_geometry import layer_bounds

        return layer_bounds(self)

    @GSLayer.LSB.setter
    def LSB(self, value):
        bounds = self._spacing_bounds()
        if bounds is None:
            float(value)
            return
        delta = float(value) - bounds[0]
        self.applyTransform((1, 0, 0, 1, delta, 0))
        self.width += delta

    @GSLayer.RSB.setter
    def RSB(self, value):
        bounds = self._spacing_bounds()
        if bounds is None:
            self.width = float(value)
            return
        self.width = bounds[0] + bounds[2] + float(value)

    def clear(self):
        self._shapes, self._anchors, self._hints = [], [], []

    def glyphMetrics(self):
        _unsupported("DetachedLayer.glyphMetrics")

    def decomposeComponents(self):
        """Expand snapshotted outlines in shape order; keep this layer's anchors."""
        from .detached_geometry import decomposed_paths

        if self.components:
            self._shapes = decomposed_paths(self, "decomposeComponents")

    def decomposeCorners(self):
        """Native FontLab PostScript hints contain no Glyphs corner components."""

    def fastBounds(self):
        return self.bounds

    def copyDecomposedLayer(self):
        result = self.copy()
        result.decomposeComponents()
        return result

    def removeOverlap(self):
        from .detached_geometry import remove_overlap

        if self._shapes:
            self._shapes = remove_overlap(self)


class DetachedGlyph(GSGlyph):
    def __init__(self, source, memo):
        memo[id(source)] = self
        self._draft = replace(source._data(), id="")
        from .glyph_metadata import FIELDS

        self._case_metadata = {}
        for field, key, flag in FIELDS:
            self._case_metadata[key] = getattr(source, field)
            self._case_metadata[flag] = source._case_state().get(flag, False)
        self._glyph_metrics_keys = {
            side: getattr(source, side + "MetricsKey")
            for side in ("left", "right", "width")
        }
        if "_draft" in source.__dict__ and not isinstance(source, DetachedGlyph):
            # A newly authored glyph has no attached geometry or native lib.
            self._layers, self._user_data = [], {}
        else:
            self._layers = deepcopy(list(source.layers), memo)
            self._user_data = deepcopy(dict(source.userData), memo)
        for layer in self._layers:
            layer._glyph = self

    id = property(lambda self: "")
    parent = property(lambda self: None)
    userData = property(lambda self: self._user_data)
    layers = property(
        lambda self: ProxySequence(
            lambda: list(self._layers), lambda layer: (layer.layerId,)
        )
    )

    def _check(self):
        pass
