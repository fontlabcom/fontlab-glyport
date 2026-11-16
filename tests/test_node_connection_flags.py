# this_file: tests/test_node_connection_flags.py
"""Flag-only connection regression; native acceptance is a separate gate."""

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace as NS
from typing import ClassVar

import pytest
from test_fontlab_backend_lazy import NodeFlags
from test_geometry_cache_updates import assert_updated
from test_geometry_cache_updates import cached as cached_fixture
from test_issue106_round9 import configure_model

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import NodeInfo, PathInfo
from fontlab_glyport.model.fontlab_backend import FontLabBackend


class FlagNode(NodeFlags):
    serial = 90000
    smooth_calls: ClassVar[list] = []

    def __init__(self, point, *, nodeType="on"):
        type(self).serial += 1
        self.id, self.isValid = self.serial, True
        self.x, self.y = point.x(), point.y()
        self.nodeState = {"on": 1, "off": 2, "curve": 4}[nodeType] | 0x8050
        self.name = ""
        self.contour = None

    @property
    def position(self):
        return NS(x=lambda: self.x, y=lambda: self.y)

    def isOff(self):
        return bool(self.nodeState & 2)

    def isCurve(self):
        return bool(self.nodeState & 4)

    @NodeFlags.smooth.setter
    def smooth(self, value):
        self.smooth_calls.append((self.id, value))
        if self.isOff() or self.isCurve():
            return  # Native setSmooth refuses control nodes.
        if value and self.contour is not None:
            for node in self.contour.nodes():
                if node.isCurve() or node.isOff():
                    node.x, node.y = node.x - 33, node.y - 33
        self.nodeState = (self.nodeState & ~8) | (8 if value else 0)


POINTS = [(100, 0), (133, 100), (166, 100), (200, 0)]


def points(contour):
    return [(node.x, node.y) for node in contour.nodes()]


def records(smooth=True, quadratic=False):
    types = ["line", "offcurve", "offcurve", "qcurve" if quadratic else "curve"]
    return tuple(
        NodeInfo("", *p, kind, smooth, True, name=f"n{i}")
        for i, (p, kind) in enumerate(zip(POINTS, types))
    )


@pytest.fixture
def flagged(monkeypatch):
    state = cached_fixture.__wrapped__(monkeypatch)
    old = state.layer.shapes[0].contours[0]
    contour_type = type(old)

    def contour(nodes, *, closed):
        result = contour_type(0)
        result._nodes, result.closed = list(nodes), closed
        for node in result._nodes:
            node.contour = result
        return result

    shape_constructor = state.module.flShape
    state.module.flNode = FlagNode
    state.module.flContour = contour
    state.module.flShape = shape_constructor
    native_nodes = [
        FlagNode(NS(x=lambda x=x: x, y=lambda y=y: y), nodeType=kind)
        for (x, y), kind in zip(POINTS, ["on", "curve", "curve", "on"])
    ]
    state.layer.shapes[0].contours = [contour(native_nodes, closed=False)]
    FlagNode.smooth_calls = []
    return state


def test_double_exposes_the_native_smooth_setter_geometry_and_control_hazards(flagged):
    contour = flagged.layer.shapes[0].contours[0]
    contour.nodes()[0].smooth = True
    assert points(contour) == [(100, 0), (100, 67), (133, 67), (200, 0)]
    control = contour.nodes()[1]
    control.smooth = True
    assert not control.smooth and control.nodeState == 0x8054


@pytest.mark.parametrize("quadratic", [False, True])
@pytest.mark.parametrize("smooth", [False, True])
def test_build_and_replace_use_raw_flags_without_changing_coordinates(
    flagged, smooth, quadratic
):
    backend = flagged.backend
    source = records(smooth, quadratic)
    built = backend._build_path(PathInfo("", source, False)).contours[0]
    assert points(built) == POINTS
    assert [n.nodeState for n in built.nodes()] == [
        (2 if quadratic else 4) | 0x8070 | (8 if smooth else 0)
        if i in (1, 2)
        else 0x8071 | (8 if smooth else 0)
        for i in range(4)
    ]
    layer = flagged.font.glyphs[0].layers[0]
    path = layer.paths[0]
    old = flagged.layer.shapes[0]
    backend.set_path_nodes(path.id, source, False)
    actual = flagged.layer.shapes[0].contours[0]
    assert points(actual) == POINTS
    assert [n.name for n in actual.nodes()] == ["n0", "n1", "n2", "n3"]
    assert [n.nodeState for n in actual.nodes()] == [n.nodeState for n in built.nodes()]
    assert points(old.contours[0]) == POINTS, "history-owned shape stays untouched"
    assert [(n.smooth, n.connection) for n in path.nodes] == [
        (smooth, 100 if smooth else 0)
    ] * 4
    assert FlagNode.smooth_calls == [], "never invoke geometry-affecting smooth"


