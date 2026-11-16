# this_file: tests/test_info_manager_selection.py
"""Real manager front-door checks with owned records and public source limits."""

from copy import copy

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphsInfo
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.info_records import GlyphInfoIndex, add_unicode, new_record


def manager(name="A", code="0041", **fields):
    record = new_record(name)
    add_unicode(record, code)
    record.__dict__.update(fields)
    record._locked = True
    index = GlyphInfoIndex()
    index.append(record)
    return GSGlyphsInfo._from_index(index), record


def font_with(manager):
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = manager
    return font


def test_default_manager_init_and_two_document_fonts_share_real_singleton():
    shared = GSGlyphsInfo.sharedManager()
    assert GSGlyphsInfo() is shared
    assert Model(FakeBackend()).font.glyphsInfo() is shared
    assert Model(FakeBackend()).font.glyphsInfo() is shared


def test_two_fonts_resolve_same_encoding_against_their_own_document_manager():
    a, ra = manager(desc="A marker", case=1)
    b, rb = manager(desc="B marker", case=2)
    fa, fb = font_with(a), font_with(b)
    assert fa.glyphs["A"].glyphInfo.desc == "A marker"
    assert fb.glyphs["A"].glyphInfo.desc == "B marker"
    assert fa.glyphs["A"].glyphInfo.case == 1
    assert ra.desc == "A marker" and rb.desc == "B marker"


def test_raw_views_are_shared_by_name_alias_unicode_and_across_local_fallback():
    a, ra = manager(altNames=["Alias"])
    a._index.names["Alias"] = ra
    local = GSGlyphsInfo._from_index(GlyphInfoIndex(shared=a._index))
    first = a.infoFromDataForName_("A")
    assert first is a.infoFromDataForName_("Alias") is a.infoFromDataForUnicode_("0041")
    assert first is local.infoFromDataForName_("A")
    assert first.productionName is None
    assert a.glyphInfoForName_("Alias") is first
    assert first.productionName == "A"
    assert local.infoFromDataForUnicode_("0041").productionName == "A"


def test_manager_a_b_a_retains_raw_identity_and_filled_state_and_copy_freezes():
    a, _ = manager()
    b, _ = manager()
    raw = a.infoFromDataForName_("A")
    frozen = copy(raw)
    a.glyphInfoForName_("A")
    b.glyphInfoForName_("A")
    assert a.infoFromDataForName_("A") is raw and raw.productionName == "A"
    assert frozen.productionName is None


def test_resolved_plural_stops_at_first_synthesized_code_and_raw_plural_skips_it():
    a, _ = manager()
    assert a.infoFromDataForUnicodes_(["1234", "0041"]).name == "A"
    assert a.glyphInfoForUnicodes_(["1234", "0041"]).name == "uni1234"


def test_recursive_suffix_keeps_selected_manager_and_does_not_modify_base():
    a, record = manager(case=2, desc="Owned base", category="Letter", script="latin")
    info = a.glyphInfoForName_("A.sc")
    assert info.desc == "Owned base" and info.case == 3
    assert record.case == 2 and record.name == "A"


def test_parent_lookup_uses_metadata_components_not_real_outline_components():
    a, ra = manager(category="Letter", case=1)
    child = new_record("OwnedChild")
    child.desc = "metadata child"
    ra._component_records = [child]
    font = font_with(a)
    # FakeBackend's A has an outline component also named A: it is not metadata.
    info = font.glyphs["A"].glyphInfo
    assert [x.name for x in info.components] == ["OwnedChild"]
    assert info.components[0].desc == "metadata child"


def test_document_manager_replacement_keeps_retained_old_record_views():
    a, _ = manager(desc="Old")
    b, _ = manager(desc="New")
    font = font_with(a)
    old = font.glyphs["A"].glyphInfo
    font.parent._local_glyph_info = b
    assert font.glyphs["A"].glyphInfo.desc == "New"
    assert old.desc == "Old"


