# this_file: tests/test_glyph_group_direction.py
"""Six-field parent-aware overlays and distinct group/direction lifecycles."""

from copy import deepcopy

import pytest
from test_info_manager_selection import font_with, manager

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSGlyph


def test_raw_fresh_group_direction_defaults_and_independent_stored_flags():
    glyph = GSGlyph("Owned")
    assert (glyph.group, glyph.groupIdx, glyph.direction) == (None, 0, 0)
    assert glyph.storeGroup is glyph.storeDirection is False
    glyph.group, glyph.groupIdx, glyph.direction = "", -3, 12
    assert (glyph.group, glyph.groupIdx, glyph.direction) == ("", -3, 12)
    assert glyph.storeGroup is glyph.storeDirection is False


def test_group_store_toggle_never_resolves_or_resets_raw_fields():
    glyph = GSGlyph("Owned")
    glyph.group, glyph.groupIdx = "OwnedGroup", 7
    glyph.storeGroup = True
    glyph.storeGroup = False
    assert (glyph.group, glyph.groupIdx, glyph.storeGroup) == ("OwnedGroup", 7, False)


@pytest.mark.parametrize(
    "field,flag,raw,base",
    [
        ("case", "storeCase", 5, 1),
        ("group", "storeGroup", None, "BaseGroup"),
        ("script", "storeScript", "owned", "latin"),
        ("category", "storeCategory", "Owned", "Letter"),
        ("subCategory", "storeSubCategory", "Owned", "Uppercase"),
        ("direction", "storeDirection", 12, 4),
    ],
)
def test_each_of_six_flags_overlays_only_its_field_and_preserves_locked_source(
    field, flag, raw, base
):
    m, source = manager(
        case=1,
        group="BaseGroup",
        groupIdx=11,
        script="latin",
        category="Letter",
        subCategory="Uppercase",
        direction=4,
    )
    glyph = font_with(m).glyphs["A"]
    setattr(glyph, field, raw)
    assert getattr(glyph.glyphInfo, field) == base
    setattr(glyph, flag, True)
    info = glyph.glyphInfo
    assert getattr(info, field) == raw
    assert getattr(source, field) == base
    assert info.groupIdx == 11, "storeGroup never overlays the glyph's raw groupIdx"
    assert getattr(glyph, field) == raw


def test_group_and_direction_refresh_uses_selected_manager_and_couples_group_idx():
    m, _ = manager(
        group="NewGroup", groupIdx=-3, direction=4, category="Letter", case=1
    )
    glyph = font_with(m).glyphs["A"]
    glyph.group, glyph.groupIdx, glyph.direction = "Old", 7, 2
    glyph.updateGlyphInfo(False)
    assert (glyph.group, glyph.groupIdx, glyph.direction) == ("NewGroup", -3, 4)
    glyph.group, glyph.groupIdx, glyph.direction = "Stored", 8, 12
    glyph.storeGroup = glyph.storeDirection = True
    glyph.updateGlyphInfo(False)
    assert (glyph.group, glyph.groupIdx, glyph.direction) == ("Stored", 8, 12)


def test_direction_disable_resolves_selected_manager_without_resetting_group():
    m, source = manager(direction=4)
    glyph = font_with(m).glyphs["A"]
    glyph.group, glyph.groupIdx = "Keep", 7
    glyph.direction = 12
    glyph.storeDirection = True
    assert glyph.glyphInfo.direction == 12
    glyph.storeDirection = False
    assert (glyph.direction, glyph.storeDirection) == (4, False)
    assert (glyph.group, glyph.groupIdx, source.direction) == ("Keep", 7, 4)


def test_direction_reset_unavailable_source_refuses_before_any_state_change():
    m, source = manager()
    source._unavailable_fields = frozenset({"direction"})
    glyph = font_with(m).glyphs["A"]
    glyph.direction, glyph.storeDirection = 12, True
    before = deepcopy(glyph._case_state())
    with pytest.raises(UnsupportedCapability) as caught:
        glyph.storeDirection = False
    assert caught.value.capability == "GSGlyphInfo.direction.source"
    assert glyph._case_state() == before


