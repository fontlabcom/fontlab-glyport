# this_file: tests/test_component_history.py
"""Measured detached-builder history behavior, simulated without FontLab."""

from copy import deepcopy
from types import SimpleNamespace as NS

import pytest
from test_component_edits import SERIAL, peer_of
from test_component_edits import components as components_fixture

from fontlab_glyport.errors import NativeOperationError, StaleNativeObject


@pytest.fixture
def history(monkeypatch):
    s = components_fixture.__wrapped__(monkeypatch)
    s.baselines, s.originals = {}, {}
    s.protected = set()
    s.publish_failure = False
    for layer in [s.layer, *s.sources.values()]:
        for shape in layer.shapes:
            if shape.isComponent:
                shape.shapeData.id = next(SERIAL)
                shape.shapeData.builder.id = next(SERIAL)

    def notify(name, items, deep):
        layers = [item for item in items if hasattr(item, "advanceWidth")]
        if s.publish_failure and any(layer.id in s.baselines for layer in layers):
            raise RuntimeError("history publication")
        s.calls.append((name, items, deep))
        for layer in layers:
            if layer.id not in s.baselines:
                s.baselines[layer.id] = layer, tuple(layer.shapes)
                for shape in layer.shapes:
                    if shape.isComponent:
                        s.originals[shape.id] = (
                            shape,
                            shape.shapeData,
                            shape.shapeData.builder,
                        )
                continue
            # Native controls: a detached component loses its builder when only
            # its old owning layer/glyph reach the final history notification.
            for shape in s.baselines[layer.id][1]:
                if shape.isComponent and shape not in layer.shapes:
                    original = s.originals[shape.id]
                    positions = [
                        next((i for i, item in enumerate(items) if item is obj), -1)
                        for obj in original
                    ]
                    if (
                        0
                        <= positions[0]
                        < positions[1]
                        < positions[2]
                        < items.index(layer)
                    ):
                        s.protected.add(shape.id)
                    elif shape.id not in s.protected:
                        shape.isComponent = shape.isComposite = False

    s.module.flItems = lambda: NS(notifyChangesApplied=notify)

    def undo():
        for layer, shapes in s.baselines.values():
            layer.shapes = list(shapes)
        s.backend._revision += 1

    s.undo = undo
    return s


def assert_originals_before_owners(s):
    items = s.calls[-1][1]
    for original in s.originals.values():
        if original[0] not in s.layer.shapes:
            publication = next(
                items
                for _, items, _ in s.calls
                if any(item is original[0] for item in items)
            )
            positions = [
                next(i for i, item in enumerate(publication) if item is obj)
                for obj in original
            ]
            assert positions == sorted(positions)
            assert (
                positions[-1] < publication.index(s.layer) < publication.index(s.glyph)
            )
    assert s.calls[0][1] == [s.layer, s.glyph], "no extra pre-change objects"
    assert all(item is not layer for item in items for layer in s.sources.values()), (
        "base layers must never be notified"
    )


@pytest.mark.parametrize(
    ("grouped", "operation"),
    [
        (False, "rename"),
        (True, "rename"),
        (False, "decompose"),
        (True, "decompose"),
        (True, "combined"),
    ],
)
def test_original_component_reference_survives_history(history, grouped, operation):
    s = history
    component = s.public.components[0]
    if grouped:
        s.backend.begin_undo("Components")
    if operation in {"rename", "combined"}:
        for name in ["C", "B", "Nested"] if operation == "combined" else ["C"]:
            component.name = name
    if operation in {"decompose", "combined"}:
        component.decompose()
    if grouped:
        s.backend.end_undo()
    assert s.target.isComponent, (
        "final notification must preserve the original builder history"
    )
    assert_originals_before_owners(s)
    s.undo()
    assert s.layer.shapes[1].isComponent, "Undo must restore a component, not outlines"
    assert s.layer.shapes[1].shapeData.componentGlyph == "B"
    assert s.backend._prepared == s.backend._changed == {}, (
        "success releases old native wrappers"
    )


def test_second_standalone_batch_does_not_republish_prior_originals(history):
    s = history
    component = s.public.components[0]
    component.name = "C"
    first_working = s.layer.shapes[1]
    component.name = "B"
    assert len(s.calls) == 4
    assert s.calls[2][1] == [s.layer, s.glyph]
    assert s.calls[3][1][:3] == [
        first_working,
        first_working.shapeData,
        first_working.shapeData.builder,
    ]
    assert all(item is not s.target for item in s.calls[3][1]), (
        "completed history wrappers must not leak into the next batch"
    )
    assert s.backend._prepared == s.backend._changed == {}


