# this_file: tests/test_fontlab_backend_lazy.py
"""Counting native doubles prove read boundaries without opening FontLab."""

import sys
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
from typing import ClassVar

import pytest
from history_scene import install_font_window

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model.backend import AnchorInfo
from fontlab_glyport.model.fontlab_backend import FontLabBackend, owned_test_package


class NodeFlags:
    """Public flNode flags used by native-shaped model doubles."""

    NodeKind: ClassVar[dict[str, int]] = {
        "Smooth": 0x8,
        "First": 0x10,
        "Selected": 0x20,
        "G2": 0x1000,
        "Hobby": 0x2000,
        "SmoothMask": 0x3008,
    }
    nodeState = 1

    @property
    def smooth(self):
        return not (self.isOff() or self.isCurve()) and bool(self.nodeState & 0x8)

    @smooth.setter
    def smooth(self, value):
        if not self.nodeState & 1:
            return
        self.nodeState = (self.nodeState & ~0x8) | (0x8 if value else 0)

    @property
    def selected(self):
        return bool(self.nodeState & 0x20)

    @selected.setter
    def selected(self, value):
        self.nodeState = (self.nodeState & ~0x20) | (0x20 if value else 0)


class CountingGlyph:
    def __init__(self, id, name, calls):
        self.id, self._name, self.calls = id, name, calls
        self.isValid = True
        self._layers = {}

    def changed(self):
        self.calls["glyph.changed"] += 1

    def update(self):
        self.calls["glyph.update"] += 1

    @property
    def name(self):
        self.calls["glyph.name"] += 1
        return self._name

    @property
    def unicodes(self):
        self.calls["glyph.unicodes"] += 1
        return [0x41 + self.id]

    @property
    def layers(self):
        raise AssertionError("Must find one layer directly, never enumerate layers")

    def findLayer(self, name):
        self.calls["findLayer"] += 1
        if name not in self._layers:
            self._layers[name] = CountingLayer((self.id, name), self.calls)
        return self._layers[name]


class CountingLayer:
    def __init__(self, id, calls):
        self.id, self.calls = id, calls
        self.isValid = True
        self.advanceWidth = 500
        self._shapes, self._anchors = [], []
        self.guidelines = []

    def changed(self):
        self.calls["layer.changed"] += 1

    def update(self):
        self.calls["layer.update"] += 1

    @property
    def shapes(self):
        self.calls["layer.shapes"] += 1
        return self._shapes

    @property
    def anchors(self):
        self.calls["layer.anchors"] += 1
        return self._anchors

    def addShape(self, shape):
        self._shapes.append(shape)
        return shape

    def removeShape(self, shape):
        self._shapes.remove(shape)

    def insertShape(self, index, shape):
        self._shapes.insert(index, shape)
        return shape

    def addAnchor(self, anchor):
        self._anchors.append(anchor)


class CountingPackage:
    def __init__(self, id, calls, glyph_count=3, master_count=2):
        self.id, self.calls = id, calls
        self.isValid = True
        self.masters = [f"Master {i}" for i in range(master_count)]
        self.upm = 1000
        self.axes, self.instances, self.fgId = [], [], 1000 + id
        self.info = SimpleNamespace(familyName=f"Owned {id}")
        self._glyphs = [
            CountingGlyph(i, f"glyph{i}", calls) for i in range(glyph_count)
        ]
        self.fgPackage = self

    @property
    def glyphs(self):
        self.calls["font.glyphs"] += 1
        return self._glyphs

    def __getitem__(self, name):
        return next(glyph for glyph in self._glyphs if glyph.name == name)

    def findFgId(self, id):
        self.calls["findFgId"] += 1
        return self._glyphs[id]


@pytest.fixture
def native(monkeypatch):
    class QPointF:
        def __init__(self, x, y):
            self._x, self._y = x, y

        def x(self):
            return self._x

        def y(self):
            return self._y

    qtcore = SimpleNamespace(QPointF=QPointF)
    monkeypatch.setitem(sys.modules, "PythonQt", SimpleNamespace(QtCore=qtcore))
    monkeypatch.setitem(sys.modules, "PythonQt.QtCore", qtcore)
    calls = Counter()
    package = CountingPackage(1, calls, glyph_count=1945, master_count=22)
    unrelated = CountingPackage(2, calls)

    packages = {p.fgId: p for p in (package, unrelated)}

    def workspace():
        calls["workspace"] += 1
        return SimpleNamespace(
            packages=lambda: [package, unrelated],
            # Native fact (probe_app_state.json): currentPackage lags behind the
            # active font; the backend must not use it.
            currentPackage=package,
            findPackageId=packages.get,
        )

    module = SimpleNamespace(
        flWorkspace=SimpleNamespace(instance=workspace),
        flPackage=lambda p: p,
        flItems=lambda: SimpleNamespace(
            notifyChangesApplied=lambda *args: calls.update(["notify"])
        ),
    )
    install_font_window(monkeypatch, module, package)
    monkeypatch.setattr(FontLabBackend, "_native", staticmethod(lambda: module))
    active = ActiveFont(unrelated.fgId)
    monkeypatch.setattr(FontLabBackend, "_fontpr", staticmethod(lambda: active))
    return module, calls, package, unrelated


class ActiveFont:
    """fontpr double for get_active_font: FontLab's active font id, or Error."""

    class Error(Exception):
        pass

    def __init__(self, font_id):
        self.font_id = font_id

    def get_active_font(self):
        if self.font_id is None:
            raise self.Error("No active font")
        return {"id": self.font_id, "family_name": "x"}


def test_package_queries_do_not_read_glyphs_or_layers(native):
    _, calls, package, _ = native
    backend = FontLabBackend()
    ids = backend.list_fonts()
    assert len(ids) == 2
    assert backend.font_info(ids[0]).familyName == "Owned 1"
    assert len(backend.font_info(ids[0]).masters) == 22
    assert backend.current_font_id() == ids[1]
    before = calls.copy()
    assert backend.is_valid(ids[0])
    assert calls == before, (
        "Stale checks must use cached handles, not workspace traversal"
    )
    assert calls["font.glyphs"] == calls["glyph.name"] == calls["findLayer"] == 0
    package.isValid = False
    assert not backend.is_valid(ids[0])
    with pytest.raises(StaleNativeObject):
        backend.font_info(ids[0])


def test_glyph_metadata_then_only_requested_layer(native):
    _, calls, _, _ = native
    backend = FontLabBackend()
    fid = backend.list_fonts()[0]
    master = backend.font_info(fid).masters[7]
    glyphs = backend.glyphs(fid)
    assert len(glyphs) == 1945
    assert calls["font.glyphs"] == 1
    assert calls["glyph.name"] == calls["glyph.unicodes"] == 1945
    assert calls["findFgId"] == calls["findLayer"] == calls["layer.shapes"] == 0
    calls.clear()
    layer = backend.layer(glyphs[12].id, master.id)
    assert layer.width == 500
    assert calls == Counter(
        {"findFgId": 1, "findLayer": 1, "layer.shapes": 1, "layer.anchors": 1}
    )
    calls.clear()
    assert backend.is_valid(layer.id)
    assert not calls
    backend.set_layer_width(layer.id, 777)
    assert backend.layer(glyphs[12].id, master.id).width == 777
    assert calls["font.glyphs"] == 0


