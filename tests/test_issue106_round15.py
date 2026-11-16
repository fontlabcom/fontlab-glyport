# this_file: tests/test_issue106_round15.py
"""Round-15 review regressions and grouped oracle reproductions."""

import pytest

from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


def make_copy(manager):
    backend = FakeBackend()
    font = Model(backend).font
    font.parent._local_glyph_info = manager
    source = font.glyphs[0].layers[0]
    source.components = []
    source.leftMetricsKey = "=B"
    source.rightMetricsKey = "=|B"
    source.widthMetricsKey = "==B"
    source.background.paths = [GSPath([GSNode((21, 34)), GSNode((55, 89))])]
    clone = font.glyphs[0].copy()
    with manager._scope():
        clone.name = "A.copy"
    return backend, font, clone


def test_attach_preserves_backgrounds_and_all_layer_metrics_keys(owned_edit_info):
    _, font, clone = make_copy(owned_edit_info)
    font.glyphs.append(clone)
    layer = clone.layers[0]
    assert [n.position for n in layer.background.paths[0].nodes] == [(21, 34), (55, 89)]
    assert (layer.leftMetricsKey, layer.rightMetricsKey, layer.widthMetricsKey) == (
        "=B",
        "=|B",
        "==B",
    )


@pytest.mark.parametrize("failure", ["foreground", "background", "metrics"])
def test_failed_attachment_removes_insertion_and_keeps_detached_copy(
    monkeypatch, failure, owned_edit_info
):
    backend, font, clone = make_copy(owned_edit_info)
    source_type, source_dict = type(clone), dict(clone.__dict__)
    saved_paths = list(clone.layers[0].paths)
    pending_before = set(backend._pending_backgrounds)
    original_append = backend.append_path
    writes = []

    def fail_append(layer_id, path):
        writes.append(layer_id)
        if failure == "foreground" or (failure == "background" and len(writes) == 2):
            raise RuntimeError("injected attachment failure")
        return original_append(layer_id, path)

    if failure == "metrics":

        def fail_metrics(*args):
            raise RuntimeError("injected attachment failure")

        monkeypatch.setattr(backend, "set_layer_metrics_key", fail_metrics)
    else:
        monkeypatch.setattr(backend, "append_path", fail_append)
    with pytest.raises(RuntimeError, match="injected attachment failure"):
        font.glyphs.append(clone)
    assert font.glyphs["A.copy"] is None
    assert set(backend._pending_backgrounds) == pending_before
    assert type(clone) is source_type and clone.parent is None and clone.id == ""
    assert clone.__dict__ == source_dict
    assert list(clone.layers[0].paths) == saved_paths
    assert clone.layers[0].leftMetricsKey == "=B"
    monkeypatch.undo()
    font.glyphs.append(clone)
    assert clone.parent is font and len(clone.layers[0].background.paths) == 1


def test_empty_layer_sidebearings_accept_writes_without_creating_geometry():
    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    layer.shapes = []
    layer.LSB = 10
    assert layer.LSB == 0 and layer.width == 500
    layer.RSB = 25
    assert layer.RSB == 25 and layer.width == 25 and not layer.shapes
    detached = layer.copy()
    detached.LSB = 20
    detached.RSB = 30
    assert detached.width == 30 and not detached.shapes


def test_node_names_survive_copy_and_path_attachment():
    node = GSNode((1, 2))
    assert node.name is None
    node.name = "entry"
    assert node.copy().name == "entry"
    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    layer.paths = [GSPath([node])]
    assert layer.paths[0].nodes[0].name == "entry"
    layer.paths[0].nodes[0].name = "exit"
    assert layer.paths[0].nodes[0].copy().name == "exit"