def test_failed_manager_scope_restores_prior_source_and_never_calls_other_manager():
    a, _ = manager(desc="A")
    b, _ = manager(desc="B")
    with a._scope():
        from fontlab_glyport.model.glyph_metadata import _direct

        assert _direct("A").desc == "A"
        with pytest.raises(RuntimeError), b._scope():
            assert _direct("A").desc == "B"
            raise RuntimeError("owned failure")
        assert _direct("A").desc == "A"


def test_unknown_public_group_is_explicit_but_known_description_still_works():
    info = GSGlyphsInfo.sharedManager().glyphInfoForName_("A")
    assert info.name == "A"
    with pytest.raises(UnsupportedCapability) as caught:
        _ = info.group
    assert caught.value.capability == "GSGlyphInfo.group.source"


def test_unlocked_compound_replacement_updates_retained_raw_view_production():
    m, source = manager(category="Letter", script="latin", case=1, sortName="A")
    source._locked = False
    raw = m.infoFromDataForName_("A")
    frozen = copy(raw)
    result = m.glyphInfoForName_("uni00410041")
    assert result.name == "A_A" and result.productionName == "A_A"
    assert raw.name == "A_A" and raw.productionName == "A_A"
    assert frozen.name == "A" and frozen.productionName is None


def test_synthesized_public_components_are_known_while_physical_recipes_remain_unknown():
    m = GSGlyphsInfo.sharedManager()
    with pytest.raises(UnsupportedCapability) as caught:
        _ = m.infoFromDataForName_("A").components
    assert caught.value.capability == "GSGlyphInfo.components.source"
    synthesized = m.glyphInfoForName_("uni00410042")
    assert [component.name for component in synthesized.components] == ["A", "B"]


def test_unlocked_pua_rebinding_preserves_raw_record_and_view_identity():
    m, source = manager(name="OwnedPUA", code="E001", category="Private Use")
    source._locked = False
    font = font_with(m)
    glyph = font.glyphs["A"]
    glyph.unicode = "E001"
    raw = m.infoFromDataForUnicode_("E001")
    assert glyph.glyphInfo is raw
    assert raw.name == "A" and source.name == "A"


def test_unlocked_additional_unicode_retains_identity_and_uses_utf16_append_bound():
    from fontlab_glyport.model.unicode_case import _append

    m, source = manager(category="Letter", script="latin", case=1)
    source._locked = False
    glyph = font_with(m).glyphs["A"]
    raw = m.infoFromDataForName_("A")
    assert glyph.glyphInfo is raw
    assert source.unicodes == ("0041", "0061")
    before = source.unicodes
    assert _append(source, "\U00010000" * 4) is source
    assert source.unicodes == before


def test_arabic_additional_lookup_uses_font_manager_while_presentation_uses_receiver():
    a, ra = manager(name="Owned-ar", code="0627", script="arabic", case=0)
    b, _ = manager(name="Owned-ar", code="0627", script="arabic", case=0)
    a_isol = new_record("Owned-ar.isol")
    add_unicode(a_isol, "FE90")
    a_isol.unicodeLegacy = "FE8E"
    a._index.append(a_isol)
    b_isol = new_record("Owned-ar.isol")
    add_unicode(b_isol, "FE8D")
    b._index.append(b_isol)
    font = font_with(b)
    glyph = font.glyphs["A"]
    glyph.unicode = "0627"
    glyph.name = "Owned-ar"
    glyph.script, glyph.case = "arabic", 0
    font.customParameters["Use Arabic Presentation Form Unicodes"] = True
    result = a.glyphInfoForGlyph_(glyph)
    assert result._resolved_record.unicodes == ("0627", "FE8D", "FE8E")
    assert ra.unicodes == ("0627",), "Locked receiver source remains unchanged"