def test_explicit_scope_never_consults_workspace(native):
    module, calls, package, unrelated = native
    module.flWorkspace = None  # Any attempted workspace access must fail.
    backend = FontLabBackend(packages=iter([package]))
    (fid,) = backend.list_fonts()
    assert backend.current_font_id() == fid
    assert backend.font_info(fid).familyName == "Owned 1"
    assert len(backend.glyphs(fid)) == 1945
    assert calls["workspace"] == 0
    unrelated.isValid = False
    assert backend.is_valid(fid)
    package.isValid = False
    assert backend.list_fonts() == ()
    assert backend.current_font_id() is None
    assert not backend.is_valid(fid)


def test_empty_explicit_scope_does_not_fall_back_to_workspace(native):
    module, calls, _, _ = native
    module.flWorkspace = None
    backend = FontLabBackend(packages=[])
    assert backend.list_fonts() == () and backend.current_font_id() is None
    assert not backend.is_valid("unknown")
    assert not calls


def test_layer_rejects_cross_document_master_and_checks_invalid_handles(native):
    _, _, package, _ = native
    backend = FontLabBackend()
    first, second = backend.list_fonts()
    glyph = backend.glyphs(first)[0]
    master = backend.font_info(first).masters[0]
    foreign_master = backend.font_info(second).masters[0]
    with pytest.raises(UnsupportedCapability):
        backend.layer(glyph.id, foreign_master.id)
    layer = backend.layer(glyph.id, master.id)
    package._glyphs[0].isValid = False
    assert not backend.is_valid(glyph.id)
    assert not backend.is_valid(layer.id)
    with pytest.raises(StaleNativeObject):
        backend.set_layer_width(layer.id, 200)


def test_helper_builds_only_owned_fontgate_data(monkeypatch):
    import sys

    fonts = []

    class Glyph:
        def __init__(self, name):
            self.name, self.unicodes, self.layers = name, [], []

        def addUnicode(self, codepoint):
            self.unicodes.append(codepoint)

    class Font:
        def __init__(self):
            self.glyphs = []
            fonts.append(self)

        def addGlyph(self, glyph):
            self.glyphs.append(glyph)

    monkeypatch.setitem(
        sys.modules,
        "fontgate",
        SimpleNamespace(
            fgFont=Font, fgGlyph=Glyph, fgLayer=lambda name: ("layer", name)
        ),
    )
    monkeypatch.setattr(
        FontLabBackend,
        "_native",
        staticmethod(
            lambda: SimpleNamespace(flPackage=lambda f: SimpleNamespace(source=f))
        ),
    )
    result = owned_test_package(["A", "B", "A.alt"])
    assert result.package.source is fonts[0] and result.fg_font is fonts[0]
    assert [g.name for g in result.fg_font.glyphs] == ["A", "B", "A.alt"]
    assert [g.unicodes for g in result.fg_font.glyphs] == [[0x41], [0x42], [0xF0002]]
    # Native fact: new fgGlyphs have no layers; the helper adds the master's.
    assert all(g.layers == [("layer", "Regular")] for g in result.fg_font.glyphs)


def test_snapshots_refresh_only_requested_metadata(native):
    _, calls, package, _ = native
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    original = backend.font_info(fid)
    package.info.familyName = "Renamed"
    assert backend.font_info(fid).familyName == "Renamed"
    assert original.familyName == "Owned 1"
    first = backend.glyphs(fid)
    package._glyphs[0]._name = "RenamedGlyph"
    second = backend.glyphs(fid)
    assert second[0].id == first[0].id and second[0].name == "RenamedGlyph"
    assert first[0].name == "glyph0"
    assert calls["findFgId"] == calls["findLayer"] == 0
    package._glyphs.pop()
    backend.glyphs(fid)
    assert not backend.is_valid(first[-1].id)
    package.masters.pop()
    assert not backend.is_valid(original.masters[-1].id)


def test_native_mutations_never_enumerate_other_layers_or_glyphs(native):
    from itertools import count

    from fontlab_glyport.model.backend import AnchorInfo, NodeInfo, PathInfo

    module, calls, package, _ = native
    serial = count(10000)

    class Node(NodeFlags):
        def __init__(self, point, *, nodeType="on"):
            type = nodeType
            # Native fact: flNode(QPointF position[, nodeType]) rejects bare floats.
            assert hasattr(point, "x") and callable(point.x), "flNode needs a QPointF"
            self.id, self.isValid = next(serial), True
            self.nodeState = {"on": 1, "off": 2, "curve": 4}[nodeType]
            self.x, self.y, self.type, self.smooth = point.x(), point.y(), type, False
            self.selected = False

        @property
        def position(self):
            return SimpleNamespace(x=lambda: self.x, y=lambda: self.y)

        def isOff(self):
            return self.type == "off"

        def isCurve(self):
            return False

    class Contour:
        def __init__(self, nodes, *, closed=False):  # native: closed is keyword-only
            self.id, self.isValid = next(serial), True
            self._nodes, self.closed, self.isTT = nodes, closed, False

        def nodes(self):
            return self._nodes

    class Shape:
        def __init__(self):
            self.id, self.isValid = next(serial), True
            self.contours, self.isComposite, self.isComponent = [], False, False
            self.transform = SimpleNamespace(map=lambda p: p)
            # Native fact: PythonQt's QTransform.inverted() returns the transform only;
            # invertibility comes from isInvertible().
            self.transform.inverted = lambda: self.transform
            self.transform.isInvertible = lambda: True

        def addContour(self, *args):
            # Native fact (FontLab 9.0.9780): the one-argument form raises
            # "IndexError: Unexpected SeqBase<T> length"; a second bool is required.
            if len(args) != 2:
                raise IndexError("Unexpected SeqBase<T> length.")
            self.contours.append(args[0])

        def removeContour(self, contour):
            self.contours.remove(contour)

        def clone(self):  # native flShape.clone(): new shape, contours and nodes
            copy = deepcopy(self)
            copy.id = next(serial)
            for contour in copy.contours:
                contour.id = next(serial)
                for node in contour.nodes():
                    node.id = next(serial)
            return copy

    module.flNode, module.flContour, module.flShape = Node, Contour, Shape
    module.flPinPoint = lambda p: SimpleNamespace(
        id=next(serial), isValid=True, point=p
    )
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    calls.clear()
    path_id = backend.append_path(layer.id, PathInfo("", (NodeInfo("", 1, 2),)))
    anchor_id = backend.add_anchor(layer.id, AnchorInfo("", "top", 20, 30))
    snapshot = backend.layer(glyph.id, master.id)
    assert snapshot.paths[0].id == path_id and snapshot.anchors[0].id == anchor_id
    node_id = snapshot.paths[0].nodes[0].id
    native_layer = package._glyphs[0].findLayer(master.name)
    (original,) = native_layer._shapes
    original_node = original.contours[0].nodes()[0]
    backend.set_node_position(node_id, 80, 90)
    assert backend.layer(glyph.id, master.id).paths[0].nodes[0].x == 80
    # Copy-on-write (probe_undo_cloned_shape.json): the shape FontLab's undo
    # history holds is left as it was; a clone at its index takes the edit and
    # the path/node tokens follow the clone.
    (clone,) = native_layer._shapes
    assert clone is not original and (original_node.x, original_node.y) == (1, 2)
    assert backend._object(node_id) is clone.contours[0].nodes()[0]
    backend.begin_undo("group")
    backend.set_node_position(node_id, 81, 91)
    (owned,) = native_layer._shapes
    backend.set_node_position(node_id, 82, 92)
    assert native_layer._shapes == [owned] and owned is not clone, (
        "one clone per shape and notification cycle"
    )
    backend.end_undo()
    assert backend.layer(glyph.id, master.id).paths[0].nodes[0].x == 82
    assert backend.layer(glyph.id, master.id).paths[0].id == path_id
    # Another session (script or plugin) holds its own tokens: they follow too.
    # (Its glyph listing is not the edit under test: counters are restored.)
    counted = calls.copy()
    other = FontLabBackend(packages=[package])
    (other_fid,) = other.list_fonts()
    other_master = other.font_info(other_fid).masters[0]
    other_layer = other.layer(other.glyphs(other_fid)[0].id, other_master.id)
    other_path = other_layer.paths[0]
    calls.clear()
    calls.update(counted)
    backend.set_node_position(node_id, 83, 93)
    assert other._object(other_path.id) is native_layer._shapes[0].contours[0]
    assert other._object(other_path.nodes[0].id).x == 83
    other.set_node_position(other_path.nodes[0].id, 84, 94)
    assert backend.layer(glyph.id, master.id).paths[0].nodes[0].x == 84
    backend.remove_path(layer.id, path_id)
    assert not backend.is_valid(path_id) and not backend.is_valid(node_id)
    assert backend.layer(glyph.id, master.id).paths == ()
    assert calls["font.glyphs"] == calls["glyph.name"] == calls["findFgId"] == 0
    assert calls["workspace"] == 0
    # insert_path (RR-merge P1 restore): before the shape at a shape-order
    # index, with node selection; -1 appends.
    last = backend.append_path(layer.id, PathInfo("", (NodeInfo("", 9, 9),)))
    first = backend.insert_path(
        layer.id, 0, PathInfo("", (NodeInfo("", 1, 1, selected=True),))
    )
    middle = backend.insert_path(layer.id, 1, PathInfo("", (NodeInfo("", 5, 5),)))
    paths = backend.layer(glyph.id, master.id).paths
    assert [p.id for p in paths] == [first, middle, last]
    assert [(p.nodes[0].x, p.nodes[0].selected) for p in paths] == [
        (1, True),
        (5, False),
        (9, False),
    ]


