# this_file: tests/test_issue106_round17_native.py
"""Native call boundaries without loading FontLab or PythonQt."""

import sys
from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture
from test_issue106_round11_selection import native_selection

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.backend import GuideInfo


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_selection_uses_scalar_legacy_indices_not_qt_ulong_list(monkeypatch):
    state = native_selection(monkeypatch)
    calls = []
    state.backend._objects[state.gid].name = "A"
    monkeypatch.setattr(
        state.backend, "_fontgate_font", lambda package: {"A": NS(index=7)}
    )
    monkeypatch.setitem(
        sys.modules,
        "FL",
        NS(
            fl=NS(
                Unselect=lambda: calls.append("clear"),
                Select=lambda index: calls.append(index),
            )
        ),
    )
    state.backend.set_font_selection(state.fid, [state.gid])
    assert calls == ["clear", 7]
    assert state.calls == [], "never send Python ints to QList<ulong>"


def test_guide_construction_uses_unambiguous_default_then_properties(
    native, monkeypatch
):
    calls = []

    def make_guide(*args, **kwargs):
        assert not args and not kwargs
        return NS(id=333, applyTransform=lambda matrix: calls.append(matrix))

    native.module.flGuideLine = make_guide
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=lambda *args: args),
    )
    guide = native.backend._new_guide(GuideInfo("", 30, 40, 25, "slant"))
    assert (guide.angle, guide.name) == (25, "slant")
    assert calls == [(1, 0, 0, 1, 30, 40)]


def test_target_append_keeps_native_glyph_and_never_passes_bare_fontgate(
    native, monkeypatch
):
    names, calls = {}, []
    added = NS(id=1234, isValid=True, fgGlyphId=4321)
    native.package.findName = names.get

    def build(name, capability, **kwargs):
        calls.append(kwargs)
        names[kwargs["glyph_name"]] = added

    monkeypatch.setattr(
        native.backend,
        "_resolve_tool",
        lambda name, capability: lambda **kw: build(name, capability, **kw),
    )
    token = native.backend.append_glyph(native.fid, "copy")
    assert native.backend._objects[token] is added
    assert calls[0]["glyph_data"] == {
        "name": "copy",
        "layers": [{"name": "Regular", "advanceWidth": 0}],
    }


def test_every_declared_glyph_layer_child_property_is_read_only(native, monkeypatch):
    """Unsupported properties may refuse; successful reads must never write."""

    def unavailable_tool(name, capability, **kwargs):
        raise UnsupportedCapability(
            "Tool not supplied by this native double", capability=capability
        )

    monkeypatch.setattr(native.backend, "_tool", unavailable_tool)
    font = native.font
    glyph = font.glyphs[0]
    layer = glyph.layers[0]
    import json

    def serialized():
        return json.dumps(
            {"glyph": native.glyph, "layer": native.layer},
            default=lambda value: {
                k: v
                for k, v in vars(value).items()
                if not callable(v) and k != "mask_calls"
            },
            sort_keys=True,
        )

    before = serialized()
    revision = native.backend._revision
    calls = list(native.calls)
    objects = [glyph, layer, *layer.paths, *(n for p in layer.paths for n in p.nodes)]
    read = set()
    for obj in objects:
        for cls in type(obj).__mro__:
            for name, descriptor in vars(cls).items():
                if name.startswith("_") or not isinstance(descriptor, property):
                    continue
                try:
                    getattr(obj, name)
                    read.add(name)
                except UnsupportedCapability:
                    # The native double deliberately implements only outline data.
                    pass
    assert {"name", "paths", "nodes", "position"} <= read
    assert native.backend._revision == revision
    assert native.calls == calls
    assert serialized() == before


def test_new_tab_text_does_not_persist_host_shape_activation(native, monkeypatch):
    shape = native.layer.shapes[0]
    shape.active = False
    native.glyph.layers = [native.layer]
    monkeypatch.setattr(native.backend, "_text_block", lambda fid: object())
    native.module.fgSymbol = lambda name: name
    native.module.fgSymbolList = list

    def request(symbols, mode):
        shape.active = True  # FontLab activates the displayed glyph's shape.

    native.module.flItems = lambda: NS(requestContent=request)
    native.backend.set_edit_glyphs(native.fid, (("A",),))
    assert shape.active is False, "navigation must not change saved glyph elements"


def test_unicode_write_uses_target_font_owned_record_not_bare_glyph_export(
    native, monkeypatch
):
    from test_issue106_round34 import isolate_unicode_backend

    isolate_unicode_backend(native, monkeypatch)

    class NativeGlyph:
        id, isValid, name = 20, True, "A"
        layers = ()

        @property
        def fgGlyph(self):
            pytest.fail("do not create a bare fontgate wrapper from flGlyph")

    target_record = NS(unicodes=[])
    native.backend._objects[native.gid] = NativeGlyph()
    monkeypatch.setattr(
        native.backend, "_fontgate_font", lambda package: {"A": target_record}
    )
    native.backend.set_glyph_unicodes(native.gid, ["0041"])
    assert target_record.unicodes == [65]


def test_generic_named_guide_with_properties_needs_no_native_reconstruction(native):
    class flObject:
        id, name, angle, isHint = 333, "baseline", 0, False
        centerPoint = NS(x=lambda: 10, y=lambda: 20)

    native.module.flGuideLine = lambda *args: pytest.fail(
        "generic wrapper already exposes guide properties"
    )
    guide = flObject()
    assert native.backend._guide_line(guide) is guide


def test_failed_guide_cast_refuses_precisely_instead_of_native_type_error(native):
    class flObject:
        id = 333

    def refuse(*args):
        raise TypeError("Error creating object of type flGuideLine")

    native.module.flGuideLine = refuse
    with pytest.raises(UnsupportedCapability) as error:
        native.backend._guide_line(flObject())
    assert error.value.capability == "GSGuide.nativeWrapper"


def test_native_master_guides_append_refuses_before_touching_unsafe_host_pointer(
    native,
):
    with pytest.raises(UnsupportedCapability) as error:
        native.backend.append_master_guide(native.mid, GuideInfo("", 10, 20))
    assert error.value.capability == "GSFontMaster.guides.append"
    assert not native.calls


def test_shape_clone_rebinds_component_tokens_before_transform(native):
    shape = native.layer.shapes[0]
    shape.isComponent = True
    shape.shapeData = NS(builder=NS())
    token = native.backend._register(
        (native.fid, "component", shape.id), shape, native.lid
    )
    native.backend._prepare_layer(native.lid)
    clone = native.backend._own_shape(native.lid, shape)
    assert native.backend._objects[token] is clone
    assert native.backend._object_keys[token] == (native.fid, "component", clone.id)
