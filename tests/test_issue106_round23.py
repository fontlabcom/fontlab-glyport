# this_file: tests/test_issue106_round23.py
"""Native rename recovery and pre-mutation refusal boundaries."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.backend import GlyphInfo
from fontlab_glyport.model.indexes import IndexedSequence


@pytest.mark.parametrize("names", [("B", "A"), ("B", "C", "A"), ("0042", "B")])
def test_native_rename_keeps_current_name_precedence(names):
    rows = [
        GlyphInfo(str(i), chr(65 + i), (f"{65 + i:04X}",)) for i in range(len(names))
    ]
    seq = IndexedSequence(
        lambda: 0,
        lambda: rows,
        lambda token: token,
        keys=lambda r: (r.name, *r.unicodes, *(chr(int(u, 16)) for u in r.unicodes)),
    )
    markers = dict.fromkeys((r.id for r in rows), 0)
    seq._validator = (markers.get, lambda token: rows[int(token)])
    for row in rows:
        seq.token_for_key(row.name)
    rows[:] = [replace(row, name=name) for row, name in zip(rows, names)]
    markers.update(dict.fromkeys(markers, 1))
    assert seq.token_for_key(names[0]) == "0"


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_refused_hint_edit_has_no_native_or_history_side_effects(native, monkeypatch):
    events = []
    backend = native.backend
    layer = native.font.glyphs[0].layers[0]
    monkeypatch.setattr(
        backend,
        "_tool_font",
        lambda *a: (_ for _ in ()).throw(UnsupportedCapability("owned font")),
    )
    for method in (
        "_writable_layer",
        "_prepare_layer",
        "_commit_layer_edits",
        "_touch_layer",
        "_tool",
    ):
        monkeypatch.setattr(
            backend, method, lambda *a, method=method, **kw: events.append(method)
        )
    with pytest.raises(UnsupportedCapability):
        backend._edit_hints(layer.id, {"op": "add"}, "GSLayer.hints")
    assert events == []


def install_path_constructors(native):
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

    node.NodeKind = node_type.NodeKind
    native.module.flNode = node
    native.module.flContour = contour
    native.module.flShape = shape
    native.layer.addShape = lambda value: native.layer.shapes.append(value) or value


def test_replacing_paths_preserves_multi_contour_group(native):
    install_path_constructors(native)
    layer = native.font.glyphs[0].layers[0]
    original = native.layer.shapes[0]
    layer.paths = [path.copy() for path in layer.paths]
    assert len(native.layer.shapes) == 1
    assert len(native.layer.shapes[0].contours) == 2
    assert [c.nodes()[0].x for c in original.contours] == [10, 20]


@pytest.mark.parametrize("replace_nodes", [False, True, "bulk"])
def test_removed_outline_nodes_drop_only_linked_hints(
    native, monkeypatch, replace_nodes
):
    layer = native.font.glyphs[0].layers[0]
    path = layer.paths[0]
    node = native.layer.shapes[0].contours[0].nodes()[0]
    linked = NS(id=900, isHint=True, center=node, vector=None)
    independent = NS(id=901, isHint=True, center=NS(id=902), vector=None)
    guide = NS(
        id=903,
        isHint=False,
        centerPoint=NS(x=lambda: 0, y=lambda: 0),
        angle=0,
        name="guide",
    )
    native.layer.guidelines = [linked, independent, guide]
    monkeypatch.setattr(native.backend, "_guide_line", lambda value: value)
    if replace_nodes == "bulk":
        layer.paths = []
    elif replace_nodes:
        install_path_constructors(native)
        type(native.layer.shapes[0].contours[0]).assign = lambda self, items: setattr(
            self, "_nodes", items
        )
        native.backend.set_path_nodes(path.id, path._data().nodes, path.closed)
    else:
        layer.paths.remove(path)
    assert [g.id for g in native.layer.guidelines] == [901, 903]


@pytest.mark.parametrize("operation", ["guide", "anchor", "transform"])
def test_constructor_refusal_precedes_pending_layer_creation(
    native, monkeypatch, operation
):
    from fontlab_glyport.model.backend import AnchorInfo, GuideInfo

    events = []
    backend = native.backend
    layer = native.font.glyphs[0].layers[0]

    def refuse(*args, **kw):
        raise UnsupportedCapability("constructor")

    def writable(*args):
        events.append("created pending layer")
        return native.layer

    monkeypatch.setattr(backend, "_writable_layer", writable)
    monkeypatch.setattr(backend, "_new_guide", refuse)
    native.module.flPinPoint = refuse
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=refuse),
    )
    with pytest.raises(UnsupportedCapability):
        if operation == "guide":
            backend.append_guide(layer.id, GuideInfo("", 0, 0, 0, "guide"))
        elif operation == "anchor":
            backend.add_anchor(layer.id, AnchorInfo("", "top", 0, 0))
        else:
            backend.transform_layer(layer.id, (1, 0, 0, 1, 0, 0))
    assert events == []


def test_owned_pending_layer_hint_refusal_keeps_layer_and_history_untouched(native):
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.fontlab_backend import _PendingLayer

    backend = native.backend
    layer = native.font.glyphs[0].layers[0]
    pending = _PendingLayer("Regular")
    backend._objects[layer.id] = pending
    backend._owned_fonts[native.package.id] = NS()
    events = []
    native.glyph.findLayerCreate = lambda name: events.append(("create", name))
    native.glyph.changed = lambda: events.append("glyph.changed")
    native.glyph.update = lambda: events.append("glyph.update")
    before = list(native.calls)
    with pytest.raises(UnsupportedCapability, match="workspace-registered"):
        backend.add_hint(layer.id, HintInfo(True, 10, 20))
    assert backend._objects[layer.id] is pending
    assert native.calls == before
    assert events == []


@pytest.mark.parametrize("names", [("B", "A"), ("B", "C", "A"), ("0042", "B")])
def test_native_catalog_in_place_renames(native, monkeypatch, names):
    from fontlab_glyport.model.fontlab_backend import FontLabBackend

    rows, objects, markers = [], {}, {}

    class Catalog:
        @property
        def glyphs(self):
            return rows

        def __getitem__(self, name):
            return next(row for row in rows if row.name == name)

    for index in range(len(names)):
        identity = 2000 + index
        name = chr(65 + index)
        rows.append(NS(id=identity, name=name, unicodes=[65 + index]))
        markers[identity] = 0
        objects[identity] = NS(
            id=identity,
            name=name,
            isValid=True,
            currentHistoryState=lambda identity=identity: markers[identity],
        )
    native.package.fgPackage = Catalog()
    native.package.findFgId = objects.get
    native.package.findName = lambda name: next(
        (obj for obj in objects.values() if obj.name == name), None
    )
    native.package.glyphsCount = len(rows)
    monkeypatch.setattr(
        native.backend, "glyphs", FontLabBackend.glyphs.__get__(native.backend)
    )
    font = native.font
    for row in rows:
        assert font.glyphs[row.name].name == row.name
    for row, name in zip(rows, names):
        row.name = objects[row.id].name = name
        markers[row.id] += 1
    assert font.glyphs[names[0]].unicode == "0041"
    for index, name in enumerate(names):
        assert font.glyphs[name].name == name
        assert font.glyphs[name].unicode == f"{65 + index:04X}"