@pytest.mark.parametrize("names", [[""], [None], ["A", "A"]])
def test_helper_rejects_invalid_names_before_native_import(monkeypatch, names):
    def fail():
        raise AssertionError(
            "Invalid names must be rejected before any native operation"
        )

    monkeypatch.setattr(FontLabBackend, "_native", staticmethod(fail))
    with pytest.raises(ValueError):
        owned_test_package(names)


def test_owned_package_never_reads_fgpackage(native):
    from fontlab_glyport.model.fontlab_backend import OwnedPackage

    module, calls, workspace_package, _ = native
    source = CountingPackage(99, calls, glyph_count=1, master_count=1)
    editing_glyph = CountingGlyph(1234, "glyph0", calls)

    class UnregisteredPackage:
        id = 100
        isValid = True
        masters = ("Regular",)
        upm = 1000

        @property
        def fgPackage(self):
            calls["owned.fgPackage"] += 1
            raise AssertionError("Reading an unregistered fgPackage can crash FontLab")

        def findFgId(self, id):
            raise AssertionError("Owned glyphs must use their retained source names")

        def findName(self, name):
            calls["owned.findName"] += 1
            assert name == source._glyphs[0]._name
            return editing_glyph

    package = UnregisteredPackage()
    backend = FontLabBackend(
        packages=[OwnedPackage(package, source), workspace_package]
    )
    module.flWorkspace = None
    owned_id, workspace_id = backend.list_fonts()
    assert backend.current_font_id() == owned_id
    assert backend.font_info(workspace_id).familyName == "Owned 1"
    original = backend.font_info(owned_id)
    assert original.familyName == "Owned 99"
    source.info.familyName = "Retained source"
    assert backend.font_info(owned_id).familyName == "Retained source"
    (glyph,) = backend.glyphs(owned_id)
    assert glyph.name == "glyph0" and glyph.unicodes == ("0041",)
    assert calls["owned.findName"] == 0, "Glyph metadata must stay lazy"
    master = original.masters[0]
    layer = backend.layer(glyph.id, master.id)
    assert backend.is_valid(glyph.id) and backend.is_valid(layer.id)
    assert backend.layer(glyph.id, master.id).id == layer.id
    assert calls["owned.findName"] == 1, "Reuse the editing handle after resolution"
    backend.set_layer_width(layer.id, 650)
    assert backend.layer(glyph.id, master.id).width == 650
    source._glyphs[0]._name = "renamed"
    assert backend.glyphs(owned_id)[0].name == "renamed"
    package.isValid = False
    assert not backend.is_valid(layer.id)
    assert backend.list_fonts() == (workspace_id,)
    assert calls["owned.fgPackage"] == calls["workspace"] == 0


class LayerlessGlyph(CountingGlyph):
    """Native fact (R021): a FontLab-created font's .notdef has no layers at all;
    findLayer returns None until findLayerCreate makes the master layer."""

    def findLayer(self, name):
        self.calls["findLayer"] += 1
        return self._layers.get(name)

    def findLayerCreate(self, name):
        self.calls["findLayerCreate"] += 1
        layer = CountingLayer((self.id, name), self.calls)
        layer.advanceWidth = 250  # native default observed on a new_font font
        self._layers[name] = layer
        return layer


def test_missing_master_layer_reads_empty_and_first_write_creates_it(native):
    from fontlab_glyport.model import Model

    module, calls, _, _ = native
    package = CountingPackage(7, calls, glyph_count=1, master_count=1)
    package._glyphs = [LayerlessGlyph(0, ".notdef", calls)]
    module.flWorkspace = None
    model = Model(FontLabBackend(packages=[package]))
    font = model.fonts[0]
    layer = font.glyphs[".notdef"].layers[0]
    token = layer.id
    # Reads never create native layers (reads also run in owner sessions).
    assert (layer.width, len(layer.paths), len(layer.anchors)) == (0.0, 0, 0)
    assert layer.layerId == font.masters[0].id
    assert calls["findLayerCreate"] == 0 and calls["notify"] == 0
    with font.undo_group("create"):
        layer.width = 640
    assert calls["findLayerCreate"] == 1
    # Pre-change states of the glyph (before creation) and the new layer, then
    # the group's one change notification (probe_undo_first_edit.json).
    assert calls["notify"] == 3
    # The same proxy stays valid and keeps its id across materialisation.
    assert layer.id == token and font.glyphs[".notdef"].layers[0] is layer
    assert layer.width == 640
    layer.width = 650
    assert calls["findLayerCreate"] == 1


