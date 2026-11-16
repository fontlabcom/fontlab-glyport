# this_file: tests/test_public_api_native_writes.py
"""Guarded native write contracts using existing native-shaped scene doubles."""

from types import SimpleNamespace as NS

import pytest
from test_component_edits import components as components_fixture
from test_fontlab_backend_lazy import native  # noqa: F401
from test_fontlab_backend_r020 import font as metadata_fixture
from test_geometry_cache_updates import cached as cached_fixture

from fontlab_glyport.errors import NativeOperationError, UnsupportedCapability
from fontlab_glyport.model import GSFontMaster, Model


@pytest.fixture
def metadata(native, monkeypatch):  # noqa: F811
    backend, fid, package, sent = metadata_fixture.__wrapped__(native, monkeypatch)
    package.master = package.masters[0]
    package.ascender_value, package.capsHeight_value = 800, 700
    package.xHeight_value, package.descender_value = 500, -200
    package.italicAngle_value = 0
    package.setUpm = lambda upm, scale: (
        setattr(package, "upm", upm)
        if not scale
        else pytest.fail("must not scale geometry")
    )
    package.setMaster = lambda name: setattr(package, "master", name)
    monkeypatch.setattr(
        type(package._glyphs[0]),
        "layers",
        property(lambda self: list(self._layers.values())),
    )

    def rename(old, new):
        package.masters[package.masters.index(old)] = new
        if package.master == old:
            package.master = new
        return new

    package.renameMaster = rename
    module = native[0]
    module.FontMetrics = lambda package, name: NS(
        ascender=package.ascender_value,
        capsHeight=package.capsHeight_value,
        xHeight=package.xHeight_value,
        descender=package.descender_value,
    )
    return Model(backend)._font(fid), backend, package, sent


@pytest.mark.parametrize(
    "field,value", [("familyName", "New"), ("upm", 2048), ("unitsPerEm", 2000)]
)
def test_native_font_metadata_uses_package_history_without_scaling(
    metadata, field, value
):
    font, backend, package, sent = metadata
    setattr(font, field, value)
    assert getattr(font, field) == value
    assert len(sent) == 2 and all(items == [package] for _, items in sent)
    assert backend._prepared == backend._changed == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Book"),
        ("ascender", 830),
        ("capHeight", 710),
        ("xHeight", 540),
        ("descender", -230),
        ("italicAngle", -11),
    ],
)
def test_native_master_metadata_preserves_identity_and_one_history_group(
    metadata, field, value
):
    font, backend, package, sent = metadata
    master = font.masters[0]
    token = master.id
    setattr(master, field, value)
    assert getattr(master, field) == value
    assert font.masters[token] is master and font.masters[0] is master
    assert len(sent) == 2 and all(items == [package] for _, items in sent)
    assert backend._prepared == backend._changed == {}


def test_native_master_other_than_current_restores_focus(metadata):
    font, backend, package, _ = metadata
    original = package.master
    package.masters.append("Bold")
    bold = font.masters["Bold"]
    bold.ascender = 900
    assert package.master == original
    assert bold.ascender == 900
    assert backend._prepared == {}


def test_native_master_append_and_duplicate_rename_refuse_before_notification(metadata):
    font, _, package, sent = metadata
    with pytest.raises(UnsupportedCapability, match="create masters"):
        font.masters.append(GSFontMaster())
    package.masters.append("Bold")
    with pytest.raises(ValueError, match="Duplicate"):
        font.masters[0].name = "Bold"
    assert sent == []


@pytest.mark.parametrize(
    "method,args,kwargs",
    [
        ("set_font_info", ("font",), {"familyName": "X"}),
        ("set_master_info", ("master",), {"ascender": 900}),
    ],
)
def test_metadata_focus_refusal_precedes_native_change(
    metadata, monkeypatch, method, args, kwargs
):
    font, backend, package, sent = metadata
    token = font.id if args[0] == "font" else font.masters[0].id

    def refuse(*args, **kwargs):
        raise UnsupportedCapability("matching Font window required")

    monkeypatch.setattr(backend, "_require_history_scope", refuse)
    with pytest.raises(UnsupportedCapability, match="Font window"):
        getattr(backend, method)(token, **kwargs)
    assert package.info.familyName == "Owned 40" and package.ascender_value == 800
    assert sent == []