@pytest.mark.parametrize("connection", [False, True])
def test_live_flags_preserve_geometry_metadata_peers_cow_and_nested_undo(
    flagged, monkeypatch, connection
):
    font = flagged.font
    layer = font.glyphs[0].layers[0]
    path = layer.paths[0]
    original = flagged.layer.shapes[0]
    for i, raw in enumerate(original.contours[0].nodes()):
        raw.name = f"original{i}"
        raw.selected = True
    peer = FontLabBackend(packages=[flagged.package])
    monkeypatch.setattr(peer, "_native", lambda: flagged.module)
    fid = peer._font_id(flagged.package)
    mid = peer._register((fid, "master", "Regular"), flagged.package, fid)
    peer._master_names[mid] = "Regular"
    gid = peer._register((fid, "glyph", 200), flagged.glyph, fid)
    configure_model(
        peer,
        NS(fid=fid, mid=mid, gid=gid, glyph=flagged.glyph, layer=flagged.layer),
        monkeypatch,
    )
    peers = Model(peer)._font(fid).glyphs[0].layers[0].paths[0].nodes
    nodes = list(path.nodes)
    with font.undo_group("Flags"), font.undo_group("Nested"):
        for value in (True, False, True):
            for i, node in enumerate(nodes):
                if connection:
                    node.connection = 100 if value else 0
                else:
                    node.smooth = value
                assert_updated(flagged)
                assert peers[i].smooth is value and peers[i].connection == (
                    100 if value else 0
                )
        assert len(flagged.calls) == 1, "all edits share one pre-change checkpoint"
    current = flagged.layer.shapes[0].contours[0]
    assert points(current) == POINTS
    assert [n.nodeState for n in current.nodes()] == [0x8079, 0x807C, 0x807C, 0x8079]
    assert [n.name for n in current.nodes()] == [f"original{i}" for i in range(4)]
    assert [n.type for n in path.nodes] == ["line", "offcurve", "offcurve", "curve"]
    assert points(original.contours[0]) == POINTS
    assert [n.nodeState for n in original.contours[0].nodes()] == [
        0x8071,
        0x8074,
        0x8074,
        0x8071,
    ]
    assert len(flagged.calls) == 2 and flagged.events[-1][0] == "notify"
    copied = path.copy()
    assert [
        (n.type, n.position, n.name, n.selected, n.connection) for n in copied.nodes
    ] == [(n.type, n.position, n.name, n.selected, n.connection) for n in path.nodes], (
        "detached copies preserve control flags and metadata"
    )
    assert FlagNode.smooth_calls == []


@pytest.mark.parametrize("advanced", [0x1000, 0x2000, 0x3008])
@pytest.mark.parametrize("value", [False, True])
def test_advanced_host_modes_read_as_smooth_and_plain_write_normalizes(
    flagged, advanced, value
):
    native = flagged.layer.shapes[0].contours[0].nodes()[1]
    native.nodeState |= advanced
    node = flagged.font.glyphs[0].layers[0].paths[0].nodes[1]
    assert node.smooth and node.connection == 100, (
        "host smart modes project to plain smooth"
    )
    node.smooth = value
    actual = flagged.backend._object(node.id)
    assert actual.nodeState == (0x805C if value else 0x8054)
    assert (node.smooth, node.connection) == (value, 100 if value else 0)
    assert FlagNode.smooth_calls == []


@pytest.mark.parametrize("route", ["live", "build", "replace"])
def test_unsupported_connection_is_rejected_before_any_mutation(flagged, route):
    layer = flagged.font.glyphs[0].layers[0]
    path = layer.paths[0]
    original = flagged.layer.shapes[0]
    source = list(records())
    source[-1] = replace(source[-1], connection=1)
    with pytest.raises(UnsupportedCapability, match="connection 1"):
        if route == "live":
            path.nodes[-1].connection = 1
        elif route == "build":
            flagged.backend._build_path(PathInfo("", tuple(source), False))
        else:
            flagged.backend.set_path_nodes(path.id, source, False)
    assert (
        flagged.layer.shapes[0] is original and points(original.contours[0]) == POINTS
    )
    assert flagged.calls == [] and flagged.events == [] and FlagNode.smooth_calls == []