def test_missing_master_layer_created_by_path_or_anchor_write(native):
    from fontlab_glyport.model.backend import AnchorInfo

    module, calls, _, _ = native
    module.flPinPoint = lambda p: SimpleNamespace(id=4242, isValid=True, point=p)
    package = CountingPackage(8, calls, glyph_count=1, master_count=1)
    package._glyphs = [LayerlessGlyph(0, ".notdef", calls)]
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    pending = backend.layer(glyph.id, master.id)
    with pytest.raises(ValueError):
        backend.remove_path(pending.id, pending.id)
    assert calls["findLayerCreate"] == 0
    backend.add_anchor(pending.id, AnchorInfo("", "top", 1, 2))
    after = backend.layer(glyph.id, master.id)
    assert after.id == pending.id and after.width == 250
    assert [a.name for a in after.anchors] == ["top"]
    assert calls["findLayerCreate"] == 1


class QtMap:
    """Native libs come back as Qt-flavoured copies (TypeRig dialogs.py notes);
    in-place edits never reach the host, only assignment does."""

    def __init__(self, data):
        self._data = dict(data)

    def items(self):
        return self._data.items()

    def __setitem__(self, key, value):
        raise AssertionError("Native lib copies must not be edited in place")


def native_lib(lossy=()):
    """A lib property: reads return QtMap copies with lists as tuples (as
    PythonQt returns QSettings lists); assignment drops keys in ``lossy``."""

    def get(self):
        store = self.__dict__.get("_lib", {})
        return QtMap(
            {k: tuple(v) if isinstance(v, list) else v for k, v in store.items()}
        )

    def set(self, value):
        assert isinstance(value, dict), "assign a plain dict"
        self.__dict__["_lib"] = {k: v for k, v in value.items() if k not in lossy}

    return property(get, set)


class LibPackage(CountingPackage):
    packageLib = native_lib()


class LossyLibGlyph(CountingGlyph):
    lib = native_lib(lossy={"bad"})


class LibLayer(CountingLayer):
    lib = native_lib()


class LibLayerlessGlyph(LayerlessGlyph):
    def findLayerCreate(self, name):
        self.calls["findLayerCreate"] += 1
        self._layers[name] = LibLayer((self.id, name), self.calls)
        return self._layers[name]


def test_lib_when_font_glyph_layer_then_plain_copies_and_assignment(native, monkeypatch):
    module, calls, _, _ = native
    package = LibPackage(9, calls, glyph_count=1, master_count=1)
    module.flWorkspace = None
    install_font_window(monkeypatch, module, package)
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    assert backend.lib(fid) == {}
    backend.set_lib(fid, {"k": [1, {"x": 2}]})
    # Tuples from the native side become lists; maps become dicts.
    assert backend.lib(fid) == {"k": [1, {"x": 2}]}
    assert calls["notify"] == 2, "pre-change state, then the change"


def test_lib_when_native_drops_a_key_then_reverted_and_unsupported(native):
    module, calls, _, _ = native
    package = CountingPackage(10, calls, glyph_count=1, master_count=1)
    package._glyphs = [LossyLibGlyph(0, "A", calls)]
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    gid = backend.glyphs(fid)[0].id
    backend.set_lib(gid, {"ok": 1})
    with pytest.raises(UnsupportedCapability) as info:
        backend.set_lib(gid, {"ok": 1, "bad": 2})
    assert "bad" in str(info.value) and info.value.capability == "glyph.lib"
    assert backend.lib(gid) == {"ok": 1}, "a lossy write is reverted"


def test_lib_when_pending_layer_then_empty_and_write_creates_layer(native):
    module, calls, _, _ = native
    package = CountingPackage(11, calls, glyph_count=1, master_count=1)
    package._glyphs = [LibLayerlessGlyph(0, ".notdef", calls)]
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    layer = backend.layer(glyph.id, backend.font_info(fid).masters[0].id)
    assert backend.lib(layer.id) == {} and calls["findLayerCreate"] == 0
    backend.set_lib(layer.id, {"a": 1})
    assert calls["findLayerCreate"] == 1 and backend.lib(layer.id) == {"a": 1}


def test_lib_when_owned_unregistered_font_then_unsupported_without_fgpackage(native):
    from fontlab_glyport.model.fontlab_backend import OwnedPackage

    module, calls, _, _ = native
    source = CountingPackage(12, calls, glyph_count=1, master_count=1)

    class Unregistered:
        id, isValid, masters, upm = 120, True, ("Regular",), 1000

        @property
        def packageLib(self):
            raise AssertionError("may read fgPackage on an unregistered package")

    module.flWorkspace = None
    backend = FontLabBackend(packages=[OwnedPackage(Unregistered(), source)])
    (fid,) = backend.list_fonts()
    with pytest.raises(UnsupportedCapability):
        backend.lib(fid)


def test_features_when_read_then_prefix_and_tags_in_native_order(native):
    module, calls, _, _ = native
    package = CountingPackage(13, calls, glyph_count=1, master_count=1)

    class Layout:
        def keys(self):
            return ["liga", "kern"]

        def get_feature(self, tag):
            return {"liga": "sub f i by fi;", "kern": "pos A V -40;"}[tag]

        def get_prefix(self):
            return "languagesystem DFLT dflt;"

    package.features = Layout()
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    info = backend.features(fid)
    assert info.prefix == "languagesystem DFLT dflt;"
    assert [(f.name, f.code) for f in info.features] == [
        ("liga", "sub f i by fi;"),
        ("kern", "pos A V -40;"),
    ]


def test_layer_edits_notify_layers_then_glyph_in_one_list(native):
    """Native fact (R023, probe_undo_forms.json): an Edit > Undo step needs the
    changed layers followed by their glyph in one notifyChangesApplied list; a
    layer alone only advances the layer history and its edit is lost to Undo."""
    module, _, package, _ = native
    sent = []
    module.flItems = lambda: SimpleNamespace(
        notifyChangesApplied=lambda name, items, recursive=False: sent.append(
            (name, list(items))
        )
    )
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[3]
    native_glyph = package._glyphs[3]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    native_layer = native_glyph.findLayer(master.name)
    # Native fact (probe_undo_first_edit.json): FontLab stores the state at each
    # notification and Undo restores the previous one, so the pre-change state is
    # notified once before the first change (else a first edit cannot be undone).
    pair = [native_layer, native_glyph]
    backend.set_layer_width(layer.id, 600)
    assert sent == [("Glyport edit", pair), ("Glyport edit", pair)]
    sent.clear()
    backend.begin_undo("group")
    backend.set_layer_width(layer.id, 610)
    backend.set_layer_width(layer.id, 620)
    assert sent == [("group", pair)], "pre-change state once per group"
    backend.end_undo()
    assert sent == [("group", pair), ("group", pair)]


class Axis:
    """flAxis double: valueWeight reads the location by shortName, as FontLab's
    own setLocation stores it (probe_locations.json)."""

    def __init__(self, name, tag, short, hidden=False):
        self.name, self.tag, self.shortName, self.hidden = name, tag, short, hidden

    def valueWeight(self, location, default):
        return location.get(self.shortName, default)


