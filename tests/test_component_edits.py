# this_file: tests/test_component_edits.py
"""Component edit contracts with native-shaped doubles; no native acceptance."""

from copy import deepcopy
from dataclasses import replace
from itertools import count
from types import SimpleNamespace as NS

import pytest
from test_geometry_cache_updates import cached as cached_fixture
from test_issue106_round9 import configure_model

from fontlab_glyport.errors import (
    NativeOperationError,
    StaleNativeObject,
    UnsupportedCapability,
)
from fontlab_glyport.model import GSComponent, Model
from fontlab_glyport.model.backend import (
    ComponentInfo,
    GlyphInfo,
    LayerInfo,
    NodeInfo,
    PathInfo,
)
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend

SERIAL = count(200000)


class Matrix:
    def __init__(self, values=(1, 0, 0, 1, 0, 0)):
        self.values = values

    def isAffine(self):
        return True

    def m11(self):
        return self.values[0]

    def m12(self):
        return self.values[1]

    def m21(self):
        return self.values[2]

    def m22(self):
        return self.values[3]

    def dx(self):
        return self.values[4]

    def dy(self):
        return self.values[5]

    def map(self, point):
        a, b, c, d, e, f = self.values
        x, y = a * point.x() + c * point.y() + e, b * point.x() + d * point.y() + f
        return NS(x=lambda: x, y=lambda: y)

    def then(self, outer):
        a, b, c, d, e, f = outer.values
        x, y, z, w, tx, ty = self.values
        return Matrix(
            (
                a * x + c * y,
                b * x + d * y,
                a * z + c * w,
                b * z + d * w,
                a * tx + c * ty + e,
                b * tx + d * ty + f,
            )
        )


@pytest.fixture
def components(monkeypatch):
    s = cached_fixture.__wrapped__(monkeypatch)
    shape_type = type(s.layer.shapes[0])
    s.layer.name = "Regular"
    s.sources = {}

    class Data(NS):
        @property
        def includes(self):
            raise TypeError("flObjectsList<flShape> is not iterable")

    class Component:
        isComponent = isComposite = isValid = True
        contours = ()

        def __init__(self, name, transform=(1, 0, 0, 1, 25, 35)):
            self.id = next(SERIAL)
            self.transform = Matrix(transform)
            self.shapeData = Data(
                id=next(SERIAL), componentGlyph=name, componentLayer=""
            )
            self.shapeData.builder = NS(id=next(SERIAL), update=lambda: True)
            self.payload = {"lock": True, "style": "retain"}

        @property
        def includesList(self):
            name = self.shapeData.componentGlyph
            return list(s.sources[name].shapes) if name in s.sources else []

        def clone(self):
            result = deepcopy(self)
            result.id = next(SERIAL)
            return result

        def ejectTo(self):
            s.events.append("eject")
            result = [
                shape.clone()
                for shape in s.sources[self.shapeData.componentGlyph].shapes
            ]
            for shape in result:
                shape.transform = shape.transform.then(self.transform)
            return result

    def base(name, shapes):
        layer = NS(
            id=next(SERIAL),
            name="Regular",
            shapes=shapes,
            autoLayer=False,
            isValid=True,
        )
        glyph = NS(
            id=next(SERIAL),
            name=name,
            isValid=True,
            findLayer=lambda name: layer if name == "Regular" else None,
        )
        s.sources[name] = layer
        return glyph

    def outline(x):
        shape = shape_type()
        shape.contours = [shape.contours[0]]
        shape.contours[0]._nodes[0].x = x
        shape.transform = Matrix()
        shape.payload = {"group": "native", "locked": True}
        return shape

    s.B, s.C = base("B", [outline(10)]), base("C", [outline(90)])
    s.Nested = base("Nested", [Component("B", (1, 0, 0, 1, 10, 20))])
    s.Cycle = base("Cycle", [Component("A")])
    s.Missing = base("Missing", [Component("absent")])
    glyphs = {g.name: g for g in [s.glyph, s.B, s.C, s.Nested, s.Cycle, s.Missing]}
    s.glyph.findLayer = lambda name: s.layer if name == "Regular" else None
    s.package.findName = glyphs.get
    s.sentinel = s.layer.shapes[0]
    s.sentinel.transform = Matrix()
    s.target, s.tail = Component("B"), Component("C", (1, 0, 0, 1, 300, 70))
    s.layer.shapes = [s.sentinel, s.target, s.tail]
    s.Component = Component
    s.public = s.font.glyphs[0].layers[0]
    return s