@pytest.mark.parametrize("operation", ["rename", "decompose"])
@pytest.mark.parametrize("failure", ["update", "publication"])
def test_failed_history_publication_retains_originals_for_retry(
    history, operation, failure
):
    s = history
    s.backend.begin_undo("Retry")
    component = s.public.components[0]
    s.fail = "glyph.update" if failure == "update" else None
    if failure == "update":
        with pytest.raises(RuntimeError, match="glyph.update"):
            component.name = "C" if operation == "rename" else component.name
            if operation == "decompose":
                component.decompose()
    elif operation == "rename":
        component.name = "C"
    else:
        component.decompose()
    s.publish_failure = failure == "publication"
    with pytest.raises(RuntimeError):
        s.backend.end_undo()
    assert len(s.calls) == 1 and s.backend._changed
    s.fail, s.publish_failure = None, False
    s.backend.end_undo()
    assert_originals_before_owners(s)
    s.undo()
    assert (
        s.layer.shapes[1].isComponent
        and s.layer.shapes[1].shapeData.componentGlyph == "B"
    )


@pytest.mark.parametrize("operation", ["rename", "decompose"])
@pytest.mark.parametrize("failure", ["update", "publication"])
def test_standalone_failed_batch_retries_at_next_layer_write(
    history, operation, failure
):
    s = history
    s.fail = "glyph.update" if failure == "update" else None
    s.publish_failure = failure == "publication"
    with pytest.raises(RuntimeError):
        if operation == "rename":
            s.public.components[0].name = "C"
        else:
            s.public.components[0].decompose()
    assert len(s.calls) == 1 and s.backend._changed
    with pytest.raises(RuntimeError, match="Unpublished"):
        s.backend.begin_undo("Cannot erase failure")
    s.fail, s.publish_failure = None, False
    s.public.width = s.public.width
    assert_originals_before_owners(s)
    assert s.backend._prepared == s.backend._changed == {}
    s.undo()
    assert (
        s.layer.shapes[1].isComponent
        and s.layer.shapes[1].shapeData.componentGlyph == "B"
    )


def test_grouped_two_components_publish_once_and_keep_public_lifetimes(
    history, monkeypatch
):
    s = history
    _, peer = peer_of(s, monkeypatch)
    stale = peer.components[0]
    first, second = list(s.public.components)
    with s.font.undo_group("Two components"):
        first.name = "Nested"
        second.name = "B"
        first.decompose()
        assert first.parent is None and first.name == "Nested"
        with pytest.raises(StaleNativeObject):
            _ = stale.name
    assert len(s.calls) == 2
    assert_originals_before_owners(s)
    s.undo()
    assert [
        shape.shapeData.componentGlyph for shape in s.layer.shapes if shape.isComponent
    ] == ["B", "C"]
    assert s.public.components[0] is not first and first.parent is None
    with pytest.raises(StaleNativeObject):
        _ = stale.name


def test_collection_rollback_drops_only_new_component_history(history):
    s = history
    first, second = list(s.public.components)
    s.backend.begin_undo("Rollback")
    first.name = "C"
    original_prepared = dict(s.backend._prepared)
    snapshot = s.backend.snapshot_collection(s.public.id, stage=True)
    second.name = "B"
    s.backend.restore_collection(s.public.id, snapshot)
    assert s.backend._prepared == original_prepared, (
        "rollback must not retain abandoned component originals"
    )
    s.backend.end_undo()
    items = s.calls[-1][1]
    assert any(item is s.target for item in items)
    assert not any(item is s.tail for item in items)
    s.undo()
    assert s.layer.shapes[1].isComponent


def test_discard_releases_component_history_without_native_calls(history):
    s = history
    s.backend.begin_undo("Discard")
    s.public.components[0].name = "C"
    calls = list(s.calls)
    s.backend.discard_undo()
    assert s.backend._prepared == s.backend._changed == {} and s.calls == calls
    s.backend.begin_undo("Empty")
    s.backend.end_undo()
    assert s.calls == calls


