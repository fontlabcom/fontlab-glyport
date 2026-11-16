# this_file: tests/test_issue106_round22.py
"""Catalog replacement, moved identities, and native edit boundaries."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model.backend import HintInfo


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("grouped", [False, True])
def test_shape_replacement_commits_before_native_hint_tool(
    native, monkeypatch, grouped
):
    from contextlib import nullcontext

    from fontlab_glyport.model import GSNode, GSPath, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    events = []
    shape_type = type(native.layer.shapes[0])
    contour_type = type(native.layer.shapes[0].contours[0])
    node_type = type(native.layer.shapes[0].contours[0].nodes()[0])

    def node(point, *, nodeType):
        result = node_type(point.x())
        result.y = point.y()
        result.nodeState = (result.nodeState & ~7) | {"on": 1, "off": 2, "curve": 4}[
            nodeType
        ]
        return result

    def contour(nodes, *, closed):
        result = contour_type(0)
        result._nodes, result.closed = list(nodes), closed
        return result

    def shape():
        result = shape_type()
        result.contours = []
        result.addContour = lambda value, clone: result.contours.append(value)
        return result

    def append(value):
        events.append("shape write")
        native.layer.shapes.append(value)
        return value

    node.NodeKind = node_type.NodeKind
    native.module.flNode, native.module.flContour, native.module.flShape = (
        node,
        contour,
        shape,
    )
    native.layer.addShape = append
    source = Model(FakeBackend()).font.glyphs[0].layers[0]
    source.paths = [GSPath([GSNode((15, 20)), GSNode((25, 30))], closed=False)]
    for item, label in ((native.layer, "layer"), (native.glyph, "glyph")):
        item.changed = lambda label=label: events.append(label + ".changed")
        item.update = lambda label=label: events.append(label + ".update")
    monkeypatch.setattr(
        native.backend,
        "_resolve_tool",
        lambda *args: lambda **kw: events.append("hint tool"),
    )
    layer = native.font.glyphs[0].layers[0]
    scope = native.font.undo_group("Replace") if grouped else nullcontext()
    with scope:
        layer.paths = []
        layer.shapes.append(source.paths[0].copy())
        native.backend.add_hint(layer.id, HintInfo(True, 30, 20))
        updates = ["layer.changed", "layer.update", "glyph.changed", "glyph.update"]
        # Two contour removals and the grouping boundary each refresh caches.
        # Appending then refreshes before the existing pre-tool barrier; the
        # completed hint edit refreshes again after the tool returns.
        assert (
            events
            == updates * 3 + ["shape write"] + updates * 2 + ["hint tool"] + updates
        )


@pytest.mark.parametrize("names", [("B",), ("A",), ("B", "A")])
def test_same_count_native_replacement_refreshes_catalog_once(
    native, monkeypatch, names
):
    from fontlab_glyport.errors import StaleNativeObject
    from fontlab_glyport.model.fontlab_backend import FontLabBackend

    listings = []
    rows, objects = [], {}

    class Catalog:
        @property
        def glyphs(self):
            listings.append(1)
            return tuple(rows)

        def __getitem__(self, name):
            return next(row for row in rows if row.name == name)

    def populate(names, start):
        for item in objects.values():
            item.isValid = False
        rows.clear()
        objects.clear()
        for index, name in enumerate(names):
            identity = start + index
            row = NS(id=identity, name=name, unicodes=[0x41 + index])
            rows.append(row)
            objects[identity] = NS(
                id=identity, name=name, isValid=True, currentHistoryState=lambda: 4
            )

    native.package.fgPackage = Catalog()
    native.package.findFgId = objects.get
    native.package.findName = lambda name: next(
        (obj for obj in objects.values() if obj.name == name), None
    )
    native.package.glyphsCount = len(names)
    monkeypatch.setattr(
        native.backend, "glyphs", FontLabBackend.glyphs.__get__(native.backend)
    )
    populate(("A",) if len(names) == 1 else ("A", "B"), 1000)
    font = native.font
    old = font.glyphs["A"]
    assert old.name == "A"
    populate(names, 2000)
    assert font.glyphs[names[0]].name == names[0]
    assert font.glyphForUnicode_("0041") is font.glyphs[names[0]]
    assert [glyph.name for glyph in font.glyphs] == list(names)
    assert listings == [1, 1], "one bounded catalog rebuild, not one per hit"
    with pytest.raises(StaleNativeObject):
        _ = old.name
    for _ in range(20):
        assert font.glyphs[names[0]].name == names[0]
    assert len(listings) == 2


@pytest.mark.parametrize("first", ["retained", "destination", "parent"])
def test_moved_native_node_rebinds_reader_and_parent(native, first):
    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    layer = native.font.glyphs[0].layers[0]
    source, destination = layer.paths[0], layer.paths[1]
    retained = source.nodes[0]
    assert retained.position == (10, 2)
    shape = native.layer.shapes[0]
    moved = shape.contours[0]._nodes.pop()
    shape.contours[1]._nodes.append(moved)
    marker[0] = 5
    if first == "parent":
        assert retained.parent is destination
    elif first == "retained":
        assert retained.position == (10, 2)
    else:
        assert destination.nodes[1].position == (10, 2)
    assert destination.nodes[1] is retained
    assert retained.parent is destination
    assert retained.index == 1
    retained.position = (31, 42)
    assert native.layer.shapes[0].contours[1].nodes()[1].x == 31


@pytest.mark.parametrize("kind", ["path", "component"])
@pytest.mark.parametrize("destination_first", [False, True])
def test_native_shapes_moved_between_layers_keep_proxy_and_parent(
    native, monkeypatch, kind, destination_first
):
    from dataclasses import replace

    from fontlab_glyport.model.backend import MasterInfo

    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    native.package.masters.append("Bold")
    bold = native.backend._register(
        (native.fid, "master", "Bold"), native.package, native.fid
    )
    native.backend._master_names[bold] = "Bold"
    info = native.backend.font_info(native.fid)
    monkeypatch.setattr(
        native.backend,
        "font_info",
        lambda fid: replace(info, masters=(*info.masters, MasterInfo(bold, "Bold"))),
    )
    second = NS(
        id=99000, isValid=True, shapes=[], advanceWidth=600, anchors=[], guidelines=[]
    )
    monkeypatch.setattr(
        native.backend,
        "layer",
        lambda gid, mid: native.backend._read_layer(
            native.fid, second if mid == bold else native.layer, mid, gid
        ),
    )
    if kind == "component":
        item = type(native.layer.shapes[0])()
        item.isComponent = item.isComposite = True
        item.shapeData = NS(componentGlyph="A")
        item.transform.isAffine = lambda: True
        for name, value in zip(
            ("m11", "m12", "m21", "m22", "dx", "dy"), (1, 0, 0, 1, 0, 0)
        ):
            setattr(item.transform, name, lambda value=value: value)
        native.layer.shapes.append(item)
    glyph = native.font.glyphs[0]
    source, destination = glyph.layers[0], glyph.layers[1]
    retained = source.paths[0] if kind == "path" else source.components[0]
    assert retained.closed is False if kind == "path" else retained.componentName == "A"
    order = (
        (destination.id, source.id)
        if destination_first
        else (source.id, destination.id)
    )

    class OrderedVisits(set):
        def __iter__(self):
            return iter(order)

    native.backend._glyph_layer_tokens[native.gid] = OrderedVisits(order)
    if kind == "path":
        item = type(native.layer.shapes[0])()
        item.contours = [native.layer.shapes[0].contours.pop(0)]
    else:
        native.layer.shapes.remove(item)
    second.shapes.append(item)
    marker[0] = 5
    if kind == "path":
        assert retained.nodes[0].position == (10, 2)
        assert destination.paths[0] is retained
    else:
        assert retained.componentName == "A"
        assert destination.components[0] is retained
    assert retained.parent is destination


@pytest.mark.parametrize("visit_before_move", [False, True])
def test_retained_component_can_follow_a_move_to_another_visited_glyph(
    native, monkeypatch, visit_before_move
):
    from fontlab_glyport.model.backend import GlyphInfo

    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    other = NS(id=80100, name="B", isValid=True, currentHistoryState=lambda: marker[0])
    gid = native.backend._register((native.fid, "glyph", other.id), other, native.fid)
    second = NS(
        id=80200, isValid=True, shapes=[], advanceWidth=500, anchors=[], guidelines=[]
    )
    infos = (GlyphInfo(native.gid, "A", ("0041",)), GlyphInfo(gid, "B", ("0042",)))
    monkeypatch.setattr(native.backend, "glyphs", lambda fid: infos)
    monkeypatch.setattr(
        native.backend,
        "glyph_info",
        lambda token: next(info for info in infos if info.id == token),
    )
    monkeypatch.setattr(
        native.backend,
        "layer",
        lambda token, mid: native.backend._read_layer(
            native.fid, native.layer if token == native.gid else second, mid, token
        ),
    )
    component = type(native.layer.shapes[0])()
    component.isComponent = component.isComposite = True
    component.shapeData = NS(componentGlyph="A")
    component.transform.isAffine = lambda: True
    for name, value in zip(
        ("m11", "m12", "m21", "m22", "dx", "dy"), (1, 0, 0, 1, 0, 0)
    ):
        setattr(component.transform, name, lambda value=value: value)
    native.layer.shapes.append(component)
    source, destination = (
        native.font.glyphs[0].layers[0],
        native.font.glyphs[1].layers[0],
    )
    retained = source.components[0]
    assert retained.parent is source
    if visit_before_move:
        assert len(destination.components) == 0
    native.layer.shapes.remove(component)
    second.shapes.append(component)
    marker[0] = 5
    if not visit_before_move:
        assert retained.componentName == "A"
        assert destination.components[0] is retained
    assert retained.componentName == "A"
    assert retained.parent is destination
    assert destination.components[0] is retained


def test_failed_native_update_does_not_enter_hint_tool(native, monkeypatch):
    events = []
    native.layer.changed = lambda: events.append("layer changed")

    def fail():
        raise RuntimeError("native update failed")

    native.layer.update = fail
    native.glyph.changed = lambda: events.append("glyph changed")
    native.glyph.update = lambda: events.append("glyph updated")
    monkeypatch.setattr(
        native.backend,
        "_resolve_tool",
        lambda *args: lambda **kw: events.append("hint tool"),
    )
    with pytest.raises(RuntimeError, match="native update failed"):
        native.backend.add_hint(native.lid, HintInfo(True, 30, 20))
    assert events == ["layer changed"]


def test_catalog_retry_is_bounded_if_fresh_records_are_still_stale():
    from fontlab_glyport.errors import StaleNativeObject
    from fontlab_glyport.model.backend import GlyphInfo
    from fontlab_glyport.model.indexes import IndexedSequence

    listings = []

    def records():
        listings.append(1)
        return (GlyphInfo("id", "A", ("0041",)),)

    def stale(token):
        raise StaleNativeObject(token)

    sequence = IndexedSequence(
        lambda: 0, records, lambda token: token, lambda info: (info.name,)
    )
    sequence._validator = (lambda token: 4, stale)
    with pytest.raises(StaleNativeObject):
        sequence["A"]
    assert len(listings) == 2