def peer_of(s, monkeypatch):
    b = FontLabBackend(packages=[s.package])
    monkeypatch.setattr(b, "_native", lambda: s.module)
    fid = b._font_id(s.package)
    mid = b._register((fid, "master", "Regular"), s.package, fid)
    b._master_names[mid] = "Regular"
    gid = b._register((fid, "glyph", 200), s.glyph, fid)
    configure_model(
        b, NS(fid=fid, mid=mid, gid=gid, glyph=s.glyph, layer=s.layer), monkeypatch
    )
    return b, Model(b)._font(fid).glyphs[0].layers[0]


@pytest.mark.parametrize("alias", ["name", "componentName"])
def test_aliases_live_draft_and_cow(components, monkeypatch, alias):
    s = components
    other, peer = peer_of(s, monkeypatch)
    retained = peer.components[0]
    component = s.public.components[0]
    assert component.name == component.componentName == "B"
    draft = component.copy()
    setattr(draft, alias, "C")
    assert draft.name == draft.componentName == "C" and draft.parent is None
    with s.font.undo_group("Swap"), s.font.undo_group("Nested"):
        setattr(component, alias, "C")
        assert retained.name == "C"
        assert other._object(retained.id) is s.layer.shapes[1]
        assert s.target.shapeData.componentGlyph == "B"
        assert s.layer.shapes[1].payload == s.target.payload
        assert s.layer.shapes[0] is s.sentinel and s.layer.shapes[2] is s.tail
    assert len(s.calls) == 2


@pytest.mark.parametrize("value", ["absent", "Cycle", "Missing", "A", "", None, 3])
def test_invalid_name_is_atomic_before_clone_or_checkpoint(components, value):
    s = components
    component = s.public.components[0]
    before = list(s.layer.shapes)
    with pytest.raises((ValueError, TypeError, UnsupportedCapability)):
        component.name = value
    assert s.layer.shapes == before and not s.calls and not s.events


@pytest.mark.parametrize("via_layer", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_one_level_decompose_exact_slot_native_payload_and_lifetime(
    components, monkeypatch, via_layer, nested
):
    s = components
    if nested:
        s.target.shapeData.componentGlyph = "Nested"
        s.backend._revision += 1  # model an externally notified host edit
    _, peer = peer_of(s, monkeypatch)
    stale = peer.components[0]
    component = s.public.components[0]
    token = component.id
    node = s.public.paths[0].nodes[0]
    with s.font.undo_group("Decompose"):
        assert (
            s.public.decomposeComponent_(component)
            if via_layer
            else component.decompose()
        ) is None
        assert (
            component.name == ("Nested" if nested else "B") and component.parent is None
        )
        assert s.layer.shapes[0] is s.sentinel and s.layer.shapes[2] is s.tail
        assert s.public.paths[0].nodes[0] is node
        inserted = s.layer.shapes[1]
        if nested:
            assert inserted.isComponent and inserted.shapeData.componentGlyph == "B"
            assert inserted.transform.values == (1, 0, 0, 1, 35, 55)
        else:
            assert (
                not inserted.isComponent
                and inserted.payload == s.sources["B"].shapes[0].payload
            )
            assert inserted.transform.values == (1, 0, 0, 1, 25, 35)
        with pytest.raises(StaleNativeObject):
            _ = stale.componentName
        component.name = "detached-only"
        assert s.target.shapeData.componentGlyph == ("Nested" if nested else "B")
    assert len(s.calls) == 2
    assert (type(component), token) not in s.font._cache


def test_foreign_layer_decompose_is_atomic(components, monkeypatch):
    s = components
    _, peer = peer_of(s, monkeypatch)
    with pytest.raises(ValueError):
        s.public.decomposeComponent_(peer.components[0])
    assert s.layer.shapes == [s.sentinel, s.target, s.tail] and not s.calls


@pytest.mark.parametrize("operation", ["name", "decompose"])
def test_auto_layer_refused_before_staging(components, operation):
    s = components
    component = s.public.components[0]
    s.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability):
        if operation == "name":
            component.name = "C"
        else:
            component.decompose()
    assert (
        s.layer.shapes == [s.sentinel, s.target, s.tail]
        and not s.calls
        and not s.events
    )