def test_failed_cow_attachment_restores_component_and_allows_retry(history):
    s = history
    component = s.public.components[0]
    insert = s.layer.insertShape

    def fail_once(index, shape):
        s.layer.insertShape = insert
        raise RuntimeError("COW attachment")

    s.layer.insertShape = fail_once
    with pytest.raises(RuntimeError, match="COW attachment"):
        component.name = "C"
    assert s.layer.shapes == [s.sentinel, s.target, s.tail]
    assert component.name == "B" and component.parent is s.public
    assert s.backend._prepared == s.backend._changed == {}
    component.name = "C"
    assert s.layer.shapes[1].shapeData.componentGlyph == "C"


@pytest.mark.parametrize("operation", ["rename", "decompose"])
def test_history_captures_builder_before_native_detachment(history, operation):
    s = history
    data, builder = s.target.shapeData, s.target.shapeData.builder
    remove = s.layer.removeShape

    def detach(shape):
        remove(shape)
        if shape is s.target:
            # Reading the original shape's current builder after removal would
            # lose the object that the final native history call must receive.
            shape.shapeData.builder = None

    s.layer.removeShape = detach
    if operation == "rename":
        s.public.components[0].name = "C"
    else:
        s.public.components[0].decompose()
    assert s.calls[-1][1][:3] == [s.target, data, builder]
    assert s.target.isComponent


def test_abandoned_group_checks_live_owners_without_registering_history_objects(
    history,
):
    s = history
    component = s.public.components[0]
    s.backend.begin_undo("Abandoned")
    component.name = "C"
    assert s.backend.can_publish_undo(s.fid)
    assert not any(obj is s.target for obj in s.backend._objects.values()), (
        "history retention must never register a detached original as live"
    )
    s.layer.isValid = False
    assert not s.backend.can_publish_undo(s.fid)
    calls = list(s.calls)
    s.backend.discard_undo()
    assert s.calls == calls and s.backend._prepared == {}


@pytest.mark.parametrize("layer_name", ["Bold", "Alternate"])
def test_multiple_layer_targets_retain_each_original_before_one_final_batch(
    history, layer_name
):
    s = history
    b = s.backend
    other = deepcopy(s.layer)
    other.id, other.name = next(SERIAL), layer_name
    other.insertShape = lambda index, shape: other.shapes.insert(index, shape)
    other.removeAllShapes = lambda: other.shapes.clear()
    other.addShapes = lambda shapes: other.shapes.extend(shapes)
    for shape in other.shapes:
        shape.id = next(SERIAL)
    s.glyph.findLayer = {"Regular": s.layer, layer_name: other}.get
    for name in ("B", "C", "Nested"):
        glyph = getattr(s, name)
        glyph.findLayer = lambda name, source=s.sources[name]: (
            source if name in {"Regular", layer_name} else None
        )
    mid = b._register((s.fid, "master", layer_name), s.package, s.fid)
    s.package.masters = ["Regular", layer_name]
    b._master_names[mid] = layer_name
    info = b._read_layer(s.fid, other, mid, s.gid)
    first_id, other_id = s.public.components[0].id, info.components[0].id
    original_other = other.shapes[1]
    b.begin_undo("Layers")
    b.set_component_name(first_id, "C")
    b.set_component_name(other_id, "C")
    b.set_component_name(first_id, "Nested")
    b.end_undo()
    assert len(s.calls) == 3, "one checkpoint per layer, one shared final publication"
    items = s.calls[-1][1]
    for shape, layer in ((s.target, s.layer), (original_other, other)):
        positions = [
            next(i for i, item in enumerate(items) if item is obj)
            for obj in (shape, shape.shapeData, shape.shapeData.builder)
        ]
        assert positions == sorted(positions) and positions[-1] < items.index(layer)
        assert items.index(layer) < items.index(s.glyph)
    s.undo()
    assert all(
        layer.shapes[1].isComponent and layer.shapes[1].shapeData.componentGlyph == "B"
        for layer in (s.layer, other)
    )


