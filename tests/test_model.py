# this_file: tests/test_model.py
"""Live model contract, tested without a native host."""

import sys

import pytest

from fontlab_glyport.errors import (
    StaleNativeObject,
    UnsupportedAttribute,
    UnsupportedCapability,
)
from fontlab_glyport.model import GSAnchor, GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.proxies import _Explicit


def test_live_lookup_identity_and_mutations():
    backend = FakeBackend()
    model = Model(backend)
    font = model.fonts[0]
    assert model.font is font is model.fonts[-1]
    assert font.familyName == "Example" and font.unitsPerEm == font.upm == 1000
    glyph = font.glyphs["A"]
    assert glyph is font.glyphs[0] is font.glyphs["0041"] is font.glyphs["A"]
    assert "0041" in font.glyphs and glyph in font.glyphs
    master = font.masters[-1]
    layer = glyph.layers[master.id]
    assert layer is glyph.layers[0]
    assert layer.paths[0] is layer.shapes[0]
    node = layer.paths[0].nodes[-1]
    node.position = (30, 40)
    node.x = 50
    node.y = 60
    assert node.position == (50, 60)
    assert node.type == "line" and not node.smooth
    layer.width = 700
    assert glyph.layers[0].width == 700
    path = layer.paths.append(GSPath([GSNode((1, 2))], closed=False))
    assert not path.closed and len(layer.paths) == 2
    anchor = layer.anchors.append(GSAnchor("top", (10, 20)))
    assert layer.anchors["top"] is anchor
    assert anchor.position == (10, 20)
    layer.paths.remove(path)
    with pytest.raises(StaleNativeObject):
        _ = path.nodes
    with pytest.raises(StaleNativeObject):
        _ = path.closed
    assert len(layer.paths) == 1


def test_stale_document_and_explicit_unsupported():
    backend = FakeBackend()
    font = Model(backend).font
    layer = font.glyphs[0].layers[0]
    paths = layer.paths
    with pytest.raises(UnsupportedCapability):
        _ = font.stems
    font.familyName = "Other"
    assert font.familyName == "Other"
    backend.close_font(font.id)
    for read in (lambda: font.familyName, lambda: layer.width, lambda: len(paths)):
        with pytest.raises(StaleNativeObject):
            read()


def test_undo_balanced_on_error_and_nested():
    backend = FakeBackend()
    font = Model(backend).font
    with pytest.raises(ValueError), font.undo_group("Edit"):
        with font.undo_group("Nested"):
            font.glyphs[0].layers[0].width = 123
        raise ValueError("script failed")
    assert backend.undo_events == [("begin", "Edit"), ("end", None)]
    assert font.glyphs[0].layers[0].width == 123


def test_collection_boundaries_and_document_cache():
    backend = FakeBackend()
    model = Model(backend)
    font = model.font
    assert list(model.fonts) == [font]
    assert next(iter(font.glyphs)) is font.glyphs[-1]
    assert font.glyphs[:][0] is font.glyphs[0]
    with pytest.raises(IndexError):
        _ = font.glyphs[-2]
    assert font.glyphs["missing"] is None
    assert "missing" not in font.glyphs
    assert font.glyphs[0] is not Model(backend).font.glyphs[0]
    with pytest.raises(UnsupportedCapability):
        font.glyphs.append(font.glyphs[0])


def test_component_shape_order_and_readonly_fields():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    component = layer.components[0]
    assert component is layer.shapes[-1]
    assert component.componentName == "A"
    assert component.transform == (1, 0, 0, 1, 0, 0)
    assert layer.paths[0].nodes[0].position.x == 0
    with pytest.raises(ValueError, match="six finite"):
        component.transform = ()
    with pytest.raises(UnsupportedCapability):
        layer.paths[0].closed = False
    layer.paths[0].nodes[0].type = "curve"
    assert layer.paths[0].nodes[0].type == "curve"
    layer.shapes.remove(component)
    assert len(layer.shapes) == 1 and not layer.components


def test_draft_construction_and_copy_identity():
    path = GSPath()
    node = GSNode()
    node.type = "offcurve"
    node.smooth = True
    node.position = (12, 34)
    path.nodes.append(node)
    assert path.nodes[-1] is node
    path.closed = False
    anchor = GSAnchor()
    anchor.name = "top"
    anchor.position = (1, 2)
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    added = layer.shapes.append(path)
    assert added is layer.paths[-1]
    assert added.nodes[0].type == "offcurve" and added.nodes[0].smooth
    node.x = 99
    assert added.nodes[0].x == 12
    layer.anchors.append(anchor)
    assert layer.anchors["top"].position == (1, 2)
    path.nodes.remove(node)
    assert len(path.nodes) == 0
    with pytest.raises(ValueError):
        node.type = "invalid"
    with pytest.raises(TypeError):
        path.nodes.append(object())


