# this_file: tests/test_model_breadth.py
"""R020 model breadth: userData, customParameters and features (no native host)."""

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import GSCustomParameter, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.proxies import (
    CUSTOM_PARAMETER_PREFIX,
    FONT_USER_DATA_KEY,
)


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def test_user_data_when_font_glyph_layer_written_then_stored_in_native_libs(font):
    backend = font._model._backend
    glyph = font.glyphs["A"]
    layer = glyph.layers[0]
    assert dict(font.userData) == {} and "x" not in font.userData
    font.userData["coffee"] = True
    glyph.userData["note"] = {"a": [1, 2]}
    layer.userData["k"] = 3
    assert font.userData["coffee"] is True and dict(glyph.userData) == {
        "note": {"a": [1, 2]}
    }
    # Glyphs keys follow glyphsLib: font userData nests under one lib key;
    # glyph and layer userData are their own native libs.
    assert backend.libs["font"] == {FONT_USER_DATA_KEY: {"coffee": True}}
    assert backend.libs["glyph"] == {"note": {"a": [1, 2]}}
    assert backend.libs["layer"] == {"k": 3}
    del font.userData["coffee"]
    assert FONT_USER_DATA_KEY not in backend.libs["font"]
    with pytest.raises(KeyError):
        del glyph.userData["missing"]
    # Glyphs' userData answers None for a missing key (scripts test
    # `if glyph.userData["key"]:`, R049 palette-nib); deleting one raises.
    assert layer.userData["missing"] is None
    assert layer.userData.get("missing", 5) == 5


def test_user_data_when_returned_value_mutated_then_native_unchanged(font):
    font.glyphs["A"].userData["l"] = [1]
    value = font.glyphs["A"].userData["l"]
    value.append(2)
    assert font.glyphs["A"].userData["l"] == [1], "reads are snapshots, not views"


def test_user_data_when_key_not_string_then_type_error(font):
    with pytest.raises(TypeError):
        font.userData[1] = "x"


def test_custom_parameters_when_set_iterated_deleted_then_glyphslib_keys(font):
    backend = font._model._backend
    params = font.customParameters
    params["glyphOrder"] = ["a", "b"]
    params.append(GSCustomParameter("trademark", "TM"))
    assert backend.libs["font"][CUSTOM_PARAMETER_PREFIX + "glyphOrder"] == ["a", "b"]
    assert font.customParameters["glyphOrder"] == ["a", "b"]
    assert font.customParameters["missing"] is None
    names = [(p.name, p.value) for p in font.customParameters]
    assert names == [("glyphOrder", ["a", "b"]), ("trademark", "TM")]
    assert len(font.customParameters) == 2 and "trademark" in font.customParameters
    assert font.customParameters[1].name == "trademark"
    params["trademark"] = "TM2"
    assert font.customParameters["trademark"] == "TM2"
    del font.customParameters["glyphOrder"]
    assert [p.name for p in font.customParameters] == ["trademark"]
    del font.customParameters["glyphOrder"]
    assert len(font.customParameters) == 1, "Missing-name deletion is a no-op"


def test_custom_parameters_when_duplicate_appended_then_first_active_wins(font):
    font.customParameters["Filter"] = "A"
    font.customParameters.append(GSCustomParameter("Filter", "B"))
    assert font.customParameters["Filter"] == "A"
    font.customParameters[0].active = False
    assert font.customParameters["Filter"] == "B"


def test_custom_parameters_do_not_leak_into_user_data_and_back(font):
    font.customParameters["x"] = 1
    font.userData["y"] = 2
    assert dict(font.userData) == {"y": 2}
    assert [p.name for p in font.customParameters] == ["x"]


def test_custom_parameter_object_when_inactive_requested_then_state_changes():
    param = GSCustomParameter("a", 1)
    assert (param.name, param.value, param.active) == ("a", 1, True)
    param.active = False
    assert param.active is False, "Detached parameter active is mutable"


def test_features_and_prefixes_when_read_then_named_snapshots(font):
    backend = font._model._backend
    backend.feature_data["font"] = (
        "languagesystem DFLT dflt;",
        (("liga", "sub f i by fi;"),),
    )
    assert [f.name for f in font.features] == ["liga"]
    assert font.features["liga"].code == "sub f i by fi;"
    assert font.features["kern"] is None
    (prefix,) = font.featurePrefixes
    assert (prefix.name, prefix.code) == ("Prefix", "languagesystem DFLT dflt;")
    with pytest.raises(TypeError):
        font.features.append(None)