@pytest.mark.parametrize(
    "helper,value",
    [
        ("glyphInfoForName", "A"),
        ("glyphInfoForName", 65),
        ("glyphInfoForUnicode", 65),
        ("glyphInfoForUnicode", "0041"),
    ],
)
def test_application_helpers_preserve_explicit_font_manager(helper, value):
    from types import SimpleNamespace

    from fontlab_glyport.glyphsapp import GSApplication

    m, _ = manager(desc="Explicit font marker")
    font = font_with(m)
    app = GSApplication(
        SimpleNamespace(font=font), object(), {}, None, lambda *args: None
    )
    assert getattr(app, helper)(value, font=font).desc == "Explicit font marker"
    assert app.currentDocument is font.parent
    assert app.glyphInfoForName("A") is GSGlyphsInfo.sharedManager().glyphInfoForName_(
        "A"
    )


def test_public_source_generation_switch_retains_canonical_views_and_cells(monkeypatch):
    from glyphsLib import glyphdata

    attrs_a = {
        "name": "OwnedA",
        "unicode": "0041",
        "category": "Letter",
        "script": "latin",
        "case": "upper",
        "description": "A",
        "altNames": "Alias",
    }
    attrs_b = {**attrs_a, "description": "B"}
    first = glyphdata.GlyphData({"OwnedA": attrs_a}, {}, {}, {"0041": attrs_a})
    second = glyphdata.GlyphData({"OwnedA": attrs_b}, {}, {}, {"0041": attrs_b})
    m = GSGlyphsInfo.sharedManager()
    monkeypatch.setattr(glyphdata, "GLYPHDATA", first)
    raw = m.infoFromDataForName_("OwnedA")
    assert raw.productionName is None
    m.glyphInfoForName_("Alias")
    monkeypatch.setattr(glyphdata, "GLYPHDATA", second)
    assert m.infoFromDataForName_("OwnedA").desc == "B"
    assert m.infoFromDataForName_("OwnedA").productionName is None
    monkeypatch.setattr(glyphdata, "GLYPHDATA", first)
    assert m.infoFromDataForUnicode_("0041") is raw
    assert raw.productionName == "OwnedA" and raw.desc == "A"
    assert "production" not in attrs_a and "production" not in attrs_b


def test_model_raw_getters_remain_stable_inside_other_manager_scopes():
    a, _ = manager(case=2, script="arabic", category="Mark", subCategory="Nonspacing")
    b, _ = manager(case=5, script="han", category="Symbol", subCategory="Math")
    glyph = font_with(b).glyphs["A"]
    before = (glyph.case, glyph.script, glyph.category, glyph.subCategory)
    for selected in [a, b, a]:
        with selected._scope():
            assert (
                glyph.case,
                glyph.script,
                glyph.category,
                glyph.subCategory,
            ) == before
    assert (glyph.case, glyph.script, glyph.category, glyph.subCategory) == before
    assert a.glyphInfoForGlyph_(glyph).case == 2
    assert b.glyphInfoForGlyph_(glyph).case == 5


@pytest.mark.parametrize("locked", [False, True])
def test_arabic_existing_isolated_record_with_nil_code_still_obeys_copy_boundary(
    locked,
):
    m, source = manager(name="Owned-ar", code="0627", script="arabic", case=0)
    source._locked = locked
    m._index.append(new_record("Owned-ar.isol"))
    glyph = font_with(m).glyphs["A"]
    glyph.unicode = "0627"
    glyph.name = "Owned-ar"
    raw = m.infoFromDataForName_("Owned-ar")
    result = m.glyphInfoForGlyph_(glyph)
    assert (result is raw) is (not locked)
    assert result._resolved_record.unicodes == ("0627",)
    assert source.unicodes == ("0627",)


@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize(
    "code, expected",
    [
        (None, ("0041",)),
        ("", ("0041",)),
        ("0041", ("0041",)),
        (
            "\U00010000\U00010000\U00010000x",
            ("0041", "\U00010000\U00010000\U00010000x"),
        ),
        ("\U00010000" * 4, ("0041",)),
    ],
)
def test_unicode_append_copy_and_utf16_bound_for_empty_duplicate_and_seven_eight_units(
    locked, code, expected
):
    from fontlab_glyport.model.unicode_case import _append

    source = new_record("Owned")
    add_unicode(source, "0041")
    source._locked = locked
    result = _append(source, code)
    assert (result is source) is (not locked)
    assert result.unicodes == expected
    if locked:
        assert source.unicodes == ("0041",)


