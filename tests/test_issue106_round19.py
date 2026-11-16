# this_file: tests/test_issue106_round19.py
"""Host-free regressions for round nineteen's native boundary and API gaps."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_new_glyph_is_built_in_target_from_values_not_inserted_native_objects(
    native, monkeypatch
):
    native.package.fgId = 777
    native.package.masters = ["Regular"]
    original = native.glyph
    target = NS(id=1234, fgGlyphId=4321, name="destination", isValid=True)
    names = {"A": original}
    calls = []

    def forbidden(*args):
        pytest.fail("never construct/insert a detached or foreign native glyph")

    def build(name, capability, **values):
        assert name == "set_glyph"
        assert values["font_id"] == native.package.fgId
        assert values["glyph_data"]["name"] == "destination"
        assert values["create"] is True
        assert all(
            isinstance(value, (str, int, float, bool, dict, list))
            for value in values.values()
        )
        calls.append(values)
        names["destination"] = target

    native.module.flGlyph = forbidden
    native.module.flGlyph.updatedFgGlyphs = lambda: ()
    native.package.addGlyph = forbidden
    native.package.findName = names.get
    monkeypatch.setattr(
        native.backend,
        "_resolve_tool",
        lambda name, capability: lambda **kw: build(name, capability, **kw),
    )
    token = native.backend.append_glyph(native.fid, "destination")
    assert native.backend._objects[token] is target
    assert calls and original.name == "A"


def test_master_font_and_named_anchor_selector():
    from fontlab_glyport.model import GSAnchor, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    font = Model(FakeBackend()).font
    assert font.selectedFontMaster.font is font
    layer = font.glyphs[0].layers[0]
    layer.anchors = [GSAnchor("top", (7, 9))]
    assert layer.anchorForName_("top").position == (7, 9)
    assert layer.anchorForName_("missing") is None


def test_master_punctuation_does_not_make_special_layers():
    from dataclasses import replace

    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    info = backend.fonts["font"]
    backend.fonts["font"] = replace(
        info,
        masters=(
            replace(info.masters[0], name="Regular [UI label] {100}"),
            *info.masters[1:],
        ),
    )
    layer = Model(backend).font.glyphs[0].layers[0]
    assert layer.isMasterLayer
    assert not layer.isBracketLayer and not layer.isBraceLayer


def test_update_glyph_info_change_name_controls_canonicalization(owned_edit_info):
    with owned_edit_info._scope():
        from fontlab_glyport.model import GSGlyph

        keep = GSGlyph("uni0041")
        keep.updateGlyphInfo(changeName=False)
        assert keep.name == "uni0041" and keep.unicode == "0041"
        rename = GSGlyph("uni0041")
        rename.updateGlyphInfo(changeName=True)
        assert rename.name == "A" and rename.unicode == "0041"


@pytest.mark.parametrize(
    "code,script",
    [
        (0x0995, "bengali"),
        (0x0A15, "gurmukhi"),
        (0x0A95, "gujarati"),
        (0x0B15, "oriya"),
        (0x0B95, "tamil"),
        (0x0C15, "telugu"),
        (0x0C95, "kannada"),
        (0x0D15, "malayalam"),
        (0x0D9A, "sinhala"),
    ],
)
def test_indic_scripts_come_from_unicode_script_property(code, script):
    from fontlab_glyport.model.proxies import unicode_facts

    assert unicode_facts(f"{code:04X}")[3] == script


def test_kerning_dict_legacy_selector_has_same_data_as_property():
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    font = Model(FakeBackend()).font
    assert font.kerningDict() == font.kerning


def test_path_bezier_containment_and_layer_remove_shape_selector():
    from fontlab_glyport.model import GSNode, GSPath, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    path = GSPath(
        [GSNode((0, 0)), GSNode((100, 0)), GSNode((100, 100)), GSNode((0, 100))],
        closed=True,
    )
    assert path.bezierPath.containsPoint_((30, 11))
    assert not path.bezierPath.containsPoint_((101, 11))
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.paths = [path]
    layer.removeShape_(layer.paths[0])
    assert not layer.paths


def test_master_parameters_and_userdata_do_not_write_font_lib():
    from copy import deepcopy

    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    font = Model(backend).font
    original = deepcopy(backend.lib(font.id))
    master = font.masters[0]
    master.customParameters["paramArea"] = 400
    master.userData["rules"] = {"A": 1}
    assert backend.lib(font.id) == original
    other = Model(backend).font.masters[0]
    assert other.customParameters["paramArea"] == 400
    assert other.userData["rules"] == {"A": 1}


def test_handle_size_matches_glyphs_integer_default():
    from test_glyphsapp import _make

    module, _, _ = _make(store={"GSHandleSize": 2})
    assert module.Glyphs.handleSize == 2


def test_italic_sidebearings_use_deslanted_geometry():
    from math import radians, tan

    from fontlab_glyport.model import GSNode, GSPath, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    font = Model(backend).font
    layer = font.glyphs[0].layers[0]
    layer.components = []
    layer.paths = [
        GSPath(
            [GSNode((10, 0)), GSNode((110, 0)), GSNode((110, 200)), GSNode((10, 200))],
            closed=True,
        )
    ]
    layer.width = 120
    layer.master.italicAngle = 9
    assert layer.master.italicAngle == 9
    assert layer.LSB == pytest.approx(
        10 - tan(radians(9)) * (200 - layer.master.xHeight / 2)
    )
    layer.LSB = 20
    assert layer.LSB == pytest.approx(20)
    layer.RSB = 30
    assert layer.RSB == pytest.approx(30)


def test_property_reads_preserve_complete_fake_document_state():
    from copy import deepcopy

    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    font = Model(backend).font
    glyph = font.glyphs[0]
    layer = glyph.layers[0]
    layer.components = []  # The generic fake fixture has a deliberate A -> A cycle.
    objects = [
        glyph,
        layer,
        *layer.paths,
        *(n for path in layer.paths for n in path.nodes),
    ]
    document = lambda: {
        key: deepcopy(dict(value) if isinstance(value, dict) else value)
        for key, value in vars(backend).items()
        if not key.startswith("_") and key != "metric_reads"
    }
    before = document()
    for obj in objects:
        for cls in type(obj).__mro__:
            for name, descriptor in vars(cls).items():
                if name.startswith("_") or not isinstance(descriptor, property):
                    continue
                try:
                    getattr(obj, name)
                except UnsupportedCapability:
                    pass
    assert document() == before


def test_cubic_containment_and_holes_use_cocoa_winding_rule():
    from fontlab_glyport.drawing.cocoa_drawing import NSBezierPath

    path = NSBezierPath.bezierPath()
    path.moveToPoint_((0, 0))
    path.curveToPoint_controlPoint1_controlPoint2_((100, 0), (0, 100), (100, 100))
    path.closePath()
    assert path.containsPoint_((50, 30))
    assert not path.containsPoint_((50, 80))
    path = NSBezierPath.bezierPathWithRect_(((0, 0), (100, 100)))
    path.appendBezierPathWithRect_(((20, 20), (60, 60)))
    assert path.containsPoint_((50, 50))
    path.setWindingRule_(1)
    assert not path.containsPoint_((50, 50))


def test_copied_glyph_attachment_remaps_master_names_and_passes_only_values(
    monkeypatch,
):
    from dataclasses import asdict

    from fontlab_glyport.model import Model
    from fontlab_glyport.model.backend import PathInfo
    from fontlab_glyport.model.fake_backend import FakeBackend

    source = Model(FakeBackend()).font
    source.glyphs[0].layers[0].components = []
    copied = source.glyphs[0].copy()
    copied.layers[0].associatedMasterId = "source-master-token"
    destination_backend = FakeBackend()
    destination = Model(destination_backend).font
    del destination.glyphs[0]
    original_append = destination_backend.append_path
    received = []

    def append(layer_id, data):
        assert isinstance(data, PathInfo)
        assert data.id == "" and all(node.id == "" for node in data.nodes)
        received.append(asdict(data))
        return original_append(layer_id, data)

    monkeypatch.setattr(destination_backend, "append_path", append)
    attached = destination.glyphs.append(copied)
    assert attached.layers[0].associatedMasterId == destination.masters[0].id
    assert received
    assert (
        source.glyphs[0].layers[0].paths[0].nodes[0].position
        == attached.layers[0].paths[0].nodes[0].position
    )


def test_void_native_delete_result_is_verified_by_target_lookup(native):
    names = {"A": native.glyph}
    native.package.findName = names.get

    def delete(glyph):
        del names[glyph.name]
        # pyflPackageImpl::deleteGlyph has a void Python result.

    native.package.deleteGlyph = delete
    native.backend.remove_glyph(native.fid, native.gid)
    assert not native.backend.is_valid(native.gid)
    assert "A" not in names


def test_canonical_name_without_glyph_data_refuses_instead_of_ignoring_flag(
    monkeypatch,
):
    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model import GSGlyph

    def unavailable(*args, **kwargs):
        raise UnsupportedCapability(
            "Glyph database unavailable", capability="Glyphs.glyphInfoForName"
        )

    monkeypatch.setattr(
        "fontlab_glyport.glyphsapp.glyph_info.glyph_categories", unavailable
    )
    with pytest.raises(UnsupportedCapability) as error:
        GSGlyph("uni1F00").updateGlyphInfo(changeName=True)
    assert error.value.capability == "Glyphs.glyphInfoForName"


def test_unicode_scripts_property_takes_precedence_over_character_name(monkeypatch):
    from fontlab_glyport.model import proxies

    monkeypatch.setattr(
        proxies.unicodedata, "name", lambda *args: "LATIN MISLEADING NAME"
    )
    assert proxies.unicode_facts("0A15")[3] == "gurmukhi"


def test_native_master_parameters_are_stored_in_master_lib(native):
    native.package.master = "Regular"
    native.package.masterLib = {}
    native.package.packageLib = {"keep": "font-wide value"}
    master = native.font.masters[0]
    master.customParameters["paramDepth"] = 12
    master.userData["rules"] = {"A": 1}
    assert master.customParameters["paramDepth"] == 12
    assert native.package.masterLib["rules"] == {"A": 1}
    assert native.package.packageLib == {"keep": "font-wide value"}