def test_font_info_when_axes_then_axis_infos_and_master_coordinates(native):
    module, calls, _, _ = native
    package = CountingPackage(20, calls, glyph_count=1, master_count=2)
    package.axes = [Axis("Weight", "wght", "wt"), Axis("Width", "wdth", "wd", True)]
    locations = {"Master 0": {"wt": 300.0, "wd": 100.0}, "Master 1": {"wt": 700.0}}
    package.location = lambda name: locations[name]
    package.instances = [
        SimpleNamespace(
            name="Bold",
            exportable=False,
            location={"wt": 700.0, "wd": 80.0},
            weight="Bold",
            weightValue=700,
            width="Condensed",
        )
    ]
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    info = backend.font_info(fid)
    assert [(a.name, a.tag, a.hidden) for a in info.axes] == [
        ("Weight", "wght", False),
        ("Width", "wdth", True),
    ]
    assert [m.axes for m in info.masters] == [(300.0, 100.0), (700.0, 0.0)]
    (instance,) = backend.instances(fid)
    assert (instance.name, instance.axes, instance.exports) == (
        "Bold",
        (700.0, 80.0),
        False,
    )


class FontPr:
    """In-process MCP tools double (FontLab `fontpr`): dict replies, paginated
    pairs, @-prefixed FontLab class names, font ids are package.fgId."""

    class Error(Exception):
        pass

    def __init__(self):
        self.pairs, self.calls, self.hints = {}, [], {}

    def list_kerning_pairs(self, font_id, master_name, offset=0, limit=200):
        self.calls.append(("list", font_id, master_name, offset))
        rows = [
            {"left": l, "right": r, "value": v}
            for (f, m, l, r), v in self.pairs.items()
            if (f, m) == (font_id, master_name)
        ]
        return {"pairs": rows[offset : offset + limit], "total_pairs": len(rows)}

    def get_kerning_pair(self, font_id, left, right, master_name):
        value = self.pairs.get((font_id, master_name, left, right))
        return {"has_value": value is not None, "value": value or 0}

    def set_kerning_pair(self, font_id, left, right, value, master_name):
        self.pairs[font_id, master_name, left, right] = value
        return {"status": "ok"}

    def delete_kerning_pair(self, font_id, left, right, master_name):
        del self.pairs[font_id, master_name, left, right]
        return {"status": "ok"}

    def get_layer_hints(self, font_id, glyph_name, layer_name, offset=0):
        hints = self.hints.get((font_id, glyph_name, layer_name), [])
        page = hints[offset : offset + 2]
        return {
            "hints": page,
            "truncated": offset + 2 < len(hints),
            "next_offset": offset + 2,
        }


@pytest.fixture
def fontpr(monkeypatch):
    tools = FontPr()
    monkeypatch.setattr(FontLabBackend, "_fontpr", staticmethod(lambda: tools))
    return tools


def test_kerning_when_listed_then_pages_and_glyphs_group_keys(native, fontpr):
    module, calls, _, _ = native
    package = CountingPackage(21, calls, glyph_count=1, master_count=1)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    master = backend.font_info(fid).masters[0]
    for i in range(250):
        fontpr.pairs[package.fgId, "Master 0", f"g{i}", "A"] = -i
    fontpr.pairs[package.fgId, "Master 0", "@T", "@A"] = -75
    pairs = backend.kerning(fid, master.id)
    assert len(pairs) == 251
    assert ("@MMK_L_T", "@MMK_R_A", -75) in [(p.left, p.right, p.value) for p in pairs]
    assert [c[3] for c in fontpr.calls] == [0, 200]


def test_set_kerning_when_group_keys_then_fontlab_class_names(native, fontpr):
    module, calls, _, _ = native
    package = CountingPackage(22, calls, glyph_count=1, master_count=1)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    master = backend.font_info(fid).masters[0]
    backend.set_kerning(fid, master.id, "@MMK_L_T", "@MMK_R_A", -75.0)
    backend.set_kerning(fid, master.id, "A", "V", -40.0)
    assert fontpr.pairs == {
        (package.fgId, "Master 0", "@T", "@A"): -75.0,
        (package.fgId, "Master 0", "A", "V"): -40.0,
    }
    backend.set_kerning(fid, master.id, "A", "V", None)
    backend.set_kerning(fid, master.id, "A", "V", None)  # missing pair: no-op
    assert (package.fgId, "Master 0", "A", "V") not in fontpr.pairs


def test_kerning_when_owned_unregistered_then_unsupported(native, fontpr):
    from fontlab_glyport.model.fontlab_backend import OwnedPackage

    module, calls, _, _ = native
    source = CountingPackage(23, calls, glyph_count=1, master_count=1)
    owned = SimpleNamespace(id=230, isValid=True, masters=("Regular",), upm=1000)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[OwnedPackage(owned, source)])
    (fid,) = backend.list_fonts()
    info = backend.font_info(fid)
    assert info.axes == () and info.masters[0].axes == ()
    with pytest.raises(UnsupportedCapability):
        backend.kerning(fid, info.masters[0].id)


def _point(x, y):
    return SimpleNamespace(x=lambda: x, y=lambda: y)


def test_guides_when_read_and_appended_then_registered(native, monkeypatch):
    module, _, package, _ = native

    class Guide:
        def __init__(self, angle=0, point=None, isHint=False):
            point = point or _point(0, 0)
            self.id, self.isValid, self.isHint = id(self), True, isHint
            self.angle, self.centerPoint, self.name = angle, point, ""

        def applyTransform(self, matrix):
            self.centerPoint = _point(
                self.centerPoint.x() + matrix[4], self.centerPoint.y() + matrix[5]
            )

    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: SimpleNamespace(QTransform=lambda *values: values),
    )
    module.flGuideLine = Guide
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    native_layer = package._glyphs[0].findLayer(master.name)
    native_layer.appendGuidelines = native_layer.guidelines.extend
    # Native fact (r020-model run 1): PostScript hints are also flGuideLines.
    native_layer.guidelines.append(Guide(0.0, _point(0, 100), isHint=True))
    from fontlab_glyport.model.backend import GuideInfo

    gid = backend.append_guide(layer.id, GuideInfo("", 10, 250, 90.0, "base"))
    (guide,) = backend.layer(glyph.id, master.id).guides
    assert (guide.id, guide.x, guide.y, guide.angle, guide.name) == (
        gid,
        10,
        250,
        90.0,
        "base",
    )
    assert backend.is_valid(gid)


def test_hints_when_paged_then_hint_infos_by_glyph_and_layer_name(native, fontpr):
    module, calls, _, _ = native
    package = CountingPackage(24, calls, glyph_count=1, master_count=1)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    row = {
        "orientation": "horizontal",
        "position": 100,
        "width": 80,
        "name": "h1",
        "ghost": False,
    }
    fontpr.hints[package.fgId, "glyph0", "Master 0"] = [
        row,
        {**row, "width": -20, "ghost": True, "name": ""},
        {**row, "orientation": "vertical", "name": "v"},
    ]
    hints = backend.hints(layer.id)
    assert [(h.horizontal, h.width, h.ghost, h.name) for h in hints] == [
        (True, 80, False, "h1"),
        (True, -20, True, ""),
        (False, 80, False, "v"),
    ]


