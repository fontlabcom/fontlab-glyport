# this_file: tests/test_issue106_round7_native.py
"""Native boundary checks using small Python doubles, without FontLab."""

from types import SimpleNamespace

import pytest
from history_scene import install_font_window
from test_fontlab_backend_lazy import NodeFlags

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.fontlab_backend import FontLabBackend


class NativeFont(dict):
    @property
    def glyphs(self):
        return list(self.values())


class Layer:
    def __init__(self, native_id):
        self.id, self.isValid = native_id, True
        self.shapes, self.anchors, self.guidelines = [], [], []
        self.advanceWidth = 500
        self.components = []
        self.autoLayer = False
        self.recipe = ""
        self.metricsLeft = self.metricsRight = self.metricsWidth = ""
        self.mask = None
        self.mask_calls = []

    def changed(self):
        pass

    def update(self):
        pass

    def getMaskLayer(self, create):
        self.mask_calls.append(create)
        if create and self.mask is None:
            self.mask = Layer(self.id + 1)
        return self.mask

    def removeShape(self, shape):
        self.shapes.remove(shape)


@pytest.fixture
def native(monkeypatch):
    package = SimpleNamespace(id=10, fgId=100, isValid=True, masters=["Regular"])
    glyph = SimpleNamespace(
        id=20, name="A", isValid=True, changed=lambda: None, update=lambda: None
    )
    package.fgPackage = NativeFont(A=SimpleNamespace(id=200, name="A", unicodes=[0x41]))
    foreground = Layer(30)
    glyph.layers = [foreground]
    calls = []
    module = SimpleNamespace(
        flNode=NodeFlags,
        flWorkspace=SimpleNamespace(
            instance=lambda: SimpleNamespace(packages=lambda: [package])
        ),
        flPackage=lambda p: p,
        flItems=lambda: SimpleNamespace(
            notifyChangesApplied=lambda *args: calls.append(args)
        ),
    )
    install_font_window(monkeypatch, module, package)
    backend = FontLabBackend(packages=[package])
    monkeypatch.setattr(backend, "_native", lambda: module)
    fid = backend._font_id(package)
    mid = backend._register((fid, "master", "Regular"), package, fid)
    backend._master_names[mid] = "Regular"
    gid = backend._register((fid, "glyph", 200), glyph, fid)
    lid = backend._read_layer(fid, foreground, mid, gid).id
    return SimpleNamespace(
        backend=backend,
        package=package,
        glyph=glyph,
        layer=foreground,
        fid=fid,
        mid=mid,
        gid=gid,
        lid=lid,
        calls=calls,
        module=module,
    )


def test_f29_native_mask_read_is_lazy_and_first_write_creates_it(native):
    b = native.backend
    info = b.background_layer(native.lid)
    assert not info.paths and native.layer.mask is None
    assert native.layer.mask_calls == [False]
    assert not native.calls, "reading an empty background must not edit the font"
    b.begin_undo("Background edit")
    b.set_layer_width(info.id, 333)
    again = b.background_layer(native.lid)
    assert again.id == info.id and again.width == 333
    assert native.layer.advanceWidth == 500
    assert native.layer.mask_calls == [False, True, False]
    b.end_undo()
    assert native.calls[-1] == (
        "Background edit",
        [native.layer, native.layer.mask, native.glyph],
        True,
    )


@pytest.mark.parametrize(
    "side,attr",
    [("left", "metricsLeft"), ("right", "metricsRight"), ("width", "metricsWidth")],
)
def test_f31_native_metrics_keys_use_expression_fields_and_publish_undo(
    native, side, attr
):
    b = native.backend
    assert b.layer_metrics_key(native.lid, side) is None
    b.begin_undo("Metrics")
    key = "=A" if side == "width" else "=|A"
    b.set_layer_metrics_key(native.lid, side, key)
    assert getattr(native.layer, attr) == key[1:]
    assert b.layer_metrics_key(native.lid, side) == key
    b.set_layer_metrics_key(native.lid, side, None)
    assert getattr(native.layer, attr) == ""
    b.end_undo()
    assert native.calls[-1] == ("Metrics", [native.layer, native.glyph], True)


def test_undo_rereading_layer_replaces_wrapper_but_still_publishes(native):
    b = native.backend
    font = Model(b)._font(native.fid)
    font._begin_undo("Edit")
    b.set_layer_width(native.lid, 650)
    reread = Layer(30)
    reread.advanceWidth = 650
    b._read_layer(native.fid, reread, native.mid, native.gid)
    assert b._objects[native.lid] is not native.layer
    notes = []
    font._finish_undo(notes.append)
    assert notes[0].code == "UNBALANCED_UNDO_CLOSED"
    assert native.calls[-1] == ("Edit", [reread, native.glyph], True)


