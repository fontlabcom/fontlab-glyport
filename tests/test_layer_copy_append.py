# this_file: tests/test_layer_copy_append.py
"""Independent auxiliary copy attachment and prewrite boundaries."""

from copy import deepcopy
from dataclasses import replace
from itertools import count

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSAnchor, GSGuide, GSHint, Model
from fontlab_glyport.model.backend import FontInfo, GlyphInfo, LayerInfo, MasterInfo
from fontlab_glyport.model.fake_backend import FakeBackend

_NATIVE_SERIAL = count(1000)


@pytest.fixture
def copied():
    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("light", "Light"), MasterInfo("master", "Regular")),
    )
    backend.layers["glyph", "light"] = replace(
        backend.layers["glyph", "master"], id="light-layer", masterId="light"
    )
    backend.libs["layer"] = {"nested": {"values": [1]}}
    font = Model(backend).font
    source = font.glyphs[0].layers["master"]
    source.anchors.append(GSAnchor("top", (100, 200)))
    source.guides.append(GSGuide((3, 4), 45, "diagonal"))
    hint = GSHint()
    hint.position, hint.width = 10, 30
    source.hints.append(hint)
    source.background.paths = source.paths
    draft = source.copy()
    draft.name = "Dated copy"
    return backend, font, source, draft


def test_copy_rename_append_binds_same_object_and_preserves_association(copied):
    _, font, source, draft = copied
    glyph = source.parent
    child, background = draft.paths[0].nodes[0], draft.background
    old_id = draft.layerId
    glyph.layers.append(draft)
    assert glyph.layers[draft.layerId] is draft and draft.parent is glyph
    assert draft.layerId != old_id and draft.id != source.id
    assert draft.associatedMasterId == "master" and not draft.isMasterLayer
    assert [layer.name for layer in glyph.layers] == ["Light", "Regular", "Dated copy"]
    assert draft.master is font.masters["master"]
    assert [type(s) for s in draft.shapes] == [type(s) for s in source.shapes]
    assert draft.paths[0].id != source.paths[0].id
    assert draft.paths[0].nodes[0].id != source.paths[0].nodes[0].id
    assert draft.components[0].id != source.components[0].id
    assert draft.anchors[0].id != source.anchors[0].id
    assert draft.guides[0].id != source.guides[0].id
    assert draft.hints[0].width == 30
    assert draft.background.id != source.background.id
    assert (
        draft.background.paths[0].nodes[0].id != source.background.paths[0].nodes[0].id
    )
    draft.width += 1
    draft.userData["nested"]["values"].append(2)
    draft.background.paths[0].nodes[0].x += 1
    assert source.width == 500 and source.userData["nested"]["values"] == [1]
    assert source.background.paths[0].nodes[0].x == 0
    child.x = 42
    background.width = 99
    assert draft.paths[0].nodes[0].x == 0 and draft.background.width != 99
    assert background.foreground() is None


def test_copy_time_snapshot_survives_source_changes(copied):
    _, _, source, draft = copied
    source.width = 900
    source.userData["nested"]["values"].append(8)
    source.background.paths[0].nodes[0].x = 30
    source.parent.layers.append(draft)
    assert draft.width == 500 and draft.userData["nested"]["values"] == [1]
    assert draft.background.paths[0].nodes[0].x == 0


@pytest.mark.parametrize(
    "name", ["", " ", "regular", "LIGHT", "mask.Copy", "MASK.copy"]
)
def test_invalid_names_refuse_without_writes(copied, name):
    backend, _, source, draft = copied
    draft.name = name
    before = deepcopy(dict(backend.layers))
    with pytest.raises((ValueError, UnsupportedCapability)):
        source.parent.layers.append(draft)
    assert dict(backend.layers) == before and draft.parent is None


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: setattr(d, "width", 501),
        lambda d: d.userData["nested"]["values"].append(4),
        lambda d: setattr(d.paths[0].nodes[0], "x", 4),
        lambda d: setattr(d.components[0], "position", (3, 4)),
        lambda d: setattr(d.background.paths[0].nodes[0], "x", 4),
        lambda d: setattr(d, "leftMetricsKey", "=A"),
        lambda d: d.attributes.__setitem__("coordinates", [3]),
        lambda d: d.clear(),
        lambda d: setattr(d.guides[0], "angle", 15),
        lambda d: setattr(d.anchors[0], "name", "other"),
        lambda d: setattr(d.hints[0], "width", 31),
        lambda d: setattr(d, "background", None),
        lambda d: d._component_layers["A"].userData.update({"changed": True}),
    ],
)
def test_modified_snapshot_is_refused_before_any_writes(copied, edit):
    backend, _, source, draft = copied
    edit(draft)
    before = deepcopy(dict(backend.layers))
    with pytest.raises(UnsupportedCapability, match="modified"):
        source.parent.layers.append(draft)
    assert dict(backend.layers) == before and draft.parent is None