def test_feature_prefixes_when_prefix_empty_then_empty_collection(font):
    assert list(font.featurePrefixes) == [] and list(font.features) == []


def _axes_font():
    from fontlab_glyport.model.backend import AxisInfo, FontInfo, MasterInfo

    backend = FakeBackend()
    backend.fonts["font"] = FontInfo(
        "font",
        "Example",
        1000,
        (MasterInfo("master", "Regular", (400.0,)),),
        (AxisInfo("wght", "Weight", "wght", False),),
    )
    return backend, Model(backend).font


def test_axes_and_master_axis_values_when_read_then_glyphs_shapes():
    _, font = _axes_font()
    (axis,) = font.axes
    assert (axis.name, axis.axisTag, axis.hidden) == ("Weight", "wght", False)
    # axisId is a glyport identity that survives name and tag edits (R020 review).
    assert axis.id and axis.axisId == axis.id and font.axes[0] is axis
    assert font.axes["Weight"] is not None
    master = font.masters[0]
    assert master.axes == [400.0] and master.internalAxesValues == [400.0]
    with pytest.raises(UnsupportedCapability):
        font.axes.append(axis)


def test_instances_when_read_then_name_axes_exports():
    from fontlab_glyport.model.backend import InstanceInfo

    backend, font = _axes_font()
    backend.instance_data["font"] = (InstanceInfo("i0", "Bold", (700.0,), True),)
    (instance,) = font.instances
    assert (instance.name, instance.axes, instance.exports) == ("Bold", [700.0], True)
    assert instance.internalAxesValues == [700.0]
    assert font.instances["Bold"] is instance or font.instances["Bold"].name == "Bold"


def test_kerning_when_set_read_removed_then_glyphs_keys_and_ids(font):
    master_id = font.masters[0].id
    glyph_id = font.glyphs["A"].id
    assert font.kerning == {}
    assert font.kerningForPair(master_id, "A", "A") is None
    font.setKerningForPair(master_id, "A", "A", -40)
    font.setKerningForPair(master_id, "@MMK_L_T", "@MMK_R_A", -75)
    # Glyphs: glyph pairs are keyed by glyph id, groups by @MMK keys.
    assert font.kerning == {
        master_id: {glyph_id: {glyph_id: -40}, "@MMK_L_T": {"@MMK_R_A": -75}}
    }
    assert font.kerningForPair(master_id, "A", "A") == -40
    assert font.kerningForPair(master_id, "@MMK_L_T", "@MMK_R_A") == -75
    font.removeKerningForPair(master_id, "A", "A")
    assert font.kerningForPair(master_id, "A", "A") is None


def test_kerning_when_bad_group_side_or_direction_then_refused(font):
    master_id = font.masters[0].id
    with pytest.raises(ValueError):
        font.setKerningForPair(master_id, "@MMK_R_T", "A", -10)
    with pytest.raises(ValueError):
        font.setKerningForPair(master_id, "A", "@MMK_L_T", -10)
    with pytest.raises(UnsupportedCapability):
        font.setKerningForPair(master_id, "A", "A", -10, direction=1)
    with pytest.raises(UnsupportedCapability):
        font.kerningForPair(master_id, "A", "A", direction=2)


def test_guides_when_appended_then_live_proxies(font):
    from fontlab_glyport.model import GSGuide

    layer = font.glyphs["A"].layers[0]
    assert list(layer.guides) == []
    guide = layer.guides.append(GSGuide((10, 250), 0, "base"))
    assert guide is layer.guides[0]
    assert (guide.position, guide.angle, guide.name) == ((10, 250), 0, "base")
    guide.angle = 5
    assert layer.guides[0].angle == 5


