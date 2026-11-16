# this_file: tests/test_issue106_round4_model.py
"""Handwritten reproductions of native real-use tickets F3-F15 and F23."""

from copy import copy, deepcopy
from dataclasses import replace

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import GSAxis, GSNode, GSPath, Model
from fontlab_glyport.model.backend import MasterInfo, MasterMetrics
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def test_f3_glyph_undo_when_nested_with_font_group_then_one_balanced_transaction(font):
    glyph = font.glyphs[0]
    backend = font._model._backend
    glyph.endUndo()
    with font.undo_group("Outer"):
        glyph.beginUndo()
        glyph.beginUndo()
        glyph.layers[0].width = 600
        glyph.endUndo()
        glyph.endUndo()
    assert backend.undo_events == [("begin", "Outer"), ("end", None)]
    glyph.beginUndo()
    glyph.endUndo()
    glyph.endUndo()
    assert len(backend.undo_events) == 4


def test_f4_path_selected_when_read_or_assigned_then_all_nodes_participate(font):
    layer = font.glyphs[0].layers[0]
    path = layer.paths.append(GSPath([GSNode(), GSNode((10, 20))]))
    assert not path.selected
    path.nodes[0].selected = True
    assert not path.selected
    path.selected = True
    assert path.selected and all(n.selected for n in path.nodes)
    path.selected = False
    assert not any(n.selected for n in path.nodes)
    assert GSPath().selected  # the SDK uses a subset test, also true for no nodes


def test_f3_glyph_end_undo_when_publication_fails_then_pair_can_be_retried(
    font, monkeypatch
):
    backend = font._model._backend
    end, attempts = backend.end_undo, []

    def flaky_end():
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("publish failed")
        end()

    monkeypatch.setattr(backend, "end_undo", flaky_end)
    glyph = font.glyphs[0]
    glyph.beginUndo()
    with pytest.raises(RuntimeError, match="publish failed"):
        glyph.endUndo()
    glyph.endUndo()
    assert backend.undo_events == [("begin", "Edit A"), ("end", None)]
    assert font._undo_depth == 0


def test_f3_glyph_undo_when_native_notifications_emitted_then_layer_and_glyph_share_each_batch(
    font, monkeypatch
):
    from types import SimpleNamespace

    from fontlab_glyport.model.fontlab_backend import FontLabBackend

    native, calls = FontLabBackend(packages=[]), []
    layer = SimpleNamespace(
        id=1, isValid=True, changed=lambda: None, update=lambda: True
    )
    glyph = SimpleNamespace(
        id=2, isValid=True, changed=lambda: None, update=lambda: True
    )
    document = native._font_id(SimpleNamespace(id=3, isValid=True))
    glyph_id = native._register((document, "glyph", glyph.id), glyph, document)
    layer_id = native._register(
        (document, "layer", glyph_id, "Regular"), layer, glyph_id
    )
    items = SimpleNamespace(
        notifyChangesApplied=lambda name, objects, recursive=False: calls.append(
            (name, objects)
        )
    )
    monkeypatch.setattr(
        native, "_native", lambda: SimpleNamespace(
            flItems=lambda: items, flGlyph=SimpleNamespace(updatedFgGlyphs=lambda: ())
        )
    )
    monkeypatch.setattr(native, "_writable_layer", lambda token: layer)
    backend, live = font._model._backend, font.glyphs[0]
    original = backend.set_layer_width

    def set_width(token, value):
        native.set_layer_width(layer_id, value)
        original(token, value)

    monkeypatch.setattr(backend, "begin_undo", native.begin_undo)
    monkeypatch.setattr(backend, "end_undo", native.end_undo)
    monkeypatch.setattr(backend, "set_layer_width", set_width)
    live.beginUndo()
    live.layers[0].width = 640
    live.endUndo()
    assert calls == [("Edit A", [layer, glyph]), ("Edit A", [layer, glyph])]


@pytest.mark.parametrize("closed", [True, False])
def test_f8_segments_when_lines_and_cubics_then_include_start_points(closed):
    path = GSPath(
        [
            GSNode((0, 0)),
            GSNode((10, 0), "offcurve"),
            GSNode((20, 30), "offcurve"),
            GSNode((30, 30), "curve"),
        ],
        closed=closed,
    )
    segments = path.segments
    expected_curve = [(0, 0), (10, 0), (20, 30), (30, 30)]
    assert segments == (
        [[(30, 30), (0, 0)], expected_curve] if closed else [expected_curve]
    )
    assert segments[-1][-1].x == 30 and segments[-1][-1].y == 30
    assert GSPath().segments == []


def test_f9_font_metrics_when_read_then_definitions_match_live_master_values(font):
    backend = font._model._backend
    backend.metrics[font.masters[0].id] = MasterMetrics(800, 710, -220, 510, -12)
    metrics = {metric.name: metric for metric in font.metrics}
    cap = metrics["Cap Height"]
    assert cap.type == 2 and cap.filter is None
    values = font.masters[0].metrics
    assert values[cap.id].position == 710
    assert font.masters[0].metricValues[cap.id].position == 710
    backend.metrics[font.masters[0].id] = MasterMetrics(800, 720, -220, 510, -12)
    assert values[cap.id].position == 720
    with pytest.raises(UnsupportedCapability):
        values[cap.id].position = 900


