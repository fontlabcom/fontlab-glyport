# this_file: tests/test_issue106_round20.py
"""Native history must refresh metadata indexes and retained logical handles."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model.backend import GlyphInfo


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("first", ["retained", "new_lookup", "old_lookup"])
def test_external_unicode_change_repairs_all_metadata_lookup_routes(
    native, monkeypatch, first
):
    marker, code = [4], ["0041"]
    native.glyph.currentHistoryState = lambda: marker[0]
    read = lambda token: GlyphInfo(native.gid, native.glyph.name, tuple(code))
    monkeypatch.setattr(native.backend, "glyphs", lambda fid: (read(native.gid),))
    monkeypatch.setattr(native.backend, "glyph_info", read, raising=False)
    font = native.font
    glyph = font.glyphs[0]
    assert glyph.unicode == "0041"
    assert font.glyphForUnicode_("0041") is glyph
    assert font.glyphs["0041"] is glyph
    code[:] = ["0042"]
    marker[0] = 5
    if first == "retained":
        assert glyph.unicode == "0042"
    elif first == "new_lookup":
        assert font.glyphForUnicode_("0042") is glyph
    else:
        assert font.glyphForUnicode_("0041") is None
    assert glyph.unicode == "0042"
    assert (
        font.glyphForUnicode_("0042")
        is font.glyphs["0042"]
        is font.glyphs["B"]
        is glyph
    )
    assert font.glyphForUnicode_("0041") is font.glyphs["0041"] is None


def test_retained_node_name_and_position_follow_native_undo(native):
    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    original = native.layer.shapes[0]
    original.contours[0].nodes()[0].name = "original"
    node = native.font.glyphs[0].layers[0].paths[0].nodes[0]
    assert node.name == "original"
    node.name = "edited"
    marker[0] = 5
    assert node.name == "edited"
    native.layer.shapes[:] = [original]
    marker[0] = 4
    assert node.name == "original"
    assert node.position == (10, 2)
    node.position = (30, 40)
    assert native.layer.shapes[0].contours[0].nodes()[0].x == 30


def test_retained_path_follows_original_contour_after_native_undo(native):
    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    original = native.layer.shapes[0]
    path = native.font.glyphs[0].layers[0].paths[0]
    path.nodes[0].x += 7
    marker[0] = 5
    assert path.nodes[0].x == 17
    native.layer.shapes[:] = [original]
    marker[0] = 4
    assert path.nodes[0].position == (10, 2)


def test_retained_anchor_reconciles_replacement_by_name(native):
    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    anchor = lambda identity, x: NS(
        id=identity, name="top", isValid=True, point=NS(x=lambda: x, y=lambda: 20)
    )
    native.layer.anchors[:] = [anchor(41000, 10)]
    retained = native.font.glyphs[0].layers[0].anchors["top"]
    assert retained.position == (10, 20)
    native.layer.anchors[:] = [anchor(41001, 70)]
    marker[0] = 5
    assert retained.position == (70, 20)


def test_aligned_width_is_a_method_not_a_boolean_property(native):
    layer = native.font.glyphs[0].layers[0]
    assert layer.hasAlignedWidth() is False


@pytest.mark.parametrize(
    "name",
    [
        "systemRedColor",
        "systemOrangeColor",
        "systemYellowColor",
        "systemGreenColor",
        "systemMintColor",
        "systemTealColor",
        "systemCyanColor",
        "systemBlueColor",
        "systemIndigoColor",
        "systemPurpleColor",
        "systemPinkColor",
        "systemBrownColor",
        "systemGrayColor",
        "quaternaryLabelColor",
        "controlBackgroundColor",
        "controlColor",
        "selectedControlColor",
        "selectedControlTextColor",
        "alternateSelectedControlTextColor",
        "selectedTextBackgroundColor",
        "placeholderTextColor",
        "gridColor",
    ],
)
def test_system_and_corpus_semantic_colors_construct_without_paint_context(name):
    from fontlab_glyport.drawing.cocoa_drawing import NSColor

    assert isinstance(getattr(NSColor, name)(), NSColor)


def test_instance_list_refreshes_after_native_population_with_constant_package_history(
    native,
):
    native.package.axes, native.package.instances = [], []
    assert list(native.font.instances) == []
    native.package.instances = [
        NS(
            name=name,
            location={},
            exportable=True,
            weight="Regular",
            weightValue=100,
            width="Normal",
        )
        for name in ("Light", "Regular", "Bold")
    ]
    assert [item.name for item in native.font.instances] == ["Light", "Regular", "Bold"]


def test_instance_export_refusal_explains_unsafe_interpolated_package():
    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model import GSInstance

    with pytest.raises(UnsupportedCapability, match="unregistered") as error:
        _ = GSInstance().interpolatedFont
    assert error.value.capability == "GSInstance.interpolatedFont"


def test_retained_component_follows_native_undo_in_writer_and_peer(native, monkeypatch):
    from test_issue106_round10 import peer_font

    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    original = type(native.layer.shapes[0])()
    original.isComponent = original.isComposite = True
    original.shapeData = NS(componentGlyph="A", builder=NS())
    original.transform.isAffine = lambda: True
    for name, value in zip(
        ("m11", "m12", "m21", "m22", "dx", "dy"), (1, 0, 0, 1, 0, 0)
    ):
        setattr(original.transform, name, lambda value=value: value)
    native.layer.shapes.append(original)
    layer = native.font.glyphs[0].layers[0]
    retained = layer.components[0]
    peer = peer_font(native, monkeypatch).glyphs[0].layers[0].components[0]
    assert retained.componentName == peer.componentName == "A"
    with native.font.undo_group("Edit"):
        native.backend._own_shape(layer._id, original)
        clone = native.layer.shapes[-1]
        clone.shapeData.componentGlyph = "Changed"
    marker[0] = 5
    assert retained.componentName == peer.componentName == "Changed"
    native.layer.shapes[-1] = original
    marker[0] = 4
    assert retained.componentName == peer.componentName == "A"
    assert native.backend._object(retained.id) is original


def test_deleted_retained_handle_refuses_with_typed_stale_error(native):
    from fontlab_glyport.errors import StaleNativeObject

    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    node = native.font.glyphs[0].layers[0].paths[0].nodes[0]
    assert node.x == 10
    native.layer.shapes.clear()
    marker[0] = 5
    with pytest.raises(StaleNativeObject):
        _ = node.position


def test_edit_text_index_observes_external_unicode_and_name_changes(
    native, monkeypatch
):
    from fontlab_glyport.model.proxies import GSEditViewController

    marker, code = [4], ["0041"]
    native.glyph.currentHistoryState = lambda: marker[0]
    read = lambda token: GlyphInfo(native.gid, native.glyph.name, tuple(code))
    monkeypatch.setattr(native.backend, "glyphs", lambda fid: (read(native.gid),))
    monkeypatch.setattr(native.backend, "glyph_info", read)
    tab = GSEditViewController(native.font, "unused")
    assert tab._glyph_lines("A/A") == (("A", "A"),)
    code[:] = ["0042"]
    native.glyph.name = "Renamed"
    marker[0] = 5
    assert tab._glyph_lines("B/Renamed") == (("Renamed", "Renamed"),)
    with pytest.raises(ValueError, match="No glyph"):
        tab._glyph_lines("A")


@pytest.mark.parametrize("size", [100, 2000])
def test_native_metadata_hits_validate_constant_work_without_relisting(
    native, monkeypatch, size
):
    counts = {"history": 0, "listings": 0}

    def history():
        counts["history"] += 1
        return 4

    infos = []
    for index in range(size):
        name, code = f"item{index}", 0x400 + index
        glyph = NS(
            id=70000 + index, isValid=True, name=name, currentHistoryState=history
        )
        token = native.backend._register(
            (native.fid, "glyph", glyph.id), glyph, native.fid
        )
        native.package.fgPackage[name] = NS(unicodes=[code])
        infos.append(GlyphInfo(token, name, (f"{code:04X}",)))

    def listing(fid):
        counts["listings"] += 1
        return tuple(infos)

    monkeypatch.setattr(native.backend, "glyphs", listing)
    glyph = native.font.glyphs[f"item{size - 1}"]
    counts["history"] = 0
    for _ in range(20):
        assert native.font.glyphs[f"item{size - 1}"] is glyph
        assert native.font.glyphForUnicode_(f"{0x400 + size - 1:04X}") is glyph
        assert glyph.unicode == f"{0x400 + size - 1:04X}"
    assert counts["listings"] == 1
    assert 60 <= counts["history"] <= 100, (
        "one marker per hit, independent of glyph count"
    )


def test_native_insertion_keeps_known_node_identity_ahead_of_slot_fallback(native):
    marker = [4]
    native.glyph.currentHistoryState = lambda: marker[0]
    path = native.font.glyphs[0].layers[0].paths[0]
    retained = path.nodes[0]
    assert retained.x == 10
    contour = native.layer.shapes[0].contours[0]
    contour._nodes.insert(0, type(contour._nodes[0])(99))
    marker[0] = 5
    assert path.nodes[0].x == 99
    assert path.nodes[1] is retained
    assert retained.x == 10