def test_deepcopy_preserves_refusal_and_memo(copied):
    _, _, source, draft = copied
    pair = deepcopy([draft, draft])
    assert pair[0] is pair[1]
    pair[0].name = "Another"
    source.parent.layers.append(pair[0])
    draft.width += 1
    with pytest.raises(UnsupportedCapability, match="modified"):
        source.parent.layers.append(draft.copy())


def test_attached_layer_cannot_be_appended(copied):
    _, _, source, _ = copied
    with pytest.raises((TypeError, ValueError)):
        source.parent.layers.append(source)


@pytest.mark.parametrize("kind", ["object", "new", "background", "owned"])
def test_noncopy_and_owned_layers_refuse_before_writes(copied, kind):
    from fontlab_glyport.model import GSLayer

    backend, _, source, draft = copied
    candidates = {
        "object": object(),
        "new": GSLayer(),
        "background": draft.background,
        "owned": draft,
    }
    if kind == "owned":
        draft.parent = source.parent
    before = deepcopy(dict(backend.layers))
    with pytest.raises((TypeError, ValueError, UnsupportedCapability)):
        source.parent.layers.append(candidates[kind])
    assert dict(backend.layers) == before


def test_copy_maps_regular_into_destination_after_source_close(copied):
    backend, font, _, draft = copied
    backend.fonts["dest-font"] = FontInfo(
        "dest-font",
        "Destination",
        1000,
        (MasterInfo("dest-light", "Light"), MasterInfo("dest-regular", "Regular")),
    )
    backend.glyph_lists["dest-font"] = (GlyphInfo("dest-glyph", "A", ()),)
    backend.layers["dest-glyph", "dest-light"] = LayerInfo("dest-l", "dest-light", 200)
    backend.layers["dest-glyph", "dest-regular"] = LayerInfo(
        "dest-r", "dest-regular", 300
    )
    target = font._model._font("dest-font").glyphs[0]
    backend.close_font("font")
    target.layers.append(draft)
    assert draft.associatedMasterId == "dest-regular" and draft.width == 500
    assert draft.userData["nested"]["values"] == [1]


def test_bad_association_and_missing_master_refuse_before_writes(copied):
    backend, _, source, draft = copied
    before = deepcopy(dict(backend.layers))
    draft.associatedMasterId = "absent"
    with pytest.raises(ValueError, match="association"):
        source.parent.layers.append(draft)
    assert dict(backend.layers) == before
    draft.associatedMasterId = "master"
    draft._master_owner = "other-owner"
    draft._master_name = "Missing"
    with pytest.raises(UnsupportedCapability, match="unmatched"):
        source.parent.layers.append(draft)
    assert dict(backend.layers) == before


def test_foreground_and_orphan_mask_case_insensitive_collisions(copied):
    backend, _, source, draft = copied
    backend.layers["glyph", "orphan#mask"] = LayerInfo(
        "orphan", "master", 100, name="MASK.DATED COPY"
    )
    before = deepcopy(dict(backend.layers))
    with pytest.raises(UnsupportedCapability, match="collides"):
        source.parent.layers.append(draft)
    assert dict(backend.layers) == before


def test_absent_mask_remains_absent_after_append():
    backend = FakeBackend()
    source = Model(backend).font.glyphs[0].layers[0]
    draft = source.copy()
    draft.name = "No mask"
    source.parent.layers.append(draft)
    assert ("glyph", draft.layerId + "#mask") not in backend.layers
    assert not draft.background.paths


def test_public_retry_keeps_caller_detached_until_success(copied, monkeypatch):
    backend, _, source, draft = copied
    append = backend.append_layer

    def fail(*args):
        raise RuntimeError("publication failed")

    monkeypatch.setattr(backend, "append_layer", fail)
    with pytest.raises(RuntimeError):
        source.parent.layers.append(draft)
    assert draft.parent is None and draft.width == 500
    monkeypatch.setattr(backend, "append_layer", append)
    source.parent.layers.append(draft)
    assert source.parent.layers[-1] is draft


