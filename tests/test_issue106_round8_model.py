# this_file: tests/test_issue106_round8_model.py
"""Small, independently written model cases for the round-eight tickets."""

import sys
from copy import deepcopy

import pytest

from fontlab_glyport.errors import PartialFailure, UnsupportedCapability
from fontlab_glyport.model import (
    GSAnchor,
    GSAxis,
    GSComponent,
    GSGuide,
    GSLayer,
    GSNode,
    GSPath,
    Model,
)
from fontlab_glyport.model.backend import GuideInfo, HintInfo
from fontlab_glyport.model.copies import DetachedLayer
from fontlab_glyport.model.fake_backend import FakeBackend


def path(x=0):
    return GSPath(
        [GSNode((x, 0)), GSNode((x + 10, 0)), GSNode((x + 10, 10)), GSNode((x, 10))]
    )


def test_f40_parent_selection_zones_guides_and_clear():
    backend = FakeBackend()
    backend.master_guides_data["master"] = (
        GuideInfo("global-guide", 1, 2, 90, "global"),
    )
    backend.master_zones_data["master"] = ((700, 15), (0, -10))
    backend.hint_data["layer"] = (HintInfo(True, 1, 2),)
    font = Model(backend).font
    glyph = font.glyphs[0]
    assert glyph.parent is font and font.parent.font is font
    with pytest.raises(UnsupportedCapability) as error:
        _ = font.parent.windowController
    assert error.value.capability == "GSDocument.windowController"
    assert not glyph.selected
    glyph.selected = True
    assert glyph.selected
    assert [guide.name for guide in font.masters[0].guides] == ["global"]
    zones = font.masters[0].alignmentZones
    assert [(zone.position, zone.size) for zone in zones] == [(700, 15), (0, -10)]
    zones[0].size = 20
    assert font.masters[0].alignmentZones[0].size == 20
    layer = glyph.layers[0]
    assert layer.isKindOfClass_(GSLayer) and not layer.isKindOfClass_(GSNode)
    layer.guides.append(GSGuide((2, 3), 90, "keep"))
    backend.undo_events.clear()
    layer.clear()
    assert not layer.shapes and not layer.anchors and not layer.hints
    assert [guide.name for guide in layer.guides] == ["keep"]
    assert len(backend.undo_events) == 2, "clear publishes just one group"


def test_f40_path_attributes_and_detached_name_survive_copies():
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    original = layer.paths[0]
    original.attributes["strokeWidth"] = 20
    clone = original.copy()
    clone.attributes["strokeWidth"] = 40
    assert original.attributes["strokeWidth"] == 20
    assert clone.attributes["strokeWidth"] == 40
    copied = layer.copy()
    assert copied.name == layer.name
    copied.name = "Temporary"
    assert deepcopy(copied).name == "Temporary" and layer.name != "Temporary"


def test_f40_path_bounds_are_geometric_not_control_bounds():
    pytest.importorskip("fontTools.pens.boundsPen")
    curve = GSPath(
        [
            GSNode((0, 0)),
            GSNode((0, 100), "offcurve"),
            GSNode((100, 100), "offcurve"),
            GSNode((100, 0), "curve"),
        ],
        closed=False,
    )
    assert curve.bounds == ((0, 0), (100, 75))


def test_f45_segments_have_nsarray_methods_even_when_empty():
    assert GSPath().segments.count() == 0
    segments = path().segments
    assert segments.count() == 4
    assert segments.objectAtIndex_(0).count() == 2
    assert segments[0].objectAtIndex_(1) == (0, 0)


def test_f46_axis_uuid_before_append_is_stable_and_usable_as_coordinate_key():
    backend = FakeBackend()
    font = Model(backend).font
    axis = GSAxis("Extra", "XTRA")
    token = axis.id
    assert len(token) == 36 and token != GSAxis().id
    font.axes.append(axis)
    assert axis.id == token and font.axes[token] is axis
    assert axis in font.axes
    font.masters[0].internalAxesValues[token] = 23
    assert font.masters[0].internalAxesValues[token] == 23
    axis.name = "Renamed"
    assert font.axes["Renamed"] is axis and font.axes["Extra"] is None