def test_hints_when_read_then_types_and_orientation(font):
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.proxies import BOTTOMGHOST, STEM, TOPGHOST

    backend = font._model._backend
    layer = font.glyphs["A"].layers[0]
    backend.hint_data[layer.id] = (
        HintInfo(True, 100, 80, "h1", False),
        HintInfo(True, 700, -20, "", True),
        HintInfo(True, 0, 21, "", True),
        HintInfo(False, 50, 60, "v", False),
    )
    hints = list(layer.hints)
    assert [h.type for h in hints] == [STEM, TOPGHOST, BOTTOMGHOST, STEM]
    assert [h.horizontal for h in hints] == [True, True, True, False]
    assert hints[0].name == "h1" and hints[0].isPostScript and not hints[0].isTrueType
    with pytest.raises(UnsupportedCapability):
        _ = hints[0].originNode
    with pytest.raises(UnsupportedCapability):
        layer.hints.append(hints[0])


def test_classes_when_read_then_named_read_only_snapshots(font):
    from fontlab_glyport.model.backend import ClassInfo

    backend = font._model._backend
    assert list(font.classes) == []
    backend.class_data["font"] = (ClassInfo("uc", ("A", "B")),)
    (uc,) = font.classes
    assert (uc.name, uc.code, uc.automatic) == ("uc", "A B", False)
    assert font.classes["uc"].code == "A B" and font.classes["lc"] is None
    with pytest.raises(UnsupportedCapability):
        font.classes.append(uc)


def test_glyph_kerning_groups_when_classes_then_glyphs_sides(font):
    from fontlab_glyport.model.backend import KerningClassInfo

    backend = font._model._backend
    glyph = font.glyphs["A"]
    assert (glyph.leftKerningGroup, glyph.rightKerningGroup) == (None, None)
    # Glyphs: rightKerningGroup names the @MMK_L_ group (glyph on the pair's left).
    backend.kerning_class_data["font"] = (
        KerningClassInfo("A_first", ("A",), left=True, right=False),
        KerningClassInfo("A_second", ("A", "V"), left=False, right=True),
    )
    assert glyph.rightKerningGroup == "A_first"
    assert glyph.leftKerningGroup == "A_second"
    glyph.rightKerningGroup = "X"
    assert glyph.rightKerningGroup == "X"
    assert glyph.leftKerningGroup == "A_second"


def test_selection_when_node_selected_then_layer_selection_lists_it(font):
    layer = font.glyphs["A"].layers[0]
    node = layer.paths[0].nodes[0]
    assert node.selected is False and list(layer.selection) == []
    node.selected = True
    assert node.selected is True
    assert list(layer.selection) == [node]
    node.selected = False
    assert list(layer.selection) == []
    with pytest.raises(UnsupportedCapability):
        layer.selection.append(node)


def _two_glyph_font():
    from fontlab_glyport.model.backend import GlyphInfo, LayerInfo

    backend = FakeBackend()
    backend.glyph_lists["font"] = (
        GlyphInfo("glyph", "A", ("0041",)),
        GlyphInfo("g2", "a.sc", ()),
    )
    backend.layers["g2", "master"] = LayerInfo("layer2", "master", 400)
    return backend, Model(backend).font


def test_current_tab_when_none_then_none_and_new_tab_opens_one():
    backend, font = _two_glyph_font()
    assert font.currentTab is None
    tab = font.newTab("A/a.sc")
    assert backend.edit_texts == [("font", (("A", "a.sc"),))] and tab is not None
    assert font.currentTab is not None


def test_current_tab_when_open_then_text_and_layers_in_tab_master():
    from fontlab_glyport.model.backend import EditViewInfo

    backend, font = _two_glyph_font()
    backend.edit_views["font"] = EditViewInfo(
        (("A", "a.sc", "A"), ("a.sc",)), "a.sc", "Regular"
    )
    tab = font.currentTab
    # Glyphs text: characters for encoded glyphs, "/name " for the others.
    assert tab.text == "A/a.sc A\n/a.sc"
    assert [layer.width for layer in tab.layers] == [500, 400, 500, 400]
    assert tab.layers[0] is font.glyphs["A"].layers[0]
    # Glyphs: the edit view's selected layers; FontLab: the tab's active glyph.
    assert tab.selectedLayers == [font.glyphs["a.sc"].layers[0]]
    tab.text = "AA\n/a.sc A/a.sc/a.sc\n"
    assert backend.edit_texts[-1] == (
        "font",
        (("A", "A"), ("a.sc", "A", "a.sc", "a.sc"), ()),
    )
    del backend.edit_views["font"]  # the tab was closed in FontLab
    with pytest.raises(StaleNativeObject):
        _ = tab.text


