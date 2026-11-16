# this_file: tests/test_live_pens.py
"""Quadratic, implied-point and metadata pen contracts."""

import pytest

from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import LayerInfo
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def live():
    """Supply a font with an empty editable layer."""
    backend = FakeBackend()
    backend.layers["glyph", "master"] = LayerInfo("layer", "master", 500)
    font = Model(backend).font
    return backend, font, font.glyphs[0].layers[0]


def test_quadratic_pen_and_extrema_preserve_bounds(live):
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import RecordingPen

    _, _, layer = live
    pen = layer.getPen()
    pen.moveTo((0, 0))
    pen.qCurveTo((0, 100), (100, 100), (100, 0))
    pen.endPath()
    before = BoundsPen(None)
    layer.draw(before)
    layer.addNodesAtExtremes()
    after = BoundsPen(None)
    layer.draw(after)
    assert before.bounds == after.bounds
    output = RecordingPen()
    layer.draw(output)
    assert any(command == "qCurveTo" for command, args in output.value)


def test_all_offcurve_quadratic_gets_explicit_extrema(live):
    from fontTools.pens.boundsPen import BoundsPen

    _, _, layer = live
    pen = layer.getPen()
    pen.qCurveTo((0, 0), (100, 0), (100, 100), (0, 100), None)
    pen.closePath()
    before = BoundsPen(None)
    layer.draw(before)
    layer.addNodesAtExtremes()
    after = BoundsPen(None)
    layer.draw(after)
    assert before.bounds == after.bounds
    assert any(n.type == "qcurve" for n in layer.paths[0].nodes)


def test_pen_names_smoothness_components_and_filter_flags(live):
    from fontTools.pens.recordingPen import RecordingPen, RecordingPointPen

    _, _, layer = live
    pen = layer.getPointPen()
    pen.beginPath()
    pen.addPoint((0, 0), "move", name="origin")
    pen.addPoint((10, 20), "line", smooth=True)
    pen.endPath()
    pen.addComponent("A", (2, 0, 0, 3, 10, 20))
    points = RecordingPointPen()
    layer.drawPoints(points)
    assert points.value[1][1][3] == "origin"
    assert points.value[2][1][2] is True
    assert points.value[-1][1] == ("A", (2, 0, 0, 3, 10, 20))
    contours = RecordingPen()
    layer.draw(contours, components=False)
    assert all(command != "addComponent" for command, args in contours.value)
    components = RecordingPen()
    layer.draw(components, contours=False)
    assert components.value == [("addComponent", ("A", (2, 0, 0, 3, 10, 20)))]
