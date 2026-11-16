# this_file: tests/test_kerning_writes.py
"""Live group and master replacement contracts, with unrelated-state sentinels."""

from copy import deepcopy
from dataclasses import replace

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import (
    FontInfo,
    GlyphInfo,
    KerningClassInfo,
    MasterInfo,
)
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def state():
    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
    )
    backend.glyph_lists["font"] = (
        GlyphInfo("glyph", "A", ()),
        GlyphInfo("vee", "V", ()),
    )
    backend.fonts["other"] = FontInfo(
        "other", "Sentinel", 1000, (MasterInfo("other-master", "Other"),)
    )
    backend.glyph_lists["other"] = (GlyphInfo("foreign", "Z", ()),)
    backend.kerning_class_data["font"] = (
        KerningClassInfo("first", ("A", "V"), left=True),
        KerningClassInfo("second", ("A", "V"), right=True),
    )
    for master in ("master", "bold"):
        backend.kerning_data["font", master] = {
            ("@MMK_L_first", "@MMK_R_second"): -80,
            ("A", "V"): -10,
        }
    backend.kerning_data["other", "other-master"] = {("Z", "Z"): -33}
    model = Model(backend)
    return backend, model.font


@pytest.mark.parametrize(
    "attribute,side", [("leftKerningGroup", "right"), ("rightKerningGroup", "left")]
)
@pytest.mark.parametrize("value", [None, "", "new"])
def test_group_assignment_changes_membership_all_masters_preserves_pairs_and_peers(
    state, attribute, side, value
):
    backend, font = state
    glyph = font.glyphs["A"]
    before_pairs = deepcopy(dict(backend.kerning_data))
    assert getattr(glyph, attribute)
    setattr(glyph, attribute, value)
    assert getattr(glyph, attribute) == (value or None)
    for master in font.masters:
        backend.set_current_master(font.id, master.id)
        groups = backend.kerning_classes(font.id)
        old = next(
            g for g in groups if g.name == ("first" if side == "left" else "second")
        )
        assert old.glyphs == ("V",)
        assert getattr(font.glyphs["V"], attribute) == old.name
        assert getattr(glyph, attribute) == (value or None)
    assert backend.kerning_data == before_pairs


def test_actual_reset_shape_clears_groups_pairs_all_masters_preserves_second_font(
    state,
):
    backend, font = state
    sentinel = deepcopy(backend.kerning_data["other", "other-master"])
    for glyph in font.glyphs:
        glyph.leftKerningGroup = None
        glyph.rightKerningGroup = None
    for master in font.masters:
        assert backend.kerning_classes(font.id, master.id), (
            "referenced empty classes retain pair keys until removal"
        )
        font.kerning[master.id] = {}
    for master in font.masters:
        backend.set_current_master(font.id, master.id)
        assert backend.kerning(font.id, master.id) == ()
        assert backend.kerning_classes(font.id) == ()
    assert backend.kerning_data["other", "other-master"] == sentinel
    assert font.familyName == "Example" and [g.name for g in font.glyphs] == ["A", "V"]


def test_master_mapping_replacement_resolves_glyph_ids_and_classes_and_is_live(state):
    backend, font = state
    mapping = font.kerning
    other_master = deepcopy(backend.kerning_data["font", "bold"])
    mapping["master"] = {"glyph": {"vee": -23.5}, "@MMK_L_first": {"@MMK_R_second": 0}}
    assert backend.kerning_data["font", "master"] == {
        ("A", "V"): -23.5,
        ("@MMK_L_first", "@MMK_R_second"): 0,
    }
    assert backend.kerning_data["font", "bold"] == other_master
    assert mapping["master"]["glyph"]["vee"] == -23.5
    mapping["master"] = mapping["master"]
    assert mapping == font.kerningDict()
    with pytest.raises(UnsupportedCapability):
        mapping["master"]["glyph"]["vee"] = 42
    with pytest.raises(UnsupportedCapability):
        del mapping["master"]["glyph"]["vee"]
    with pytest.raises(UnsupportedCapability):
        del mapping["master"]


@pytest.mark.parametrize("value", [3, False, [], {}, " ", "@bad", " x", "x\x00"])
def test_group_invalid_values_refused_before_mutation(state, value):
    backend, font = state
    before = deepcopy(dict(backend.kerning_class_data))
    with pytest.raises((TypeError, ValueError)):
        font.glyphs["A"].leftKerningGroup = value
    assert backend.kerning_class_data == before


@pytest.mark.parametrize("key", ["missing", "other-master", "bold", "empty"])
@pytest.mark.parametrize("operation", ["getitem", "get", "contains"])
def test_master_mapping_missing_reads_preserve_mapping_semantics(state, key, operation):
    backend, font = state
    mapping = font.kerning
    if key == "bold":
        backend.fonts["font"] = replace(
            backend.fonts["font"], masters=(MasterInfo("master", "Regular"),)
        )
    elif key == "empty":
        key = "bold"
        backend.kerning_data["font", key] = {}
    if operation == "getitem":
        with pytest.raises(KeyError) as error:
            mapping[key]
        assert error.value.args == (key,), "missing reads must identify the key"
    elif operation == "get":
        default = {}
        assert mapping.get(key, default) is default, "return the exact default"
    else:
        assert key not in mapping, "missing and empty masters must be absent"


