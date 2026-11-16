# this_file: tests/test_issue106_round18.py
"""Native history changes must invalidate long-lived model snapshots."""

import pytest
from test_issue106_round9 import native as native_fixture


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_native_undo_refreshes_long_lived_layer_and_node_snapshots(native):
    marker = [0]
    native.glyph.currentHistoryState = lambda: marker[0]
    original = native.layer.shapes[0]
    node_type = type(original.contours[0].nodes()[0])
    original.contours[0]._nodes = [node_type(10 + i) for i in range(5)]
    layer = native.font.glyphs[0].layers[0]
    assert len(layer.paths[0].nodes) == 5
    assert layer.paths[0].nodes[0].x == 10
    changed = original.clone()
    changed.contours[0]._nodes = [node_type(77 + i) for i in range(12)]
    native.layer.shapes[:] = [changed]
    marker[0] = 1
    assert layer.paths[0].nodes[0].x == 77
    assert len(layer.paths[0].nodes) == 12
    native.layer.shapes[:] = [original]
    marker[0] = 0
    assert layer.paths[0].nodes[0].x == 10
    assert len(layer.paths[0].nodes) == 5


def test_node_write_reaches_current_native_contour_and_preserves_original(native):
    original = native.layer.shapes[0]
    node = native.font.glyphs[0].layers[0].paths[0].nodes[0]
    node.x += 7
    assert native.layer.shapes[0].contours[0].nodes()[0].x == 17
    assert original.contours[0].nodes()[0].x == 10


def test_keyed_assignment_copies_attached_anchor_before_renaming():
    from fontlab_glyport.model import GSAnchor, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.anchors = [GSAnchor("source", (12, 34))]
    source = layer.anchors["source"]
    layer.anchors["target"] = source
    assert layer.anchors["target"].position == (12, 34)
    assert layer.anchors["source"].name == "source"
    layer.anchors["source"] = layer.anchors["source"]
    assert layer.anchors["source"].position == (12, 34)


def test_system_pink_color_available_without_graphics_context():
    from fontlab_glyport.drawing.cocoa_drawing import NSColor

    color = NSColor.systemPinkColor()
    assert color.redComponent() == 1


def test_plain_layer_has_no_automatically_aligned_width():
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.components = []
    assert layer.hasAlignedWidth() is False


def test_export_messages_and_exceptions_are_written_to_plugin_output():
    from types import SimpleNamespace as NS

    from fontlab_glyport.plugins.base import FileFormatPlugin

    output = []
    plugin = FileFormatPlugin()
    plugin.name = "Example"
    plugin._env = NS(log=output.append, host=NS(notify=lambda *args: None))
    plugin.export = lambda font: (False, "No destination selected")
    plugin.exportFont_(None)
    assert any("No destination selected" in line for line in output)

    def fail(font):
        raise RuntimeError("export failed visibly")

    plugin.export = fail
    with pytest.raises(RuntimeError, match="export failed visibly"):
        plugin.exportFont_(None)
    assert any("RuntimeError: export failed visibly" in line for line in output)


def test_native_history_refreshes_retained_node_even_when_ids_do_not_change(native):
    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    node = native.font.glyphs[0].layers[0].paths[0].nodes[0]
    assert node.x == 10
    current = native.layer.shapes[0].contours[0].nodes()[0]
    for history, x in [(5, 90), (4, 10), (6, 123)]:
        current.x = x
        marker[0] = history
        assert node.x == x


def test_bulk_paths_preserves_retained_component_in_writer_and_peer(
    native, monkeypatch
):
    from types import SimpleNamespace as NS

    from test_issue106_round10 import peer_font

    component = type(native.layer.shapes[0])()
    component.isComponent = component.isComposite = True
    component.shapeData = NS(componentGlyph="A", builder=NS())
    component.transform.isAffine = lambda: True
    for name, value in zip(
        ("m11", "m12", "m21", "m22", "dx", "dy"), (1, 0, 0, 1, 0, 0)
    ):
        setattr(component.transform, name, lambda value=value: value)
    native.layer.shapes.append(component)
    layer = native.font.glyphs[0].layers[0]
    writer = layer.components[0]
    observer = peer_font(native, monkeypatch).glyphs[0].layers[0].components[0]
    assert writer.componentName == observer.componentName == "A"
    layer.paths = []
    assert writer.componentName == observer.componentName == "A"
    assert writer.transform == observer.transform == (1, 0, 0, 1, 0, 0)
    assert native.backend._objects[writer.id] is not component


def test_attached_anchor_assignment_failure_leaves_source_and_target_unchanged(
    monkeypatch,
):
    from fontlab_glyport.model import GSAnchor, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    layer.anchors = [GSAnchor("source", (12, 34))]
    source = layer.anchors["source"]

    def fail(*args):
        raise RuntimeError("insertion failed")

    monkeypatch.setattr(backend, "add_anchor", fail)
    with pytest.raises(RuntimeError, match="insertion failed"):
        layer.anchors["target"] = source
    assert [(a.name, a.position) for a in layer.anchors] == [("source", (12, 34))]
    assert source.name == "source"


@pytest.mark.parametrize("font_size", [100, 2000])
def test_history_validation_does_not_relist_geometry_on_unchanged_reads(
    native, monkeypatch, font_size
):
    # Extra font siblings must have no effect on a node's cache validation cost.
    for number in range(font_size):
        native.backend._register(
            (native.fid, "glyph", 50000 + number), None, native.fid
        )
    history_calls = []
    native.glyph.currentHistoryState = lambda: history_calls.append(1) or 0
    reads = []
    read_layer = native.backend.layer

    def counted(*args):
        reads.append(1)
        return read_layer(*args)

    monkeypatch.setattr(native.backend, "layer", counted)
    node = native.font.glyphs[0].layers[0].paths[0].nodes[0]
    reads.clear()
    history_calls.clear()
    for _ in range(100):
        assert node.x == 10
    assert not reads, "unchanged native history must reuse the geometry snapshot"
    assert 100 <= len(history_calls) <= 500, "bounded history checks per read"


def test_component_aligned_width_refuses_instead_of_inventing_alignment_state():
    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model import GSComponent, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.components = [GSComponent("A")]
    with pytest.raises(UnsupportedCapability) as error:
        _ = layer.hasAlignedWidth()
    assert error.value.capability == "GSLayer.hasAlignedWidth"


def test_attached_anchor_can_be_assigned_across_layers_with_key_rename():
    from fontlab_glyport.model import GSAnchor, GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    font = Model(FakeBackend()).font
    source = font.glyphs[0].layers[0]
    target = font.glyphs.append(GSGlyph("destination")).layers[0]
    source.anchors = [GSAnchor("top", (30, 70))]
    target.anchors["top"] = source.anchors["top"]
    target.anchors["renamed"] = source.anchors["top"]
    assert [(a.name, a.position) for a in target.anchors] == [
        ("top", (30, 70)),
        ("renamed", (30, 70)),
    ]
    assert source.anchors["top"].name == "top"