@pytest.mark.parametrize(
    "failure", ["layer.update", "glyph.update", "layer.update:false"]
)
def test_failed_decompose_update_retires_peers_and_blocks_then_retries(
    components, monkeypatch, failure
):
    s = components
    marker = [4]
    s.glyph.currentHistoryState = lambda: marker[0]
    _, peer = peer_of(s, monkeypatch)
    stale = peer.components[0]
    component = s.public.components[0]
    s.backend.begin_undo("Failure")
    s.fail = failure
    with pytest.raises((RuntimeError, NativeOperationError)):
        component.decompose()
    assert component.name == "B" and component.parent is None
    marker[0] = 5
    with pytest.raises(StaleNativeObject):
        _ = stale.name
    count = len(s.calls)
    with pytest.raises((RuntimeError, NativeOperationError)):
        s.backend.end_undo()
    assert len(s.calls) == count and s.backend._pending_layer_updates
    s.fail = None
    s.backend.end_undo()
    assert len(s.calls) == count + 1 and not s.backend._pending_layer_updates


def test_failed_insertion_rolls_back_originals_and_peer_bindings(
    components, monkeypatch
):
    s = components
    _, peer = peer_of(s, monkeypatch)
    retained = peer.components[0]
    component = s.public.components[0]
    original_insert = s.layer.insertShape

    def fail_once(index, shape):
        s.layer.insertShape = original_insert
        raise RuntimeError("attachment")

    s.layer.insertShape = fail_once
    with pytest.raises(RuntimeError, match="attachment"):
        component.decompose()
    assert s.layer.shapes == [s.sentinel, s.target, s.tail]
    assert retained.name == component.name == "B" and component.parent is s.public


def test_fake_same_font_resolution_alias_and_nested_transform():
    b = FakeBackend()
    b.glyph_lists["font"] += (
        GlyphInfo("base", "B", ()),
        GlyphInfo("nested", "Nested", ()),
    )
    b.layers["base", "master"] = LayerInfo(
        "base-layer",
        "master",
        300,
        (PathInfo("bp", (NodeInfo("bn", 1, 2),)),),
        shape_ids=("bp",),
    )
    b.layers["nested", "master"] = LayerInfo(
        "nested-layer",
        "master",
        400,
        components=(ComponentInfo("nc", "B", (1, 0, 0, 1, 10, 20)),),
        shape_ids=("nc",),
    )
    font = Model(b).font
    layer = font.glyphs[0].layers[0]
    component = layer.components[0]
    component.name = "Nested"
    component.position = (25, 35)
    component.decompose()
    assert component.name == "Nested" and component.parent is None
    assert layer.components[0].name == "B" and layer.components[0].position == (35, 55)
    b.fonts["other"] = replace(b.fonts["font"], id="other")
    b.glyph_lists["other"] = (GlyphInfo("foreign", "Foreign", ()),)
    with pytest.raises(ValueError):
        layer.components[0].name = "Foreign"
    layer.components[0].decompose()
    assert layer.paths[-1].nodes[0].position == (36, 57)


@pytest.mark.parametrize("name", ["absent", "Cycle", "Missing"])
def test_decomposition_invalid_reference_preserves_complete_layer(components, name):
    s = components
    component = s.public.components[0]
    s.target.shapeData.componentGlyph = name
    s.backend._revision += 1
    with pytest.raises((ValueError, UnsupportedCapability)):
        component.decompose()
    assert s.layer.shapes == [s.sentinel, s.target, s.tail]
    assert not s.events and not s.calls and component.parent is s.public


