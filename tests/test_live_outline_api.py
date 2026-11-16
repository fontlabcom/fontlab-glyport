# this_file: tests/test_live_outline_api.py
"""Geometry and pen outcomes on the live backend protocol."""

from dataclasses import replace

import pytest

from fontlab_glyport.errors import StaleNativeObject
from fontlab_glyport.model import GSComponent, GSNode, GSPath, Model
from fontlab_glyport.model.backend import GlyphInfo, LayerInfo, ModelBackend
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def live():
    backend = FakeBackend()
    backend.layers["glyph", "master"] = LayerInfo("layer", "master", 500)
    font = Model(backend).font
    return backend, font, font.glyphs[0].layers[0]


def square(x=0, y=0, size=100):
    return GSPath(
        [
            GSNode(p)
            for p in [(x, y), (x + size, y), (x + size, y + size), (x, y + size)]
        ]
    )


def test_backend_protocol_and_font_persistence(live, tmp_path):
    backend, font, layer = live
    assert isinstance(backend, ModelBackend)
    assert font.filepath is None and font.familyName == "Example"
    with pytest.raises(ValueError, match="path"):
        font.save()
    target = tmp_path / "Example.ufo"
    assert font.save(str(target)) is None
    assert target.exists() and font.filepath == str(target)
    layer.paths.append(square())
    assert font.save() is None
    assert font.close() is None and backend.current_font_id() is None
    with pytest.raises(StaleNativeObject):
        _ = layer.width


def test_remove_overlap_geometry_and_nested_undo(live):
    pytest.importorskip("pathops")
    backend, font, layer = live
    layer.paths = [square(), square(50)]
    glyph = font.glyphs[0]
    glyph.beginUndo()
    layer.beginChanges()
    assert layer.removeOverlap() is None
    layer.endChanges()
    glyph.endUndo()
    assert len(layer.paths) == 1
    from fontTools.pens.boundsPen import BoundsPen

    bounds = BoundsPen(None)
    layer.draw(bounds)
    assert bounds.bounds == (0, 0, 150, 100)
    assert layer.paths[0].area() == pytest.approx(15000)
    assert backend.undo_events[-2:] == [("begin", "Edit A"), ("end", None)]


def test_decompose_components_transforms_nested_outlines(live):
    backend, font, layer = live
    layer.paths.append(square())
    base = backend.layers["glyph", "master"]
    backend.glyph_lists["font"] += (GlyphInfo("composite", "B", ()),)
    backend.layers["composite", "master"] = LayerInfo("other", "master", 500)
    destination = font.glyphs["B"].layers[0]
    component = GSComponent("A")
    component._draft = replace(component._draft, transform=(2, 0, 0, 3, 10, 20))
    destination.components.append(component)
    assert destination.decomposeComponents() is None
    assert not destination.components and len(destination.paths) == 1
    assert [(n.x, n.y) for n in destination.paths[0].nodes] == [
        (10, 20),
        (210, 20),
        (210, 320),
        (10, 320),
    ]
    assert backend.layers["glyph", "master"] == base


def test_correct_direction_handles_counters_and_open_paths(live):
    _, _, layer = live
    outer, inner = square(), square(25, 25, 50)
    open_path = GSPath([GSNode((2, 3)), GSNode((4, 5))], closed=False)
    layer.paths = [inner, outer, open_path]
    assert layer.correctPathDirection() is None
    by_area = sorted(layer.paths[:2], key=lambda p: p.area())
    assert by_area[0].direction == 1 and by_area[1].direction == -1
    assert not layer.paths[2].closed


def test_extrema_splits_cubic_without_changing_bounds(live):
    _, _, layer = live
    layer.paths = [
        GSPath(
            [
                GSNode((0, 0)),
                GSNode((0, 100), "offcurve"),
                GSNode((100, 100), "offcurve"),
                GSNode((100, 0), "curve"),
            ],
            closed=False,
        )
    ]
    assert layer.addNodesAtExtremes() is None
    path = layer.paths[0]
    assert len(path.nodes) == 7
    assert any(n.position == (50, 75) and n.type == "curve" for n in path.nodes)
    assert path.area() == pytest.approx(6000)
    count = len(path.nodes)
    layer.addNodesAtExtremes(force=True)
    assert len(layer.paths[0].nodes) == count


def test_segment_and_point_pen_roundtrip(live):
    from fontTools.pens.recordingPen import RecordingPen, RecordingPointPen

    _, _, layer = live
    pen = layer.getPen()
    pen.moveTo((0, 0))
    pen.lineTo((100, 0))
    pen.curveTo((120, 20), (120, 80), (100, 100))
    pen.closePath()
    recording = RecordingPen()
    assert layer.draw(recording) is None
    assert recording.value == [
        ("moveTo", ((0, 0),)),
        ("lineTo", ((100, 0),)),
        ("curveTo", ((120, 20), (120, 80), (100, 100))),
        ("closePath", ()),
    ]
    points = RecordingPointPen()
    layer.drawPoints(points)
    layer.paths = []
    points.replay(layer.getPointPen())
    second = RecordingPointPen()
    layer.drawPoints(second)
    assert second.value == points.value


def test_empty_operations_and_selected_extrema(live):
    _, _, layer = live
    assert layer.decomposeComponents() is None
    assert layer.correctPathDirection() is None
    assert layer.addNodesAtExtremes(checkSelection=True) is None
    layer.paths = [square()]
    before = [(n.x, n.y) for n in layer.paths[0].nodes]
    layer.addNodesAtExtremes(checkSelection=True)
    assert [(n.x, n.y) for n in layer.paths[0].nodes] == before


def test_geometry_write_failure_restores_entire_collection(live, monkeypatch):
    backend, _, layer = live
    layer.paths = [square(), square(25, 25, 50)]
    before = backend.outline_layer(layer.id)
    monkeypatch.setattr(
        backend,
        "insert_path",
        lambda *args: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    with pytest.raises(RuntimeError, match="write failed"):
        layer.correctPathDirection()
    assert backend.outline_layer(layer.id) == before
    assert not backend._undo


def test_cyclic_components_are_refused_before_any_write(live):
    backend, _, layer = live
    layer.components.append(GSComponent("A"))
    before = backend.outline_layer(layer.id)
    with pytest.raises(ValueError, match="cycle"):
        layer.decomposeComponents()
    assert backend.outline_layer(layer.id) == before


def test_remove_overlap_without_boolean_dependency_fails_without_mutation(
    live, monkeypatch
):
    import builtins

    from fontlab_glyport.errors import UnsupportedCapability

    backend, _, layer = live
    layer.paths = [square()]
    before = backend.outline_layer(layer.id)
    original = builtins.__import__

    def no_boolean(name, *args, **kwargs):
        if name == "pathops":
            raise ImportError("unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_boolean)
    with pytest.raises(UnsupportedCapability, match="skia-pathops"):
        layer.removeOverlap()
    assert backend.outline_layer(layer.id) == before