def test_stale_node_and_retained_collections_after_path_deletion():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    path = layer.paths[0]
    nodes = path.nodes
    node = nodes[0]
    layer.paths.remove(path)
    for read in (lambda: node.x, lambda: len(nodes), lambda: list(nodes)):
        with pytest.raises(StaleNativeObject):
            read()
    with pytest.raises(StaleNativeObject):
        node.position = (1, 2)
    with pytest.raises(ValueError):
        layer.paths.remove(path)


def test_empty_fonts_and_protocol():
    from fontlab_glyport.model import ModelBackend
    from fontlab_glyport.model.fontlab_backend import FontLabBackend

    backend = FakeBackend()
    assert isinstance(backend, ModelBackend)
    assert isinstance(FontLabBackend(), ModelBackend)
    model = Model(backend)
    backend.close_font("font")
    assert model.font is None and len(model.fonts) == 0


def test_multiple_documents_order_identity_and_character_lookup():
    from dataclasses import replace

    from fontlab_glyport.model.backend import GlyphInfo, MasterInfo

    backend = FakeBackend()
    backend.fonts["second"] = replace(
        backend.fonts["font"],
        id="second",
        masters=(MasterInfo("second-master", "Bold"),),
    )
    backend.glyph_lists["second"] = (GlyphInfo("second-glyph", "Uhorn", ("01AF",)),)
    backend.layers["second-glyph", "second-master"] = replace(
        backend.layers["glyph", "master"],
        id="second-layer",
        masterId="second-master",
        paths=(),
        components=(),
        shape_ids=(),
    )
    model = Model(backend)
    first, second = model.fonts
    backend.current = "second"
    assert model.font is second
    assert second.glyphs["Ư"] is second.glyphs["01AF"] is second.glyphs["Uhorn"]
    assert second.masters["Bold"] is second.masters[-1]
    assert second.glyphs[0].layers[0] is not first.glyphs[0].layers[0]
    backend.close_font("font")
    assert list(model.fonts) == [second]
    assert second.familyName == "Example"


def test_bad_mutations_do_not_change_model():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    for collection in (layer.paths, layer.anchors):
        with pytest.raises(TypeError):
            collection.append(object())
    layer.anchors.append(GSAnchor("top"))
    with pytest.raises(ValueError):
        layer.anchors.append(GSAnchor("top"))
    assert len(layer.anchors) == 1
    with pytest.raises(TypeError):
        _ = layer.paths[object()]
    assert len(layer.paths) == 1


def test_undo_begin_failure_does_not_end_or_mutate():
    class FailingBackend(FakeBackend):
        def begin_undo(self, name):
            raise RuntimeError("begin failed")

    backend = FailingBackend()
    font = Model(backend).font
    with pytest.raises(RuntimeError), font.undo_group("edit"):
        font.glyphs[0].layers[0].width = 10
    assert backend.undo_events == []
    assert font.glyphs[0].layers[0].width == 500


@pytest.mark.parametrize("node_type", ["line", "curve", "offcurve", "qcurve"])
def test_backend_snapshots_reflect_all_node_types_and_writes(node_type):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    path = layer.paths.append(GSPath([GSNode((-100, 1e9), node_type, True)]))
    node = path.nodes[0]
    node.position = (0, -123)
    layer.width = -10
    snapshot = backend.layer("glyph", "master")
    assert snapshot.width == -10
    assert snapshot.paths[-1].nodes[0].type == node_type
    assert snapshot.paths[-1].nodes[0].x == 0
    assert snapshot.paths[-1].nodes[0].y == -123
    layer.shapes.remove(path)
    assert not backend.is_valid(node._id)
    assert len(layer.paths) == 1


@pytest.mark.parametrize("exception", [ValueError, KeyboardInterrupt, SystemExit])
def test_undo_balances_process_exits_too(exception):
    backend = FakeBackend()
    font = Model(backend).font
    with pytest.raises(exception), font.undo_group("exit"):
        raise exception()
    assert backend.undo_events == [("begin", "exit"), ("end", None)]
    with font.undo_group("empty"):
        pass
    assert backend.undo_events[-2:] == [("begin", "empty"), ("end", None)]