@pytest.mark.parametrize("operation", [copy, deepcopy, lambda value: value.copy()])
def test_f11_copy_when_native_handles_are_uncopyable_then_geometry_is_detached(
    font, operation
):
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise AssertionError("native handle traversed")

    backend = font._model._backend
    backend.native_handle = Uncopyable()
    source = font.glyphs[0].layers[0].paths[0]
    duplicate = operation(source)
    assert isinstance(duplicate, GSPath) and duplicate is not source
    duplicate.nodes[0].position = (25, 35)
    assert source.nodes[0].position == (0, 0)
    assert duplicate.nodes[0].position == (25, 35)
    detached_nodes = deepcopy(source.nodes)
    assert isinstance(detached_nodes, list) and detached_nodes[0] is not source.nodes[0]
    backend.close_font(font.id)
    assert duplicate.nodes[0].x == 25


def test_f11_deepcopy_layer_and_glyph_when_copied_then_no_native_parent_is_retained(
    font,
):
    layer = font.glyphs[0].layers[0]
    cloned_layer = deepcopy(layer)
    cloned_glyph = deepcopy(font.glyphs[0])
    assert isinstance(cloned_layer, type(layer)) and cloned_layer.parent is None
    assert cloned_glyph.layers[0].parent is cloned_glyph
    cloned_layer.width = 700
    cloned_layer.paths[0].nodes[0].x = 90
    assert layer.width == 500 and layer.paths[0].nodes[0].x == 0
    font._model._backend.close_font(font.id)
    assert cloned_layer.width == 700 and cloned_glyph.name == "A"


def test_f12_master_index_when_set_then_selected_master_and_backend_agree(font):
    backend = font._model._backend
    backend.fonts[font.id] = replace(
        backend.fonts[font.id],
        masters=(
            MasterInfo("master", "Regular"),
            MasterInfo("second", "Bold"),
        ),
    )
    assert font.masterIndex == 0
    font.masterIndex = 1
    assert font.selectedFontMaster is font.masters[1] and font.masterIndex == 1
    font.selectedFontMaster = font.masters[0]
    assert font.masterIndex == 0
    with pytest.raises(IndexError):
        font.masterIndex = 2
    assert font.masterIndex == 0


def test_f14_glyph_string_when_unicode_or_unencoded_then_character_or_none(font):
    assert font.glyphs[0].string == "A"
    backend = font._model._backend
    backend.glyph_lists[font.id] = (
        replace(backend.glyph_lists[font.id][0], unicodes=()),
    )
    assert font.glyphs[0].string is None


def test_f15_internal_axis_values_when_indexed_by_id_or_index_then_write_through(font):
    font.axes.append(GSAxis("Weight", "wght"))
    font.axes.append(GSAxis("Width", "wdth"))
    master = font.masters[0]
    values = master.internalAxesValues
    values[font.axes[1].axisId] = 72
    values[0] = 400
    assert list(values) == master.axes == [400, 72]
    assert values[font.axes[1].axisId] == 72
    with pytest.raises(KeyError):
        values["unknown"] = 1
    assert master.axes == [400, 72]


def test_f23_font_selection_when_multiple_layers_same_glyph_then_unique_glyphs(font):
    font._model._backend.current_layer_data[font.id] = (
        ("A", "Regular"),
        ("A", "Regular"),
    )
    assert font.selection == [font.glyphs[0]]
    font._model._backend.current_layer_data[font.id] = ()
    assert font.selection == []


def test_review_connection_when_raw_integer_set_then_not_normalized(font):
    for node in (GSNode(), font.glyphs[0].layers[0].paths[0].nodes[0]):
        node.connection = 1
        assert node.connection == 1 and not node.smooth
        node.smooth = True
        assert node.connection == 100
    font._model._backend.close_font(font.id)
    with pytest.raises(StaleNativeObject):
        node.connection = 1


def test_native_connection_when_unrepresentable_value_then_refused_before_mutation(
    monkeypatch,
):
    from fontlab_glyport.model.fontlab_backend import FontLabBackend

    backend, writes = FontLabBackend(packages=[]), []
    monkeypatch.setattr(backend, "_object", lambda token: object())
    monkeypatch.setattr(
        backend, "set_node_smooth", lambda token, smooth: writes.append((token, smooth))
    )
    backend.set_node_connection("node", 100)
    backend.set_node_connection("node", 0)
    assert writes == [("node", True), ("node", False)]
    with pytest.raises(UnsupportedCapability) as error:
        backend.set_node_connection("node", 1)
    assert error.value.capability == "GSNode.connection" and len(writes) == 2
    path = GSPath([GSNode()])
    path.nodes[0].connection = 1
    backend._object_keys["unused-layer"] = ("font", "layer", "glyph", "master")
    with pytest.raises(UnsupportedCapability) as error:
        backend.insert_path("unused-layer", 0, path._data())
    assert error.value.capability == "GSNode.connection"
