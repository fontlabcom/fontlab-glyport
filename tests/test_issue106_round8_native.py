# this_file: tests/test_issue106_round8_native.py
"""Native-boundary doubles: no FontLab process or native probes required."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_issue106_round7_native import Layer
from test_issue106_round7_native import native as native_double

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import GlyphInfo
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture(name="native")
def native_backend(monkeypatch):
    return native_double.__wrapped__(monkeypatch)


def point(x, y):
    return NS(x=lambda: x, y=lambda: y)


def test_selection_native_with_anchor_returns_selected_nodes(native, monkeypatch):
    b = native.backend
    node = NS(
        id=71,
        isValid=True,
        position=point(1, 2),
        smooth=False,
        nodeState=0x21,
        selected=True,
        isOff=lambda: False,
        isCurve=lambda: False,
    )
    contour = NS(id=72, isValid=True, nodes=lambda: [node], closed=False, isTT=False)
    shape = NS(
        id=73,
        isComposite=False,
        isComponent=False,
        contours=[contour],
        transform=NS(map=lambda p: p),
    )
    native.layer.shapes = [shape]
    native.layer.anchors = [NS(id=74, isValid=True, name="top", point=point(1, 20))]
    info = b._read_layer(native.fid, native.layer, native.mid, native.gid)
    template = FakeBackend().font_info("font")
    monkeypatch.setattr(
        b,
        "font_info",
        lambda fid: replace(
            template,
            id=native.fid,
            masters=(replace(template.masters[0], id=native.mid),),
        ),
    )
    monkeypatch.setattr(
        b, "glyphs", lambda fid: (GlyphInfo(native.gid, "A", ("0041",)),)
    )
    monkeypatch.setattr(b, "layer", lambda glyph, master: info)
    layer = Model(b)._font(native.fid).glyphs[0].layers[0]
    assert list(layer.selection) == [layer.paths[0].nodes[0]]
    with pytest.raises(UnsupportedCapability) as error:
        _ = layer.anchors[0].selected
    assert error.value.capability == "GSAnchor.selected"
    node.selected = False
    assert list(layer.selection) == [], (
        "node editor selection is live even without history changes"
    )


def test_mask_hint_reads_and_writes_use_actual_mask_name(native, monkeypatch):
    native.layer.name = "Regular"
    native.glyph.name = "A"
    mask = Layer(31)
    mask.name = "Mask Regular"
    native.layer.mask = mask
    b = native.backend
    lid = b.background_layer(native.lid).id
    seen = []
    monkeypatch.setattr(b, "_tool_font", lambda *args: 10)

    def tool(name, capability, **kw):
        seen.append((name, kw))
        return {"hints": []}

    monkeypatch.setattr(
        b,
        "_resolve_tool",
        lambda name, capability: lambda **kw: tool(name, capability, **kw),
    )
    assert b.hints(lid) == ()
    b._edit_hints(lid, {"action": "clear"}, "GSLayer.hints")
    assert [kw["layer_name"] for _, kw in seen] == ["Mask Regular", "Mask Regular"]
    assert native.calls[-1][1] == [mask, native.glyph]


def test_mask_indexed_shape_order_reads_mask_never_foreground(native, monkeypatch):
    b = native.backend
    mask = Layer(31)
    mask.name = "Mask Regular"
    native.layer.mask = mask
    lid = b.background_layer(native.lid).id
    component = NS(id=40, isValid=True)
    cid = b._register((native.fid, "component", 40), component, lid)
    seen = []

    def read(document, layer, master, glyph, background=False, *, layer_key=None):
        assert layer_key == native.mid
        seen.append((layer, background))
        return NS(shape_ids=(cid,))

    monkeypatch.setattr(b, "_read_layer", read)
    assert b._shape_at(lid, 0) is component
    assert b._shape_at(lid, 1) is None
    assert seen == [(mask, True), (mask, True)]


@pytest.mark.parametrize(
    "source,native_value",
    [("=H", "H"), ("=|n", "|n"), ("==H", "H"), ("==H+12", "H+12"), (None, "")],
)
def test_metrics_translation_and_roundtrip(native, source, native_value):
    b = native.backend
    b.set_layer_metrics_key(native.lid, "left", source)
    assert native.layer.metricsLeft == native_value
    assert b.layer_metrics_key(native.lid, "left") == source
    native.layer.metricsLeft = "Other"
    assert b.layer_metrics_key(native.lid, "left") == "=Other"


@pytest.mark.parametrize(
    "side,source",
    [("width", "=|n"), ("left", "=rsb(H)"), ("right", "==H*2"), ("left", "=H=1")],
)
def test_unknown_metrics_syntax_refuses_before_mutation(native, side, source):
    with pytest.raises(UnsupportedCapability) as error:
        native.backend.set_layer_metrics_key(native.lid, side, source)
    assert error.value.capability == f"GSLayer.{side}MetricsKey.syntax"
    assert not native.calls


def test_guide_readback_mismatch_publishes_even_when_refusing(native):
    class ReidsGuides(Layer):
        @property
        def guidelines(self):
            return self._guides

        @guidelines.setter
        def guidelines(self, value):
            self._guides = [NS(id=g.id + 100, isValid=True) for g in value]

    layer = ReidsGuides(30)
    first, second = NS(id=80, isValid=True), NS(id=81, isValid=True)
    layer._guides = [first, second]
    b = native.backend
    b._objects[native.lid] = layer
    token = b._register((native.fid, "guide", first.id), first, native.lid)
    with pytest.raises(UnsupportedCapability):
        b.remove_guide(native.lid, token)
    assert [g.id for g in layer.guidelines] == [181]
    assert native.calls[-1][1] == [layer, native.glyph]


def test_native_collection_rollback_restores_original_tokens_objects_and_order(native):
    b = native.backend
    original_shape = NS(id=90, isValid=True)
    original_anchor = NS(id=91, isValid=True)
    native.layer.shapes = [original_shape]
    native.layer.anchors = [original_anchor]
    native.layer.removeAllShapes = lambda: native.layer.shapes.clear()
    native.layer.addShapes = lambda shapes: native.layer.shapes.extend(shapes)
    native.layer.clearAnchors = lambda: native.layer.anchors.clear()
    native.layer.addAnchor = lambda anchor: native.layer.anchors.append(anchor)
    token = b._register((native.fid, "anchor", 91), original_anchor, native.lid)
    b._layer_members[native.lid] = {token}
    state = b.snapshot_collection(native.lid)
    b._invalidate(token)
    added = NS(id=92, isValid=True)
    new = b._register((native.fid, "anchor", 92), added, native.lid)
    b._layer_members[native.lid] = {new}
    native.layer.anchors = [added]
    native.layer.shapes = []
    b.restore_collection(native.lid, state)
    assert b.is_valid(token) and not b.is_valid(new)
    assert b._objects[token] is original_anchor
    assert native.layer.shapes == [original_shape] and native.layer.anchors == [
        original_anchor
    ]
    assert native.calls[-1][1] == [native.layer, native.glyph]


def test_undo_validation_does_not_resolve_unrelated_unresolved_glyphs(native):
    b = native.backend
    for i in range(100):
        b._register((native.fid, "glyph", 1000 + i), None, native.fid)
    native.package.findFgId = lambda *_: pytest.fail("unrelated glyph resolution")
    b.begin_undo("One layer")
    b.set_layer_width(native.lid, 900)
    assert b.can_publish_undo(native.fid)
    b.end_undo()
    assert native.calls[-1][1] == [native.layer, native.glyph]


def test_native_revision_tracks_host_history_and_glyph_count(native):
    history = [1]
    native.package.currentHistoryState = lambda: history[0]
    native.package.glyphsCount = 100
    first = native.backend.revision(native.fid)
    history[0] += 1
    second = native.backend.revision(native.fid)
    native.package.glyphsCount += 1
    assert first != second != native.backend.revision(native.fid)


def test_empty_mask_hint_write_refuses_without_creating_mask(native):
    b = native.backend
    lid = b.background_layer(native.lid).id
    assert b.hints(lid) == ()
    with pytest.raises(UnsupportedCapability) as error:
        b._edit_hints(lid, {"action": "clear"}, "GSLayer.hints")
    assert error.value.capability == "GSLayer.background.hints"
    assert native.layer.mask is None and not native.calls


def test_unmapped_native_selection_and_styles_refuse_at_public_api(native):
    b = native.backend
    for call, capability in (
        (lambda: b.glyph_selected(native.fid, native.gid), "GSGlyph.selected"),
        (
            lambda: b.set_glyph_selected(native.fid, native.gid, True),
            "GSGlyph.selected",
        ),
        (lambda: b.path_attributes("unmapped-style"), "GSPath.attributes"),
        (lambda: b.set_path_attributes("unmapped-style", {}), "GSPath.attributes"),
        (
            lambda: b.set_master_zone(native.mid, 0, 700, 10),
            "GSFontMaster.alignmentZones",
        ),
    ):
        with pytest.raises(UnsupportedCapability) as error:
            call()
        assert error.value.capability == capability
    assert not native.calls


def test_native_master_guides_and_zones_are_read_in_correct_master_then_restored(
    native,
):
    p = native.package
    p.master = "Other"
    changes = []

    def master(name):
        changes.append(name)
        p.master = name

    p.setMaster = master
    p.guidelines = [
        NS(
            id=95,
            isValid=True,
            isHint=False,
            centerPoint=point(3, 4),
            angle=90,
            name="global",
        ),
        NS(id=96, isValid=True, isHint=True),
    ]
    p.ps_zonesT = [NS(position=700, width=15)]
    p.ps_zonesB = [NS(position=0, width=10)]
    b = native.backend
    guides = b.master_guides(native.mid)
    assert [(g.x, g.y, g.angle, g.name) for g in guides] == [(3, 4, 90, "global")]
    assert b.master_zones(native.mid) == ((700, 15), (0, -10))
    assert p.master == "Other" and changes == ["Regular", "Other", "Regular", "Other"]


def test_append_glyph_registers_added_id_without_listing_entire_font(
    native, monkeypatch
):
    b = native.backend
    added = NS(id=210, isValid=True, fgGlyphId=211)
    exists = []
    native.package.findName = lambda name: added if exists else None
    native.package.addGlyph = lambda glyph: exists.append(glyph)
    native.module.flGlyph = lambda: NS(name="")
    native.module.flGlyph.updatedFgGlyphs = lambda: ()
    monkeypatch.setattr(
        b, "_resolve_tool", lambda *args: lambda **kwargs: exists.append(kwargs)
    )
    monkeypatch.setattr(b, "glyphs", lambda fid: pytest.fail("append scanned the font"))
    token = b.append_glyph(native.fid, "New")
    assert b._glyph_native_ids[token] == 211 and b._glyph_names[token] == "New"
    assert b._objects[token] is added


def test_mask_with_foreground_name_refuses_hints_before_any_tool_or_mutation(
    native, monkeypatch
):
    mask = Layer(31)
    mask.name = "Regular"
    native.glyph.name = "A"
    native.layer.mask = mask
    b = native.backend
    lid = b.background_layer(native.lid).id
    monkeypatch.setattr(b, "_tool_font", lambda *args: 10)
    monkeypatch.setattr(
        b, "_tool", lambda *args, **kwargs: pytest.fail("foreground tool call")
    )
    for call in (lambda: b.hints(lid), lambda: b._edit_hints(lid, {}, "GSLayer.hints")):
        with pytest.raises(UnsupportedCapability) as error:
            call()
        assert error.value.capability == "GSLayer.background.hints"
    assert not native.calls


def test_indexed_mask_path_insertion_preserves_foreground_and_uses_mask_order(native):
    from fontlab_glyport.model.backend import PathInfo

    b = native.backend
    foreground_shape = object()  # any attempt to enumerate it as geometry fails
    native.layer.shapes = [foreground_shape]
    mask = Layer(31)
    mask.name = "Mask Regular"
    native.layer.mask = mask
    transform = NS(
        isAffine=lambda: True,
        m11=lambda: 1,
        m12=lambda: 0,
        m21=lambda: 0,
        m22=lambda: 1,
        dx=lambda: 0,
        dy=lambda: 0,
    )
    component = NS(
        id=120,
        isValid=True,
        isComposite=True,
        isComponent=True,
        shapeData=NS(componentGlyph="A"),
        transform=transform,
    )
    mask.shapes = [component]
    lid = b.background_layer(native.lid).id

    class Shape:
        id = 121

        def __init__(self):
            self.contours = []

        def addContour(self, contour, clone):
            assert clone is True
            self.contours.append(contour)

    native.module.flShape = Shape
    native.module.flContour = lambda nodes, *, closed: NS(id=122, isValid=True)

    def insert(index, shape):
        mask.shapes.insert(index, shape)
        return shape

    mask.insertShape = insert
    token = b.insert_path(lid, 0, PathInfo("", (), False))
    assert native.layer.shapes == [foreground_shape]
    assert isinstance(mask.shapes[0], Shape) and mask.shapes[1] is component
    assert b._parents[token] == lid
    assert native.calls[-1][1] == [mask, native.glyph]