def test_kerning_classes_when_listed_then_sides_and_members(native, fontpr):
    module, calls, _, _ = native
    package = CountingPackage(25, calls, glyph_count=1, master_count=1)
    fontpr.list_kerning_classes = lambda font_id: (
        {
            "classes": [
                {"name": "T", "glyph_names": ["T"], "left": True, "right": False},
                {"name": "O", "glyph_names": ["O", "Q"], "left": True, "right": True},
            ]
        }
        if font_id == package.fgId
        else {}
    )
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    assert [
        (c.name, c.glyphs, c.left, c.right) for c in backend.kerning_classes(fid)
    ] == [
        ("T", ("T",), True, False),
        ("O", ("O", "Q"), True, True),
    ]


def test_current_font_when_active_font_switches_or_closes_then_follows_fontlab(native):
    _, _, package, _ = native
    backend = FontLabBackend()
    first, second = backend.list_fonts()
    active = FontLabBackend._fontpr()
    assert backend.current_font_id() == second
    active.font_id = package.fgId
    assert backend.current_font_id() == first
    active.font_id = 999  # an id the workspace no longer knows
    assert backend.current_font_id() is None
    # Native fact (r019-document run 2): after the active font closes FontLab has
    # no active font (and currentPackage is None) although another font is open.
    active.font_id = None
    assert backend.current_font_id() is None


def test_node_selected_when_set_then_native_flag_without_notification(native):
    from fontlab_glyport.model.backend import NodeInfo, PathInfo

    module, calls, package, _ = native

    class Node(NodeFlags):
        def __init__(self, point, *, nodeType="on"):
            self.nodeState = {"on": 1, "off": 2, "curve": 4}[nodeType]
            self.id, self.isValid, self.selected, self.smooth = (
                id(self),
                True,
                False,
                False,
            )
            self.x, self.y = point.x(), point.y()
            self.position = point

        def isOff(self):
            return False

        def isCurve(self):
            return False

    class Contour:
        def __init__(self, nodes, *, closed=False):
            self.id, self.isValid, self._nodes = id(self), True, nodes
            self.closed, self.isTT = closed, False

        def nodes(self):
            return self._nodes

    class Shape:
        def __init__(self):
            self.id, self.isValid, self.contours = id(self), True, []
            self.isComposite = self.isComponent = False
            self.transform = SimpleNamespace(map=lambda p: p)

        def addContour(self, contour, _):
            self.contours.append(contour)

    module.flNode, module.flContour, module.flShape = Node, Contour, Shape
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    backend.append_path(layer.id, PathInfo("", (NodeInfo("", 1, 2),)))
    node = backend.layer(glyph.id, master.id).paths[0].nodes[0]
    assert node.selected is False
    before = calls["notify"]
    backend.set_node_selected(node.id, True)
    assert backend.layer(glyph.id, master.id).paths[0].nodes[0].selected is True
    assert calls["notify"] == before, "selection is UI state: no change notification"


class TextBlock:
    """flTextBlock double (probe_glyph_tab.json, probe_text_cursor.json):
    glyph infos with .glyph and .id; each read returns new wrappers."""

    def __init__(self, package, names, active=None, lines=None):
        self.package, self.id = package, id(self)
        self._infos = [
            SimpleNamespace(id=i, glyph=SimpleNamespace(name=n))
            for i, n in enumerate(names)
        ]
        self._lines = lines or [0] * len(names)
        self._active = next((i.id for i in self._infos if i.glyph.name == active), None)

    def getAllGlyphs(self):
        return [SimpleNamespace(**vars(info)) for info in self._infos]

    def getLineIndex(self, info):
        return self._lines[info.id]

    def symbolList(self):
        count = getattr(self, "_breaks", max(self._lines, default=0))
        return SimpleNamespace(symbols=lambda: [SimpleNamespace(cr=True)] * count)

    def getActiveGlyph(self):
        if self._active is None:
            return None
        return SimpleNamespace(**vars(self._infos[self._active]))

    def setActiveGlyph(self, info):
        self._active = info.id


def test_edit_view_when_active_tab_belongs_to_font_then_glyphs_and_master(native):
    module, _, package, _ = native
    package.master = "Master 3"
    workspace = module.flWorkspace.instance()
    blocks = {"active": TextBlock(package, ["glyph0", "glyph1"], "glyph1", [0, 1])}
    workspace.getActiveTextBlock = lambda: blocks["active"]
    module.flWorkspace = SimpleNamespace(instance=lambda: workspace)
    sent = []

    class Symbols:
        """fgSymbolList double: built from a str or a list of fgSymbols."""

        def __init__(self, source):
            self.parts = [source]

        def append(self, other):
            self.parts.extend(other.parts)

    module.fgSymbolList = Symbols
    module.fgSymbol = lambda name: ("sym", name)
    module.flItems = lambda: SimpleNamespace(
        requestContent=lambda symbols, cursor: sent.append((symbols.parts, cursor))
    )
    backend = FontLabBackend()
    first, second = backend.list_fonts()
    view = backend.edit_view(first)
    assert (view.lines, view.active, view.master) == (
        (("glyph0",), ("glyph1",)),
        "glyph1",
        "Master 3",
    )
    assert backend.edit_view(second) is None, "the active tab shows another font"
    assert view.cursor == 2, "glyph0, line break, glyph1"
    backend.set_edit_cursor(first, 1)  # a line-break slot: the glyph before it
    assert backend.edit_view(first).active == "glyph0"
    backend.set_edit_cursor(first, 9)
    assert backend.edit_view(first).cursor == 2
    # Native facts (probe_tab_text.json): unencoded names need fgSymbol objects;
    # only the string form "\n" makes a line break.
    package.findName = lambda name: None
    backend.set_edit_glyphs(first, (("A", "a.sc"), (), ("B",)))
    assert sent == [([[("sym", "A"), ("sym", "a.sc")], "\n", "\n", [("sym", "B")]], 0)]
    backend.set_edit_glyphs(first, ())
    assert sent[-1] == ([""], 0)
    with pytest.raises(UnsupportedCapability):
        backend.set_edit_glyphs(second, (("A",),))
    # Native fact (r019-tab run 2): a fresh glyph tab has no active text block;
    # the active canvas's first block is the tab's text.
    blocks["active"] = None
    canvas = {"blocks": [TextBlock(package, ["glyph1"])]}
    workspace.getActiveCanvas = lambda: SimpleNamespace(
        textBlocks=lambda: canvas["blocks"]
    )
    assert backend.edit_view(first).lines == (("glyph1",),)
    canvas["blocks"] = []
    assert backend.edit_view(first) is None


@pytest.mark.parametrize(
    "indices,breaks,expected",
    [
        ([0], 2, (("glyph0",), (), ())),
        ([1, 3], 4, ((), ("glyph0",), (), ("glyph1",), ())),
        ([], 2, ((), (), ())),
    ],
)
def test_edit_view_preserves_leading_internal_and_trailing_empty_lines(
    native, indices, breaks, expected
):
    module, _, package, _ = native
    package.master = "Regular"
    workspace = module.flWorkspace.instance()
    block = TextBlock(
        package, [f"glyph{i}" for i in range(len(indices))], lines=indices
    )
    block._breaks = breaks
    workspace.getActiveTextBlock = lambda: block
    module.flWorkspace = SimpleNamespace(instance=lambda: workspace)
    backend = FontLabBackend()
    font_id, _ = backend.list_fonts()
    assert backend.edit_view(font_id).lines == expected, (
        "Glyph infos omit empty lines; explicit native symbol breaks must survive"
    )