@pytest.mark.parametrize(
    "mode", ["auto-source", "missing-layer", "unsupported-composite", "projective"]
)
@pytest.mark.parametrize("operation", ["name", "decompose"])
def test_unsupported_sources_refused_before_mutation(components, mode, operation):
    s = components
    name = "C" if operation == "name" else "B"
    source = s.sources[name]
    if mode == "auto-source":
        source.autoLayer = True
    elif mode == "missing-layer":
        getattr(s, name).findLayer = lambda name: None
    elif mode == "unsupported-composite":
        source.shapes[0].isComposite = True
    else:
        source.shapes[0].transform.isAffine = lambda: False
    component = s.public.components[0]
    with pytest.raises(UnsupportedCapability):
        if operation == "name":
            component.name = name
        else:
            component.decompose()
    assert s.layer.shapes == [s.sentinel, s.target, s.tail]
    assert not s.events and not s.calls


def test_empty_base_removes_only_target_and_leaves_safe_snapshot(components):
    s = components
    component = s.public.components[0]
    s.sources["B"].shapes.clear()
    component.decompose()
    assert s.layer.shapes == [s.sentinel, s.tail]
    assert component.name == "B" and component.parent is None


def test_full_affine_nested_composition_and_source_preservation(components):
    s = components
    s.target.shapeData.componentGlyph = "Nested"
    s.target.transform = Matrix((2, 3, -4, 5, 25, 35))
    s.backend._revision += 1
    component = s.public.components[0]
    component.decompose()
    assert s.layer.shapes[1].transform.values == (2, 3, -4, 5, -35, 165)
    assert s.sources["Nested"].shapes[0].transform.values == (1, 0, 0, 1, 10, 20)
    assert s.target.transform.values == (2, 3, -4, 5, 25, 35)


def test_swap_update_failure_is_pending_then_retried_without_touching_original(
    components,
):
    s = components
    component = s.public.components[0]
    s.backend.begin_undo("Swap failure")
    s.fail = "glyph.update"
    with pytest.raises(RuntimeError, match="glyph.update"):
        component.name = "C"
    assert component.name == "C" and s.target.shapeData.componentGlyph == "B"
    assert s.backend._pending_layer_updates
    s.fail = None
    s.backend.end_undo()
    assert not s.backend._changed and not s.backend._pending_layer_updates


def test_name_noop_does_not_clone_or_publish(components):
    s = components
    component = s.public.components[0]
    component.name = "B"
    component.componentName = "B"
    assert s.layer.shapes[1] is s.target and not s.events and not s.calls


def test_draft_aliases_are_strict_and_decompose_requires_parent():
    component = GSComponent("B")
    assert component.name == component.componentName == "B"
    component.componentName = "C"
    component.name = "D"
    assert component.componentName == "D" and component.parent is None
    for value in ("", None, 3):
        with pytest.raises((ValueError, TypeError)):
            component.name = value
    with pytest.raises(ValueError):
        component.decompose()


def test_two_replacements_stage_before_mutation_and_restore_partial_attachment(
    components,
):
    s = components
    s.sources["B"].shapes.append(s.sources["C"].shapes[0])
    component = s.public.components[0]
    insert = s.layer.insertShape
    calls = []

    def second_fails(index, shape):
        calls.append(shape)
        if len(calls) == 2:
            raise RuntimeError("second attachment")
        return insert(index, shape)

    s.layer.insertShape = second_fails
    with pytest.raises(RuntimeError, match="second attachment"):
        component.decompose()
    assert len(calls) == 2
    assert s.layer.shapes == [s.sentinel, s.target, s.tail]
    assert component.name == "B" and component.parent is s.public


def test_eject_staging_failure_never_checkpoints_or_removes_component(components):
    s = components
    component = s.public.components[0]

    def failed():
        raise RuntimeError("eject staging")

    s.target.ejectTo = failed
    with pytest.raises(RuntimeError, match="eject staging"):
        component.decompose()
    assert s.layer.shapes == [s.sentinel, s.target, s.tail]
    assert not s.calls and component.parent is s.public