def test_undo_appended_unresolved_glyph_matches_native_id(native):
    b, package = native.backend, native.package
    package.fgPackage = SimpleNamespace(glyphs=[])
    package.findName = lambda name: (
        SimpleNamespace(id=201, isValid=True, fgGlyphId=77)
        if package.fgPackage.glyphs
        else None
    )
    package.findFgId = lambda fg_id: SimpleNamespace(id=201, isValid=True)
    package.addGlyph = lambda glyph: package.fgPackage.glyphs.append(
        SimpleNamespace(id=77, name=glyph.name, unicodes=[])
    )
    native.module.flGlyph = lambda: SimpleNamespace(name="")
    native.module.flGlyph.updatedFgGlyphs = lambda: ()
    b._resolve_tool = lambda *args: (
        lambda **kwargs: package.addGlyph(SimpleNamespace(name=kwargs["glyph_name"]))
    )
    font = Model(b)._font(native.fid)
    font._begin_undo("Append")
    token = b.append_glyph(native.fid, "B")
    assert b._objects[token] is not None
    stored = b._changed["glyph", 201]
    notes = []
    font._finish_undo(notes.append)
    assert notes[0].code == "UNBALANCED_UNDO_CLOSED"
    validated = native.calls[-1][1][0]
    assert validated.id == stored.id


def test_f35_native_anchor_selection_refuses_instead_of_storing_invisible_state(native):
    b = native.backend
    anchor = SimpleNamespace(id=55, isValid=True)
    token = b._register((native.fid, "anchor", 55), anchor, native.lid)
    for access in (
        lambda: b.anchor_selected(token),
        lambda: b.set_anchor_selected(token, True),
    ):
        with pytest.raises(UnsupportedCapability) as error:
            access()
        assert error.value.capability == "GSAnchor.selected"
        assert "flPinPoint" in str(error.value)
    assert not hasattr(anchor, "selected")


def test_f36_native_component_and_guide_removal_preserves_other_members(native):
    b = native.backend
    component = SimpleNamespace(id=66, isValid=True)
    guide = SimpleNamespace(id=67, isValid=True)
    hint = SimpleNamespace(id=68, isValid=True)
    native.layer.shapes = [component]
    native.layer.guidelines = [guide, hint]
    cid = b._register((native.fid, "component", 66), component, native.lid)
    guide_id = b._register((native.fid, "guide", 67), guide, native.lid)
    b.remove_component(native.lid, cid)
    b.remove_guide(native.lid, guide_id)
    assert not native.layer.shapes
    assert native.layer.guidelines == [hint]
    assert not b.is_valid(cid) and not b.is_valid(guide_id)
    assert native.calls[-1][1] == [native.layer, native.glyph]


def test_f29_f36_native_background_clear_removes_mask_and_drops_its_pending_batch(
    native,
):
    b = native.backend
    native.glyph.removeLayer = lambda mask: setattr(native.layer, "mask", None)
    b.begin_undo("Background")
    background_id = b.background_layer(native.lid).id
    b.set_layer_width(background_id, 200)
    mask_id = native.layer.mask.id
    assert ("layer", mask_id) in b._changed
    b.clear_background_layer(native.lid)
    assert native.layer.mask is None
    assert not b.is_valid(background_id)
    assert ("layer", mask_id) not in b._changed
    assert b.can_publish_undo(native.fid)
    b.end_undo()
    assert native.calls[-1] == ("Background", [native.layer, native.glyph], True)
    replacement = b.background_layer(native.lid)
    assert replacement.id != background_id and not replacement.paths


def test_f36_readonly_native_guidelines_refuse_with_public_capability(native):
    class ReadOnlyLayer(Layer):
        @property
        def guidelines(self):
            return self._guidelines

        @guidelines.setter
        def guidelines(self, value):
            if hasattr(self, "_guidelines"):
                raise AttributeError("read only")
            self._guidelines = value

    layer = ReadOnlyLayer(30)
    guide = SimpleNamespace(id=69, isValid=True)
    layer._guidelines = [guide]
    b = native.backend
    b._objects[native.lid] = layer
    token = b._register((native.fid, "guide", 69), guide, native.lid)
    with pytest.raises(UnsupportedCapability) as error:
        b.remove_guide(native.lid, token)
    assert error.value.capability == "GSLayer.guides"
    assert layer.guidelines == [guide]
