# this_file: tests/test_transform_overflow.py
"""Finite matrices must be checked against all Python-managed geometry first."""

from copy import deepcopy
from dataclasses import replace

import pytest

from fontlab_glyport.model import GSAnchor, GSComponent, GSNode, GSPath, Model
from fontlab_glyport.model.backend import NodeInfo, PathInfo
from fontlab_glyport.model.fake_backend import FakeBackend

MATRIX = (2, 0, 0, 2, 13, -7)


@pytest.mark.parametrize("kind", ["path", "selector-all", "selector-selected"])
def test_live_transform_when_late_point_overflows_then_no_history_or_write(kind):
    backend = FakeBackend()
    data = backend.layers["glyph", "master"]
    nodes = (
        NodeInfo("first", 2, 3, selected=True),
        NodeInfo("last", 1e308, 5, selected=True),
    )
    backend.layers["glyph", "master"] = replace(
        data, paths=(PathInfo("path", nodes),), components=(), shape_ids=("path",)
    )
    layer = Model(backend).font.glyphs[0].layers[0]
    before = deepcopy(dict(backend.layers)), list(backend.undo_events)
    with pytest.raises(ValueError, match="finite"):
        if kind == "path":
            layer.paths[0].applyTransform(MATRIX)
        else:
            layer.transform_checkForSelection_doComponents_(
                MATRIX, kind == "selector-selected", False
            )
    assert (dict(backend.layers), backend.undo_events) == before, (
        "preflight must leave all points and history untouched"
    )


@pytest.mark.parametrize("overflow_in", ["node", "anchor", "component"])
def test_detached_layer_when_late_item_overflows_then_every_payload_is_unchanged(
    overflow_in,
):
    layer = Model(FakeBackend()).font.glyphs[0].layers[0].copy()
    layer.paths = [
        GSPath([GSNode((2, 3)), GSNode((1e308 if overflow_in == "node" else 4, 5))])
    ]
    layer.anchors = [GSAnchor("top", (1e308 if overflow_in == "anchor" else 11, 19))]
    component = GSComponent("A")
    component.position = (1e308 if overflow_in == "component" else 23, 29)
    layer.components = [component]

    def snapshot():
        return (
            [tuple(n.position) for p in layer.paths for n in p.nodes],
            [tuple(a.position) for a in layer.anchors],
            [tuple(c.transform) for c in layer.components],
        )

    before = snapshot()
    with pytest.raises(ValueError, match="finite"):
        layer.applyTransform(MATRIX)
    assert snapshot() == before, (
        "late overflow must preserve earlier nodes, anchors and components"
    )


def test_detached_path_when_late_point_overflows_then_earlier_point_is_unchanged():
    path = GSPath([GSNode((2, 3)), GSNode((1e308, 5))])
    before = [tuple(n.position) for n in path.nodes]
    with pytest.raises(ValueError, match="finite"):
        path.applyTransform(MATRIX)
    assert [tuple(n.position) for n in path.nodes] == before, (
        "do not partially transform a draft path"
    )


def test_detached_layer_when_finite_combined_matrix_then_shapes_and_anchors_keep_order():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0].copy()
    layer.paths = [GSPath([GSNode((2, 3))])]
    layer.anchors = [GSAnchor("top", (11, 19))]
    component = GSComponent("A")
    component._draft = replace(component._draft, transform=(0, 1, -1, 0, 23, 29))
    layer.components = [component]
    layer.applyTransform((2, 1, 3, 4, 5, 6))
    assert tuple(layer.paths[0].nodes[0].position) == (18, 20)
    assert tuple(layer.anchors[0].position) == (84, 93)
    assert tuple(layer.components[0].transform) == (3, 4, -2, -1, 138, 145)


@pytest.mark.parametrize("kind", ["path", "node", "component"])
def test_transform_when_same_object_repeats_then_each_occurrence_is_applied(kind):
    node = GSNode((2, 3))
    path = GSPath([node, node] if kind == "node" else [node])
    layer = Model(FakeBackend()).font.glyphs[0].layers[0].copy()
    layer.paths = [path, path] if kind == "path" else [path]
    component = GSComponent("A")
    component.position = (2, 3)
    layer.components = [component, component] if kind == "component" else []
    if kind == "node":
        path.applyTransform((2, 0, 0, 2, 0, 0))
    else:
        layer.applyTransform((2, 0, 0, 2, 0, 0))
    actual = component.position if kind == "component" else node.position
    assert tuple(actual) == (8, 12), "each repeated object receives the transform again"


def test_transform_when_repeat_overflows_then_preflight_does_not_write_first_occurrence():
    node = GSNode((5e307, 3))
    path = GSPath([node, node])
    with pytest.raises(ValueError, match="finite"):
        path.applyTransform((2, 0, 0, 2, 0, 0))
    assert tuple(node.position) == (5e307, 3), "repeated transforms must be preflighted sequentially"
