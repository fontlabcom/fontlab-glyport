# this_file: tests/test_issue106_round33b.py
"""Native auto layers must never enter glyport's edit notification protocol."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.errors import UnsupportedCapability


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_auto_layer_guides_clear_refuses_before_mutation_or_notification(native):
    native.layer.guidelines = [
        NS(
            id=900,
            isValid=True,
            isHint=False,
            centerPoint=NS(x=lambda: 1, y=lambda: 2),
            angle=0,
            name="keep",
        )
    ]
    layer = native.font.glyphs[0].layers[0]
    assert len(layer.guides) > 0
    before = list(native.layer.guidelines)
    native.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability, match="auto layer"):
        layer.guides.clear()
    assert native.layer.guidelines == before
    assert native.calls == []


@pytest.mark.parametrize(
    "operation",
    [
        "width",
        "node",
        "anchor",
        "guide",
        "paths",
        "components",
        "anchors",
        "guides",
        "hints",
        "append_path",
        "append_component",
        "append_anchor",
        "append_guide",
        "background",
        "grouping",
        "touch",
    ],
)
def test_auto_layer_edit_boundaries_refuse_before_native_work(
    native, monkeypatch, operation
):
    from fontlab_glyport.model import GSAnchor, GSComponent, GSGuide, GSPath

    b = native.backend
    layer = native.font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    native.layer.anchors = [NS(id=901, isValid=True, name="top", point=None)]
    aid = b._register((native.fid, "anchor", 901), native.layer.anchors[0], native.lid)
    guide = NS(id=902, isValid=True, name="guide", angle=0)
    native.layer.guidelines = [guide]
    gid = b._register((native.fid, "guide", 902), guide, native.lid)
    shapes = list(native.layer.shapes)
    native.layer.autoLayer = True

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Native construction/tool/mutation occurred before auto-layer refusal"
        )

    monkeypatch.setattr(b, "_build_component", forbidden)
    monkeypatch.setattr(b, "_build_path", forbidden)
    monkeypatch.setattr(b, "_build_anchor", forbidden)
    monkeypatch.setattr(b, "_new_guide", forbidden)
    monkeypatch.setattr(b, "_resolve_tool", forbidden)
    actions = {
        "width": lambda: setattr(layer, "width", 123),
        "node": lambda: setattr(node, "position", (12, 34)),
        "anchor": lambda: b.set_anchor_position(aid, 3, 4),
        "guide": lambda: b.set_guide(gid, name="changed"),
        "paths": lambda: setattr(layer, "paths", []),
        "components": lambda: setattr(layer, "components", []),
        "anchors": lambda: setattr(layer, "anchors", []),
        "guides": lambda: setattr(layer, "guides", []),
        "hints": lambda: b._edit_hints(native.lid, {}, "GSLayer.hints"),
        "append_path": lambda: layer.paths.append(GSPath()),
        "append_component": lambda: layer.components.append(GSComponent("A")),
        "append_anchor": lambda: layer.anchors.append(GSAnchor("new", (1, 2))),
        "append_guide": lambda: layer.guides.append(GSGuide()),
        "background": lambda: b._writable_layer(b.background_layer(native.lid).id),
        "grouping": lambda: b.restore_path_grouping(native.lid, (2,)),
        "touch": lambda: b._touch_layer(native.lid),
    }
    with pytest.raises(UnsupportedCapability, match="auto layer"):
        actions[operation]()
    assert native.calls == []
    assert native.layer.shapes == shapes
    assert native.layer.anchors[0].name == "top"
    assert native.layer.guidelines == [guide]
    assert guide.name == "guide"
    assert native.layer.mask is None
    assert native.layer.advanceWidth == 500
    assert node.position == (10, 2)


@pytest.mark.parametrize("existing", [False, True])
def test_auto_foreground_blocks_mask_creation_and_existing_mask_edits(native, existing):
    from test_issue106_round7_native import Layer

    b = native.backend
    if existing:
        native.layer.mask = Layer(987)
    mask = native.layer.mask
    lid = b.background_layer(native.lid).id
    native.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability, match="auto layer"):
        b.set_layer_width(lid, 123)
    assert native.layer.mask is mask
    if existing:
        assert mask.advanceWidth == 500
    assert native.calls == []
    assert True not in native.layer.mask_calls


@pytest.mark.parametrize("field", ["paths", "anchors", "shapes", "components"])
def test_auto_layer_collection_clear_and_remove_refuse(native, field):
    if field == "anchors":
        native.layer.anchors = [
            NS(id=903, isValid=True, name="top", point=NS(x=lambda: 1, y=lambda: 2))
        ]
    elif field == "components":
        shape = native.layer.shapes[0]
        shape.isComponent = shape.isComposite = True
        shape.shapeData = NS(componentGlyph="A")
        shape.transform.isAffine = lambda: True
        shape.transform.m11 = shape.transform.m22 = lambda: 1
        shape.transform.m12 = shape.transform.m21 = shape.transform.dx = (
            shape.transform.dy
        ) = lambda: 0
    layer = native.font.glyphs[0].layers[0]
    collection = getattr(layer, field)
    assert len(collection) > 0
    member = collection[0]
    shapes = list(native.layer.shapes)
    anchors = list(native.layer.anchors)
    native.layer.autoLayer = True
    for edit in (collection.clear, lambda: collection.remove(member)):
        with pytest.raises(UnsupportedCapability, match="auto layer"):
            edit()
        assert native.layer.shapes == shapes
        assert native.layer.anchors == anchors
        assert native.calls == []