def test_selected_layers_when_fontlab_has_current_glyphs_then_their_layers():
    backend, font = _two_glyph_font()
    assert font.selectedLayers == []
    backend.current_layer_data["font"] = (("a.sc", "Regular"), ("A", "Regular"))
    assert [layer.width for layer in font.selectedLayers] == [400, 500]


@pytest.mark.parametrize("text", ["AZ", "/b.sc"])
def test_tab_text_when_unknown_glyph_or_character_then_value_error(text):
    from fontlab_glyport.model.backend import EditViewInfo

    backend, font = _two_glyph_font()
    backend.edit_views["font"] = EditViewInfo((), None, "Regular")
    with pytest.raises(ValueError):
        font.currentTab.text = text
    assert backend.edit_texts == [], "nothing reaches FontLab"


def test_layer_name_bounds_sidebearings_when_read_then_glyphs_values(font):
    backend = font._model._backend
    layer = font.glyphs["A"].layers[0]
    assert layer.name == "Regular"
    backend.bounds_data[layer.id] = (40.0, -10.0, 300.0, 700.0)
    bounds = layer.bounds
    assert (bounds.origin.x, bounds.origin.y) == (40.0, -10.0)
    assert (bounds.size.width, bounds.size.height) == (300.0, 700.0)
    assert layer.LSB == 40.0 and layer.RSB == 500 - 340.0


def test_sidebearings_when_written_then_translate_and_width(font):
    backend = font._model._backend
    layer = font.glyphs["A"].layers[0]
    backend.bounds_data[layer.id] = (40.0, 0.0, 300.0, 700.0)
    layer.LSB = 60
    # Glyphs: LSB moves the outline and keeps RSB, so the width grows by 20.
    assert backend.transforms[-1] == (layer.id, (1, 0, 0, 1, 20.0, 0))
    assert layer.width == 520
    backend.bounds_data[layer.id] = (60.0, 0.0, 300.0, 700.0)
    layer.RSB = 100
    assert layer.width == 460


def test_layer_when_empty_then_zero_bounds_and_sidebearing_writes_accepted(font):
    layer = font.glyphs["A"].layers[0]
    bounds = layer.bounds
    assert (bounds.origin.x, bounds.size.width) == (0, 0)
    assert layer.LSB == 0 and layer.RSB == 500
    layer.LSB = 10
    assert layer.LSB == 0 and layer.width == 500


def test_apply_transform_when_six_values_then_backend_transform(font):
    backend = font._model._backend
    layer = font.glyphs["A"].layers[0]
    layer.applyTransform([1, 0, 0, 1, 5, 6])
    assert backend.transforms[-1] == (layer.id, (1.0, 0.0, 0.0, 1.0, 5.0, 6.0))
    with pytest.raises(ValueError):
        layer.applyTransform([1, 0, 0])


def test_anchor_position_when_written_on_stored_anchor_then_moved():
    from fontlab_glyport.model import GSAnchor

    font = Model(FakeBackend()).font
    layer = font.glyphs["A"].layers[0]
    anchor = layer.anchors.append(GSAnchor("top", (10, 20)))
    anchor.position = (30, 40)
    assert anchor.position == (30, 40) and layer.anchors["top"] is anchor
    anchor.x = 35
    assert anchor.position == (35, 40)


def test_selected_master_and_update_interface_calls(font):
    assert font.selectedFontMaster is font.masters[0]
    assert font.disableUpdateInterface() is None
    assert font.enableUpdateInterface() is None


# Review R-L1 fix round ----------------------------------------------------------


def test_glyphsapp_facade_exports_model_types_and_constants():
    from fontlab_glyport.glyphsapp import make_glyphsapp_module

    module = make_glyphsapp_module(None, object(), defaults={}, error_sink=print)
    for name in (
        "GSAxis",
        "GSInstance",
        "GSGuide",
        "GSHint",
        "GSCustomParameter",
        "GSClass",
        "GSFeature",
        "GSFeaturePrefix",
        "TOPGHOST",
        "STEM",
        "BOTTOMGHOST",
        "GSLTR",
    ):
        assert hasattr(module, name), name
    assert module.GSClass("uc", "A B").code == "A B"
    assert module.GSCustomParameter("x", 1).value == 1
    assert (module.GSAxis().name, module.GSInstance().exports) == ("", True)