def test_current_layers_when_fontpr_reports_then_this_fonts_glyphs_only(native):
    module, _, package, unrelated = native
    workspace = module.flWorkspace.instance()
    workspace.activeFontPanel = None  # this test models the active Glyph window
    module.flWorkspace.instance = lambda: workspace
    tools = FontLabBackend._fontpr()
    tools.get_current_glyphs = lambda: {
        "glyphs": [
            {"name": "A", "package_id": package.fgId, "active_layer_name": "Bold"},
            {"name": "B", "package_id": unrelated.fgId, "active_layer_name": "Bold"},
        ]
    }
    backend = FontLabBackend()
    first, _ = backend.list_fonts()
    assert backend.current_layers(first) == (("A", "Bold"),)

    def none():
        raise tools.Error("No current glyphs.")

    tools.get_current_glyphs = none
    assert backend.current_layers(first) == ()


def test_open_edit_view_when_called_then_connected_empty_tab_slot(native, monkeypatch):
    from test_tab_activation_preservation import EmptyTabEmitter

    module, _, package, _ = native
    state = SimpleNamespace(
        events=[],
        emitters=[],
        contents=[],
        selected="old-tab",
        main=object(),
        connected=True,
        disconnected=True,
        fail_at=None,
        open_tab=None,
    )
    module.MainWindow = lambda: state.main
    workspace = module.flWorkspace.instance()
    workspace.getActiveTextBlock = lambda: None
    workspace.getActiveCanvas = lambda: None
    module.flWorkspace = SimpleNamespace(instance=lambda: workspace)
    tools = FontLabBackend._fontpr()
    tools.set_active_font = lambda font_id: state.events.append(("activate", font_id))
    qtgui = SimpleNamespace(QLineEdit=lambda: EmptyTabEmitter(state))
    monkeypatch.setitem(sys.modules, "PythonQt.QtGui", qtgui)
    sys.modules["PythonQt"].QtGui = qtgui
    backend = FontLabBackend()
    first, _ = backend.list_fonts()
    backend.open_edit_view(first)
    assert state.events[1][0] == "text" and state.events[1][1]
    assert state.events[2:] == [
        "connect",
        ("activate", package.fgId),
        ("text", ""),
        ("emit", ""),
        "disconnect",
        "delete",
    ]
    assert state.contents == [""] and state.selected == "new-empty-tab"


def test_classes_when_fontgate_groups_then_feature_classes_only(native):
    """Native fact (probe_ot_classes.json): fgFont.groups maps names to fgGroup
    objects; OpenType classes have isFeaGroup(); indexing yields glyph names."""
    module, calls, _, _ = native
    package = CountingPackage(26, calls, glyph_count=1, master_count=1)

    class Group(list):
        def __init__(self, names, fea):
            super().__init__(names)
            self._fea = fea

        def isFeaGroup(self):
            return self._fea

    package.groups = SimpleNamespace(
        items=lambda: [
            ("uc", Group(["A", "B"], True)),
            ("kern_T", Group(["T"], False)),
        ]
    )
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    assert [(c.name, c.glyphs) for c in backend.classes(fid)] == [("uc", ("A", "B"))]


def test_pending_layer_creation_prepares_glyph_then_layer(native):
    module, calls, _, _ = native
    sent = []
    module.flItems = lambda: SimpleNamespace(
        notifyChangesApplied=lambda name, items, recursive=False: sent.append(
            (name, list(items))
        )
    )
    package = CountingPackage(27, calls, glyph_count=1, master_count=1)
    package._glyphs = [LayerlessGlyph(0, ".notdef", calls)]
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    layer = backend.layer(glyph.id, backend.font_info(fid).masters[0].id)
    backend.begin_undo("create")
    backend.set_layer_width(layer.id, 640)
    backend.end_undo()
    native_glyph = package._glyphs[0]
    native_layer = native_glyph.findLayer("Master 0")
    # Review R-L1: a layer is always prepared together with its glyph.
    assert sent == [
        ("create", [native_glyph]),
        ("create", [native_layer, native_glyph]),
        ("create", [native_layer, native_glyph]),
    ]


def test_component_when_shape_is_component_and_composite_then_read(native):
    """Native fact (probe_components.json): a glyph component is a shape with
    isComponent AND isComposite true; shapeData.componentGlyph names the base."""
    _, _, package, _ = native

    class Transform:
        def isAffine(self):
            return True

        def m11(self):
            return 1.0

        def m12(self):
            return 0.0

        def m21(self):
            return 0.0

        def m22(self):
            return 1.0

        def dx(self):
            return 30.0

        def dy(self):
            return 10.0

    component = SimpleNamespace(
        id=555,
        isValid=True,
        isComponent=True,
        isComposite=True,
        transform=Transform(),
        shapeData=SimpleNamespace(componentGlyph="A"),
    )
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    package._glyphs[0].findLayer(master.name)._shapes.append(component)
    (info,) = backend.layer(glyph.id, master.id).components
    assert (info.componentName, info.transform) == (
        "A",
        (1.0, 0.0, 0.0, 1.0, 30.0, 10.0),
    )


def test_bounds_anchor_move_and_current_master_natively_shaped(native):
    module, _, package, _ = native
    rect = SimpleNamespace(
        isNull=lambda: False,
        x=lambda: 100.0,
        y=lambda: 0.0,
        width=lambda: 200.0,
        height=lambda: 500.0,
    )
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    info = backend.font_info(fid)
    native_layer = package._glyphs[0].findLayer(info.masters[0].name)
    native_layer.boundingBox = rect
    layer = backend.layer(glyph.id, info.masters[0].id)
    assert backend.layer_bounds(layer.id) == (100.0, 0.0, 200.0, 500.0)
    native_layer.boundingBox = SimpleNamespace(isNull=lambda: True)
    assert backend.layer_bounds(layer.id) is None
    pin = SimpleNamespace(id=777, isValid=True, name="top", point=None)
    module.flPinPoint = lambda p: pin
    anchor_id = backend.add_anchor(layer.id, AnchorInfo("", "top", 1, 2))
    backend.set_anchor_position(anchor_id, 30, 40)
    assert (pin.point.x(), pin.point.y()) == (30, 40)
    package.master = "Master 5"
    assert backend.current_master(fid) == info.masters[5].id


# Review R-L1 fix round ----------------------------------------------------------


def _recording_items(module):
    sent, failures = [], []

    def notify(name, items, recursive=False):
        if failures:
            raise failures.pop(0)
        sent.append((name, list(items)))

    module.flItems = lambda: SimpleNamespace(notifyChangesApplied=notify)
    return sent, failures


def test_two_layers_of_one_glyph_each_prepared_with_layer_and_glyph(native):
    module, calls, _, _ = native
    sent, _ = _recording_items(module)
    package = CountingPackage(30, calls, glyph_count=1, master_count=2)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    masters = backend.font_info(fid).masters
    first = backend.layer(glyph.id, masters[0].id)
    second = backend.layer(glyph.id, masters[1].id)
    g = package._glyphs[0]
    l0, l1 = g.findLayer(masters[0].name), g.findLayer(masters[1].name)
    backend.begin_undo("two masters")
    backend.set_layer_width(first.id, 600)
    backend.set_layer_width(second.id, 610)
    backend.end_undo()
    assert sent == [
        ("two masters", [l0, g]),
        ("two masters", [l1, g]),
        ("two masters", [l0, l1, g]),
    ]


