# this_file: tests/test_issue106_round33.py
"""Component placement/bounds and mutable indexed collection clearing."""

from dataclasses import replace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSComponent, GSGuide, Model
from fontlab_glyport.model.backend import (
    ComponentInfo,
    GlyphInfo,
    LayerInfo,
    NodeInfo,
    PathInfo,
)
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def font():
    backend = FakeBackend()
    backend.glyph_lists["font"] += (GlyphInfo("base", "base", ()),)
    backend.layers["base", "master"] = LayerInfo(
        "base-layer",
        "master",
        500,
        paths=(
            PathInfo(
                "base-path",
                (NodeInfo("b0", 0, 0), NodeInfo("b1", 100, 0), NodeInfo("b2", 0, 50)),
                True,
            ),
        ),
        shape_ids=("base-path",),
    )
    backend.layers["glyph", "master"] = replace(
        backend.layers["glyph", "master"],
        components=(ComponentInfo("component", "base", (0, 2, -1, 0, 20, 30)),),
    )
    return Model(backend).font


def test_live_position_changes_only_translation_and_bounds_use_full_transform(font):
    pytest.importorskip("fontTools")
    component = font.glyphs["A"].layers[0].components[0]
    assert tuple(component.position) == (20, 30)
    assert tuple(component.bounds.origin) == (-30, 30)
    assert tuple(component.bounds.size) == (50, 200)
    component.position = (40, 60)
    assert component.transform == (0, 2, -1, 0, 40, 60)
    assert tuple(component.bounds.origin) == (-10, 60)


def test_draft_position_can_move_without_attaching():
    component = GSComponent("A", (2, 3))
    component.position = (5, 9)
    assert tuple(component.position) == (5, 9)
    assert component.transform == (1, 0, 0, 1, 5, 9)


def test_guides_clear_uses_indexed_collection_removal_and_handles_empty(font):
    layer = font.glyphs["A"].layers[0]
    layer.guides = [GSGuide((10, 20)), GSGuide((30, 40))]
    font._model._backend.undo_events.clear()
    with font.undo_group("Clear guides"):
        assert layer.guides.clear() is None
    assert list(layer.guides) == []
    assert layer.guides.clear() is None
    assert font._model._backend.undo_events == [
        ("begin", "Clear guides"),
        ("end", None),
    ]


def test_readonly_indexed_collection_clear_refuses(font):
    with pytest.raises(UnsupportedCapability) as info:
        font.masters.clear()
    assert info.value.capability == "collection.clear"
    assert len(font.masters) == 1


@pytest.fixture
def native_component(monkeypatch):
    from types import SimpleNamespace as NS

    from test_issue106_round9 import native as native_fixture

    n = native_fixture.__wrapped__(monkeypatch)

    def transform(a=1, b=0, c=0, d=1, x=0, y=0):
        return NS(
            isAffine=lambda: True,
            m11=lambda: a,
            m12=lambda: b,
            m21=lambda: c,
            m22=lambda: d,
            dx=lambda: x,
            dy=lambda: y,
        )

    shape = n.layer.shapes[0]
    shape.isComponent = shape.isComposite = True
    shape.shapeData = NS(componentGlyph="base", builder=NS())
    shape.transform = transform(0, 2, -1, 0, 20, 30)
    shape.inkBox = lambda identity: NS(
        isNull=lambda: False,
        x=lambda: -30,
        y=lambda: 30,
        width=lambda: 50,
        height=lambda: 200,
    )
    n.original = shape
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=transform),
    )
    n.component = n.font.glyphs[0].layers[0].components[0]
    return n


def test_native_position_owns_clone_and_preserves_undo_notification(native_component):
    n = native_component
    with n.font.undo_group("Move component"):
        n.component.position = (40, 60)
        assert n.backend._undo_name == "Move component"
    assert n.layer.shapes[0] is not n.original
    assert (n.original.transform.dx(), n.original.transform.dy()) == (20, 30)
    assert tuple(n.component.position) == (40, 60)
    assert n.component.transform == (0, 2, -1, 0, 40, 60)
    assert len(n.calls) == 2
    assert n.calls[0] == ("Move component", [n.layer, n.glyph], True)
    assert n.calls[1] == (
        "Move component",
        [
            n.original,
            n.original.shapeData,
            n.original.shapeData.builder,
            n.layer,
            n.glyph,
        ],
        True,
    )


def test_native_component_bounds_reads_transformed_ink_without_writes(native_component):
    n = native_component
    assert tuple(n.component.bounds.origin) == (-30, 30)
    assert tuple(n.component.bounds.size) == (50, 200)
    assert n.layer.shapes[0] is n.original
    assert n.calls == []


def test_native_auto_layer_move_refuses_without_notifying(native_component):
    n = native_component
    n.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability) as info:
        n.component.position = (40, 60)
    assert info.value.capability == "GSComponent.position.autoLayer"
    assert n.layer.shapes[0] is n.original
    assert n.calls == []


def test_collection_clear_stops_and_propagates_remove_failure():
    from types import SimpleNamespace as NS

    from fontlab_glyport.model.indexes import IndexedSequence

    values = [NS(id=str(i), _id=str(i)) for i in range(3)]
    attempts = []

    def remove(value):
        attempts.append(value.id)
        if value.id == "1":
            raise RuntimeError("remove refused")
        values.remove(value)

    seq = IndexedSequence(
        lambda: len(values),
        lambda: values,
        lambda key: next(v for v in values if v.id == key),
        remove=remove,
    )
    with pytest.raises(RuntimeError, match="remove refused"):
        seq.clear()
    assert attempts == ["2", "1"]
    assert [value.id for value in values] == ["0", "1"]