def test_native_failed_rename_is_reported(metadata):
    font, _, package, _ = metadata
    package.renameMaster = lambda old, new: None
    with pytest.raises(NativeOperationError, match="rename refused"):
        font.masters[0].name = "Book"
    assert package.masters == ["Master 0"]


def test_native_master_rename_ignores_retired_tokens(metadata):
    font, backend, package, sent = metadata
    master = font.masters[0]
    token = backend._register((font.id, "master", "retired"), package, font.id)
    backend._master_names[token] = master.name
    backend._invalidate(token)
    master.name = "Book"
    assert master.name == "Book" and font.masters[0] is master
    assert not backend.is_valid(token) and len(sent) == 2


def test_native_component_transform_keeps_history_owned_original(monkeypatch):
    s = components_fixture.__wrapped__(monkeypatch)
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=lambda *values: type(s.target.transform)(values)),
    )
    component = s.public.components[0]
    original = s.target.transform.values
    component.transform = (2, 0, 0, 3, 40, 50)
    assert component.transform == (2, 0, 0, 3, 40, 50)
    assert s.target.transform.values == original
    assert len(s.calls) == 2
    assert s.backend._prepared == s.backend._changed == {}
    s.layer.autoLayer = True
    with pytest.raises(UnsupportedCapability, match="auto layer"):
        component.scale = (4, 5)
    assert len(s.calls) == 2


def test_native_selection_components_are_ui_only_and_other_kinds_refuse(monkeypatch):
    s = components_fixture.__wrapped__(monkeypatch)
    s.target.selected = s.tail.selected = False
    component, tail = s.public.components
    node = s.public.paths[0].nodes[0]
    s.public.selection = [component, node]
    assert list(s.public.selection) == [node, component]
    s.public.selection = [tail]
    assert tail.selected and not component.selected and not node.selected
    s.public.clearSelection()
    assert list(s.public.selection) == [] and s.calls == []
    assert s.backend._prepared == s.backend._changed == {}
    anchor = NS(id=999, isValid=True)
    token = s.backend._register((s.fid, "anchor", 999), anchor, s.public.id)
    with pytest.raises(UnsupportedCapability, match="GSAnchor|flPinPoint"):
        s.backend.set_anchor_selected(token, True)
    with pytest.raises(UnsupportedCapability, match="GSGuide"):
        s.backend.set_guide_selected(token, True)


def test_native_anchor_name_uses_layer_history(monkeypatch):
    s = cached_fixture.__wrapped__(monkeypatch)
    anchor = NS(id=999, isValid=True, name="top", point=NS(x=lambda: 40, y=lambda: 90))
    s.layer.anchors = [anchor]
    live = s.font.glyphs[0].layers[0].anchors[0]
    live.name = "upper"
    assert live.name == "upper" and live.position == (40, 90)
    assert len(s.calls) == 2
    assert all(s.layer in items and s.glyph in items for _, items, _ in s.calls)


@pytest.mark.parametrize("kind", ["anchor", "guide"])
def test_native_selection_clears_supported_objects_with_unobservable_members(
    monkeypatch, kind
):
    s = cached_fixture.__wrapped__(monkeypatch)
    point = NS(x=lambda: 40, y=lambda: 90)
    item = NS(
        id=999,
        isValid=True,
        name="top",
        point=point,
        centerPoint=point,
        angle=0,
        isHint=False,
    )
    if kind == "anchor":
        s.layer.anchors = [item]
    else:
        s.layer.guidelines = [item]
    layer = s.font.glyphs[0].layers[0]
    node, other = layer.paths[0].nodes
    unsupported = (layer.anchors if kind == "anchor" else layer.guides)[0]

    def forbidden(*args):
        pytest.fail("unobservable selection was read or written")

    monkeypatch.setattr(s.backend, kind + "_selected", forbidden)
    monkeypatch.setattr(s.backend, "set_" + kind + "_selected", forbidden)
    layer.selection = [node]
    with pytest.raises(UnsupportedCapability, match=kind + "Selection"):
        layer.selection = [other, unsupported]
    assert list(layer.selection) == [node]
    layer.selection = [other]
    assert other.selected and not node.selected
    layer.selection = []
    assert not layer.selection
    layer.selection = [node]
    assert layer.clearSelection() is None
    assert not node.selected and not layer.selection
    assert s.calls == [] and s.backend._prepared == s.backend._changed == {}