@pytest.mark.parametrize("attribute", ["smooth", "connection"])
def test_stale_proxy_fails_before_flags_history_or_geometry_mutation(
    flagged, attribute
):
    layer = flagged.font.glyphs[0].layers[0]
    path = layer.paths[0]
    node = path.nodes[0]
    flagged.backend.set_path_nodes(path.id, records(), False)
    before = list(flagged.events)
    with pytest.raises(StaleNativeObject):
        setattr(node, attribute, True if attribute == "smooth" else 100)
    assert flagged.events == before and FlagNode.smooth_calls == []


def test_singular_path_replacement_and_position_reject_before_mutation(flagged):
    layer = flagged.font.glyphs[0].layers[0]
    path = layer.paths[0]
    original = flagged.layer.shapes[0]
    original.transform.isInvertible = lambda: False
    with pytest.raises(UnsupportedCapability, match="singular"):
        flagged.backend.set_path_nodes(path.id, records(), False)
    with pytest.raises(UnsupportedCapability, match="singular"):
        path.nodes[0].position = (23, 42)
    assert (
        flagged.layer.shapes[0] is original and points(original.contours[0]) == POINTS
    )
    assert not flagged.events and not flagged.calls and not FlagNode.smooth_calls


def test_replacement_maps_to_local_coordinates_and_flags_leave_transforms_alone(
    flagged,
):
    layer = flagged.font.glyphs[0].layers[0]
    path = layer.paths[0]
    shape = flagged.layer.shapes[0]
    inverse = NS(
        map=lambda p: NS(x=lambda: (p.x() - 10) / 2, y=lambda: (p.y() + 7) / 3)
    )
    shape.transform = NS(
        isInvertible=lambda: True,
        inverted=lambda: inverse,
        map=lambda p: NS(x=lambda: p.x() * 2 + 10, y=lambda: p.y() * 3 - 7),
    )
    flagged.backend.set_path_nodes(path.id, records(), False)
    actual = flagged.layer.shapes[0].contours[0]
    assert points(actual) == [(45, 7 / 3), (61.5, 107 / 3), (78, 107 / 3), (95, 7 / 3)]
    assert [(n.x, n.y) for n in path.nodes] == POINTS
    path.nodes[1].smooth = False
    assert points(flagged.layer.shapes[0].contours[0]) == points(actual)
    assert FlagNode.smooth_calls == []


def test_auto_layer_refuses_live_flag_edit_before_clone_or_history(flagged):
    layer = flagged.font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    original = flagged.layer.shapes[0]
    flagged.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability):
        node.connection = 100
    assert (
        flagged.layer.shapes[0] is original and points(original.contours[0]) == POINTS
    )
    assert not flagged.events and not flagged.calls and not FlagNode.smooth_calls


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("connection", [False, True])
def test_repeated_flag_writes_preserve_all_prior_flags_through_native_clones(
    flagged, monkeypatch, grouped, connection
):
    # Five sharp corners joined by cubic handles, matching the native failure's
    # geometry. None is geometrically smooth; checkSmooth clears Smooth/G2.
    coordinates = [
        (66, 133),
        (83, 117),
        (100, 100),
        (133, 100),
        (166, 100),
        (200, 100),
        (200, 133),
        (200, 166),
        (200, 200),
        (167, 200),
        (134, 200),
        (100, 200),
        (83, 183),
        (67, 167),
        (50, 150),
    ]
    data = tuple(
        NodeInfo("", x, y, "curve" if i % 3 == 2 else "offcurve", name=f"node{i}")
        for i, (x, y) in enumerate(coordinates)
    )
    flagged.layer.shapes = [flagged.backend._build_path(PathInfo("", data, True))]
    source = flagged.layer.shapes[0]
    for i, raw in enumerate(source.contours[0].nodes()):
        raw.nodeState = (raw.nodeState & ~0x10) | (0x10 if i == 0 else 0)
        raw.selected = i % 2 == 0
    original_states = [n.nodeState for n in source.contours[0].nodes()]
    clone_type, clone_calls = type(source), []
    plain_clone = clone_type.clone

    def native_clone(shape):
        cloned = plain_clone(shape)
        # flshapedata.cpp cloneCustom clones a contour then calls checkSmooth;
        # flnode.cpp canBeSmooth(true) clears Smooth/G2 at these sharp corners
        # and all controls, even though node.clone initially copies raw state.
        for contour in cloned.contours:
            for node in contour.nodes():
                node.nodeState &= ~0x1008
        clone_calls.append(cloned)
        return cloned

    monkeypatch.setattr(clone_type, "clone", native_clone)
    layer = flagged.font.glyphs[0].layers[0]
    path = layer.paths[0]
    nodes = list(path.nodes)
    tokens = [n.id for n in nodes]
    peer = FontLabBackend(packages=[flagged.package])
    monkeypatch.setattr(peer, "_native", lambda: flagged.module)
    fid = peer._font_id(flagged.package)
    mid = peer._register((fid, "master", "Regular"), flagged.package, fid)
    peer._master_names[mid] = "Regular"
    gid = peer._register((fid, "glyph", 200), flagged.glyph, fid)
    configure_model(
        peer,
        NS(fid=fid, mid=mid, gid=gid, glyph=flagged.glyph, layer=flagged.layer),
        monkeypatch,
    )
    peers = list(Model(peer)._font(fid).glyphs[0].layers[0].paths[0].nodes)
    peer_tokens = [n.id for n in peers]
    expected = [0] * 15
    baseline = [(n.type, n.position, n.name, n.selected) for n in nodes]
    with flagged.font.undo_group("Flags") if grouped else nullcontext():
        for value in (True, False, True):
            for i, node in enumerate(nodes):
                before = flagged.layer.shapes[0]
                before_states = [n.nodeState for n in before.contours[0].nodes()]
                if connection:
                    node.connection = 100 if value else 0
                else:
                    node.smooth = value
                expected[i] = 100 if value else 0
                assert [n.connection for n in nodes] == expected, (
                    "a later ungrouped write must preserve every earlier flag"
                )
                assert [n.connection for n in peers] == expected
                assert [n.id for n in nodes] == tokens
                assert [n.id for n in peers] == peer_tokens
                assert [
                    (n.type, n.position, n.name, n.selected) for n in nodes
                ] == baseline
                assert [flagged.backend._object(n.id).id for n in nodes] == [
                    peer._object(n.id).id for n in peers
                ], "peer tokens follow native-order clones"
                if before is not flagged.layer.shapes[0]:
                    assert [
                        n.nodeState for n in before.contours[0].nodes()
                    ] == before_states
                updates = flagged.events if grouped else flagged.events[:-1]
                assert updates[-4:] == [
                    "layer.changed",
                    "layer.update",
                    "glyph.changed",
                    "glyph.update",
                ]
    assert [n.connection for n in nodes] == [100] * 15
    assert [n.nodeState for n in source.contours[0].nodes()] == original_states
    assert len(clone_calls) == (1 if grouped else 45)
    assert len(flagged.calls) == (2 if grouped else 90)
    assert FlagNode.smooth_calls == []