def test_tab_proxy_when_another_tab_becomes_active_then_stale():
    from fontlab_glyport.model.backend import EditViewInfo

    backend, font = _two_glyph_font()
    backend.edit_views["font"] = EditViewInfo((("A",),), None, "Regular", "tab-1")
    tab = font.currentTab
    backend.edit_views["font"] = EditViewInfo((("a.sc",),), None, "Regular", "tab-2")
    with pytest.raises(StaleNativeObject):
        _ = tab.text
    with pytest.raises(StaleNativeObject):
        tab.text = "A"
    assert font.currentTab.text == "/a.sc"


@pytest.mark.parametrize(
    "lines, text",
    [
        ((("A", "space"),), "A "),
        ((("a.sc", "space"),), "/a.sc  "),
        ((("space", "space"),), "  "),
        ((("A",), ("space",)), "A\n "),
    ],
)
def test_tab_text_when_space_glyphs_then_kept_and_round_trip(lines, text):
    from fontlab_glyport.model.backend import EditViewInfo, GlyphInfo

    backend, font = _two_glyph_font()
    backend.glyph_lists["font"] += (GlyphInfo("g3", "space", ("0020",)),)
    backend.edit_views["font"] = EditViewInfo(lines, None, "Regular", "tab-1")
    tab = font.currentTab
    assert tab.text == text
    tab.text = text
    assert backend.edit_texts[-1] == ("font", lines)


def test_undo_group_when_body_and_end_both_fail_then_body_error_kept():
    font = Model(FakeBackend()).font
    backend = font._model._backend

    def failing_end():
        raise RuntimeError("end failed")

    backend.end_undo = failing_end
    with pytest.raises(ValueError, match="body"), font.undo_group("x"):
        raise ValueError("body")


def test_master_metrics_and_glyph_metrics_when_read_then_glyphs_tuple():
    from fontlab_glyport.model.backend import MasterMetrics

    backend = FakeBackend()
    backend.metrics["master"] = MasterMetrics(750, 700, -250, 500, 12)
    font = Model(backend).font
    gm = font.masters[0]
    assert (gm.ascender, gm.capHeight, gm.descender, gm.xHeight, gm.italicAngle) == (
        750,
        700,
        -250,
        500,
        12,
    )
    layer = font.glyphs["A"].layers[0]
    # Glyphs: (width, ascender, capHeight, descender, xHeight, italicAngle, vertWidth)
    assert layer.glyphMetrics() == (500, 750, 700, -250, 500, 12, None)
    assert layer.master.name == "Regular"
    assert backend.metric_reads == ["master"] * 6, "read on access, never in font_info"
    # R049 reporter (CJK Metrics): layer.ascender/descender are its master's.
    assert (layer.ascender, layer.descender) == (750, -250)


def test_glyph_export_metadata_when_read_then_glyphs_api(font):
    """ExportCSV's fields (R049 fileformat): ids, GlyphData classes, note,
    last change, vertical metrics and the character."""
    backend = font._model._backend
    glyph = font.glyphs["A"]
    layer = glyph.layers[0]
    backend.notes["glyph"] = "hello"
    backend.last_changes["glyph"] = "2026-10-15 17:52:11"
    assert glyph.glyphId() == 0 and glyph.export is True
    assert (glyph.category, glyph.subCategory, glyph.case, glyph.script) == (
        "Letter",
        None,
        1,
        "latin",
    )
    assert (glyph.note, glyph.lastChange, glyph.charString()) == (
        "hello",
        "2026-10-15 17:52:11",
        "A",
    )
    assert font.fontMasterForId_(font.masters[0].id) is not None
    assert font.fontMasterForId_("nope") is None
    assert layer.vertWidth is None, "no advance height set"
    # Glyphs: TSB from the vertical origin (ascender) to the top of the outline;
    # BSB from the bottom of the outline to origin - vertical width (default asc - desc).
    backend.bounds_data["layer"] = (0.0, -10.0, 100.0, 610.0)
    assert (layer.TSB, layer.BSB) == (800 - 600, -10 - (800 - 1000))
    backend.vertical_widths["layer"] = 900.0
    assert layer.vertWidth == 900.0 and layer.BSB == -10 - (800 - 900)


