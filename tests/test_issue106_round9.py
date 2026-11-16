# this_file: tests/test_issue106_round9.py
"""Regressions for the five independent round-nine review findings."""

from copy import deepcopy
from dataclasses import replace
from itertools import count
from types import SimpleNamespace as NS

import pytest
from test_fontlab_backend_lazy import NodeFlags
from test_issue106_round7_native import native as native_double

from fontlab_glyport.errors import NativeOperationError
from fontlab_glyport.model import GSAnchor, GSGuide, GSNode, GSPath, Model
from fontlab_glyport.model.backend import GlyphInfo
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend

_SERIAL = count(10000)


@pytest.fixture
def native(monkeypatch):
    state = native_double.__wrapped__(monkeypatch)
    state.glyph.lib = {}  # Real flGlyphs expose lib for retained metadata.
    serial = _SERIAL

    class Node(NodeFlags):
        def __init__(self, x):
            self.id, self.isValid = next(serial), True
            self.x, self.y = x, 2
            self.smooth, self.selected = False, True

        @property
        def position(self):
            return NS(x=lambda: self.x, y=lambda: self.y)

        def isOff(self):
            return False

        isCurve = isOff

    class Contour:
        def __init__(self, x):
            self.id, self.isValid = next(serial), True
            self.closed, self.isTT = False, False
            self._nodes = [Node(x)]

        def nodes(self):
            return list(self._nodes)

    class Shape:
        def __init__(self):
            self.id, self.isValid = next(serial), True
            self.isComponent = self.isComposite = False
            self.active, self.shapeData = True, NS(name="")
            self.contours = [Contour(10), Contour(20)]
            self.transform = NS(map=lambda p: p, isInvertible=lambda: True)
            self.transform.inverted = lambda: self.transform

        def clone(self):
            clone = deepcopy(self)
            clone.id = next(serial)
            for contour in clone.contours:
                contour.id = next(serial)
                for node in contour.nodes():
                    node.id = next(serial)
            return clone

        def removeContour(self, contour):
            self.contours.remove(contour)

    state.package.checkInitHistoryState = lambda index: None

    class CopyLayer(type(state.layer)):
        def clone(self):
            clone = deepcopy(self)
            clone.id = next(serial)
            clone.shapes = [shape.clone() for shape in self.shapes]
            return clone

    state.layer.__class__ = CopyLayer
    state.layer.isMasterLayer = True
    state.layer.isMaskLayer = state.layer.isService = False
    state.layer.lib = {}
    state.layer.shapes = [Shape()]
    state.layer.insertShape = lambda i, shape: state.layer.shapes.insert(i, shape)
    state.layer.removeAllShapes = lambda: state.layer.shapes.clear()
    state.layer.addShapes = lambda shapes: state.layer.shapes.extend(shapes)
    state.layer.clearAnchors = lambda: state.layer.anchors.clear()
    state.layer.addAnchor = lambda anchor: state.layer.anchors.append(anchor)
    state.glyph.name = "A"
    state.glyph.fgGlyph = NS(id=200, unicodes=[0x41])
    state.glyph.fgGlyphId = 200
    state.glyph.fgGlyph.name = "A"
    from test_issue106_round7_native import NativeFont

    state.package.fgPackage = NativeFont(A=state.glyph.fgGlyph)
    state.package.findName = lambda name: (
        state.glyph if name == state.glyph.name else None
    )
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._qpoint",
        lambda x, y: NS(x=lambda: x, y=lambda: y),
    )
    configure_model(state.backend, state, monkeypatch)
    state.font = Model(state.backend)._font(state.fid)
    # Bulk writes stage native inputs before invoking append methods.
    from test_issue106_round23 import install_path_constructors

    install_path_constructors(state)
    return state


