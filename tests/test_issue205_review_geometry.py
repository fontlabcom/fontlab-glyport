# this_file: tests/test_issue205_review_geometry.py
"""Review regressions: preserve contour rotation and avoid empty history steps."""

import pytest

from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.backend import LayerInfo
from fontlab_glyport.model.fake_backend import FakeBackend


def live_layer():
    backend = FakeBackend()
    backend.layers["glyph", "master"] = LayerInfo("layer", "master", 500)
    return backend, Model(backend).font.glyphs[0].layers[0]


@pytest.mark.parametrize("rotation", [0, 1, 2])
def test_extrema_when_circle_already_has_extrema_then_preserves_rotation_and_history(
    rotation,
):
    backend, layer = live_layer()
    points = [
        (0, 55),
        (45, 100),
        (100, 100),
        (155, 100),
        (200, 55),
        (200, 0),
        (200, -55),
        (155, -100),
        (100, -100),
        (45, -100),
        (0, -55),
        (0, 0),
    ]
    nodes = [
        GSNode(point, "curve" if i % 3 == 2 else "offcurve")
        for i, point in enumerate(points)
    ]
    layer.paths = [GSPath(nodes[rotation:] + nodes[:rotation])]
    before = backend.outline_layer(layer.id)
    revision = backend.revision("font")
    backend.undo_events.clear()
    layer.addNodesAtExtremes()
    assert backend.outline_layer(layer.id) == before, (
        "No-op must retain every node and token"
    )
    assert backend.revision("font") == revision, "No-op must not mark the font changed"
    assert backend.undo_events == [], "No-op must not begin or publish Undo"


def test_extrema_when_closed_curve_is_split_then_original_start_stays_last():
    _, layer = live_layer()
    layer.paths = [
        GSPath(
            [
                GSNode((0, 100), "offcurve"),
                GSNode((100, 100), "offcurve"),
                GSNode((100, 0), "curve"),
                GSNode((0, 0), "line"),
            ]
        )
    ]
    layer.addNodesAtExtremes()
    assert layer.paths[0].nodes[-1].position == (0, 0)
    assert layer.paths[0].nodes[-1].type == "line"
    assert any(
        n.position == (50, 75) and n.type == "curve" for n in layer.paths[0].nodes
    )


def test_overlap_when_square_is_unchanged_then_no_closing_duplicate_or_history():
    pytest.importorskip("pathops")
    from fontlab_glyport.model.detached_geometry import remove_overlap

    backend, layer = live_layer()
    layer.paths = [
        GSPath([GSNode(point) for point in [(0, 0), (100, 0), (100, 100), (0, 100)]])
    ]
    result = remove_overlap(layer.copy())
    assert len(result[0].nodes) == 4, "Boolean output must not repeat the closing point"
    before = backend.outline_layer(layer.id)
    revision = backend.revision("font")
    backend.undo_events.clear()
    layer.removeOverlap()
    assert backend.outline_layer(layer.id) == before
    assert backend.revision("font") == revision
    assert backend.undo_events == []


def test_pen_when_two_contours_drawn_then_one_history_step():
    backend, layer = live_layer()
    backend.undo_events.clear()
    with layer.getPen() as pen:
        for x in (0, 100):
            pen.moveTo((x, 0))
            pen.lineTo((x + 20, 0))
            pen.lineTo((x + 20, 20))
            pen.closePath()
    assert len(layer.paths) == 2
    assert backend.undo_events == [("begin", "Draw layer"), ("end", None)]


def test_pen_when_explicitly_finished_then_group_is_closed_once():
    backend, layer = live_layer()
    backend.undo_events.clear()
    pen = layer.getPointPen()
    for x in (0, 100):
        pen.beginPath()
        pen.addPoint((x, 0), "move")
        pen.addPoint((x, 20), "line")
        pen.endPath()
    pen.doneDrawing()
    pen.doneDrawing()
    assert backend.undo_events == [("begin", "Draw layer"), ("end", None)]
