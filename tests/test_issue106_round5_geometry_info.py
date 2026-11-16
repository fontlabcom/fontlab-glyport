# this_file: tests/test_issue106_round5_geometry_info.py
"""Detached geometry and database metadata never depend on native handles."""

from copy import deepcopy
from dataclasses import replace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.glyph_info import glyph_info
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.backend import ComponentInfo, GlyphInfo, LayerInfo
from fontlab_glyport.model.copies import DetachedLayer
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def geometry():
    from fontlab_glyport.fonttools import fonttools_module

    try:
        fonttools_module("pens.boundsPen", "DetachedLayer.bounds.dependency")
    except UnsupportedCapability:
        pytest.skip("requires geometry extra or FontLab's bundled fontTools")


@pytest.fixture
def glyphdata():
    pytest.importorskip("glyphsLib.glyphdata")


def test_m3_layer_copy_when_curved_then_exact_bounds_and_sidebearings_after_font_close(
    geometry,
):
    backend = FakeBackend()
    backend.layers["glyph", "master"] = replace(
        backend.layers["glyph", "master"], components=(), shape_ids=("path",)
    )
    layer = Model(backend).font.glyphs[0].layers[0].copy()
    layer.paths = [
        GSPath(
            [
                GSNode((10, 0)),
                GSNode((10, 100), "offcurve"),
                GSNode((110, 100), "offcurve"),
                GSNode((110, 0), "curve"),
            ],
            closed=False,
        )
    ]
    backend.close_font("font")
    assert layer.bounds == ((10, 0), (100, 75))
    assert (layer.LSB, layer.RSB) == (10, 390)
    layer.LSB = 30
    assert layer.bounds == ((30, 0), (100, 75))
    assert layer.width == 520 and layer.RSB == 390
    layer.RSB = 40
    assert layer.width == 170 and layer.LSB == 30
    clone = deepcopy(layer)
    clone.applyTransform((1, 0, 0, 1, 7, -10))
    assert clone.bounds == ((37, -10), (100, 75))
    assert layer.bounds.origin.x == 30


def test_m3_empty_detached_layer_when_measured_then_zero_bounds_and_sidebearing_writes():
    layer = DetachedLayer()
    layer.width = 400
    assert layer.bounds == ((0, 0), (0, 0)) and layer.LSB == 0 and layer.RSB == 400
    layer.decomposeComponents()
    layer.removeOverlap()
    layer.LSB = 20
    assert layer.width == 400 and layer.LSB == 0
    layer.RSB = 20
    assert layer.width == 20 and layer.RSB == 20


def test_m3_component_copy_when_decomposed_then_snapshot_transforms_and_order_preserved(
    geometry,
):
    backend = FakeBackend()
    backend.glyph_lists["font"] += (GlyphInfo("base", "base", ()),)
    path = replace(
        GSPath([GSNode((0, 0)), GSNode((20, 10))], closed=False)._data(), id="base-path"
    )
    path = replace(
        path,
        nodes=tuple(replace(n, id=f"base-node-{i}") for i, n in enumerate(path.nodes)),
    )
    backend.layers["base", "master"] = LayerInfo(
        "base-layer", "master", 20, (path,), shape_ids=("base-path",)
    )
    backend.layers["glyph", "master"] = replace(
        backend.layers["glyph", "master"],
        components=(ComponentInfo("component", "base", (2, 0, 0, 3, 50, -20)),),
    )
    layer = Model(backend).font.glyphs[0].layers[0].copy()
    backend.close_font("font")
    assert layer.bounds == ((0, -20), (90, 30))
    clone = deepcopy(layer)
    clone.decomposeComponents()
    assert len(clone.components) == 0 and len(clone.paths) == 2
    assert clone.paths[-1].nodes[-1].position == (90, 10)
    assert clone.bounds == layer.bounds and len(layer.components) == 1
    assert layer.copyDecomposedLayer().bounds == layer.bounds


@pytest.mark.parametrize("method", ["bounds", "decomposeComponents"])
def test_m3_cyclic_components_when_used_then_named_refusal_without_partial_mutation(
    method,
):
    layer = Model(FakeBackend()).font.glyphs[0].layers[0].copy()
    with pytest.raises(UnsupportedCapability) as error:
        value = getattr(layer, method)
        if callable(value):
            value()
    assert error.value.capability == f"DetachedLayer.{method}.cyclicComponent"
    assert "_font" not in str(error.value) and len(layer.components) == 1


@pytest.mark.parametrize("method", ["glyphMetrics", "removeOverlap"])
def test_m3_host_only_copy_operations_when_unavailable_then_precise_refusal(
    method, monkeypatch
):
    layer = DetachedLayer()
    layer.paths = [GSPath([GSNode((0, 0)), GSNode((20, 20))])]
    before = list(layer.paths)
    if method == "removeOverlap":
        import sys

        monkeypatch.setitem(sys.modules, "pathops", None)
    with pytest.raises(UnsupportedCapability) as error:
        getattr(layer, method)()
    assert error.value.capability == f"DetachedLayer.{method}" + (
        ".dependency" if method == "removeOverlap" else ""
    )
    assert "_font" not in str(error.value) and list(layer.paths) == before


@pytest.mark.parametrize("font", [None, Model(FakeBackend()).font])
def test_f13_known_name_absent_from_font_when_queried_then_metadata_and_canonical_components(
    font,
    glyphdata,
    owned_composition_info,
):
    info = glyph_info(font, "Aacute")
    assert (
        info.name == "Aacute" and info.unicode == "00C1" and info.category == "Letter"
    )
    assert [c.name for c in info.components] == ["A", "acutecomb"]
    assert info.components[-1].unicode == "0301"
    assert info.components[-1].category == "Mark"
    assert glyph_info(font, "Zcaron").unicode == "017D"
    assert glyph_info(font, "uni00C1").name == "Aacute"
    assert glyph_info(font, "certainly-not-in-glyph-data-106") is None, (
        "A known missing manager record is nil, not an unsupported selector"
    )


def test_f13_outline_component_is_not_a_metadata_recipe(
    glyphdata,
    owned_composition_info,
):
    backend = FakeBackend()
    layer = backend.layers["glyph", "master"]
    backend.layers["glyph", "master"] = replace(
        layer, components=(replace(layer.components[0], componentName="acutecomb"),)
    )
    font = Model(backend).font
    info = glyph_info(font, "A")
    assert font.glyphs["A"].layers[0].components[0].componentName == "acutecomb"
    assert info.components == [], (
        "Metadata must not borrow the font's outline components"
    )


def test_f13_unknown_component_when_parent_known_then_parent_metadata_remains_available(
    owned_composition_info,
):
    backend = FakeBackend()
    layer = backend.layers["glyph", "master"]
    backend.layers["glyph", "master"] = replace(
        layer,
        components=(replace(layer.components[0], componentName="missing-helper-106"),),
    )
    info = glyph_info(Model(backend).font, "A")
    assert info.name == "A" and info.unicode == "0041" and info.components == []
    suffix = glyph_info(None, "A.not-in-the-database")
    assert suffix.productionName == "A.not-in-the-database", (
        "Audited generic suffixes do not require a stored full-name record"
    )
