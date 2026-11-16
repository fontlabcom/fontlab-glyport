# this_file: tests/test_geometry_cache_updates.py
"""Write-boundary cache contracts using native-shaped doubles, never FontLab."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import configure_model
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.errors import (
    NativeOperationError,
    StaleNativeObject,
    UnsupportedCapability,
)
from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import NodeInfo, PathInfo
from fontlab_glyport.model.fontlab_backend import FontLabBackend


class CachedRect:
    def __init__(self, values):
        self.values = values

    def isNull(self):
        return self.values is None

    def x(self):
        return self.values[0]

    def y(self):
        return self.values[1]

    def width(self):
        return self.values[2]

    def height(self):
        return self.values[3]


@pytest.fixture
def cached(monkeypatch):
    state = native_fixture.__wrapped__(monkeypatch)
    contour = state.layer.shapes[0].contours[0]
    node_type = type(contour.nodes()[0])
    contour._nodes = [node_type(10), node_type(30)]
    contour._nodes[0].y, contour._nodes[1].y = 20, 40
    state.layer.shapes[0].contours = [contour]
    monkeypatch.setattr(
        type(contour),
        "assign",
        lambda self, nodes: setattr(self, "_nodes", list(nodes)),
        raising=False,
    )
    state.events, state.cache = [], None
    state.fail = None

    def bounds(layer):
        if state.cache is None:
            points = [
                shape.transform.map(node.position)
                for shape in layer.shapes
                for path in shape.contours
                for node in path.nodes()
            ]
            if not points:
                return CachedRect(None)
            xs, ys = [p.x() for p in points], [p.y() for p in points]
            state.cache = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        return CachedRect(state.cache)

    def event(name):
        state.events.append(name)
        if state.fail == name:
            raise RuntimeError(f"injected {name}")
        if state.fail == name + ":false":
            return False
        if name == "layer.update":
            state.cache = None
        return True

    monkeypatch.setattr(
        type(state.layer), "boundingBox", property(bounds), raising=False
    )
    for kind, item in (("layer", state.layer), ("glyph", state.glyph)):
        item.changed = lambda kind=kind: event(f"{kind}.changed")
        item.update = lambda kind=kind: event(f"{kind}.update")

    def notify(name, items, deep):
        state.events.append(("notify", name, tuple(item.id for item in items), deep))
        state.calls.append((name, items, deep))

    state.module.flItems = lambda: NS(notifyChangesApplied=notify)
    return state


def assert_updated(state):
    assert state.events[-4:] == [
        "layer.changed",
        "layer.update",
        "glyph.changed",
        "glyph.update",
    ], "cache updates must finish at the write boundary"


def test_replacement_then_node_edit_refreshes_warmed_bounds_inside_nested_undo(cached):
    b, font = cached.backend, cached.font
    layer = font.glyphs[0].layers[0]
    path = layer.paths[0]
    original = cached.layer.shapes[0]
    assert b.layer_bounds(layer.id) == (10, 20, 20, 20)
    font.disableUpdateInterface()
    with font.undo_group("Outer geometry"), font.undo_group("Inner geometry"):
        b.set_path_nodes(
            path.id, (NodeInfo("", 100, 100), NodeInfo("", 200, 10000)), False
        )
        assert b.layer_bounds(layer.id) == (100, 100, 100, 9900), (
            "replacement must invalidate already-warm native bounds"
        )
        assert_updated(cached)
        for node in path.nodes:
            node.x += 37
            assert_updated(cached)
        assert b.layer_bounds(layer.id) == (137, 100, 100, 9900), (
            "node edits must refresh bounds before Undo publication"
        )
        assert [(n.x, n.y) for n in original.contours[0].nodes()] == [
            (10, 20),
            (30, 40),
        ], "history-owned geometry must remain unchanged"
    font.enableUpdateInterface()
    notes = [event for event in cached.events if isinstance(event, tuple)]
    assert (
        notes
        == [("notify", "Outer geometry", (cached.layer.id, cached.glyph.id), True)] * 2
    ), "nested edits keep one pre-change and one final notification"
    assert cached.events[-1] == notes[-1], (
        "final notification follows all native cache updates"
    )
    before = list(cached.events)
    assert b.layer_bounds(layer.id) == (137, 100, 100, 9900)
    assert cached.events == before, "bounds reads must never update or notify"


def test_append_remove_and_layer_transform_refresh_bounds_before_publication(
    cached, monkeypatch
):
    b, lid = cached.backend, cached.lid
    assert b.layer_bounds(lid) == (10, 20, 20, 20)
    b.begin_undo("Geometry")
    added = b.append_path(
        lid, PathInfo("", (NodeInfo("", 100, 200), NodeInfo("", 200, 300)))
    )
    assert_updated(cached)
    assert b.layer_bounds(lid) == (10, 20, 190, 280)
    b.remove_path(lid, added)
    assert_updated(cached)
    assert b.layer_bounds(lid) == (10, 20, 20, 20)
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=lambda *v: v),
    )

    def transform(matrix):
        for shape in cached.layer.shapes:
            for path in shape.contours:
                for node in path.nodes():
                    node.x += matrix[4]
                    node.y += matrix[5]

    cached.layer.applyTransform = transform
    b.transform_layer(lid, (1, 0, 0, 1, 37, -5))
    assert_updated(cached)
    assert b.layer_bounds(lid) == (47, 15, 20, 20)
    b.end_undo()
    assert cached.events[-1] == (
        "notify",
        "Geometry",
        (cached.layer.id, cached.glyph.id),
        True,
    )


def test_peer_views_observe_geometry_inside_undo_without_extra_updates(
    cached, monkeypatch
):
    b, font = cached.backend, cached.font
    peer = FontLabBackend(packages=[cached.package])
    monkeypatch.setattr(peer, "_native", lambda: cached.module)
    fid = peer._font_id(cached.package)
    mid = peer._register((fid, "master", "Regular"), cached.package, fid)
    peer._master_names[mid] = "Regular"
    gid = peer._register((fid, "glyph", 200), cached.glyph, fid)
    state = NS(fid=fid, mid=mid, gid=gid, glyph=cached.glyph, layer=cached.layer)
    configure_model(peer, state, monkeypatch)
    other = Model(peer)._font(fid).glyphs[0].layers[0]
    retained = other.paths[0].nodes[0]
    assert peer.layer_bounds(other.id) == (10, 20, 20, 20)
    with font.undo_group("Peer geometry"):
        font.glyphs[0].layers[0].paths[0].nodes[0].position = (100, 200)
        assert_updated(cached)
        before = list(cached.events)
        assert retained.position == (100, 200)
        assert peer.layer_bounds(other.id) == (30, 40, 70, 160)
        assert cached.events == before, "peer reads must not repair native caches"
    assert b._changed == {}


@pytest.mark.parametrize(
    "failure", ["layer.changed", "layer.update", "glyph.changed", "glyph.update"]
)
@pytest.mark.parametrize("grouped", [False, True])
def test_native_update_failure_keeps_pending_edits_without_final_notification(
    cached, failure, grouped
):
    b = cached.backend
    path = cached.font.glyphs[0].layers[0].paths[0]
    node = path.nodes[0]
    if grouped:
        b.begin_undo("Retry geometry")
    cached.fail = failure
    with pytest.raises(RuntimeError, match=f"injected {failure}"):
        b.set_node_position(node.id, 100, 200)
    assert len(cached.calls) == 1, (
        "only the pre-change notification may have been published"
    )
    assert b._changed == {
        ("layer", cached.layer.id): cached.layer,
        ("glyph", cached.glyph.id): cached.glyph,
    }, "failed updates must retain the edited native objects"
    if grouped:
        with pytest.raises(RuntimeError, match=f"injected {failure}"):
            b.end_undo()
        assert len(cached.calls) == 1, "failed retries must never publish success"
    else:
        with pytest.raises(RuntimeError, match="[Uu]npublished"):
            b.begin_undo("Must not erase failed edit")
        assert len(cached.calls) == 1
    cached.fail = None
    if grouped:
        b.end_undo()
    else:
        b.set_node_position(node.id, 101, 201)
    assert b._changed == {}, "successful retry publishes and clears the retained batch"
    assert len(cached.calls) == 2
    assert b.layer_bounds(cached.lid) == (
        (30, 40, 70, 160) if grouped else (30, 40, 71, 161)
    )


@pytest.mark.parametrize("operation", ["node", "replacement", "append", "transform"])
def test_auto_layer_refusal_precedes_clone_updates_and_notifications(
    cached, monkeypatch, operation
):
    b = cached.backend
    path = cached.font.glyphs[0].layers[0].paths[0]
    node = path.nodes[0]
    original = cached.layer.shapes[0]
    cached.layer.autoLayer = True
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=lambda *v: v),
    )
    actions = {
        "node": lambda: b.set_node_position(node.id, 100, 200),
        "replacement": lambda: b.set_path_nodes(
            path.id, tuple(replace(n, x=n.x + 10) for n in path._data().nodes), False
        ),
        "append": lambda: b.append_path(
            cached.lid, PathInfo("", (NodeInfo("", 100, 200),))
        ),
        "transform": lambda: b.transform_layer(cached.lid, (1, 0, 0, 1, 37, 0)),
    }
    with pytest.raises(UnsupportedCapability):
        actions[operation]()
    assert cached.events == [], (
        "auto-layer refusal must happen before native updates or notifications"
    )
    assert cached.layer.shapes == [original]
    assert b._changed == {}


@pytest.mark.parametrize("failure", ["layer.update", "glyph.update"])
def test_false_native_update_result_refuses_publication_until_retry(cached, failure):
    b = cached.backend
    node = cached.font.glyphs[0].layers[0].paths[0].nodes[0]
    b.begin_undo("False update")
    cached.fail = failure + ":false"
    with pytest.raises(NativeOperationError, match="refused to update"):
        b.set_node_position(node.id, 100, 200)
    with pytest.raises(NativeOperationError, match="refused to update"):
        b.end_undo()
    assert len(cached.calls) == 1, "a false native update is not a successful edit"
    assert b._changed, "failed native update must leave the batch retryable"
    before = list(cached.events)
    b.layer_bounds(cached.lid)
    assert cached.events == before, "reads must not retry a failed write"
    cached.fail = None
    b.end_undo()
    assert len(cached.calls) == 2
    assert b.layer_bounds(cached.lid) == (30, 40, 70, 160)


def test_outside_undo_updates_precede_notification_and_reads_stay_silent(cached):
    b = cached.backend
    node = cached.font.glyphs[0].layers[0].paths[0].nodes[0]
    assert b.layer_bounds(cached.lid) == (10, 20, 20, 20)
    b.set_node_position(node.id, 100, 200)
    assert cached.events == [
        ("notify", "Glyport edit", (cached.layer.id, cached.glyph.id), True),
        "layer.changed",
        "layer.update",
        "glyph.changed",
        "glyph.update",
        ("notify", "Glyport edit", (cached.layer.id, cached.glyph.id), True),
    ]
    before = list(cached.events)
    assert b.layer_bounds(cached.lid) == (30, 40, 70, 160)
    assert b._read_layer(cached.fid, cached.layer, cached.mid, cached.gid).paths
    b.set_node_selected(node.id, False)
    assert cached.events == before, "selection and geometry reads need no cache update"


def test_discard_failed_group_drops_only_local_pending_work(cached):
    b = cached.backend
    node = cached.font.glyphs[0].layers[0].paths[0].nodes[0]
    b.begin_undo("Failed update")
    cached.fail = "layer.update"
    with pytest.raises(RuntimeError, match="injected"):
        b.set_node_position(node.id, 100, 200)
    before = list(cached.events)
    b.discard_undo()
    assert cached.events == before, "discard must never dereference native objects"
    assert b._changed == {}
    assert b._pending_layer_updates == set()
    b.begin_undo("New empty group")
    b.end_undo()
    assert cached.events == before


def test_failed_update_during_model_undo_stays_pending_until_explicit_retry(cached):
    font = cached.font
    layer = font.glyphs[0].layers[0]
    cached.fail = "glyph.update"
    with (
        pytest.raises(RuntimeError, match="injected glyph.update"),
        font.undo_group("Failed geometry"),
    ):
        layer.paths[0].nodes[0].position = (100, 200)
    assert font._undo_pending, (
        "closing a failed cache update must preserve model Undo recovery"
    )
    assert cached.backend._changed
    assert len(cached.calls) == 1, (
        "neither failed update nor failed group close may publish"
    )
    cached.fail = None
    font._end_undo()
    assert not font._undo_pending
    assert cached.backend._changed == {}
    assert len(cached.calls) == 2
    assert cached.backend.layer_bounds(layer.id) == (30, 40, 70, 160)


def test_restoring_pending_layer_after_update_failure_drops_deleted_layer_retry(cached):
    from fontlab_glyport.model.fontlab_backend import _PendingLayer

    b = cached.backend
    pending = _PendingLayer("Regular")
    b._objects[cached.lid] = pending
    snapshot = b.snapshot_collection(cached.lid)
    removed = []
    cached.glyph.findLayerCreate = lambda name: cached.layer
    cached.glyph.removeLayer = removed.append
    b.begin_undo("Create and recover")
    cached.fail = "layer.update"
    with pytest.raises(RuntimeError, match="injected layer.update"):
        b.set_layer_width(cached.lid, 640)
    assert b._pending_layer_updates == {cached.lid}
    cached.fail = None
    b.restore_collection(cached.lid, snapshot)
    assert removed == [cached.layer]
    assert b._objects[cached.lid] is pending
    assert b._pending_layer_updates == set(), (
        "deleted native layers must not reach an updater"
    )
    b.end_undo()
    assert cached.calls[-1] == ("Create and recover", [cached.glyph], True)


def test_collection_rollback_after_update_failure_restores_warmed_geometry(cached):
    b = cached.backend
    path = cached.font.glyphs[0].layers[0].paths[0]
    retained = path.nodes[0]
    assert b.layer_bounds(cached.lid) == (10, 20, 20, 20)
    snapshot = b.snapshot_collection(cached.lid, stage=True)
    b.begin_undo("Recover geometry")
    cached.fail = "layer.update"
    with pytest.raises(RuntimeError, match="injected layer.update"):
        b.set_node_position(retained.id, 100, 200)
    cached.fail = None
    b.restore_collection(cached.lid, snapshot)
    assert_updated(cached)
    assert retained.position == (10, 20), "rollback restores the original token binding"
    assert b.layer_bounds(cached.lid) == (10, 20, 20, 20)
    b.end_undo()
    assert len(cached.calls) == 2


def test_repeated_stale_update_retries_never_publish_or_drop_the_failed_batch(cached):
    b = cached.backend
    node = cached.font.glyphs[0].layers[0].paths[0].nodes[0]
    b.begin_undo("Stale geometry")
    cached.fail = "layer.update"
    with pytest.raises(RuntimeError, match="injected layer.update"):
        b.set_node_position(node.id, 100, 200)
    cached.fail = None
    cached.layer.isValid = False
    changed = dict(b._changed)
    for attempt in range(2):
        with pytest.raises(StaleNativeObject):
            b.end_undo()
        assert b._changed == changed, (
            f"stale retry {attempt + 1} must keep the failed batch"
        )
        assert len(cached.calls) == 1, (
            "stale native wrappers must never reach notification"
        )
    assert b._pending_layer_updates == {cached.lid}, (
        "invalidation must not erase the failed publication barrier"
    )
    before = list(cached.events)
    b.discard_undo()
    assert cached.events == before, "stale batch discard is entirely local"
    assert b._changed == {}
    assert b._pending_layer_updates == set()


@pytest.mark.parametrize("rollback", [False, True])
def test_failed_replacement_retires_owner_and_peer_nodes_until_explicit_rollback(
    cached, monkeypatch, rollback
):
    b = cached.backend
    layer = cached.font.glyphs[0].layers[0]
    path = layer.paths[0]
    owner_node = path.nodes[0]
    peer = FontLabBackend(packages=[cached.package])
    monkeypatch.setattr(peer, "_native", lambda: cached.module)
    fid = peer._font_id(cached.package)
    mid = peer._register((fid, "master", "Regular"), cached.package, fid)
    peer._master_names[mid] = "Regular"
    gid = peer._register((fid, "glyph", 200), cached.glyph, fid)
    state = NS(fid=fid, mid=mid, gid=gid, glyph=cached.glyph, layer=cached.layer)
    configure_model(peer, state, monkeypatch)
    other = Model(peer)._font(fid).glyphs[0].layers[0]
    peer_node = other.paths[0].nodes[0]
    snapshot = b.snapshot_collection(layer.id, stage=True)
    b.begin_undo("Failed replacement")
    cached.fail = "layer.update"
    with pytest.raises(RuntimeError, match="injected layer.update"):
        b.set_path_nodes(
            path.id, (NodeInfo("", 100, 100), NodeInfo("", 200, 10000)), False
        )
    attached = cached.layer.shapes[0].contours[0].nodes()
    assert [(n.x, n.y) for n in attached] == [(100, 100), (200, 10000)]
    cached.fail = None
    for retained in (owner_node, peer_node):
        with pytest.raises(StaleNativeObject):
            retained.position = (300, 300)
        assert [(n.x, n.y) for n in attached] == [(100, 100), (200, 10000)], (
            "retired handles may never silently write detached nodes"
        )
    assert len(cached.calls) == 1, (
        "failed writes through retired proxies must not publish"
    )
    if rollback:
        b.restore_collection(layer.id, snapshot)
        assert owner_node.position == peer_node.position == (10, 20), (
            "explicit rollback must restore both original bindings"
        )
        peer_node.position = (50, 60)
        assert owner_node.position == (50, 60), (
            "restored peer writes must affect attached geometry"
        )
        assert [(n.x, n.y) for n in cached.layer.shapes[0].contours[0].nodes()] == [
            (50, 60),
            (30, 40),
        ]
    else:
        fresh = layer.paths[0].nodes[0]
        fresh.position = (300, 300)
        assert [(n.x, n.y) for n in attached] == [(300, 300), (200, 10000)], (
            "fresh handles must write the attached replacement"
        )
    b.end_undo()
    assert b._changed == {}
