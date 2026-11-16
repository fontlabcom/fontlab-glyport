# this_file: tests/test_detached_geometry_behaviour.py
"""Detached outline geometry and optional Boolean-engine boundary contracts."""

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fontTools.pens.recordingPen import RecordingPen

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSComponent, GSLayer, GSNode, GSPath
from fontlab_glyport.model.detached_geometry import layer_bounds, remove_overlap


def rectangle():
    return GSPath([GSNode(point) for point in [(0, 0), (40, 0), (40, 20), (0, 20)]])


def outline(path):
    return path.closed, [(tuple(n.position), n.type) for n in path.nodes]


@pytest.fixture
def recording_boolean(monkeypatch):
    """Record/replay one simple closed contour; do not simulate Boolean unions.

    For these nonintersecting fixtures simplification is the identity. Real
    skia-pathops integration is tested separately when that extra is available.
    """
    recordings = []

    class SingleContourPath:
        def __init__(self):
            self.pen = RecordingPen()
            self.options = None
            recordings.append(self)

        def getPen(self):
            return self.pen

        def simplify(self, **options):
            commands = [command for command, _ in self.pen.value]
            assert commands.count("moveTo") == commands.count("closePath") == 1
            assert "endPath" not in commands, (
                "Open paths must bypass the Boolean engine"
            )
            self.options = options

        def draw(self, pen):
            self.pen.replay(pen)

    monkeypatch.setitem(sys.modules, "pathops", SimpleNamespace(Path=SingleContourPath))
    return recordings


def test_boolean_conversion_when_closing_cubic_then_preserves_type_and_open_paths(
    recording_boolean,
):
    layer = GSLayer()
    closed = GSPath(
        [
            GSNode((0, 0)),
            GSNode((0, 100), "offcurve"),
            GSNode((100, 100), "offcurve"),
            GSNode((100, 0), "curve"),
        ]
    )
    opened = GSPath([GSNode((200, 0)), GSNode((240, 20))], closed=False)
    layer.paths = [GSPath(), closed, opened]
    before = [outline(path) for path in layer.paths]
    result = remove_overlap(layer)
    assert [outline(path) for path in result] == [outline(closed), outline(opened)]
    assert len(result[0].nodes) == 4 and result[0].nodes[-1].type == "curve"
    assert result[0].bounds == ((0, 0), (100, 75))
    assert result[1] is not opened, "Results must not retain source-owned node objects"
    assert [outline(path) for path in layer.paths] == before
    assert recording_boolean[0].options == {
        "fix_winding": True,
        "keep_starting_points": True,
    }
    assert recording_boolean[0].pen.value == [
        ("moveTo", ((100, 0),)),
        ("lineTo", ((0, 0),)),
        ("curveTo", ((0, 100), (100, 100), (100, 0))),
        ("closePath", ()),
    ]


def test_boolean_conversion_when_polygon_then_removes_duplicate_closing_node(
    recording_boolean,
):
    layer = GSLayer()
    layer.paths = [rectangle()]
    result = remove_overlap(layer)
    assert outline(result[0]) == outline(layer.paths[0])
    assert len(result[0].nodes) == 4
    assert result[0].area() == 800
    assert result[0].bounds == ((0, 0), (40, 20))


def test_boolean_when_styled_closed_path_then_refuses_before_conversion(
    recording_boolean,
):
    layer = GSLayer()
    path = rectangle()
    path._draft = replace(path._draft, attributes={"strokeWidth": 12})
    layer.paths = [path]
    before = outline(path)
    with pytest.raises(UnsupportedCapability) as error:
        remove_overlap(layer)
    assert error.value.capability == "DetachedLayer.removeOverlap.styledPaths"
    assert outline(layer.paths[0]) == before
    assert layer.paths[0].attributes["strokeWidth"] == 12
    assert recording_boolean == [], (
        "A styled path must be refused before engine construction"
    )


def test_empty_geometry_when_queried_then_has_no_bounds_or_boolean_output():
    layer = GSLayer()
    assert layer_bounds(layer) is None
    assert remove_overlap(layer) == []


def test_detached_bounds_when_curves_open_paths_and_empty_contours_then_exact_extents():
    layer = GSLayer()
    curve = GSPath(
        [
            GSNode((0, 0)),
            GSNode((0, 100), "offcurve"),
            GSNode((100, 100), "offcurve"),
            GSNode((100, 0), "curve"),
        ],
        closed=False,
    )
    layer.paths = [
        GSPath(),
        curve,
        GSPath([GSNode((150, -10)), GSNode((200, 20))], closed=False),
    ]
    assert layer_bounds(layer) == (0, -10, 200, 85)
    assert outline(curve) == (
        False,
        [
            ((0, 0), "line"),
            ((0, 100), "offcurve"),
            ((100, 100), "offcurve"),
            ((100, 0), "curve"),
        ],
    )


def test_detached_bounds_when_component_reference_missing_then_refuses_without_mutation():
    layer = GSLayer()
    layer.shapes = [rectangle(), GSComponent("Missing")]
    with pytest.raises(UnsupportedCapability) as error:
        layer_bounds(layer)
    assert error.value.capability == "DetachedLayer.bounds.component.Missing"
    assert len(layer.paths) == len(layer.components) == 1
    assert layer.paths[0].bounds == ((0, 0), (40, 20))


def test_detached_bounds_when_open_contour_starts_offcurve_then_reports_specific_refusal():
    layer = GSLayer()
    path = GSPath([GSNode((0, 10), "offcurve"), GSNode((20, 0), "curve")], closed=False)
    layer.paths = [path]
    with pytest.raises(UnsupportedCapability) as error:
        layer_bounds(layer)
    assert error.value.capability == "DetachedLayer.bounds.openOffcurveStart"
    assert outline(path) == (False, [((0, 10), "offcurve"), ((20, 0), "curve")])
