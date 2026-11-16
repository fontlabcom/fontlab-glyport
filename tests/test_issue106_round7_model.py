# this_file: tests/test_issue106_round7_model.py
"""Handwritten model regressions for native real-use round two."""

from copy import deepcopy

import pytest

from fontlab_glyport.errors import UnsupportedAttribute
from fontlab_glyport.model import (
    GSAnchor,
    GSComponent,
    GSGuide,
    GSLayer,
    GSNode,
    GSPath,
    Model,
)
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def test_f33_empty_layer_and_selected_layer_copy_are_detached(font):
    layer = GSLayer()
    assert isinstance(layer, GSLayer) and not layer.shapes and layer.parent is None
    layer.width = 321
    layer.paths.append(GSPath([GSNode((11, 23))]))
    assert layer.copy().width == 321
    selected = font.glyphs[0].layers[0]
    detached = selected.copy()
    detached.width = 42
    assert selected.width != detached.width
    master = font.selectedFontMaster
    assert isinstance((master.italicAngle, master.xHeight, master.capHeight), tuple)


def test_f29_background_is_independent_persistent_and_copyable(font):
    foreground = font.glyphs[0].layers[0]
    background = foreground.background
    assert isinstance(background, GSLayer) and not background.shapes
    background.paths = [GSPath([GSNode((31, 42))])]
    assert foreground.background.paths[0].nodes[0].position == (31, 42)
    assert foreground.paths[0].nodes[0].position == (0, 0)
    assert not background.isMasterLayer
    assert background.foreground() is foreground
    detached = deepcopy(background)
    detached.paths[0].nodes[0].x = 100
    assert background.paths[0].nodes[0].x == 31


def test_f30_tabs_expose_current_edit_view_after_opening(font):
    assert list(font.tabs) == []
    tab = font.newTab("/A")
    assert font.tabs[-1]._tab_id == tab._tab_id
    assert font.tabs[-1].text == tab.text


@pytest.mark.parametrize("side", ["left", "right", "width"])
def test_f31_metrics_keys_roundtrip_and_clear(font, side):
    layer = font.glyphs[0].layers[0]
    name = side + "MetricsKey"
    assert getattr(layer, name) is None
    for key in ("=H", "=|n", "==A+12", None):
        setattr(layer, name, key)
        assert getattr(layer, name) == key
    detached = layer.copy()
    setattr(detached, name, "=A")
    assert getattr(detached.copy(), name) == "=A"
    assert getattr(layer, name) is None


def test_f35_selected_anchors_participate_in_selection_and_copies(font):
    layer = font.glyphs[0].layers[0]
    anchor = layer.anchors.append(GSAnchor("upper", (10, 20)))
    assert not anchor.selected
    anchor.selected = True
    assert anchor.selected and anchor in layer.selection
    detached = layer.copy()
    assert detached.anchors[0].selected
    detached.anchors[0].selected = False
    assert anchor.selected
    anchor.selected = False
    assert anchor not in layer.selection


@pytest.mark.parametrize("detached", [False, True])
def test_f36_objc_setters_match_writable_properties_and_clear_collections(
    font, detached
):
    layer = font.glyphs[0].layers[0]
    if detached:
        layer = layer.copy()
    layer.setWidth_(601)
    assert layer.width == 601
    layer.setAnchors_([GSAnchor("upper")])
    assert layer.anchors["upper"] is not None
    layer.setAnchors_(None)
    assert not layer.anchors
    layer.setPaths_([GSPath([GSNode((20, 30))])])
    assert layer.paths[0].nodes[0].x == 20
    layer.setComponents_([GSComponent("A")])
    assert len(layer.components) == 1
    layer.setComponents_(None)
    assert not layer.components
    layer.setGuides_([GSGuide()])
    assert len(layer.guides) == 1
    layer.setGuides_(None)
    assert not layer.guides
    layer.setShapes_(None)
    assert not layer.shapes
    with pytest.raises(UnsupportedAttribute):
        layer.setMadeUp_(1)


def test_f36_collection_self_assignment_snapshots_before_removing_native_members(font):
    layer = font.glyphs[0].layers[0]
    layer.anchors.append(GSAnchor("upper", (22, 33)))
    layer.guides.append(GSGuide((5, 9)))
    layer.setAnchors_(layer.anchors)
    layer.setPaths_(layer.paths)
    layer.setGuides_(layer.guides)
    layer.setShapes_(layer.shapes)
    assert layer.anchors["upper"].position == (22, 33)
    assert len(layer.paths) == len(layer.components) == len(layer.guides) == 1
    draft = GSAnchor("old")
    draft.setName_("new")
    assert draft.name == "new"
    layer.setLeftMetricsKey_("=A")
    assert layer.leftMetricsKey == "=A"


def test_f29_background_type_foreground_and_width_assignment_match_sdk(font):
    from fontlab_glyport.model.background import GSBackgroundLayer

    background = font.glyphs[0].layers[0].background
    assert isinstance(background, GSBackgroundLayer)
    before = background.width
    background.width = 999
    assert background.width == before
    assert background.background is None
    copied = background.copy()
    assert isinstance(copied, GSBackgroundLayer) and copied.foreground() is None
    copied.width = 999
    assert copied.width == before
    assert not GSLayer().isMasterLayer


@pytest.mark.parametrize("detached", [False, True])
def test_f29_f36_background_assignment_and_none_clear_are_independent(font, detached):
    layer = font.glyphs[0].layers[0]
    if detached:
        layer = layer.copy()
    source = GSLayer()
    source.paths.append(GSPath([GSNode((30, 40))]))
    source.anchors.append(GSAnchor("upper", (3, 4)))
    source.leftMetricsKey = "=A"
    source.userData["owned"] = "value"
    layer.setBackground_(source)
    assert layer.background.paths[0].nodes[0].position == (30, 40)
    assert layer.background.anchors["upper"].position == (3, 4)
    assert layer.background.leftMetricsKey == "=A"
    assert layer.background.userData["owned"] == "value"
    source.paths[0].nodes[0].x = 99
    assert layer.background.paths[0].nodes[0].x == 30
    cloned = layer.copy()
    cloned.background.paths[0].nodes[0].x = 88
    assert layer.background.paths[0].nodes[0].x == 30
    layer.setBackground_(None)
    assert not layer.background.shapes and not layer.background.anchors
    assert len(layer.paths) == 1


def test_f36_objc_selector_has_one_argument_and_preserves_acronym_properties(font):
    layer = font.glyphs[0].layers[0]
    font._model._backend.bounds_data[layer.id] = (4, 0, 16, 0)
    layer.setWidth_(100)
    layer.setRSB_(15)
    assert layer.width == 35
    with pytest.raises(TypeError):
        layer.setWidth_(1, "name")
    with pytest.raises(TypeError):
        layer.setWidth_()