def configure_model(backend, state, monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(backend, "hints", lambda lid: ())
    monkeypatch.setattr(
        backend,
        "master_metrics",
        lambda mid: fake.master_metrics(fake.font_info("font").masters[0].id),
    )
    template = fake.font_info("font")
    monkeypatch.setattr(
        backend,
        "font_info",
        lambda fid: replace(
            template,
            id=state.fid,
            masters=(replace(template.masters[0], id=state.mid),),
        ),
    )
    monkeypatch.setattr(
        backend,
        "glyphs",
        lambda fid: (GlyphInfo(state.gid, state.glyph.name, ("0041",)),),
    )
    monkeypatch.setattr(
        backend,
        "layer",
        lambda glyph, master: backend._read_layer(
            state.fid, state.layer, state.mid, state.gid
        ),
    )


@pytest.mark.parametrize("peer", [False, True])
def test_rollback_multicontour_removal_restores_bindings_then_retained_position_is_writable(
    native, monkeypatch, peer
):
    b, font = native.backend, native.font
    layer = font.glyphs[0].layers[0]
    retained = layer.paths[1].nodes[0]
    if peer:
        other = FontLabBackend(packages=[native.package])
        monkeypatch.setattr(other, "_native", lambda: native.module)
        other._register((777, "font", 777), NS(id=777, isValid=True))
        fid = other._font_id(native.package)
        mid = other._register((fid, "master", "Regular"), native.package, fid)
        other._master_names[mid] = "Regular"
        gid = other._register((fid, "glyph", 200), native.glyph, fid)
        state = NS(fid=fid, mid=mid, gid=gid, glyph=native.glyph, layer=native.layer)
        configure_model(other, state, monkeypatch)
        retained = Model(other)._font(fid).glyphs[0].layers[0].paths[1].nodes[0]
        owner = other
    else:
        owner = b
    old_key = owner._object_keys[retained.id]
    original_shape = native.layer.shapes[0]
    old_node = owner._objects[retained.id]
    old_shape_ref = owner._node_shapes[retained.id]

    def fail(*args):
        raise RuntimeError("append failed after removals")

    monkeypatch.setattr(b, "append_path", fail)
    with font.undo_group("Outer edit"):
        b._owned_shapes.add(-1)  # unrelated ownership from an earlier outer edit
        with pytest.raises(RuntimeError, match="after removals"):
            layer.paths = [GSPath([GSNode((99, 99))])]
        assert native.layer.shapes == [original_shape]
        assert owner._object_keys[retained.id] == old_key
        assert owner._objects[retained.id] is old_node
        assert owner._keys[old_key] == retained.id
        assert owner._node_shapes[retained.id] == old_shape_ref
        assert all(
            token != retained.id or key == old_key for key, token in owner._keys.items()
        )
        assert b._owned_shapes == {-1}
        retained.position = (45, 67)
        assert retained.position == (45, 67)


@pytest.mark.parametrize("detached", [False, True])
def test_clear_preserves_guides_and_removes_shapes_anchors_selection(detached):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    layer.guides.append(GSGuide((2, 3), 90, "keep"))
    layer.anchors.append(GSAnchor("top", (10, 20)))
    layer.paths[0].nodes[0].selected = True
    if detached:
        layer = layer.copy()
    guide = layer.guides[0]
    layer.clear()
    assert list(layer.guides) == [guide], "clear preserves guide identity and geometry"
    assert not layer.shapes and not layer.anchors and not layer.selection
    assert guide.position == (2, 3)


def test_script_selection_invalidates_snapshot_without_undo_publication(native):
    b = native.backend
    path = native.font.glyphs[0].layers[0].paths[0]
    node = path.nodes[0]
    assert node._data().selected
    revision = b.revision(native.fid)
    node.selected = False
    assert b.revision(native.fid) != revision
    assert not node._data().selected
    assert not node.copy().selected and not path.copy().nodes[0].selected
    assert not native.calls, "selection never publishes Undo notifications"


@pytest.mark.parametrize("kind", ["node", "path", "layer"])
def test_editor_selection_is_live_in_copies_and_refreshes_snapshots(native, kind):
    layer = native.font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    assert node._data().selected
    original = native.backend._objects[node.id]
    original.selected = False  # editor mutation: no Python setter or history change
    source = {"node": node, "path": layer.paths[0], "layer": layer}[kind]
    copy = source.copy()
    copied_node = (
        copy
        if kind == "node"
        else copy.nodes[0]
        if kind == "path"
        else copy.paths[0].nodes[0]
    )
    assert not copied_node.selected
    assert not node._data().selected, "live selection read invalidates stale records"
    assert not native.calls


@pytest.mark.parametrize("fake", [False, True])
def test_rename_to_current_name_is_noop_with_no_revision_or_native_calls(native, fake):
    if fake:
        backend = FakeBackend()
        font = Model(backend).font
        glyph = font.glyphs[0]
        revision = backend.revision(font.id)
        glyph.name = glyph.name
        assert backend.revision(font.id) == revision
    else:
        b = native.backend
        revision = b.revision(native.fid)
        native.package.renameGlyph = lambda *args, **kw: pytest.fail("unchanged rename")
        # A fresh wrapper of the same native glyph is not a name collision.
        native.package.findName = lambda name: NS(id=native.glyph.id, name="A")
        native.font.glyphs[0].name = "A"
        assert b.revision(native.fid) == revision and not native.calls


def test_refused_native_delete_keeps_token_valid_and_reports_failure(native):
    b = native.backend
    glyph = native.font.glyphs[0]
    native.package.deleteGlyph = lambda glyph: False
    revision = b.revision(native.fid)
    with pytest.raises(NativeOperationError) as error:
        native.font.glyphs.remove(glyph)
    assert error.value.capability == "GSFont.glyphs.remove"
    assert "A" in str(error.value)
    assert b.is_valid(glyph.id) and native.font.glyphs["A"] is glyph
    assert b.revision(native.fid) == revision


def test_failed_delete_restores_preparation_state_for_next_edit(native):
    b = native.backend
    native.package.deleteGlyph = lambda glyph: False
    before = dict(b._prepared)
    with pytest.raises(NativeOperationError):
        b.remove_glyph(native.fid, native.gid)
    assert b._prepared == before, "failed delete must not skip later glyph preparation"


def test_clone_updates_peer_tokens_and_revision_when_document_tokens_differ(
    native, monkeypatch
):
    other = FontLabBackend(packages=[native.package])
    monkeypatch.setattr(other, "_native", lambda: native.module)
    other._register((777, "font", 777), NS(id=777, isValid=True))
    fid = other._font_id(native.package)
    mid = other._register((fid, "master", "Regular"), native.package, fid)
    other._master_names[mid] = "Regular"
    gid = other._register((fid, "glyph", 200), native.glyph, fid)
    state = NS(fid=fid, mid=mid, gid=gid, glyph=native.glyph, layer=native.layer)
    configure_model(other, state, monkeypatch)
    node = Model(other)._font(fid).glyphs[0].layers[0].paths[0].nodes[0]
    assert node.position == (10, 2)
    revision = other.revision(fid)
    with native.font.undo_group("Edit before publication"):
        original = native.font.glyphs[0].layers[0].paths[0].nodes[0]
        original.position = (80, 90)
        assert other.revision(fid) != revision
        assert node.position == (80, 90)


def test_rollback_removes_new_token_metadata_and_keeps_previously_dead_tokens_dead(
    native,
):
    b = native.backend
    layer = native.font.glyphs[0].layers[0]
    dead = layer.paths[0].nodes[0]
    b.remove_path(layer.id, layer.paths[0].id)
    assert not b.is_valid(dead._id)
    survivor = layer.paths[0].nodes[0]
    state = b.snapshot_collection(layer.id)
    token = b._register(
        (native.fid, "node", -50),
        NS(id=-50, isValid=True),
        b._parents[survivor.id],
    )
    b._node_shapes[token] = (native.layer.shapes[0], layer.id)
    b._selection_flags[token] = True
    b.restore_collection(layer.id, state)
    assert not b.is_valid(dead._id), (
        "rollback cannot resurrect tokens already dead at snapshot time"
    )
    assert not b.is_valid(token)
    assert token not in b._object_keys and token not in b._parents
    assert token not in b._node_shapes and token not in b._selection_flags
    assert all(value != token for value in b._keys.values())
    survivor.position = (55, 66)
    assert survivor.position == (55, 66)


@pytest.mark.parametrize("fake", [False, True])
def test_rename_still_rejects_another_glyph_name_and_empty_name(native, fake):
    if fake:
        b = FakeBackend()
        b.glyph_lists["font"] += (GlyphInfo("other", "B", ()),)
        font_id, glyph_id = "font", "glyph"
    else:
        b, font_id, glyph_id = native.backend, native.fid, native.gid
        native.package.findName = lambda name: (
            NS(id=999, name="B")
            if name == "B"
            else native.glyph
            if name == "A"
            else None
        )
    revision = b.revision(font_id)
    for name in ("", "B"):
        with pytest.raises(ValueError, match="Duplicate or empty"):
            b.rename_glyph(font_id, glyph_id, name)
    assert b.revision(font_id) == revision and not native.calls


def test_successful_delete_invalidates_the_original_token_and_publishes(native):
    native.package.deleteGlyph = lambda glyph: True
    b = native.backend
    b.remove_glyph(native.fid, native.gid)
    assert not b.is_valid(native.gid)
    assert native.calls[-1][1] == [native.package]