def test_manager_nil_empty_short_and_unknown_raw_inputs_keep_real_miss_boundaries():
    m, _ = manager()
    assert m.glyphInfoForName_(None) is m.glyphInfoForName_("") is None
    assert m.glyphInfoForUnicode_(None) is m.glyphInfoForUnicode_("41") is None
    assert m.glyphInfoForUnicodes_([None, "41"]) is None
    assert m.infoFromDataForName_("OwnedMissing") is None
    assert m.infoFromDataForUnicode_("FFFF") is None
    assert m.infoFromDataForUnicodes_(["FFFF", "FFFE"]) is None
    with pytest.raises(UnsupportedCapability) as caught:
        m.glyphInfoForName_(42)
    assert caught.value.capability == "GSGlyphsInfo.name.inputType"
    assert isinstance(GSGlyphsInfo.applicationSupportPath(), str)


def test_direct_manager_can_resolve_detached_record_while_glyph_property_refuses():
    from fontlab_glyport.model import GSGlyph

    m, _ = manager()
    glyph = GSGlyph("A")
    assert m.glyphInfoForGlyph_(glyph).name == "A"
    with pytest.raises(UnsupportedCapability):
        _ = glyph.glyphInfo


def test_actual_glyphsapp_export_preserves_parent_manager_and_raw_constructor():
    from fontlab_glyport.glyphsapp import make_glyphsapp_module

    m, _ = manager(desc="Exported manager", case=2)
    font = font_with(m)
    module = make_glyphsapp_module(
        font._model, object(), defaults={}, error_sink=lambda text: None
    )
    assert module.GSGlyphsInfo is GSGlyphsInfo
    glyph = module.Glyphs.font.glyphs["A"]
    assert glyph.glyphInfo.desc == "Exported manager" and glyph.glyphInfo.case == 2
    assert module.GSGlyphInfo(glyph).case == glyph.case == 1
    assert module.Glyphs.glyphInfoForUnicode(65, font=font).desc == "Exported manager"
    assert module.Glyphs.currentDocument is font.parent


def test_smallcap_remap_unknown_physical_recipe_refuses_explicitly():
    m, source = manager(
        name="a", code="0061", category="Letter", script="latin", case=2
    )
    donor = new_record("A")
    add_unicode(donor, "0041")
    donor._unavailable_fields = frozenset({"components"})
    m._index.append(donor)
    info = m.glyphInfoForName_("a.sc")
    assert info.case == 3
    with pytest.raises(UnsupportedCapability) as caught:
        _ = info.components
    assert caught.value.capability == "GSGlyphInfo.components.source"
    assert source.name == "a" and source.case == 2


def test_smallcap_remap_establishes_known_components_for_owned_donor():
    m, source = manager(
        name="a", code="0061", category="Letter", script="latin", case=2
    )
    source._unavailable_fields = frozenset({"components"})
    donor = new_record("A")
    add_unicode(donor, "0041")
    m._index.append(donor)
    result = m.glyphInfoForName_("a.sc")
    assert result.case == 3 and result.components == []
    assert source.case == 2 and "components" in source._unavailable_fields


def test_local_loader_without_provider_is_explicit_gap_without_global_success():
    # The retained selection path establishes this method; resource/provider access stays held.
    from fontlab_glyport.errors import UnsupportedCapability

    m, _ = manager(desc="Owned")
    before = m.infoFromDataForName_("A")
    with pytest.raises(UnsupportedCapability) as caught:
        m.initWithLocalFile_("unused-owned-path")
    assert caught.value.capability == "GSGlyphsInfo.initialization.provider"
    assert m.infoFromDataForName_("A") is before