def test_raw_connection_flags_survive_eject_clone_smoothing(components):
    s = components
    source = s.sources["B"].shapes[0]
    node = source.contours[0].nodes()[0]
    node.nodeState = 0x8079
    clone = source.clone

    def smoothed():
        copy = clone()
        copy.contours[0].nodes()[0].nodeState = 0x8071
        return copy

    source.clone = smoothed
    s.public.components[0].decompose()
    assert node.nodeState == 0x8079
    assert s.layer.shapes[1].contours[0].nodes()[0].nodeState == 0x8079


def test_repeated_grouped_swaps_and_decompose_preserve_history_and_one_checkpoint(
    components,
):
    s = components
    component = s.public.components[0]
    with s.font.undo_group("Combined"):
        component.name = "C"
        component.componentName = "B"
        component.name = "Nested"
        assert s.target.shapeData.componentGlyph == "B"
        component.decompose()
        assert s.layer.shapes[1].shapeData.componentGlyph == "B"
        assert len(s.calls) == 1
    assert len(s.calls) == 2 and component.name == "Nested"


def test_native_history_reread_does_not_reuse_initiating_detached_proxy(components):
    s = components
    component = s.public.components[0]
    component.decompose()
    component.name = "detached-snapshot"
    # Simulate the native layer restored by Undo, then notify/re-read it.
    s.layer.shapes = [s.sentinel, s.target, s.tail]
    s.backend._revision += 1
    current = s.public.components[0]
    assert current is not component and current.name == "B"
    assert current.parent is s.public
    assert component.name == "detached-snapshot" and component.parent is None


@pytest.mark.parametrize("operation", ["name", "decompose"])
@pytest.mark.parametrize("descendant", ["cycle", "missing", "unsupported"])
def test_later_explicit_layer_descendants_refuse_before_native_mutation(
    components, monkeypatch, operation, descendant
):
    s = components
    first, later = s.Component("Shared"), s.Component("Shared")
    first.shapeData.componentLayer = "Regular"
    later.shapeData.componentLayer = "Alternate"
    target = {"cycle": "A", "missing": "Missing", "unsupported": "C"}[descendant]
    regular = NS(id=next(SERIAL), isValid=True, autoLayer=False, shapes=[])
    alternate = NS(
        id=next(SERIAL), isValid=True, autoLayer=False, shapes=[s.Component(target)]
    )
    shared = NS(
        id=next(SERIAL),
        isValid=True,
        findLayer={"Regular": regular, "Alternate": alternate}.get,
    )
    lookup = s.package.findName
    s.package.findName = lambda name: shared if name == "Shared" else lookup(name)
    s.sources["B"].shapes = [first, later]
    if descendant == "unsupported":
        s.sources["C"].autoLayer = True
    if operation == "name":
        s.target.shapeData.componentGlyph = "C"
        s.backend._revision += 1
    component = s.public.components[0]
    original_name = component.name
    original_shapes = list(s.layer.shapes)

    def mutation(*args, **kwargs):
        raise AssertionError("crossed preflight before refusal")

    monkeypatch.setattr(s.backend, "_own_shape", mutation)
    monkeypatch.setattr(s.target, "ejectTo", mutation)
    monkeypatch.setattr(s.target.shapeData.builder, "update", mutation)
    error = UnsupportedCapability if descendant == "unsupported" else ValueError
    with pytest.raises(error):
        if operation == "name":
            component.name = "B"
        else:
            component.decompose()
    assert s.layer.shapes == original_shapes
    assert component.name == original_name and component.parent is s.public
    assert not s.calls and not s.events and not s.backend._prepared


def test_reference_to_other_layer_of_owner_is_not_a_false_cycle(components):
    from fontlab_glyport.model.component_edits import native_reference

    s = components
    alternate = NS(id=next(SERIAL), isValid=True, autoLayer=False, shapes=[])
    s.glyph.findLayer = {"Regular": s.layer, "Alternate": alternate}.get
    reference = s.Component("A")
    reference.shapeData.componentLayer = "Alternate"
    s.sources["B"].shapes = [reference]
    assert native_reference(s.backend, s.public.id, "B") is s.sources["B"]
    assert not s.calls and not s.events