def test_name_lookup_wins_over_unicode_alias():
    from fontlab_glyport.model.backend import GlyphInfo

    backend = FakeBackend()
    backend.glyph_lists["font"] += (GlyphInfo("named", "0041", ()),)
    font = Model(backend).font
    assert font.glyphs["0041"].id == "named"
    assert font.glyphs["A"].unicode == "0041"
    with pytest.raises(IndexError):
        _ = font.glyphs[10**30]


def test_empty_layer_and_stale_all_proxy_kinds():
    backend = FakeBackend()
    model = Model(backend)
    font = model.font
    glyph = font.glyphs[0]
    layer = glyph.layers[0]
    anchor = layer.anchors.append(GSAnchor("top"))
    component = layer.components[0]
    master = font.masters[0]
    path = layer.paths[0]
    layer.paths.remove(path)
    assert list(layer.paths) == [] and layer.paths["missing"] is None
    backend.close_font(font.id)
    for read in (
        lambda: master.name,
        lambda: glyph.name,
        lambda: component.transform,
        lambda: anchor.name,
    ):
        with pytest.raises(StaleNativeObject):
            read()


# Probe semantics (integration task 1) ----------------------------------------


def test_proxies_when_unknown_member_probed_then_hasattr_false_and_default():
    font = Model(FakeBackend()).font
    glyph = font.glyphs[0]
    layer = glyph.layers[0]
    assert hasattr(layer, "smartComponentPoleMapping") is False
    assert hasattr(layer, "syncMetrics") is False
    assert hasattr(font, "gridLength") is False
    assert glyph.leftMetricsKey is None
    assert getattr(layer.paths[0], "absentBounds", None) is None
    assert hasattr(layer, "shapes") and hasattr(layer, "paths")
    assert hasattr(glyph, "layers") and hasattr(font, "glyphs")


def test_proxies_when_unknown_read_uncaught_then_capability_and_script_line():
    font = Model(FakeBackend()).font
    with pytest.raises(UnsupportedCapability) as info:
        font.stems  # noqa: B018
    assert isinstance(info.value, UnsupportedAttribute)
    assert info.value.capability == "GSFont.stems"
    assert info.value.location.path == __file__
    assert info.value.location.line == sys._getframe().f_lineno - 4


def test_proxies_when_unknown_write_then_plain_unsupported_capability():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    for write in (
        lambda: setattr(layer, "vertOrigin", 1),
        lambda: setattr(layer, "layerId", "x"),
        lambda: layer.paths[0].nodes[0].__setattr__("unmappedMember", "curve"),
    ):
        with pytest.raises(UnsupportedCapability) as info:
            write()
        assert not isinstance(info.value, AttributeError)
        assert info.value.location.path == __file__


def test_proxies_when_private_name_missing_then_plain_attribute_error():
    font = Model(FakeBackend()).font
    with pytest.raises(AttributeError) as info:
        font._nothing  # noqa: B018
    assert not isinstance(info.value, UnsupportedCapability)


class _Probe(_Explicit):
    def __init__(self, other):
        self._other = other

    @property
    def inner(self):
        return self._other.notAThing

    @property
    def plain(self):
        return self._absent


def test_property_when_body_hits_unsupported_read_then_reports_inner_capability():
    probe = _Probe(Model(FakeBackend()).font)
    with pytest.raises(UnsupportedCapability) as info:
        probe.inner  # noqa: B018
    assert info.value.capability == "GSFont.notAThing"
    assert not isinstance(info.value, AttributeError)
    assert isinstance(info.value.__cause__, UnsupportedAttribute)
    assert info.value.location.path == __file__
    with pytest.raises(UnsupportedCapability):
        hasattr(probe, "inner")


def test_property_when_body_raises_plain_attribute_error_then_not_attribute_error():
    probe = _Probe(None)
    with pytest.raises(UnsupportedCapability) as info:
        probe.plain  # noqa: B018
    assert info.value.capability == "_Probe.plain"
    assert not isinstance(info.value, AttributeError)


def test_draft_when_id_read_then_unsupported_not_probe_false():
    for draft in (GSNode(), GSPath(), GSAnchor()):
        with pytest.raises(UnsupportedCapability) as info:
            hasattr(draft, "id")
        assert info.value.capability == f"{type(draft).__name__}.id"
        assert not isinstance(info.value, AttributeError)