@pytest.mark.parametrize("key", ["master", "missing", "other-master"])
@pytest.mark.parametrize("operation", ["getitem", "get", "contains"])
def test_master_mapping_reads_validate_retained_font_lifetime(state, key, operation):
    backend, font = state
    mapping = font.kerning
    backend.fonts.pop("font")
    with pytest.raises(StaleNativeObject):
        if operation == "getitem":
            mapping[key]
        elif operation == "get":
            mapping.get(key, {})
        else:
            _ = key in mapping


@pytest.mark.parametrize(
    "master,error",
    [
        ("missing", ValueError),
        ("other-master", ValueError),
        (1, TypeError),
        (None, TypeError),
    ],
)
def test_master_assignment_rejects_missing_foreign_and_invalid_master(
    state, master, error
):
    backend, font = state
    before = deepcopy(dict(backend.kerning_data))
    with pytest.raises(error):
        font.kerning[master] = {}
    assert backend.kerning_data == before


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"missing": {"vee": -2}},
        {"foreign": {"vee": -2}},
        {"glyph": {"vee": float("nan")}},
        {"glyph": {"vee": float("inf")}},
        {"glyph": {"vee": True}},
        {"glyph": {"vee": "-4"}},
        {"glyph": []},
        {1: {}},
        {"@MMK_R_second": {"vee": -2}},
        {"glyph": {"@MMK_L_first": -2}},
        {"@MMK_L_missing": {"vee": -2}},
    ],
)
def test_invalid_mapping_is_fully_preflighted(state, value):
    backend, font = state
    before = deepcopy(dict(backend.kerning_data))
    with pytest.raises((TypeError, ValueError, UnsupportedCapability)):
        font.kerning["master"] = value
    assert backend.kerning_data == before


def test_two_sided_class_refuses_independent_membership_change_before_writes(state):
    backend, font = state
    backend.kerning_class_data["font"] = (
        KerningClassInfo("both", ("A", "V"), True, True),
    )
    with pytest.raises(UnsupportedCapability):
        font.glyphs["A"].leftKerningGroup = None
    assert backend.kerning_class_data["font"][0].glyphs == ("A", "V")


def test_overlap_clear_removes_every_membership_without_touching_other_side(state):
    backend, font = state
    backend.kerning_class_data["font"] += (
        KerningClassInfo("overlap", ("A",), left=True),
    )
    font.glyphs["A"].rightKerningGroup = None
    assert font.glyphs["A"].rightKerningGroup is None
    assert font.glyphs["A"].leftKerningGroup == "second"
    assert all("A" not in g.glyphs for g in backend.kerning_classes(font.id) if g.left)


def test_stale_font_and_glyph_cannot_mutate_kerning(state):
    backend, font = state
    glyph, mapping = font.glyphs["A"], font.kerning
    backend.glyph_lists["font"] = (GlyphInfo("vee", "V", ()),)
    with pytest.raises(StaleNativeObject):
        glyph.leftKerningGroup = None
    backend.fonts.pop("font")
    with pytest.raises(StaleNativeObject):
        mapping["master"] = {}


def test_new_group_name_cannot_overwrite_an_opentype_class(state):
    from fontlab_glyport.model.backend import ClassInfo

    backend, font = state
    backend.class_data[font.id] = (ClassInfo("new", ("V",)),)
    before = deepcopy(dict(backend.kerning_class_data))
    with pytest.raises(UnsupportedCapability):
        font.glyphs["A"].leftKerningGroup = "new"
    assert backend.kerning_class_data == before


def test_moving_to_existing_group_preserves_names_order_pairs_and_other_members(state):
    backend, font = state
    backend.kerning_class_data["font"] += (
        KerningClassInfo("target", ("V",), left=True),
    )
    before = deepcopy(dict(backend.kerning_data))
    font.glyphs["A"].rightKerningGroup = "target"
    for master in font.masters:
        groups = backend.kerning_classes(font.id, master.id)
        assert [g.name for g in groups] == ["first", "second", "target"]
        assert groups[0].glyphs == ("V",) and groups[2].glyphs == ("V", "A")
    assert backend.kerning_data == before


def test_unchanged_two_sided_membership_and_repeated_clear_are_idempotent(state):
    backend, font = state
    backend.kerning_class_data[font.id] = (
        KerningClassInfo("both", ("A", "V"), True, True),
    )
    before = backend.revision(font.id)
    font.glyphs["A"].leftKerningGroup = "both"
    assert backend.revision(font.id) == before
    assert (
        font.glyphs["A"].leftKerningGroup
        == font.glyphs["A"].rightKerningGroup
        == "both"
    )


@pytest.mark.parametrize("direction", [1, 2, 3])
def test_group_writes_do_not_enable_non_ltr_pair_methods(state, direction):
    _, font = state
    font.glyphs["A"].rightKerningGroup = "new"
    for method, args in (
        (font.kerningForPair, ()),
        (font.setKerningForPair, (-10,)),
        (font.removeKerningForPair, ()),
    ):
        with pytest.raises(UnsupportedCapability):
            method("master", "A", "V", *args, direction=direction)