def test_unicode_facts_when_cjk_digit_or_none_then_glyphs_like_values():
    from fontlab_glyport.model.proxies import unicode_facts

    assert unicode_facts("4E00") == ("Letter", None, 0, "han")
    assert unicode_facts("0031") == ("Number", None, 0, None)
    assert unicode_facts("0061") == ("Letter", "Lowercase", 2, "latin")
    assert unicode_facts(None) == (None, None, 0, None)


def test_make_node_first_when_called_then_node_is_last_and_drafts_refuse(font):
    from fontlab_glyport.model import GSNode, GSPath

    layer = font.glyphs["A"].layers[0]
    layer.paths.append(
        GSPath([GSNode((0, 0)), GSNode((10, 0)), GSNode((10, 10))], closed=True)
    )
    path = layer.paths[-1]
    path.nodes[0].makeNodeFirst()
    assert [(n.x, n.y) for n in layer.paths[-1].nodes] == [(10, 0), (10, 10), (0, 0)]
    with pytest.raises(UnsupportedCapability):
        GSNode((1, 1)).makeNodeFirst()


def test_layer_parent_when_read_then_its_glyph(font):
    glyph = font.glyphs["A"]
    assert glyph.layers[0].parent is glyph
    assert font.selectedLayers == [] or font.selectedLayers[0].parent.name


def test_label_color_when_set_then_fontlab_mark_hue_and_back(font):
    """Glyphs label colour indices map to FontLab mark hues (0 = no mark):
    R049 filter-dialog sets layer.color = 8 (purple)."""
    backend = font._model._backend
    glyph = font.glyphs["A"]
    layer = glyph.layers[0]
    assert layer.color is None and glyph.color is None
    layer.color = 8
    assert backend.marks["layer"] == 280 and layer.color == 8
    glyph.color = 0
    assert backend.marks["glyph"] == 3 and glyph.color == 0
    layer.color = None
    assert backend.marks["layer"] == 0 and layer.color is None
    with pytest.raises(UnsupportedCapability):
        layer.color = 10  # Glyphs' light gray: FontLab marks are hues


def test_layer_paths_when_assigned_then_replaced(font):
    from fontlab_glyport.model import GSNode, GSPath

    layer = font.glyphs["A"].layers[0]
    layer.paths = [GSPath([GSNode((1, 1)), GSNode((2, 2))])]
    assert [[(n.x, n.y) for n in p.nodes] for p in layer.paths] == [[(1, 1), (2, 2)]]
    assert [type(s).__name__ for s in layer.shapes] == ["GSComponent", "GSPath"]
    layer.paths = None
    assert len(layer.paths) == 0


def test_glyph_tags_when_appended_removed_assigned_then_stored(font):
    """R049 palette-nib (EOD) tags glyphs: tags.append('EOD_Done'),
    'EOD_Done' in tags, tags.remove(...). FontLab flGlyph.tags is a list
    assigned whole (native probe glyport-matrix/probe_glyph_tags.json)."""
    backend = font._model._backend
    glyph = font.glyphs["A"]
    assert list(glyph.tags) == [] and "EOD_Done" not in glyph.tags
    glyph.tags.append("EOD_Done")
    glyph.tags.append("Review")
    assert "EOD_Done" in glyph.tags and backend.tags["glyph"] == ("EOD_Done", "Review")
    glyph.tags.remove("EOD_Done")
    assert list(glyph.tags) == ["Review"]
    with pytest.raises(ValueError):
        glyph.tags.remove("missing")
    glyph.tags = ["a", "b"]
    assert list(glyph.tags) == ["a", "b"]
    glyph.tags = None
    assert list(glyph.tags) == []


def test_tab_text_cursor_when_set_then_active_glyph_index_with_line_breaks():
    """R049 palette-nib (EOD) sets font.currentTab.textCursor. FontLab's cursor
    is the tab's active glyph (probe_text_cursor.json): the index counts one
    slot per glyph and per line break, as Glyphs' text does."""
    from fontlab_glyport.model.backend import EditViewInfo

    backend, font = _two_glyph_font()
    backend.edit_views["font"] = EditViewInfo(
        (("A", "a.sc"), ("A",)), "a.sc", "Regular", "tab-1", cursor=1
    )
    tab = font.currentTab
    assert tab.textCursor == 1
    tab.textCursor = 3  # "A", "a.sc", line break, "A"
    assert backend.edit_views["font"].cursor == 3 and tab.textCursor == 3
    with pytest.raises(ValueError):
        tab.textCursor = -1


