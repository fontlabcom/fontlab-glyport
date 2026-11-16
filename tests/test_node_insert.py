# this_file: tests/test_node_insert.py
"""Insertion contracts; native and saved-original acceptance belong to the parent."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import configure_model
from test_node_connection_flags import flagged as flagged_fixture

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend
from fontlab_glyport.model.proxies import ProxySequence


@pytest.fixture
def insertion(monkeypatch):
    state = flagged_fixture.__wrapped__(monkeypatch)
    contour = state.layer.shapes[0].contours[0]

    def insert(self, index, node):
        assert 0 <= index <= len(self._nodes)
        self._nodes.insert(index, node)
        node.contour = self

    def remove_one(self, node):
        self._nodes.remove(node)
        node.contour = None

    monkeypatch.setattr(type(contour), "insert", insert, raising=False)
    monkeypatch.setattr(type(contour), "removeOne", remove_one, raising=False)
    return state


def path_of(state):
    return state.font.glyphs[0].layers[0].paths[0]


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize(
    "index,expected",
    [
        (0, [9, 1, 2, 3]),
        (1, [1, 9, 2, 3]),
        (3, [1, 2, 3, 9]),
        (-1, [1, 2, 9, 3]),
        (-3, [9, 1, 2, 3]),
    ],
)
def test_insert_literal_order_attachment_and_retained_nodes(
    insertion, live, closed, index, expected
):
    path = GSPath([GSNode((i, i * 10)) for i in (1, 2, 3)], closed)
    if live:
        layer = insertion.font.glyphs[0].layers[0]
        path = layer.paths.append(path)
    old = list(path.nodes)
    ids = [n.id for n in old] if live else None
    added = GSNode((9, 90), smooth=True)
    added.name, added.selected = "added", True
    assert path.nodes.insert(index, added) is None
    assert [n.x for n in path.nodes] == expected
    assert [n.y for n in path.nodes] == [i * 10 for i in expected]
    assert path.nodes[expected.index(9)] is added
    assert added.parent is path and added.index == expected.index(9)
    assert added.name == "added" and added.selected and added.connection == 100
    assert [n.id for n in old] == ids if live else all(n.parent is path for n in old)
    assert [n.x for n in old] == [1, 2, 3]
    if live:
        added.x = 10
        assert path.nodes[expected.index(9)].x == 10


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("live", [False, True])
def test_empty_insert_then_append_attaches_exact_handles(insertion, live, closed):
    path = GSPath([], closed)
    if live:
        path = insertion.font.glyphs[0].layers[0].paths.append(path)
    first, second = GSNode((1, 2)), GSNode((3, 4))
    path.nodes.insert(0, first)
    assert path.nodes.append(second) is None
    assert list(path.nodes) == [first, second]
    assert first.parent is path and second.parent is path
    assert (first.index, second.index) == (0, 1)


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize(
    "index,error",
    [
        (4, IndexError),
        (-4, IndexError),
        (1.5, TypeError),
        ("1", TypeError),
        (None, TypeError),
    ],
)
def test_invalid_indices_never_mutate(insertion, live, index, error):
    path = GSPath([GSNode((i, 0)) for i in range(3)])
    if live:
        path = insertion.font.glyphs[0].layers[0].paths.append(path)
    before = list(path.nodes)
    calls = len(insertion.calls)
    with pytest.raises(error):
        path.nodes.insert(index, GSNode())
    assert list(path.nodes) == before and len(insertion.calls) == calls


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("bad", ["object", "nan", "inf", "connection", "parented"])
def test_invalid_inputs_do_not_clone_notify_or_attach(insertion, live, bad):
    path = path_of(insertion) if live else GSPath([GSNode((1, 2))])
    node = GSNode((9, 10))
    if bad == "object":
        node = object()
    elif bad in {"nan", "inf"}:
        node.x = float(bad)
    elif bad == "connection":
        node.connection = 1
    else:
        GSPath([node])
    before = list(path.nodes)
    original = insertion.layer.shapes[0]
    with pytest.raises((TypeError, ValueError, UnsupportedCapability)):
        path.nodes.insert(0, node)
    assert list(path.nodes) == before
    assert insertion.layer.shapes[0] is original and not insertion.calls


def test_retained_selected_nodes_sequential_controls_peers_cow_and_undo(
    insertion, monkeypatch
):
    path = path_of(insertion)
    peer = FontLabBackend(packages=[insertion.package])
    monkeypatch.setattr(peer, "_native", lambda: insertion.module)
    fid = peer._font_id(insertion.package)
    mid = peer._register((fid, "master", "Regular"), insertion.package, fid)
    peer._master_names[mid] = "Regular"
    gid = peer._register((fid, "glyph", 200), insertion.glyph, fid)
    configure_model(
        peer,
        NS(fid=fid, mid=mid, gid=gid, glyph=insertion.glyph, layer=insertion.layer),
        monkeypatch,
    )
    peerpath = Model(peer)._font(fid).glyphs[0].layers[0].paths[0]
    old, peers = list(path.nodes), list(peerpath.nodes)
    tokens, peer_tokens = [n.id for n in old], [n.id for n in peers]
    for node in old:
        node.selected = True
    original = insertion.layer.shapes[0]
    coords = [(n.x, n.y) for n in original.contours[0].nodes()]
    with insertion.font.undo_group("Insert nodes"):
        for selected in (old[0], old[-1]):
            for offset, kind in enumerate(("offcurve", "offcurve", "curve"), 1):
                new = GSNode((selected.x + offset, selected.y), kind, True)
                new.selected = True
                path.nodes.insert(selected.index + offset, new)
                assert new.parent is path and new.selected
                assert len(insertion.calls) == 1
                assert [n.id for n in old] == tokens
                assert [n.id for n in peers] == peer_tokens
                assert [(n.x, n.y) for n in old] == [
                    (100, 0),
                    (133, 100),
                    (166, 100),
                    (200, 0),
                ]
                assert [n.x for n in peerpath.nodes] == [n.x for n in path.nodes]
        assert [n.x for n in path.nodes] == [
            100,
            101,
            102,
            103,
            133,
            166,
            200,
            201,
            202,
            203,
        ]
    assert len(insertion.calls) == 2
    assert [(n.x, n.y) for n in original.contours[0].nodes()] == coords
    assert all(n.selected for n in old)
    assert [
        n.connection for n in path.nodes if n.x in {101, 102, 103, 201, 202, 203}
    ] == [100] * 6


def test_transform_maps_only_new_node_and_preserves_metadata(insertion):
    path = path_of(insertion)
    shape = insertion.layer.shapes[0]
    shape.transform = NS(
        isInvertible=lambda: True,
        inverted=lambda: NS(
            map=lambda p: NS(x=lambda: (p.x() - 10) / 2, y=lambda: (p.y() + 7) / 3)
        ),
        map=lambda p: NS(x=lambda: p.x() * 2 + 10, y=lambda: p.y() * 3 - 7),
    )
    before = [(n.x, n.y, n.nodeState) for n in shape.contours[0].nodes()]
    added = GSNode((30, 53), smooth=True)
    path.nodes.insert(1, added)
    raw = insertion.backend._object(added.id)
    assert (raw.x, raw.y) == (10, 20)
    assert added.position == (30, 53)
    assert [
        (n.x, n.y, n.nodeState)
        for n in insertion.layer.shapes[0].contours[0].nodes()
        if n.id != raw.id
    ] == before


def test_singular_and_auto_layers_refuse_before_mutation(insertion):
    path = path_of(insertion)
    source = insertion.layer.shapes[0]
    source.transform.isInvertible = lambda: False
    with pytest.raises(UnsupportedCapability, match="singular"):
        path.nodes.insert(0, GSNode())
    source.transform.isInvertible = lambda: True
    insertion.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability):
        path.nodes.insert(0, GSNode())
    assert insertion.layer.shapes[0] is source and not insertion.calls


def test_failed_update_keeps_attached_handle_and_existing_tokens_for_retry(insertion):
    path = path_of(insertion)
    retained = list(path.nodes)
    added = GSNode((1, 2))
    insertion.backend.begin_undo("Insert failure")
    insertion.fail = "layer.update"
    with pytest.raises(RuntimeError, match="injected"):
        path.nodes.insert(1, added)
    assert added.parent is path and added.index == 1 and path.nodes[1] is added
    assert [n.x for n in retained] == [100, 133, 166, 200]
    with pytest.raises(RuntimeError):
        insertion.backend.end_undo()
    assert len(insertion.calls) == 1 and insertion.backend._pending_layer_updates
    insertion.fail = None
    insertion.backend.end_undo()
    assert len(insertion.calls) == 2 and not insertion.backend._pending_layer_updates
    added.x = 5
    assert path.nodes[1] is added and added.x == 5


def test_foreign_live_and_stale_handles_refused(insertion):
    path = path_of(insertion)
    original = insertion.layer.shapes[0]
    with pytest.raises(UnsupportedCapability, match="copy"):
        path.nodes.insert(0, path.nodes[0])
    foreign = Model(FakeBackend())._font("font").glyphs[0].layers[0].paths[0].nodes[0]
    with pytest.raises(UnsupportedCapability, match="copy"):
        path.nodes.append(foreign)
    node = path.nodes[0]
    insertion.backend.set_path_nodes(
        path.id, [replace(n._data(), id="") for n in path.nodes], False
    )
    with pytest.raises(StaleNativeObject):
        path.nodes.insert(0, node)
    assert original is not insertion.layer.shapes[0]


def test_fake_backend_insert_preserves_old_token_and_selected_copy():
    backend = FakeBackend()
    path = Model(backend)._font("font").glyphs[0].layers[0].paths[0]
    original = path.nodes[0]
    original.selected = True
    copied = original.copy()
    path.nodes.append(copied)
    assert path.nodes[0] is original and original.id == "node"
    assert path.nodes[1] is copied and copied.selected
    assert copied.parent is path and copied.index == 1


def test_unsupported_collections_refuse_insert_explicitly():
    with pytest.raises(UnsupportedCapability, match="collection.insert"):
        ProxySequence(list).insert(0, GSNode())


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_wrapper_bounds_bool_and_empty_negative_indices(insertion, closed, empty):
    path = GSPath([] if empty else [GSNode((1, 2))], closed)
    path = insertion.font.glyphs[0].layers[0].paths.append(path)
    before = list(path.nodes)
    with pytest.raises(IndexError):
        path.nodes.insert(-len(before) - 1, GSNode())
    path.nodes.insert(bool(before), GSNode((3, 4)))
    assert [n.position for n in path.nodes] == ([(3, 4)] if empty else [(1, 2), (3, 4)])


@pytest.mark.parametrize(
    "failure",
    [
        "layer.changed",
        "layer.update",
        "glyph.changed",
        "glyph.update",
        "layer.update:false",
    ],
)
@pytest.mark.parametrize("grouped", [False, True])
def test_each_update_failure_keeps_tokens_attachment_and_publication_barrier(
    insertion, failure, grouped
):
    from fontlab_glyport.errors import NativeOperationError

    path = path_of(insertion)
    originals = list(path.nodes)
    tokens = [node.id for node in originals]
    added = GSNode((500, 600))
    assert insertion.backend.layer_bounds(path.parent.id) == (100, 0, 100, 100)
    if grouped:
        insertion.backend.begin_undo("Retry insertion")
    insertion.fail = failure
    with pytest.raises((RuntimeError, NativeOperationError)):
        path.nodes.insert(2, added)
    assert path.nodes[2] is added and added.parent is path and added.index == 2
    assert [node.id for node in originals] == tokens
    assert len(insertion.calls) == 1 and insertion.backend._pending_layer_updates
    if grouped:
        with pytest.raises((RuntimeError, NativeOperationError)):
            insertion.backend.end_undo()
    else:
        with pytest.raises(RuntimeError, match="[Uu]npublished"):
            insertion.backend.begin_undo("Must not publish")
    assert len(insertion.calls) == 1
    insertion.fail = None
    if grouped:
        insertion.backend.end_undo()
    else:
        added.x = 501
    assert len(insertion.calls) == 2 and not insertion.backend._pending_layer_updates
    assert insertion.backend.layer_bounds(path.parent.id) == (
        100,
        0,
        400 if grouped else 401,
        600,
    )


def test_native_ids_survive_insert_after_first_cow_and_raw_clone_flags(
    insertion, monkeypatch
):
    path = path_of(insertion)
    original = insertion.layer.shapes[0]
    raw = original.contours[0].nodes()
    states = [0x8071, 0x9054, 0xA07C, 0xB059]
    for node, state in zip(raw, states):
        node.nodeState = state
    shape_type, clone = type(original), type(original).clone

    def native_clone(shape):
        copied = clone(shape)
        for contour in copied.contours:
            for node in contour.nodes():
                node.nodeState &= ~0x3008
        return copied

    monkeypatch.setattr(shape_type, "clone", native_clone)
    old = list(path.nodes)
    with insertion.font.undo_group("Raw insertion"):
        path.nodes.insert(1, GSNode((123, 456)))
        native_ids = [insertion.backend._object(n.id).id for n in old]
        native_path_id = insertion.backend._object(path.id).id
        native_shape_id = insertion.layer.shapes[0].id
        path.nodes.insert(3, GSNode((789, 987)))
        assert [insertion.backend._object(n.id).id for n in old] == native_ids
        assert insertion.backend._object(path.id).id == native_path_id
        assert insertion.layer.shapes[0].id == native_shape_id
        assert [insertion.backend._object(n.id).nodeState for n in old] == states
    assert [n.nodeState for n in original.contours[0].nodes()] == states


def test_other_paths_masters_fonts_and_layer_metadata_unchanged():
    from fontlab_glyport.model.backend import (
        GlyphInfo,
        LayerInfo,
        MasterInfo,
        NodeInfo,
        PathInfo,
    )

    backend = FakeBackend()
    backend.fonts["other-font"] = replace(backend.fonts["font"], id="other-font")
    backend.glyph_lists["other-font"] = (GlyphInfo("other-glyph", "B", ()),)
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
    )
    backend.layers["glyph", "bold"] = LayerInfo(
        "bold-layer",
        "bold",
        900,
        (PathInfo("bold-path", (NodeInfo("bold-node", 2, 3),)),),
    )
    backend.layers["other-glyph", "master"] = LayerInfo(
        "other-layer",
        "master",
        1000,
        (PathInfo("other-path", (NodeInfo("other-node", 4, 5),)),),
    )
    layer = backend.layers["glyph", "master"]
    backend.layers["glyph", "master"] = replace(
        layer,
        paths=(
            *layer.paths,
            PathInfo("sentinel-path", (NodeInfo("sentinel-node", 8, 9),)),
        ),
        shape_ids=(*layer.shape_ids, "sentinel-path"),
    )
    before = deepcopy(dict(backend.layers))
    path = Model(backend)._font("font").glyphs[0].layers[0].paths[0]
    path.nodes.append(GSNode((30, 40)))
    assert backend.layers["glyph", "bold"] == before["glyph", "bold"]
    assert backend.layers["other-glyph", "master"] == before["other-glyph", "master"]
    assert (
        backend.layers["glyph", "master"].paths[1] == before["glyph", "master"].paths[1]
    )
    assert (
        replace(
            backend.layers["glyph", "master"], paths=before["glyph", "master"].paths
        )
        == before["glyph", "master"]
    )


def test_callback_failure_still_records_actual_insertion(insertion):
    from fontlab_glyport.model.backend import NodeInfo

    path = path_of(insertion)
    attached = []

    def fail(token):
        attached.append(token)
        raise RuntimeError("attachment callback")

    with pytest.raises(RuntimeError, match="attachment callback"):
        insertion.backend.insert_path_node(
            path.id, 1, NodeInfo("", 500, 600), on_attach=fail
        )
    assert path.nodes[1].id == attached[0]
    assert path.nodes[1].position == (500, 600)
    assert len(insertion.calls) == 2 and not insertion.backend._pending_layer_updates


def test_stale_target_path_refuses_before_new_node_attachment(insertion):
    layer = insertion.font.glyphs[0].layers[0]
    path = layer.paths[0]
    layer.paths.remove(path)
    added = GSNode()
    calls = len(insertion.calls)
    with pytest.raises(StaleNativeObject):
        path.nodes.append(added)
    assert added.parent is None and len(insertion.calls) == calls


@pytest.mark.parametrize("live", [False, True])
def test_explicit_backend_connection_overrides_redundant_smooth(insertion, live):
    from fontlab_glyport.model.backend import NodeInfo

    backend = insertion.backend if live else FakeBackend()
    path = (
        path_of(insertion)
        if live
        else Model(backend)._font("font").glyphs[0].layers[0].paths[0]
    )
    backend.insert_path_node(
        path.id, 0, NodeInfo("", 20, 30, smooth=False, connection=100)
    )
    assert path.nodes[0].connection == 100


def test_nonfinite_inverse_coordinates_fail_before_clone(insertion):
    path = path_of(insertion)
    shape = insertion.layer.shapes[0]
    shape.transform.inverted = lambda: NS(
        map=lambda p: NS(x=lambda: float("inf"), y=lambda: 0)
    )
    added = GSNode((1, 2))
    with pytest.raises(ValueError, match="finite"):
        path.nodes.insert(1, added)
    assert insertion.layer.shapes[0] is shape and not insertion.calls
    assert added.parent is None


@pytest.mark.parametrize("length", [1, 2, 5])
@pytest.mark.parametrize("grouped", [False, True])
def test_closed_control_control_on_appends_keep_exact_order_and_identity(
    insertion, length, grouped
):
    from contextlib import nullcontext

    path = (
        insertion.font.glyphs[0]
        .layers[0]
        .paths.append(GSPath([GSNode((i, i * 10)) for i in range(1, length + 1)]))
    )
    original = list(path.nodes)
    for node in original:
        node.selected = True
    tokens = [n.id for n in original]
    inserted = []
    scope = insertion.font.undo_group("Closed controls") if grouped else nullcontext()
    with scope:
        for x, kind in zip((10, 20, 30), ("offcurve", "offcurve", "curve")):
            node = GSNode((x, 100), kind, True)
            node.selected = True
            path.nodes.append(node)
            inserted.append(node)
            assert list(path.nodes) == original + inserted
            assert [n.position for n in path.nodes] == [
                (i, i * 10) for i in range(1, length + 1)
            ] + [(n, 100) for n in (10, 20, 30)[: len(inserted)]]
            assert [n.id for n in original] == tokens
            assert all(n.parent is path and n.selected for n in original + inserted)
            assert [n.type for n in inserted] == ["offcurve"] * min(
                2, len(inserted)
            ) + (["curve"] if len(inserted) == 3 else [])
            assert [n.connection for n in inserted] == [100] * len(inserted)
        assert [n.type for n in path.nodes][-3:] == ["offcurve", "offcurve", "curve"]


def test_native_closed_append_preserves_hint_objects_and_raw_node_targets(insertion):
    path = (
        insertion.font.glyphs[0]
        .layers[0]
        .paths.append(GSPath([GSNode((1, 2)), GSNode((3, 4)), GSNode((5, 6))]))
    )
    with insertion.font.undo_group("Hint handles"):
        path.nodes.insert(1, GSNode((7, 8)))  # establish owned COW shape first
        nodes = list(path.nodes)
        native = [insertion.backend._object(n.id) for n in nodes]
        targets = [NS(originNode=native[-1], targetNode=native[0])]
        insertion.layer.hintTargets = targets
        before = [(n.id, n.x, n.y, n.nodeState, n.selected) for n in native]
        for kind in ("offcurve", "offcurve", "curve"):
            path.nodes.append(GSNode((9, 10), kind))
            assert [(n.id, n.x, n.y, n.nodeState, n.selected) for n in native] == before
            assert all(
                insertion.backend._object(p.id) is n for p, n in zip(nodes, native)
            )
            assert insertion.layer.hintTargets is targets
            assert (
                targets[0].originNode is native[-1]
                and targets[0].targetNode is native[0]
            )