@pytest.mark.parametrize(
    "field,items",
    [
        ("paths", lambda: [path(20), path(40)]),
        ("components", lambda: [GSComponent("A"), GSComponent("A")]),
        ("shapes", lambda: [path(20), GSComponent("A")]),
        ("anchors", lambda: [GSAnchor("one", (10, 20)), GSAnchor("two", (30, 40))]),
        ("guides", lambda: [GSGuide((10, 20), 0), GSGuide((30, 40), 90)]),
    ],
)
def test_bulk_setter_publishes_one_group_and_restores_after_second_append_failure(
    field, items, monkeypatch
):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    before = backend.layers["glyph", "master"]
    method = {
        "paths": "append_path",
        "components": "append_component",
        "shapes": "append_component",
        "anchors": "add_anchor",
        "guides": "append_guide",
    }[field]
    original = getattr(backend, method)
    calls = []

    def fail(*args, **kwargs):
        calls.append(None)
        if field == "shapes" or len(calls) == 2:
            raise RuntimeError("injected append failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, method, fail)
    with pytest.raises(RuntimeError, match="injected append"):
        setattr(layer, field, items())
    assert backend.layers["glyph", "master"] == before
    assert len(backend.undo_events) == 2, "rollback stays in the same undo group"
    monkeypatch.setattr(backend, method, original)
    backend.undo_events.clear()
    setattr(layer, field, items())
    assert len(getattr(layer, field)) == 2 and len(backend.undo_events) == 2


@pytest.mark.parametrize(
    "field,items",
    [
        ("shapes", lambda: [path(), GSComponent("no-such-base")]),
        ("components", lambda: [GSComponent("no-such-base")]),
        ("anchors", lambda: [GSAnchor("duplicate"), GSAnchor("duplicate")]),
        ("paths", lambda: [object()]),
        ("guides", lambda: [object()]),
    ],
)
def test_bulk_setters_validate_before_removing_anything(field, items):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    before = backend.layers["glyph", "master"]
    with pytest.raises((ValueError, TypeError)):
        setattr(layer, field, items())
    assert backend.layers["glyph", "master"] == before and not backend.undo_events


def test_bulk_failed_rollback_is_loud_with_both_errors(monkeypatch):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]

    def fail(*args):
        raise RuntimeError("write failed")

    def fail_restore(*args):
        raise RuntimeError("restore failed")

    monkeypatch.setattr(backend, "add_anchor", fail)
    monkeypatch.setattr(backend, "restore_collection", fail_restore)
    with pytest.raises(PartialFailure) as error:
        layer.anchors = [GSAnchor("new")]
    assert [str(e) for e in error.value.errors] == ["write failed", "restore failed"]
    assert error.value.capability == "GSLayer.anchors"


def test_background_fake_read_does_not_create_layer_and_first_write_does():
    backend = FakeBackend()
    font = Model(backend).font
    original = dict(backend.layers)
    background = font.glyphs[0].layers[0].background
    assert len(background.paths) == 0 and dict(backend.layers) == original
    background.paths.append(path())
    assert len(backend.layers) == len(original) + 1
    assert len(font.glyphs[0].layers[0].paths) == 1


def test_f40_overlap_when_dependency_missing_refuses_before_mutation(monkeypatch):
    layer = DetachedLayer()
    layer.paths = [path(), path(5)]
    before = list(layer.paths)
    monkeypatch.setitem(sys.modules, "pathops", None)
    with pytest.raises(UnsupportedCapability) as error:
        layer.removeOverlap()
    assert error.value.capability == "DetachedLayer.removeOverlap.dependency"
    assert list(layer.paths) == before


def test_f40_optional_boolean_unions_rectangles_keeps_open_paths_and_is_detached():
    pytest.importorskip("pathops")
    layer = DetachedLayer()
    open_path = GSPath([GSNode((0, 20)), GSNode((15, 20))], closed=False)
    layer.paths = [path(), path(5), open_path]
    clone = deepcopy(layer)
    clone.removeOverlap()
    assert len(clone.paths) == 2 and len(layer.paths) == 3
    assert sorted(p.closed for p in clone.paths) == [False, True]
    closed = next(p for p in clone.paths if p.closed)
    assert closed.bounds == ((0, 0), (15, 10))
    assert next(p for p in clone.paths if not p.closed).nodes[-1].position == (15, 20)