def test_new_glyph_when_appended_then_same_object_attached_with_master_layers(font):
    """R049 palette-nib (EOD getBombComponent): GSGlyph(name) appended to
    font.glyphs becomes that font's glyph; its master layers take width and
    shapes; a GSComponent of it goes into another glyph's layer."""
    from fontlab_glyport.model import GSComponent, GSGlyph, GSNode, GSPath

    glyph = GSGlyph("_EOD.aBomb")
    assert glyph.name == "_EOD.aBomb"
    assert font.glyphs.append(glyph) is glyph
    assert font.glyphs["_EOD.aBomb"] is glyph
    assert len(glyph.layers) == len(font.masters)
    node = GSNode()
    node.position = (10, 20)
    node.type = "line"
    path = GSPath()
    path.nodes.append(node)
    path.nodes.append(GSNode((30, 40)))
    path.closed = True
    for layer in glyph.layers:
        layer.width = 1000
        layer.shapes = [path]
    assert [[(n.x, n.y) for n in p.nodes] for p in glyph.layers[0].paths] == [
        [(10, 20), (30, 40)]
    ]
    target = font.glyphs["A"].layers[0]
    component = target.shapes.append(GSComponent(glyph))
    assert component.componentName == "_EOD.aBomb"
    assert target.shapes[-1].componentName == "_EOD.aBomb"
    with pytest.raises(ValueError):
        font.glyphs.append(GSGlyph("_EOD.aBomb"))  # duplicate name
    with pytest.raises(ValueError):
        target.shapes.append(GSComponent("missing"))


def test_layer_bezier_paths_when_read_then_glyphs_segments_and_decomposed_components(
    font,
):
    """R049 reporter (CJK Metrics: layer.bezierPath) and custom-nsview
    (Waterfall: layer.completeBezierPath). A closed path starts at its last
    (on-curve) node; offcurves before a curve node are its controls;
    completeBezierPath adds components through their transform."""
    from fontlab_glyport.model import GSNode, GSPath

    layer = font.glyphs["A"].layers[0]
    layer.paths = [
        GSPath(
            [
                GSNode((100, 0), "line"),
                GSNode((100, 50), "offcurve"),
                GSNode((50, 100), "offcurve"),
                GSNode((0, 100), "curve"),
                GSNode((0, 0), "line"),
            ],
            closed=True,
        )
    ]
    elements = layer.bezierPath._elements
    assert elements == [
        ("move", (0.0, 0.0)),
        ("line", (100.0, 0.0)),
        ("curve", (100.0, 50.0), (50.0, 100.0), (0.0, 100.0)),
        ("line", (0.0, 0.0)),
        ("close",),
    ]
    # The fake's A has a component of A itself: refused, never recursing.
    with pytest.raises(ValueError):
        layer.completeBezierPath  # noqa: B018
    from fontlab_glyport.model import GSComponent, GSGlyph

    base = font.glyphs.append(GSGlyph("bar"))
    base.layers[0].shapes = [GSPath([GSNode((0, 0)), GSNode((10, 0))], closed=False)]
    user = font.glyphs.append(GSGlyph("user")).layers[0]
    user.shapes = [GSPath([GSNode((1, 1)), GSNode((2, 2))], closed=False)]
    user.shapes.append(GSComponent(base, (100, 5)))
    assert user.completeBezierPath._elements == [
        ("move", (1.0, 1.0)),
        ("line", (2.0, 2.0)),
        ("move", (100.0, 5.0)),
        ("line", (110.0, 5.0)),
    ]
    assert user.bezierPath._elements[:2] == [("move", (1.0, 1.0)), ("line", (2.0, 2.0))]
    layer.paths = None
    assert layer.bezierPath is None