def test_fake_explicit_reference_is_separate_from_auxiliary_association(copied):
    backend, _, source, draft = copied
    draft.associatedMasterId = "light"
    source.parent.layers.append(draft)
    assert draft.associatedMasterId == "light"
    second = draft.copy()
    second.name = "Second"
    del backend.layers["glyph", "master"]
    before = dict(backend.layers)
    with pytest.raises(ValueError, match="reference layer"):
        draft.parent.layers.append(second)
    assert dict(backend.layers) == before


@pytest.fixture
def native_copy(monkeypatch):
    from types import SimpleNamespace as NS

    from test_background_auxiliary import layers
    from test_fontlab_backend_lazy import NodeFlags

    native = layers.__wrapped__(monkeypatch)
    serial = _NATIVE_SERIAL
    native.glyph.layers = [native.layer, native.bold]
    native.glyph.activeLayer = native.bold
    native.package.findName = lambda name: native.glyph if name == "A" else None
    native.module.ShapeType = {"AnyShape\t": 7}

    def add_layer(layer, back):
        layer.isMasterLayer = layer.name in native.package.masters
        layer.isMaskLayer = layer.name.startswith("mask.")
        layer.isService = layer.isMaskLayer
        layer.mask = next(
            (l for l in native.glyph.layers if l.name == "mask." + layer.name), None
        )
        native.glyph.layers.append(layer)

    native.glyph.addLayer = add_layer
    native.glyph.removeLayer = lambda layer: native.glyph.layers.remove(layer)
    native.backend.hints = lambda lid: ()
    native.backend.master_metrics = lambda mid: FakeBackend().master_metrics("master")

    class Node(NodeFlags):
        def __init__(self):
            self.id, self.isValid = next(serial), True
            self.nodeState = 0x3009
            self.x, self.y = 10, 20

        @property
        def position(self):
            return NS(x=lambda: self.x, y=lambda: self.y)

        def isOff(self):
            return False

        isCurve = isOff

    class Contour:
        def __init__(self):
            self.id, self.isValid = next(serial), True
            self._nodes = [Node()]
            self.closed, self.isTT = False, False

        def nodes(self):
            return list(self._nodes)

    class Shape:
        def __init__(self, component=False):
            self.id = next(serial)
            self.isValid = True
            self.isComponent, self.active = component, True
            self.isComposite = component
            self.transform = NS(
                isAffine=lambda: True,
                m11=lambda: 1,
                m12=lambda: 0,
                m21=lambda: 0,
                m22=lambda: 1,
                dx=lambda: 33,
                dy=lambda: 44,
                map=lambda point: point,
            )
            self.contours = [] if component else [Contour()]
            self.shapeData = NS(
                name="owned data",
                componentGlyph="A",
                componentLayer="Regular",
                builder=NS(changed=lambda: None, update=lambda: None),
            )

        def resetInkBox(self):
            pass

    class RichLayer(type(native.layer)):
        @property
        def isMasterLayer(self):
            return self.name in native.package.masters or ":" in self.name

        @isMasterLayer.setter
        def isMasterLayer(self, value):
            pass

        def clone(self):
            clone = deepcopy(self)
            clone.id = next(serial)
            for shape in clone.shapes:
                shape.id = next(serial)
                shape.active, shape.shapeData.name = False, ""
                for contour in shape.contours:
                    contour.id = next(serial)
                    for node in contour.nodes():
                        node.id = next(serial)
                        node.nodeState ^= 0x3008
            return clone

        def takeShapes(self, kind):
            assert kind == 7
            shapes, self.shapes = self.shapes, []
            return shapes

        def addShape(self, shape):
            self.shapes.append(shape)

        def resetInkBox(self):
            pass

    for layer in (native.layer, native.layer.mask):
        layer.__class__ = RichLayer
        layer.lib = {"nested": [1]}
        layer.unprojected = {"native": ["retained"]}
        layer.wireframeColor = 123
        layer.shapes = [Shape(), Shape(True), Shape()]
    return native