def test_group_refresh_unavailable_source_refuses_before_other_metadata_or_codes_change():
    m, source = manager(case=2)
    source._unavailable_fields = frozenset({"group"})
    glyph = font_with(m).glyphs["A"]
    glyph.group = "Keep"
    before = (glyph.name, glyph.unicodes, deepcopy(glyph._case_state()))
    with pytest.raises(UnsupportedCapability) as caught:
        glyph.updateGlyphInfo(False)
    assert caught.value.capability == "GSGlyphInfo.group.source"
    assert (glyph.name, glyph.unicodes, glyph._case_state()) == before


def test_stored_group_protects_both_fields_from_unavailable_refresh_source():
    m, source = manager(case=2)
    source._unavailable_fields = frozenset({"group", "groupIdx"})
    glyph = font_with(m).glyphs["A"]
    glyph.group, glyph.groupIdx, glyph.storeGroup = "Keep", 7, True
    glyph.updateGlyphInfo(False)
    assert (glyph.group, glyph.groupIdx, glyph.case) == ("Keep", 7, 2)
    assert glyph.glyphInfo.group == "Keep"
    with pytest.raises(UnsupportedCapability):
        _ = glyph.glyphInfo.groupIdx


def test_keep_name_early_return_precedes_group_direction_overlays():
    m, _ = manager(group="Base", direction=4)
    glyph = font_with(m).glyphs["A"]
    glyph.category, glyph.group, glyph.direction = "Icon", "Raw", 12
    glyph.storeGroup = glyph.storeDirection = True
    info = glyph.glyphInfo
    assert (info.category, info.group, info.groupIdx, info.direction) == (
        "Icon",
        None,
        0,
        0,
    )


def test_unlocked_record_overlay_mutates_same_record_and_view():
    m, source = manager(group="Base", direction=4)
    source._locked = False
    raw = m.infoFromDataForName_("A")
    glyph = font_with(m).glyphs["A"]
    glyph.group, glyph.direction = "Raw", 12
    glyph.storeGroup = glyph.storeDirection = True
    assert glyph.glyphInfo is raw
    assert (source.group, source.direction) == ("Raw", 12)


@pytest.mark.parametrize(
    "field,valid",
    [("direction", [0, 1, 2, 4, 8, 12, 255]), ("groupIdx", [-32768, -3, 0, 7, 32767])],
)
def test_owned_integer_storage_preserves_valid_widths(field, valid):
    glyph = GSGlyph("Owned")
    for value in valid:
        setattr(glyph, field, value)
        assert getattr(glyph, field) == value


@pytest.mark.parametrize(
    "field,bad",
    [("direction", -1), ("direction", 256), ("groupIdx", -32769), ("groupIdx", 32768)],
)
def test_out_of_range_storage_refuses_without_wrapping(field, bad):
    glyph = GSGlyph("Owned")
    before = glyph._case_state()
    with pytest.raises(ValueError):
        setattr(glyph, field, bad)
    assert glyph._case_state() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("group", 42),
        ("group", object()),
        ("groupIdx", True),
        ("groupIdx", 0.5),
        ("direction", False),
        ("direction", 1.5),
        ("direction", "2"),
        ("direction", None),
    ],
)
def test_unqualified_scalar_types_refuse_before_mutating_owned_storage(field, value):
    glyph = GSGlyph("Owned")
    before = glyph._case_state()
    with pytest.raises(TypeError):
        setattr(glyph, field, value)
    assert glyph._case_state() == before


def test_group_flag_does_not_snapshot_field_and_repeated_value_is_noop():
    from fontlab_glyport.model.stored_glyph_fields import STORE_GROUP_KEY

    glyph = GSGlyph("Owned")
    glyph.storeGroup = False
    assert glyph._case_state() == {}
    glyph.storeGroup = True
    assert glyph._case_state() == {STORE_GROUP_KEY: True}
    glyph.storeGroup = True
    assert glyph._case_state() == {STORE_GROUP_KEY: True}


def test_detached_direction_reset_keeps_raw_value_and_flag_on_refusal():
    glyph = GSGlyph("Owned")
    glyph.direction, glyph.storeDirection = 12, True
    before = glyph._case_state()
    with pytest.raises(UnsupportedCapability) as caught:
        glyph.storeDirection = False
    assert caught.value.capability == "GSGlyph.storeDirection.detachedReset"
    assert glyph._case_state() == before