def test_layer_anchor_mover_members_when_used_then_master_metrics_and_detached_copy(
    font,
):
    """R049 plain-model (mekkablue Anchor Mover): glyph(), isMasterLayer,
    metricForType_, associatedFontMaster(), and copyDecomposedLayer() whose
    transforms and bounds never touch the font."""
    pytest.importorskip("fontTools")

    from fontlab_glyport.model import GSAnchor, GSGlyph, GSNode, GSPath

    layer = font.glyphs.append(GSGlyph("plain")).layers[0]
    layer.width = 600
    layer.paths = [GSPath([GSNode((100, 0)), GSNode((300, 0)), GSNode((300, 500))])]
    layer.anchors.append(GSAnchor("top", (250, 700)))
    assert (
        layer.glyph() is layer.parent
        and layer.isMasterLayer
        and not layer.isSpecialLayer
    )
    assert layer.associatedFontMaster() is layer.master
    m = layer.master
    # GSMetricsType: Ascender 1, CapHeight 2, xHeight 4, Descender 7, Baseline 8, ItalicAngle 9
    assert [layer.metricForType_(t) for t in (1, 2, 4, 7, 8, 9)] == [
        m.ascender,
        m.capHeight,
        m.xHeight,
        m.descender,
        0,
        m.italicAngle,
    ]
    assert layer.metricForType_(5) is None  # mid height: no FontLab counterpart
    copy = layer.copyDecomposedLayer()
    copy.decomposeCorners()
    copy.applyTransform(
        (1, 0, 0.5, 1, 0, -100)
    )  # a skew, as Anchor Mover's italic undo
    assert (copy.width, copy.anchors["top"].x, copy.anchors["top"].y) == (600, 600, 600)
    bounds = copy.fastBounds()
    assert (
        bounds.origin.x,
        bounds.origin.y,
        bounds.size.width,
        bounds.size.height,
    ) == (100, -100, 450, 500)
    assert next((n.x, n.y) for n in layer.paths[0].nodes) == (100, 0), (
        "the font is untouched"
    )
    assert layer.anchors["top"].position == (250, 700)


def test_glyph_export_and_script_when_set_then_stored_in_libs(font):
    """R049 reporter (CJK Metrics) writes export = False, storeScript = True
    and script = 'han' on its guide glyph. FontLab 9 has no per-glyph export
    flag (probe_glyph_export.json): export is the UFO font lib list
    public.skipExportGlyphs; script/storeScript live in the glyph lib."""
    backend = font._model._backend
    glyph = font.glyphs["A"]
    assert glyph.export is True and glyph.script == "latin"  # derived until stored
    glyph.export = False
    assert backend.libs["font"]["public.skipExportGlyphs"] == ["A"]
    assert glyph.export is False
    glyph.export = True
    assert backend.libs["font"]["public.skipExportGlyphs"] == []
    glyph.storeScript = True
    glyph.script = "han"
    assert glyph.script == "han" and glyph.storeScript is True
    assert backend.libs["glyph"]["com.schriftgestaltung.Glyphs.script"] == "han"


def test_glyph_export_when_set_to_same_value_then_no_lib_write(font):
    """CJK Metrics writes the same values on every paint: no native writes."""
    backend = font._model._backend
    glyph = font.glyphs["A"]
    glyph.export, glyph.storeScript, glyph.script = False, True, "han"
    writes = []
    original = backend.set_lib
    backend.set_lib = lambda id, data: (writes.append(id), original(id, data))
    glyph.export, glyph.storeScript, glyph.script = False, True, "han"
    assert writes == []


def test_font_glyph_for_unicode_when_hex_then_glyph_or_none(font):
    """R049 custom-nsview (Waterfall): font.glyphForUnicode_('0020') after a
    glyphs[...] miss; unknown code points give None."""
    assert font.glyphForUnicode_("0041") is font.glyphs["A"]
    assert font.glyphForUnicode_("0041".lower()) is font.glyphs["A"]
    assert font.glyphForUnicode_("0020") is None


def test_layer_kerning_for_next_layer_when_pair_then_value_else_ns_not_found(font):
    """R049 custom-nsview (Waterfall's getKernValue): nextKerningForLayer_
    direction_ (Glyphs 3) and rightKerningForLayer_ (Glyphs 2) give the pair's
    kerning (exceptions, then groups), NSNotFound when there is none."""
    master_id = font.masters[0].id
    layer = font.glyphs["A"].layers[0]
    assert layer.nextKerningForLayer_direction_(layer, 0) == float(2**63)
    font.setKerningForPair(master_id, "A", "A", -40)
    assert layer.nextKerningForLayer_direction_(layer, 0) == -40
    assert layer.rightKerningForLayer_(layer) == -40