def test_native_snapshot_repairs_omissions_and_keeps_mixed_order(native_copy):
    n = native_copy
    snapshot = n.backend.snapshot_layer(n.lid)
    n.layer.advanceWidth = 999
    n.layer.unprojected["native"].append("later")
    token = n.backend.append_layer(n.gid, n.mid, "Dated copy", snapshot)
    added = n.backend._object(token)
    assert added.advanceWidth == 500 and added.name == "Dated copy"
    assert [s.isComponent for s in added.shapes] == [False, True, False]
    assert all(s.active and s.shapeData.name == "owned data" for s in added.shapes)
    assert added.shapes[1].shapeData.componentLayer == "Regular"
    assert n.glyph.layers[-2].name == "mask.Dated copy"
    assert n.glyph.activeLayer is n.bold and added.wireframeColor == 123
    assert {s.id for s in added.shapes}.isdisjoint(s.id for s in n.layer.shapes)
    assert added.unprojected == {"native": ["retained"]}
    for copied_layer, source in ((added, n.layer), (n.glyph.layers[-2], n.layer.mask)):
        assert copied_layer.shapes[0].contours[0].nodes()[0].nodeState == 0x3009
        assert (
            copied_layer.shapes[0].contours[0].nodes()[0].id
            != source.shapes[0].contours[0].nodes()[0].id
        )


@pytest.mark.parametrize("phase", ["prepare", "mask", "foreground", "update", "notify"])
def test_native_failure_rolls_back_and_retry_does_not_duplicate(native_copy, phase):
    n = native_copy
    snapshot = n.backend.snapshot_layer(n.lid)
    before = list(n.glyph.layers)
    add, update, notify = n.glyph.addLayer, n.glyph.update, n.backend._notify

    def fail():
        raise RuntimeError("injected")

    if phase in {"mask", "foreground"}:

        def insert(layer, back):
            add(layer, back)
            if layer.name.startswith("mask.") == (phase == "mask"):
                fail()

        n.glyph.addLayer = insert
    elif phase == "update":
        attempts = []

        def update_once():
            attempts.append(1)
            if len(attempts) == 1:
                fail()

        n.glyph.update = update_once
    else:

        def publish(*args, **kwargs):
            if bool(kwargs.get("post")) == (phase == "notify"):
                fail()
            return notify(*args, **kwargs)

        n.backend._notify = publish
    with pytest.raises(RuntimeError, match="injected"):
        n.backend.append_layer(n.gid, n.mid, "Dated copy", snapshot)
    assert n.glyph.layers == before and n.glyph.activeLayer is n.bold
    assert not n.backend._changed and not n.backend._prepared
    n.glyph.addLayer, n.glyph.update, n.backend._notify = add, update, notify
    n.backend.append_layer(n.gid, n.mid, "Dated copy", snapshot)
    assert [l.name for l in n.glyph.layers] == [
        "Regular",
        "Bold",
        "mask.Dated copy",
        "Dated copy",
    ]


def test_native_rollback_failure_is_explicit(native_copy):
    from fontlab_glyport.errors import PartialFailure

    n = native_copy
    snapshot = n.backend.snapshot_layer(n.lid)
    n.glyph.update = lambda: False

    def fail(_):
        raise RuntimeError("cannot remove")

    n.glyph.removeLayer = fail
    with pytest.raises(PartialFailure):
        n.backend.append_layer(n.gid, n.mid, "Dated copy", snapshot)


def test_native_public_same_object_and_retry_boundary(native_copy):
    n = native_copy
    layer = n.proxy.layers[0]
    draft = layer.copy()
    detached_background = draft.background
    draft.name = "Public copy"
    original_notify = n.backend._notify

    def fail_post(*args, **kwargs):
        if kwargs.get("post"):
            raise RuntimeError("publish failed")
        return original_notify(*args, **kwargs)

    n.backend._notify = fail_post
    with pytest.raises(RuntimeError, match="publish failed"):
        n.proxy.layers.append(draft)
    assert draft.parent is None and draft.name == "Public copy"
    assert [l.name for l in n.glyph.layers] == ["Regular", "Bold"]
    n.backend._notify = original_notify
    n.proxy.layers.append(draft)
    assert draft.parent is n.proxy and n.proxy.layers[draft.layerId] is draft
    assert draft.width == 500 and draft.userData["nested"] == [1]
    assert len(n.glyph.layers) == 4
    captured_reference = detached_background._component_layers["A"]
    assert captured_reference is not draft and captured_reference.parent is None
    assert captured_reference.width == 500
    draft.width = 901
    assert captured_reference.width == 500


