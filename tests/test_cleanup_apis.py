# this_file: tests/test_cleanup_apis.py
"""Literal path geometry and additive selection/tab contracts (Task 3C)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.foundation import NSValue
from fontlab_glyport.glyphsapp import GSControlLayer
from fontlab_glyport.model import GSAnchor, GSLayer, GSNode, GSPath, Model
from fontlab_glyport.model.backend import LayerInfo, MasterInfo
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.ui.cocoa import NSPoint


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def coordinates(path):
    return [[tuple(point) for point in segment] for segment in path.segments]


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("live", [False, True])
def test_segments_reconstruct_literal_lines_and_cubics(font, closed, live):
    segments = [[(0, 0), (10, 0)], [(10, 0), (12, 0), (15, 8), (20, 10)]]
    if closed:
        segments.append([(20, 10), (0, 0)])
    path = GSPath([GSNode((90, 91), smooth=True)], closed=closed)
    path.attributes["strokeWidth"] = 17
    if live:
        path = font.glyphs[0].layers[0].paths.append(path)
    old_node = path.nodes[0]
    old_id = path.id if live else None
    path.segments = segments
    expected = [(10, 0), (12, 0), (15, 8), (20, 10)]
    types = ["line", "offcurve", "offcurve", "curve"]
    if closed:
        expected.append((0, 0))
        types.append("line")
    else:
        expected.insert(0, (0, 0))
        types.insert(0, "line")
    assert [tuple(n.position) for n in path.nodes] == expected
    assert [n.type for n in path.nodes] == types
    assert all(
        not n.smooth and not n.selected and n.connection == 0 for n in path.nodes
    )
    assert coordinates(path) == segments
    assert path.closed is closed and path.attributes["strokeWidth"] == 17
    assert (path.bounds.origin.x, path.bounds.origin.y) == (0, 0)
    if live:
        assert path.id == old_id, "Replacing segments must retain the contour identity"
        with pytest.raises(StaleNativeObject):
            _ = old_node.position
        assert font._model._backend.undo_events == [
            ("begin", "Replace path segments"),
            ("end", None),
        ]
    else:
        assert old_node.parent is None, "Replaced detached nodes lose ownership"
    path.segments = path.segments
    assert coordinates(path) == segments, "Get/set preserves exact segment endpoints"


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize(
    "bad",
    [
        [],
        None,
        [object()],
        [[(0, 0)]],
        [[(0, 0), (1, 1), (2, 2)]],
        [[(0, 0), (float("nan"), 0)]],
        [[(0, 0), (0, float("inf"))]],
        [[(0, 0), ("bad", 2)]],
        [[(0, 0), (1, 2, 3)]],
        [[(0, 0), "12"]],
        [[(0, 0), (10**500, 0)]],
        [[(0, 0), (1, 1)], [(2, 2), (3, 3)]],
        [[(0, 0), (1, 1)], [(1, 1), (object(), 0)]],
    ],
)
def test_segments_reject_whole_bad_input_before_mutation(font, live, bad):
    path = GSPath([GSNode((8, 9)), GSNode((10, 11))], closed=False)
    if live:
        path = font.glyphs[0].layers[0].paths.append(path)
    original_nodes = list(path.nodes)
    with pytest.raises((TypeError, ValueError)):
        path.segments = bad
    assert list(path.nodes) == original_nodes
    assert [tuple(n.position) for n in path.nodes] == [(8, 9), (10, 11)]
    assert font._model._backend.undo_events == []


def test_closed_segments_reject_unjoined_final_endpoint(font):
    path = font.glyphs[0].layers[0].paths[0]
    with pytest.raises(ValueError, match="closed"):
        path.segments = [[(0, 0), (10, 10)]]
    assert path.nodes[0].position == (0, 0)


def test_segments_copy_cocoa_xy_points_into_numeric_geometry():
    path = GSPath(closed=False)
    path.segments = [[NSPoint(1, 2), SimpleNamespace(x=3, y=4)]]
    assert [tuple(n.position) for n in path.nodes] == [(1, 2), (3, 4)]
    assert all(isinstance(n.x, float) and isinstance(n.y, float) for n in path.nodes)


@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("native_shaped", [False, True])
def test_segments_accept_literal_nsvalue_wrapped_controls(font, live, native_shaped):
    # Cocoa's native pointValue() returns a struct with x/y, not a model tuple.
    # No real Cocoa/native calls: parent verifies both routes inside FontLab.
    class BoxedPoint:
        def __init__(self, x, y):
            self.point = SimpleNamespace(x=x, y=y)

        def pointValue(self):
            return self.point

    box = (
        BoxedPoint
        if native_shaped
        else lambda x, y: NSValue.valueWithPoint_(NSPoint(x, y))
    )
    path = GSPath(closed=False)
    if live:
        path = font.glyphs[0].layers[0].paths.append(path)
    path.segments = [[NSPoint(0, 0), box(3, 0), box(7, 10), NSPoint(10, 10)]]
    assert coordinates(path) == [[(0, 0), (3, 0), (7, 10), (10, 10)]]
    assert [node.type for node in path.nodes] == [
        "line",
        "offcurve",
        "offcurve",
        "curve",
    ]
    assert all(
        isinstance(node.x, float) and isinstance(node.y, float) for node in path.nodes
    )


def test_bad_wrapped_control_keeps_every_old_live_node(font):
    path = font.glyphs[0].layers[0].paths[0]
    original = list(path.nodes)
    invalid = NSValue.valueWithPoint_(NSPoint(float("nan"), 10))
    with pytest.raises(ValueError, match="finite"):
        path.segments = [
            [
                NSPoint(0, 0),
                NSValue.valueWithPoint_(NSPoint(3, 0)),
                invalid,
                NSPoint(0, 0),
            ]
        ]
    assert list(path.nodes) == original
    assert font._model._backend.undo_events == []


def test_closed_single_cubic_preserves_closing_controls_and_start():
    path = GSPath()
    segment = [(1, 2), (3, 8), (9, 4), (1, 2)]
    path.segments = [segment]
    assert [tuple(node.position) for node in path.nodes] == segment[1:]
    assert [node.type for node in path.nodes] == ["offcurve", "offcurve", "curve"]
    assert coordinates(path) == [segment]


def test_segment_replacement_refreshes_same_backend_peer_and_nests_undo(font):
    backend = font._model._backend
    layer = font.glyphs[0].layers[0]
    peer_layer = Model(backend).font.glyphs[0].layers[0]
    previous_node = peer_layer.paths[0].nodes[0]
    path_id = layer.paths[0].id
    with font.undo_group("Earlier edit"):
        layer.paths[0].segments = [[(0, 0), (20, 30)], [(20, 30), (0, 0)]]
        assert backend.undo_events == [("begin", "Earlier edit")]
        assert peer_layer.paths[0].id == path_id
        assert coordinates(peer_layer.paths[0]) == [
            [(0, 0), (20, 30)],
            [(20, 30), (0, 0)],
        ]
        with pytest.raises(StaleNativeObject):
            _ = previous_node.position
    assert backend.undo_events == [("begin", "Earlier edit"), ("end", None)]


def test_segment_setter_rejects_stale_path_before_writing(font):
    layer = font.glyphs[0].layers[0]
    path = layer.paths[0]
    layer.paths.remove(path)
    with pytest.raises(StaleNativeObject):
        path.segments = [[(0, 0), (10, 10)], [(10, 10), (0, 0)]]


@pytest.mark.parametrize("detached", [False, True])
def test_layer_selection_adds_idempotently_and_clears_without_undo(font, detached):
    layer = font.glyphs[0].layers[0]
    layer.paths.append(GSPath([GSNode((10, 20)), GSNode((30, 40))], closed=False))
    layer.anchors.append(GSAnchor("top", (0, 50)))
    if detached:
        layer = layer.copy()
    node, other = layer.paths[-1].nodes
    anchor = layer.anchors[0]
    assert layer.addSelection_(node) is None
    layer.addSelection_(anchor)
    layer.addSelection_(node)
    layer.addSelection_(other)
    assert list(layer.selection) == [node, other, anchor]
    assert layer.clearSelection() is None and not layer.selection
    assert not node.selected and not other.selected and not anchor.selected
    layer.clearSelection()
    assert font._model._backend.undo_events == []


@pytest.mark.parametrize("detached", [False, True])
def test_selection_rejects_foreign_and_unrepresented_elements(font, detached):
    layer = font.glyphs[0].layers[0]
    if detached:
        layer = layer.copy()
    own = layer.paths[0].nodes[0]
    layer.addSelection_(own)
    foreign = Model(FakeBackend()).font.glyphs[0].layers[0]
    for element in (foreign.paths[0].nodes[0], GSNode(), GSAnchor()):
        with pytest.raises(ValueError, match="belong"):
            layer.addSelection_(element)
        assert list(layer.selection) == [own]
    for element in (layer.paths[0], object()):
        with pytest.raises(UnsupportedCapability):
            layer.addSelection_(element)
        assert list(layer.selection) == [own]


def test_selection_rejects_stale_node_anchor_and_layer(font):
    layer = font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    anchor = layer.anchors.append(GSAnchor("top"))
    layer.paths.remove(layer.paths[0])
    layer.anchors.remove(anchor)
    for element in (node, anchor):
        with pytest.raises(StaleNativeObject):
            layer.addSelection_(element)
    font._model._backend.close_font(font.id)
    with pytest.raises(StaleNativeObject):
        layer.clearSelection()


def test_selection_refuses_anchors_without_backend_selection_support(font):
    layer = font.glyphs[0].layers[0]
    anchor = layer.anchors.append(GSAnchor("top"))
    font._model._backend.supports_anchor_selection = False
    with pytest.raises(UnsupportedCapability, match="anchorSelection"):
        layer.addSelection_(anchor)
    assert not anchor.selected and not layer.selection


def test_new_tab_routes_exact_layer_lists_and_empty_list(font, monkeypatch):
    from fontlab_glyport.model.proxies import GSEditViewController

    layers = [font.glyphs[0].layers[0]]
    setter = GSEditViewController.layers.fset
    calls = []

    def capture(tab, value):
        calls.append(value)
        setter(tab, value)

    monkeypatch.setattr(
        GSEditViewController,
        "layers",
        property(GSEditViewController.layers.fget, capture),
    )
    font.newTab(layers)
    assert calls[0] is layers
    assert font._model._backend.edit_texts[-1] == (font.id, (("A",),))
    font.newTab([])
    assert calls[-1] == []
    assert font._model._backend.edit_texts[-1] == (font.id, ((),))
    font.newTab("/A")
    assert font._model._backend.edit_texts[-1] == (font.id, (("A",),))
    before = list(font._model._backend.edit_texts)
    font.newTab()
    assert font._model._backend.edit_texts == before


@pytest.mark.parametrize(
    "bad", ["foreign", "detached", "background", "wrong", "mixed", "stale"]
)
def test_new_tab_checks_all_layers_before_opening_ui(font, bad, monkeypatch):
    backend = font._model._backend
    layer = font.glyphs[0].layers[0]
    if bad == "foreign":
        invalid = Model(FakeBackend()).font.glyphs[0].layers[0]
    elif bad == "detached":
        invalid = GSLayer()
    elif bad == "background":
        invalid = layer.background
    elif bad == "wrong":
        invalid = object()
    elif bad == "mixed":
        backend.fonts[font.id] = replace(
            backend.fonts[font.id],
            masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
        )
        backend.layers["glyph", "bold"] = LayerInfo("bold-layer", "bold", 500)
        invalid = layer.parent.layers["bold"]
    else:
        invalid = layer.background
        backend.clear_background_layer(layer.id)
    opens = []
    monkeypatch.setattr(backend, "open_edit_view", opens.append)
    with pytest.raises((UnsupportedCapability, TypeError, StaleNativeObject)):
        font.newTab([layer, invalid])
    assert opens == [] and backend.edit_texts == []


def test_tab_layer_list_preserves_control_layer_line_breaks(font):
    layer = font.glyphs[0].layers[0]
    font.newTab([layer, GSControlLayer.newline(), layer])
    assert font._model._backend.edit_texts[-1] == (font.id, (("A",), ("A",)))
