# this_file: tests/test_transform_finite.py
"""Reject invalid transform inputs before owned geometry or history changes."""

from copy import deepcopy

import pytest

from fontlab_glyport.model import GSAnchor, GSComponent, GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize(
    "kind",
    [
        "layer",
        "path",
        "detached-layer",
        "detached-path",
        "empty-path",
        "selector-00",
        "selector-01",
        "selector-10",
        "selector-11",
    ],
)
@pytest.mark.parametrize("position", range(6))
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_transform_when_nonfinite_then_no_mutation_or_history(
    kind, position, invalid, monkeypatch
):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    detached = layer.copy()
    detached.paths = [GSPath([GSNode((2, 3)), GSNode((-4, 5))])]
    detached.anchors = [GSAnchor("top", (11, 19))]
    detached.components = [GSComponent("A")]
    targets = {
        "layer": layer,
        "path": layer.paths[0],
        "detached-layer": detached,
        "detached-path": detached.paths[0],
        "empty-path": GSPath([]),
    }
    target = targets.get(kind, layer)
    backend_calls = []
    original = backend.transform_layer

    def transform(*args):
        backend_calls.append(args)
        return original(*args)

    monkeypatch.setattr(backend, "transform_layer", transform)
    before = deepcopy(dict(backend.layers)), list(backend.undo_events)
    detached_before = (
        [tuple(n.position) for p in detached.paths for n in p.nodes],
        [tuple(c.transform) for c in detached.components],
        [tuple(a.position) for a in detached.anchors],
    )
    values = [1, 0, 0, 1, 13, -7]
    values[position] = invalid
    with pytest.raises(ValueError, match="finite"):
        if kind.startswith("selector-"):
            layer.transform_checkForSelection_doComponents_(
                values, bool(int(kind[-2])), bool(int(kind[-1]))
            )
        else:
            target.applyTransform(values)
    assert not backend_calls, "invalid input must not enter any backend"
    assert (dict(backend.layers), backend.undo_events) == before, (
        "invalid input must not reach geometry/history"
    )
    assert (
        [tuple(n.position) for p in detached.paths for n in p.nodes],
        [tuple(c.transform) for c in detached.components],
        [tuple(a.position) for a in detached.anchors],
    ) == detached_before, "detached geometry must remain intact"


@pytest.mark.parametrize("scale", [-1, 0, 1.5])
def test_transform_when_finite_scale_then_existing_geometry_semantics_remain(scale):
    path = GSPath([GSNode((2, 3)), GSNode((-4, 5))])
    path.applyTransform((scale, 0, 0, scale, 13, -7))
    assert [tuple(n.position) for n in path.nodes] == [
        (scale * 2 + 13, scale * 3 - 7),
        (-4 * scale + 13, scale * 5 - 7),
    ]