def test_unknown_smallcap_recipe_does_not_hide_independently_known_metadata():
    m, source = manager(
        name="a",
        code="0061",
        category="Letter",
        script="latin",
        case=2,
        desc="Known owned text",
    )
    donor = new_record("A")
    add_unicode(donor, "0041")
    donor._unavailable_fields = frozenset({"components"})
    m._index.append(donor)
    result = m.glyphInfoForName_("a.sc")
    assert (result.case, result.script, result.desc) == (3, "latin", "Known owned text")
    with pytest.raises(UnsupportedCapability) as caught:
        _ = result.components
    assert caught.value.capability == "GSGlyphInfo.components.source"
    assert source.case == 2 and source.name == "a"


def test_public_full_refresh_when_group_unknown_then_refuses_and_preserves_state():
    font = Model(FakeBackend()).font
    glyph = font.glyphs["A"]
    glyph.category = "Owned previous category"
    glyph.userData["owned.refusal"] = {"keep": [1]}
    before = (glyph.name, glyph.unicodes, glyph.category, dict(glyph.userData))
    with pytest.raises(UnsupportedCapability) as caught:
        glyph.updateGlyphInfo(changeName=False)
    assert caught.value.capability == "GSGlyphInfo.group.source"
    assert (
        glyph.name,
        glyph.unicodes,
        glyph.category,
        dict(glyph.userData),
    ) == before, "Unavailable public group must refuse before mutating any metadata"


def test_owned_parser_manager_when_fresh_rows_then_known_defaults_and_private_selection(
    owned_info_manager,
):
    selected = owned_info_manager()
    record = selected.infoFromDataForName_("A")
    assert (record.group, record.groupIdx, record.components) == (None, 0, None), (
        "Fresh parsed custom records establish nil/zero, not unknown public defaults"
    )
    font = font_with(selected)
    glyph = font.glyphs["A"]
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.category == "Letter" and glyph.group is None and glyph.groupIdx == 0
    assert font.glyphsInfo() is selected
    assert GSGlyphsInfo.sharedManager() is not selected, (
        "Fixture must not replace shared manager"
    )


@pytest.mark.parametrize("operation", ["rename", "refresh"])
def test_real_public_unknown_group_refuses_before_any_backend_write(
    operation, monkeypatch
):
    from copy import deepcopy

    font = Model(FakeBackend()).font
    glyph = font.glyphs["A"]
    glyph.category = "Owned previous category"
    before = (
        glyph.name,
        glyph.unicodes,
        deepcopy(glyph._case_state()),
        [g.name for g in font.glyphs],
    )

    def refuse(*args):
        pytest.fail("An unqualified public field reached a backend mutation")

    monkeypatch.setattr(font._model._backend, "set_lib", refuse)
    monkeypatch.setattr(font._model._backend, "rename_glyph", refuse)
    with pytest.raises(UnsupportedCapability) as caught:
        if operation == "rename":
            glyph.name = "acutecomb"
        else:
            glyph.updateGlyphInfo(changeName=False)
    assert caught.value.capability == "GSGlyphInfo.group.source"
    assert (
        glyph.name,
        glyph.unicodes,
        glyph._case_state(),
        [g.name for g in font.glyphs],
    ) == before


def test_real_public_group_index_stays_unknown_with_other_fields_readable():
    record = GSGlyphsInfo.sharedManager().infoFromDataForName_("A")
    assert record.name == "A" and record.category == "Letter"
    with pytest.raises(UnsupportedCapability) as caught:
        _ = record.groupIdx
    assert caught.value.capability == "GSGlyphInfo.groupIdx.source"


@pytest.mark.parametrize("owned_source", [False, True])
def test_manager_when_public_dependency_missing_then_typed_error_or_independent_owned_graph(
    monkeypatch,
    owned_source,
    owned_info_manager,
):
    import sys

    selected = owned_info_manager() if owned_source else GSGlyphsInfo.alloc().init()
    monkeypatch.setitem(sys.modules, "glyphsLib", None)
    if owned_source:
        assert selected.glyphInfoForName_("A").category == "Letter", (
            "Parsed owned graphs must remain independent of public resources"
        )
    else:
        with pytest.raises(UnsupportedCapability, match="glyphsLib") as caught:
            selected.glyphInfoForName_("A")
        assert caught.value.capability == "GSGlyph.categories.dependency"