def test_successful_delete_keeps_component_originals_for_package_publication_retry(
    history,
):
    """Retired glyph owners must not strand their still-needed native payloads."""
    s = history
    b = s.backend
    b.begin_undo("Edit then delete")
    s.public.components[0].name = "C"
    originals = {
        key: value
        for key, value in b._prepared.items()
        if key[0] == "component_history"
    }
    assert originals, "Control did not retain an edited component's originals"
    deleted, fail = [], [True]

    def delete(glyph):
        deleted.append(glyph.id)
        glyph.isValid = False
        return True

    notify = s.module.flItems().notifyChangesApplied

    def publish(name, items, deep):
        if deleted and fail[0]:
            raise RuntimeError("package publication")
        notify(name, items, deep)

    s.package.deleteGlyph = delete
    s.module.flItems = lambda: NS(notifyChangesApplied=publish)
    b.remove_glyph(s.fid, s.gid)
    assert deleted == [s.glyph.id], "Native deletion was not performed exactly once"
    assert set(b._changed) == {("font", s.package.id)}
    assert b._prepared and not b.is_valid(s.gid)
    retained = tuple(
        value for key, value in b._prepared.items() if key[0] == "component_history"
    )
    assert retained == tuple(originals.values()), "Deletion discarded native originals"
    prepared = dict(b._prepared)
    with pytest.raises(RuntimeError, match="package publication"):
        b.end_undo()
    assert b._prepared == prepared and b._changed, (
        "Failed publication lost its retry state"
    )
    fail[0] = False
    b.end_undo()
    assert s.calls[-1][1] == [*next(iter(originals.values())), s.package], (
        "Deleted glyph dependencies must precede the surviving package history owner"
    )
    assert not b._prepared and not b._changed and b._undo_name is None


@pytest.mark.parametrize("failure", ["false", "exception"])
def test_failed_delete_preserves_component_owner_batch_and_can_publish(
    history, failure
):
    s = history
    b = s.backend
    b.begin_undo("Failed delete")
    s.public.components[0].name = "C"
    before = (dict(b._prepared), dict(b._changed), set(b._owned_shapes))
    deleted = []

    def delete(glyph):
        deleted.append(glyph.id)
        if failure == "exception":
            raise RuntimeError("native delete refused")
        return False

    s.package.deleteGlyph = delete
    expected = RuntimeError if failure == "exception" else NativeOperationError
    with pytest.raises(expected, match="refused"):
        b.remove_glyph(s.fid, s.gid)
    assert deleted == [s.glyph.id] and b.is_valid(s.gid)
    prepared = dict(before[0])
    if failure == "exception":
        prepared["font", s.package.id] = s.package  # successful preparation receipt
    assert (b._prepared, b._changed, b._owned_shapes) == (
        prepared,
        before[1],
        before[2],
    )
    b.end_undo()
    assert_originals_before_owners(s)
    s.undo()
    assert s.layer.shapes[1].isComponent
    assert s.layer.shapes[1].shapeData.componentGlyph == "B"


def test_successful_delete_keeps_other_glyph_component_batch_in_its_live_domain(
    history,
):
    """Retiring one glyph must neither remap nor discard another live batch."""
    s = history
    b = s.backend
    other = deepcopy(s.layer)
    other.id = next(SERIAL)
    other.shapes = [s.Component("B")]
    other.insertShape = lambda index, shape: other.shapes.insert(index, shape)
    glyph = NS(
        id=next(SERIAL),
        name="Other",
        isValid=True,
        findLayer=lambda name: other,
        changed=lambda: None,
        update=lambda: None,
    )
    find = s.package.findName
    s.package.findName = lambda name: glyph if name == "Other" else find(name)
    gid = b._register((s.fid, "glyph", glyph.id), glyph, s.fid)
    info = b._read_layer(s.fid, other, s.mid, gid)
    b.begin_undo("Two owners then delete one")
    s.public.components[0].name = "C"
    b.set_component_name(info.components[0].id, "C")
    live_originals = {
        key: value
        for key, value in b._prepared.items()
        if key[0] == "component_history" and key[1] == info.id
    }
    assert live_originals, "Second glyph did not have retained component history"
    s.package.deleteGlyph = lambda value: setattr(value, "isValid", False) or True
    b.remove_glyph(s.fid, s.gid)
    assert all(b._prepared[key] == value for key, value in live_originals.items())
    assert ("layer", other.id) in b._changed and ("glyph", glyph.id) in b._changed
    b.end_undo()
    items = s.calls[-1][1]
    for original in live_originals.values():
        assert all(items.index(value) < items.index(other) for value in original)
    assert items.index(other) < items.index(glyph) < items.index(s.package)
    assert s.target in items, "Deleted owner's original was lost beside a live batch"
    assert not b._prepared and not b._changed