def test_prepare_when_notification_fails_then_retry_sends_pre_change_again(native):
    module, _, package, _ = native
    sent, failures = _recording_items(module)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    backend.begin_undo("g")
    failures.append(RuntimeError("notify failed"))
    with pytest.raises(RuntimeError):
        backend.set_layer_width(layer.id, 600)
    backend.set_layer_width(layer.id, 610)
    assert len(sent) == 1 and sent[0][0] == "g", "pre-change sent on the retry"


def test_end_undo_when_publication_fails_then_changes_kept_for_retry(native):
    module, _, package, _ = native
    sent, failures = _recording_items(module)
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    backend.begin_undo("g")
    backend.set_layer_width(layer.id, 600)
    failures.append(RuntimeError("publish failed"))
    with pytest.raises(RuntimeError):
        backend.end_undo()
    backend.end_undo()  # retry publishes the retained changes
    assert sent[-1][0] == "g" and len(sent[-1][1]) == 2
    with pytest.raises(RuntimeError):
        backend.end_undo()  # now closed


def test_edit_view_carries_the_text_block_id(native):
    module, _, package, _ = native
    workspace = module.flWorkspace.instance()
    package.master = "Master 0"
    block = TextBlock(package, ["glyph0"])
    block.id = 4242
    workspace.getActiveTextBlock = lambda: block
    module.flWorkspace = SimpleNamespace(instance=lambda: workspace)
    backend = FontLabBackend()
    first, _ = backend.list_fonts()
    assert backend.edit_view(first).id == "4242"


def test_master_metrics_when_read_then_font_metrics_and_italic_from_its_master(
    monkeypatch,
):
    calls = Counter()
    package = CountingPackage(1, calls)
    package.master = "Master 0"
    package.italicAngle_value = 0.0

    def set_master(name):
        calls["setMaster"] += 1
        package.master = name
        package.italicAngle_value = {"Master 0": 0.0, "Master 1": 12.0}[name]

    package.setMaster = set_master
    module = SimpleNamespace(
        FontMetrics=lambda pkg, name: SimpleNamespace(
            ascender=750,
            capsHeight=700,
            descender=-250,
            xHeight={"Master 0": 500, "Master 1": 520}[name],
        )
    )
    monkeypatch.setattr(FontLabBackend, "_native", staticmethod(lambda: module))
    backend = FontLabBackend([package])
    (font_id,) = backend.list_fonts()
    first, second = backend.font_info(font_id).masters
    assert calls["setMaster"] == 0, "font_info reads no metrics"
    assert tuple(backend.master_metrics(first.id)) == (750, 700, -250, 500, 0)
    assert calls["setMaster"] == 0, "the current master needs no switch"
    assert tuple(backend.master_metrics(second.id)) == (750, 700, -250, 520, 12)
    assert package.master == "Master 0" and calls["setMaster"] == 2, (
        "switched for the angle, then restored"
    )


def test_closed_path_when_read_then_glyphs_order_curve_types_and_start_node(native):
    """FontLab's closed contour starts with its start node; Glyphs lists the
    start node last. Cubic control points are native "curve" nodes; on-curve
    types come from the incoming segment (native facts: glyport-matrix
    probe_nodes)."""
    from fontlab_glyport.model.backend import NodeInfo, PathInfo

    module, _, package, _ = native

    class Node(NodeFlags):
        def __init__(self, point, *, nodeType="on"):
            self.nodeState = {"on": 1, "off": 2, "curve": 4}[nodeType]
            self.id, self.isValid, self.selected, self.smooth = (
                id(self),
                True,
                False,
                False,
            )
            self.x, self.y, self.kind = point.x(), point.y(), nodeType
            self.position = point

        def isOff(self):
            return self.kind == "off"  # native: quadratic off-curve points

        def isCurve(self):
            return self.kind == "curve"  # native: cubic control points

    class Contour:
        def __init__(self, nodes, *, closed=False):
            self.id, self.isValid, self._nodes = id(self), True, list(nodes)
            self.closed, self.isTT = closed, False

        def nodes(self):
            return list(self._nodes)

        def setStartPoint(self, index):
            self._nodes = self._nodes[index:] + self._nodes[:index]

    class Shape:
        def __init__(self):
            self.id, self.isValid, self.contours = id(self), True, []
            self.isComposite = self.isComponent = False
            self.transform = SimpleNamespace(map=lambda p: p)

        def addContour(self, contour, _):
            self.contours.append(contour)

        def removeContour(self, contour):
            self.contours.remove(contour)

        def clone(self):  # native flShape.clone(): new shape, contours and nodes
            copy = deepcopy(self)
            copy.id = id(copy)
            for contour in copy.contours:
                contour.id = id(contour)
                for node in contour.nodes():
                    node.id = id(node)
            return copy

    module.flNode, module.flContour, module.flShape = Node, Contour, Shape
    module.flWorkspace = None
    backend = FontLabBackend(packages=[package])
    (fid,) = backend.list_fonts()
    glyph = backend.glyphs(fid)[0]
    master = backend.font_info(fid).masters[0]
    layer = backend.layer(glyph.id, master.id)
    glyphs_order = (
        NodeInfo("", 100, 0, "line"),
        NodeInfo("", 300, 0, "line"),
        NodeInfo("", 400, 100, "offcurve"),
        NodeInfo("", 400, 300, "offcurve"),
        NodeInfo("", 200, 300, "curve"),
    )
    path_id = backend.append_path(layer.id, PathInfo("", glyphs_order, True))
    contour = backend._object(path_id)
    assert [n.kind for n in contour.nodes()] == ["on", "on", "on", "curve", "curve"]
    assert next((n.x, n.y) for n in contour.nodes()) == (200, 300), (
        "start node first natively"
    )

    def read():
        (path,) = backend.layer(glyph.id, master.id).paths
        return [(n.x, n.y, n.type) for n in path.nodes], path

    nodes, path = read()
    assert nodes == [(n.x, n.y, n.type) for n in glyphs_order]
    open_id = backend.append_path(layer.id, PathInfo("", glyphs_order[:2], False))
    opened = next(
        p for p in backend.layer(glyph.id, master.id).paths if p.id == open_id
    )
    assert [n.type for n in opened.nodes] == ["line", "line"], "open: no wrap-around"
    backend.remove_path(layer.id, open_id)
    backend.make_node_first(path.nodes[1].id)  # Glyphs: (300, 0) becomes the start node
    nodes, edited = read()
    assert nodes[-1] == (300, 0, "line") and nodes[0] == (400, 100, "offcurve")
    assert next((n.x, n.y) for n in backend._object(path_id).nodes()) == (300, 0)
    # Copy-on-write: the edit went to a clone at the same index; the shape the
    # undo history references keeps its start node, and the path id is stable.
    assert next((n.x, n.y) for n in contour.nodes()) == (200, 300)
    assert edited.id == path_id and backend._object(path_id) is not contour