def test_node_index_paths_use_shape_order_and_round_trip():
    from fontlab_glyport.model import GSComponent

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.shapes = [GSComponent("A"), GSPath([GSNode((1, 2)), GSNode((3, 4))])]
    node = layer.paths[0].nodes[1]
    index = layer.indexPathOfNode_(node)
    assert (
        index.length() == 2
        and index.indexAtPosition_(0) == 1
        and tuple(index) == (1, 1)
    )
    assert layer.nodeAtIndexPath_(index) is node
    assert layer.indexPathOfNode_(GSNode()) is None
    assert layer.nodeAtIndexPath_((0, 0)) is None
    assert layer.nodeAtIndexPath_((99, 0)) is None


def test_master_custom_parameters_are_separate_from_font_parameters():
    font = Model(FakeBackend()).font
    master = font.masters[0]
    assert master.customParameters["Link Metrics With Master"] is None
    master.customParameters["test"] = "master value"
    font.customParameters["test"] = "font value"
    assert master.customParameters["test"] == "master value"
    assert font.customParameters["test"] == "font value"
    assert (
        Model(font._model._backend).font.masters[0].customParameters["test"]
        == "master value"
    )


def test_segments_have_the_entire_ticket_iteration_protocol():
    segment = GSPath([GSNode((0, 0)), GSNode((30, 40))], closed=False).segments[0]
    assert (segment.type, segment.count(), len(segment), segment.length()) == (
        "line",
        2,
        2,
        50,
    )
    assert segment.pointAtIndex_(0) == (0, 0)
    assert list(segment) == [(0, 0), (30, 40)]


@pytest.mark.parametrize("detached", [False, True])
def test_anchor_key_assignment_renames_argument_and_replaces(detached):
    from fontlab_glyport.model import GSAnchor

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    if detached:
        layer = layer.copy()
    source = GSAnchor("source", (12, 34))
    layer.anchors["target"] = source
    assert layer.anchors["target"].position == (12, 34)
    assert source.name == "target" and source.position == (12, 34)
    layer.anchors["target"] = GSAnchor("other", (56, 78))
    assert len(layer.anchors) == 1 and layer.anchors["target"].position == (56, 78)
    layer.anchors["target"].position = (90, 12)
    assert source.position == (12, 34)


def test_master_compatibility_compares_ordered_topology_not_coordinates():
    from dataclasses import replace

    from fontlab_glyport.model.backend import LayerInfo, MasterInfo, NodeInfo, PathInfo

    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
    )
    backend.layers["glyph", "master"] = LayerInfo(
        "layer", "master", 500, (PathInfo("path", (NodeInfo("node", 0, 0),), False),)
    )
    backend.layers["glyph", "bold"] = LayerInfo(
        "layer-bold",
        "bold",
        600,
        (PathInfo("path-bold", (NodeInfo("node-bold", 500, 700),), False),),
    )
    glyph = Model(backend).font.glyphs[0]
    assert glyph.mastersCompatibleForLayerIds_(["master", "bold"]) is True
    backend.layers["glyph", "bold"] = replace(backend.layers["glyph", "bold"], paths=())
    assert glyph.mastersCompatibleForLayerIds_(["master", "bold"]) is False
    assert glyph.mastersCompatibleForLayerIds_(["master", "missing"]) is True


def test_master_compatibility_includes_anchor_names_and_ignores_anchor_positions():
    from dataclasses import replace

    from fontlab_glyport.model.backend import AnchorInfo, LayerInfo, MasterInfo

    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
    )
    backend.layers["glyph", "master"] = LayerInfo(
        "layer", "master", 500, anchors=(AnchorInfo("a", "top", 10, 20),)
    )
    backend.layers["glyph", "bold"] = LayerInfo(
        "layer-bold", "bold", 600, anchors=(AnchorInfo("b", "top", 30, 40),)
    )
    glyph = Model(backend).font.glyphs[0]
    assert glyph.mastersCompatibleForLayerIds_(["master", "bold"])
    backend.layers["glyph", "bold"] = replace(
        backend.layers["glyph", "bold"], anchors=(AnchorInfo("b", "bottom", 30, 40),)
    )
    assert not glyph.mastersCompatibleForLayerIds_(["master", "bold"])