@pytest.mark.parametrize(
    "failure", ["foreground", "mask", "reference", "glyph", "auto", "role"]
)
def test_native_validation_refuses_without_notifications(native_copy, failure):
    n = native_copy
    snapshot = n.backend.snapshot_layer(n.lid)
    name = "Copy"
    if failure in {"foreground", "mask"}:
        n.bold.name = "COPY" if failure == "foreground" else "MASK.COPY"
    elif failure == "reference":
        snapshot.foreground.shapes[1].shapeData.componentLayer = "Missing"
    elif failure == "glyph":
        snapshot.foreground.shapes[1].shapeData.componentGlyph = "Missing"
    elif failure == "auto":
        snapshot.foreground.autoLayer = True
    else:
        name = "Intermediate:400"
    before = list(n.glyph.layers)
    with pytest.raises((ValueError, UnsupportedCapability)):
        n.backend.append_layer(n.gid, n.mid, name, snapshot)
    assert n.glyph.layers == before and not n.calls


def test_native_association_survives_enumeration_peers_and_history(
    native_copy, monkeypatch
):
    from fontlab_glyport.model.fontlab_backend import FontLabBackend

    n = native_copy
    bold = n.font.masters[1].id
    token = n.backend.append_layer(n.gid, bold, "Copy", n.backend.snapshot_layer(n.lid))
    assert n.backend.glyph_layers(n.gid)[-1].masterId == bold
    assert n.backend.layer(n.gid, token).masterId == bold
    peer = FontLabBackend(packages=[n.package])
    monkeypatch.setattr(peer, "_native", lambda: n.module)
    other_font = Model(peer).font
    other = other_font.glyphs[0]
    assert list(other.layers)[-1].associatedMasterId == other_font.masters[1].id
    added = n.backend._object(token)
    replacement = deepcopy(added)
    n.glyph.layers[-1] = replacement
    added.isValid = False
    n.marker += 1
    assert n.backend.layer(n.gid, token).masterId == bold
    assert n.backend._object(token) is replacement


def test_native_missing_mask_does_not_create_one(native_copy):
    n = native_copy
    n.layer.mask = None
    token = n.backend.append_layer(
        n.gid, n.mid, "Copy", n.backend.snapshot_layer(n.lid)
    )
    assert len(n.glyph.layers) == 3
    assert n.backend._object(token).getMaskLayer(False) is None


def test_native_removed_history_children_stay_stale_on_redo(native_copy):
    from fontlab_glyport.errors import StaleNativeObject

    n = native_copy
    source = n.proxy.layers[0]
    source_node = source.paths[0].nodes[0]
    draft = source.copy()
    draft.name = "History copy"
    n.proxy.layers.append(draft)
    node = draft.paths[0].nodes[0]
    added = n.glyph.layers[-2:]
    n.glyph.layers = n.glyph.layers[:-2]
    n.marker += 1
    with pytest.raises(StaleNativeObject):
        _ = node.x
    assert source_node.x == 10
    n.glyph.layers.extend(added)
    n.marker += 1
    revived = list(n.proxy.layers)[-1]
    assert revived.name == "History copy" and revived.paths[0].nodes[0].x == 10
    with pytest.raises(StaleNativeObject):
        _ = node.x


def test_native_grouped_append_keeps_one_prepare_and_existing_pending_edits(
    native_copy,
):
    n = native_copy
    n.backend.begin_undo("Copies")
    snapshot = n.backend.snapshot_layer(n.lid)
    first = n.backend.append_layer(n.gid, n.mid, "One", snapshot)
    second = n.backend.append_layer(n.gid, n.mid, "Two", snapshot)
    assert len(n.calls) == 1, "one glyph baseline is prepared for the enclosing group"
    assert first != second and len(n.glyph.layers) == 6
    n.backend.end_undo()
    assert len(n.calls) == 2 and not n.backend._changed
    assert n.glyph.activeLayer is n.bold


def test_native_association_is_visible_during_publication(native_copy):
    n = native_copy
    bold = n.font.masters[1].id
    notify = n.backend._notify

    def observe(*args, **kwargs):
        if kwargs.get("post"):
            assert n.backend.glyph_layers(n.gid)[-1].masterId == bold
        return notify(*args, **kwargs)

    n.backend._notify = observe
    n.backend.append_layer(n.gid, bold, "Copy", n.backend.snapshot_layer(n.lid))