@pytest.mark.parametrize("staged", [False, True])
def test_clone_preserves_sharp_and_advanced_flags_before_history_attachment(
    flagged, monkeypatch, staged
):
    layer = flagged.font.glyphs[0].layers[0]
    _ = list(layer.paths[0].nodes)  # register all native-order handles
    source = flagged.layer.shapes[0]
    states = [0x8071, 0x9054, 0xA07C, 0xB059]
    for node, state in zip(source.contours[0].nodes(), states):
        node.nodeState = state
    clone_type = type(source)
    plain_clone = clone_type.clone

    def native_clone(shape):
        cloned = plain_clone(shape)
        for contour in cloned.contours:
            for node in contour.nodes():
                # Geometry-derived Smooth can also be added to a sharp source.
                node.nodeState = (node.nodeState & ~0x1008) | (
                    8 if node.nodeState & 1 else 0
                )
        return cloned

    monkeypatch.setattr(clone_type, "clone", native_clone)
    clone = source.clone() if staged else None
    flagged.backend.begin_undo("Clone flags")
    owned = flagged.backend._own_shape(layer.id, source, clone=clone)
    assert [n.nodeState for n in owned.contours[0].nodes()] == states
    assert [n.nodeState for n in source.contours[0].nodes()] == states
    assert points(owned.contours[0]) == POINTS
    flagged.backend._touch_layer(layer.id)
    flagged.backend.end_undo()
    assert len(flagged.calls) == 2
    assert FlagNode.smooth_calls == []


@pytest.mark.parametrize("missing", ["contour", "node"])
def test_staged_clone_arity_mismatch_fails_before_history_or_attachment(
    flagged, missing
):
    layer = flagged.font.glyphs[0].layers[0]
    source = flagged.layer.shapes[0]
    clone = source.clone()
    if missing == "contour":
        clone.contours.clear()
    else:
        clone.contours[0]._nodes.pop()
    before = [n.nodeState for n in source.contours[0].nodes()]
    with pytest.raises(ValueError, match="zip"):
        flagged.backend._own_shape(layer.id, source, clone=clone)
    assert flagged.layer.shapes[0] is source
    assert [n.nodeState for n in source.contours[0].nodes()] == before
    assert points(source.contours[0]) == POINTS
    assert not flagged.events and not flagged.calls
    assert not flagged.backend._owned_shapes