@pytest.fixture(params=["empty", "nonempty"])
def stale_component(components, monkeypatch, request):
    """Native grouped swaps can leave empty includes until builder refresh."""
    s = components
    original_getter = s.Component.includesList.fget
    monkeypatch.setattr(
        s.Component,
        "includesList",
        property(
            lambda shape: shape.__dict__.get("cached_includes", original_getter(shape))
        ),
    )

    def cached_eject(shape):
        s.events.append("eject")
        clones = [item.clone() for item in shape.includesList]
        for item in clones:
            item.transform = item.transform.then(shape.transform)
        return clones

    monkeypatch.setattr(s.Component, "ejectTo", cached_eject)
    s.backend.begin_undo("Grouped stale component")
    component = s.public.components[0]
    for name in ("C", "B", "Nested"):
        component.name = name
    current = s.layer.shapes[1]
    current.cached_includes = (
        [] if request.param == "empty" else list(s.sources["B"].shapes)
    )
    s.refresh_failure = None

    def refresh():
        s.events.append("component.refresh")
        if s.refresh_failure == "raise":
            raise RuntimeError("component refresh refused")
        if s.refresh_failure == "false":
            return False
        current.cached_includes = original_getter(current)
        return True

    current.shapeData.builder = NS(id=next(SERIAL), update=refresh)
    s.stale_proxy = component
    return s


def test_grouped_renames_do_not_decompose_stale_empty_includes_as_empty_base(
    stale_component,
):
    s = stale_component
    s.stale_proxy.decompose()
    s.backend.end_undo()
    assert len(s.layer.shapes) == 3, (
        "stale empty includes must not delete the replacement"
    )
    inserted = s.layer.shapes[1]
    assert inserted.isComponent and inserted.shapeData.componentGlyph == "B"
    assert inserted.transform.values == (1, 0, 0, 1, 35, 55)
    assert s.layer.shapes[0] is s.sentinel and s.layer.shapes[2] is s.tail
    assert s.events.index("component.refresh") < s.events.index("eject")
    assert s.stale_proxy.name == "Nested" and s.stale_proxy.parent is None


@pytest.mark.parametrize("failure", ["false", "raise"])
def test_builder_refresh_failure_retains_attachment_for_safe_retry(
    stale_component, failure
):
    s = stale_component
    component = s.stale_proxy
    originals, count = list(s.layer.shapes), len(s.calls)
    s.refresh_failure = failure
    with pytest.raises((NativeOperationError, RuntimeError)):
        component.decompose()
    assert s.layer.shapes == originals and len(s.calls) == count
    assert component.name == "Nested" and component.parent is s.public
    assert "eject" not in s.events, "failed refresh must refuse before copying"
    s.refresh_failure = None
    component.decompose()
    s.backend.end_undo()
    assert len(s.layer.shapes) == 3 and len(s.calls) == count + 1
    assert s.layer.shapes[1].shapeData.componentGlyph == "B"
    assert s.layer.shapes[1].transform.values == (1, 0, 0, 1, 35, 55)


@pytest.mark.parametrize("first_read", ["retained", "collection"])
def test_decomposed_peer_stays_retired_across_history_reconciliation_and_undo(
    components, monkeypatch, first_read
):
    s = components
    marker = [4]
    s.glyph.currentHistoryState = lambda: marker[0]
    other, peer = peer_of(s, monkeypatch)
    retained = peer.components[0]
    component = s.public.components[0]
    with s.font.undo_group("History retirement"):
        component.name = "Nested"
        assert retained.name == "Nested"
        token = retained.id
        component.decompose()
        assert token not in other._objects, "native retirement precedes cache updates"
        marker[0] = 5
        if first_read == "collection":
            assert peer.components[0].name == "B"
        with pytest.raises(StaleNativeObject):
            _ = retained.name
    # Restoring native history can create a live proxy, never reuse the retired one.
    s.layer.shapes = [s.sentinel, s.target, s.tail]
    marker[0] = 4
    restored = peer.components[0]
    assert restored.name == "B" and restored is not retained
    assert component.name == "Nested" and component.parent is None
    with pytest.raises(StaleNativeObject):
        _ = retained.name