@pytest.mark.parametrize("value", [None, "invalid", "move", "hobbycurve", 1, []])
def test_native_invalid_node_type_never_reaches_backend(monkeypatch, value):
    s = cached_fixture.__wrapped__(monkeypatch)
    node = s.font.glyphs[0].layers[0].paths[0].nodes[0]
    before = node._data()

    def forbidden(*args):
        pytest.fail("invalid type reached native backend")

    with monkeypatch.context() as guard:
        guard.setattr(s.backend, "is_valid", forbidden)
        guard.setattr(s.backend, "set_node_type", forbidden)
        with pytest.raises(ValueError, match="Invalid node type"):
            node.type = value
    assert node._data() == before and s.calls == []


def test_native_node_type_preserves_position_flags_and_undo_original(monkeypatch):
    s = cached_fixture.__wrapped__(monkeypatch)
    s.module.flNode.NodeType = {"On": 1, "Off": 2, "Curve": 4, "AnyNodeMask": 7}
    node_class = type(s.layer.shapes[0].contours[0].nodes()[0])
    monkeypatch.setattr(node_class, "isOff", lambda self: bool(self.nodeState & 2))
    monkeypatch.setattr(node_class, "isCurve", lambda self: bool(self.nodeState & 4))
    layer = s.font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    original = s.layer.shapes[0]
    node.selected, node.smooth = True, True
    s.calls.clear()
    node.type = "offcurve"
    assert node.type == "offcurve" and node.position == (10, 20)
    assert node.selected and node.smooth
    assert original.contours[0].nodes()[0].nodeState & 7 == 1
    assert len(s.calls) == 2
    with pytest.raises(UnsupportedCapability, match="incoming controls"):
        node.type = "curve"
    assert len(s.calls) == 2


def test_native_cubic_quadratic_type_conversion_changes_only_control_kinds(monkeypatch):
    s = cached_fixture.__wrapped__(monkeypatch)
    flags = {"On": 1, "Off": 2, "Curve": 4, "AnyNodeMask": 7}
    s.module.flNode.NodeType = flags
    contour = s.layer.shapes[0].contours[0]
    node_class = type(contour.nodes()[0])
    monkeypatch.setattr(node_class, "isOff", lambda self: bool(self.nodeState & 2))
    monkeypatch.setattr(node_class, "isCurve", lambda self: bool(self.nodeState & 4))
    monkeypatch.setattr(
        type(contour),
        "isTT",
        property(
            lambda self: any(node.isOff() for node in self.nodes()),
            lambda self, value: None,
        ),
        raising=False,
    )
    contour._nodes = [node_class(x) for x in (0, 10, 30, 40)]
    for control in contour._nodes[1:3]:
        control.nodeState = 4
    path = s.font.glyphs[0].layers[0].paths[0]
    end = path.nodes[-1]
    positions = [node.position for node in path.nodes]
    assert [node.type for node in path.nodes] == [
        "line",
        "offcurve",
        "offcurve",
        "curve",
    ]
    end.type = "qcurve"
    assert [node.type for node in path.nodes] == [
        "line",
        "offcurve",
        "offcurve",
        "qcurve",
    ]
    assert [node.position for node in path.nodes] == positions
    assert len(s.calls) == 2
    with pytest.raises(UnsupportedCapability, match="remove incoming controls"):
        end.type = "line"
    assert len(s.calls) == 2
    end.type = "curve"
    assert end.type == "curve" and len(s.calls) == 4
    assert [node.position for node in path.nodes] == positions


def test_native_master_rename_prepares_affected_layers_and_refuses_auto(metadata):
    font, _, package, sent = metadata
    glyph = package._glyphs[0]
    layer = NS(
        id=888,
        isValid=True,
        name="Master 0",
        autoLayer=False,
        getMaskLayer=lambda create: None,
    )
    glyph._layers = {"Master 0": layer}
    master = font.masters[0]
    layer.autoLayer = True
    with pytest.raises(UnsupportedCapability, match="automatic"):
        master.name = "Book"
    assert package.masters == ["Master 0"] and sent == []
    layer.autoLayer = False
    rename = package.renameMaster

    def rename_with_layers(old, new):
        assert len(sent) == 1 and layer in sent[0][1] and glyph in sent[0][1]
        layer.name = new
        return rename(old, new)

    package.renameMaster = rename_with_layers
    master.name = "Book"
    assert master.name == layer.name == "Book"
    assert len(sent) == 2
    assert all(
        layer in items and glyph in items and package in items for _, items in sent
    )
