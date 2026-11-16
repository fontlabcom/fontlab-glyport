# this_file: tests/test_info_record_graph.py
"""Owned oracles for retained InfoLoading index mutation, not native execution."""

from copy import deepcopy

import pytest

from fontlab_glyport.model.custom_info import merge_custom
from fontlab_glyport.model.info_records import (
    GlyphInfoIndex,
    add_unicode,
    copy_record,
    new_record,
)


def record(name, codes=(), production=None, **fields):
    result = new_record(name)
    for code in codes:
        add_unicode(result, code)
    result._production_state.value = production
    result.__dict__.update(fields)
    return result


def test_new_record_has_known_fresh_defaults_without_shared_mutable_state():
    a, b = new_record("OwnedA"), new_record("OwnedB")
    assert (a.group, a.groupIdx, a.direction, a.case, a.desc) == (None, 0, 0, 0, None)
    assert (a.unicode, a.unicodes, a.altNames, a._locked) == (None, (), None, False)
    a._production_state.value = "OwnedProduction"
    assert b._production_state.value is None


@pytest.mark.parametrize("code", [None, "", "12345678", "\U00010000" * 4])
def test_add_unicode_rejects_nil_empty_and_eight_utf16_units(code):
    a = new_record("OwnedA")
    add_unicode(a, code)
    assert (a.unicode, a.unicodes) == (None, ())


def test_add_unicode_keeps_order_and_exact_spelling_without_replacing_first():
    a = new_record("OwnedA")
    for code in ["0041", "0042", "0041", "abcd", "ABCD", "1234567"]:
        add_unicode(a, code)
    assert a.unicode == "0041"
    assert a.unicodes == ("0041", "0042", "abcd", "ABCD", "1234567")


def test_record_copy_freezes_scalars_and_production_but_components_stay_shallow():
    child = new_record("OwnedChild")
    a = record(
        "OwnedA",
        ["0041"],
        group="",
        groupIdx=-3,
        direction=255,
        anchors=["top"],
        marks=["mark"],
        _component_records=[child],
    )
    a._locked = True
    b = copy_record(a)
    assert (b.group, b.groupIdx, b.direction, b._locked) == ("", -3, 255, False)
    assert (
        b._component_records == [child]
        and b._component_records is not a._component_records
    )
    assert b._component_records[0] is child
    a._production_state.value = "Changed"
    a.anchors.append("bottom")
    assert b._production_state.value is None and b.anchors == ["top"]


def test_base_indexes_primary_production_aliases_then_codes_and_legacy_last_wins():
    index = GlyphInfoIndex()
    a = record(
        "OwnedA",
        ["0041", "0042"],
        "ProdA",
        altNames=["Alias", "OwnedB"],
        unicodeLegacy="0043",
    )
    b = record("OwnedB", ["0042"], "uni0042", altNames=["ProdA"], unicodeLegacy="0041")
    index.append(a)
    index.append(b)
    assert index.raw_name("OwnedA") is a and index.raw_name("Alias") is a
    assert index.raw_name("OwnedB") is b and index.raw_name("ProdA") is b
    assert index.raw_name("uni0042") is None
    assert [index.raw_unicode(c) for c in ["0041", "0042", "0043"]] == [b, b, a]
    assert index.records == [a, b]


def test_local_raw_miss_returns_shared_object_and_own_override_is_distinct():
    shared = GlyphInfoIndex()
    shared_a = record("OwnedA", ["0041"], "Shared", desc="shared text")
    shared.append(shared_a)
    local = GlyphInfoIndex(shared=shared)
    assert local.raw_name("OwnedA") is shared_a
    assert local.raw_unicode("0041") is shared_a
    own = merge_custom(local, {"name": "OwnedA", "unicode": "0042"})
    assert own is not shared_a and own.desc is None
    assert local.raw_name("OwnedA") is own and local.raw_unicode("0041") is shared_a
    assert shared_a.desc == "shared text" and shared.raw_name("OwnedA") is shared_a


def test_switching_indexes_a_b_a_does_not_evict_record_or_production_cell():
    a, b = GlyphInfoIndex(), GlyphInfoIndex()
    ra, rb = record("OwnedA", ["0041"], altNames=["Alias"]), record("OwnedA", ["0041"])
    a.append(ra)
    b.append(rb)
    slot = ra._production_state
    slot.value = "FilledA"
    rb._production_state.value = "FilledB"
    assert a.raw_name("Alias") is a.raw_unicode("0041") is ra
    assert a.raw_name("OwnedA")._production_state is slot
    assert (
        slot.value == "FilledA"
        and b.raw_name("OwnedA")._production_state.value == "FilledB"
    )


def test_raw_plural_skips_missing_codes_without_synthesizing():
    index = GlyphInfoIndex()
    a = record("OwnedA", ["0041"])
    index.append(a)
    assert index.raw_unicodes(["1234", "0041"]) is a
    assert index.raw_unicodes(["1234", "5678"]) is None


def test_named_custom_merge_removes_index_codes_without_clearing_ordered_codes():
    index = GlyphInfoIndex()
    a = record(
        "OwnedA",
        ["0041", "0042"],
        "OldProd",
        altNames=["OldAlias"],
        desc="keep",
        group="Group",
        groupIdx=-3,
    )
    index.append(a)
    result = merge_custom(
        index,
        {
            "name": "OwnedA",
            "unicode": "0043",
            "production": "NewProd",
            "description": "ignored",
            "group": "ignored",
            "unicodeLegacy": "9999",
        },
    )
    assert result is a and index.records == [a]
    assert a.unicodes == ("0041", "0042", "0043") and a.unicode == "0041"
    assert index.raw_unicode("0041") is a and index.raw_unicode("0042") is None
    assert index.raw_unicode("0043") is None
    assert index.raw_name("OldAlias") is a and a.altNames is None
    assert index.raw_name("OldProd") is index.raw_name("NewProd") is a
    assert (a.desc, a.group, a.groupIdx, a.unicodeLegacy) == ("keep", "Group", -3, None)
    assert a._locked is True


@pytest.mark.parametrize(
    "attributes",
    [
        {"unicode": "0042"},
        {"unicode": "9999, 0042, 0043"},
        {"unicode": "9999", "unicode2": "0042"},
    ],
)
def test_custom_code_match_reuses_local_object_and_leaves_unselected_keys(attributes):
    index = GlyphInfoIndex()
    a = record("OldName", ["0041", "0042"], altNames=["Alias"])
    index.append(a)
    result = merge_custom(index, {"name": "NewName", **attributes})
    assert result is a and a.name == "NewName"
    assert index.raw_name("OldName") is None and index.raw_name("Alias") is a
    assert index.raw_name("NewName") is a and index.raw_unicode("0041") is a
    assert index.raw_unicode("0042") is None
    assert a.unicodes[:2] == ("0041", "0042") and index.records == [a]


def test_first_represented_multi_code_is_chosen_in_input_order():
    index = GlyphInfoIndex()
    a, b = record("OldA", ["0041"]), record("OldB", ["0042"])
    index.append(a)
    index.append(b)
    assert merge_custom(index, {"name": "New", "unicode": "9999, 0042, 0041"}) is b
    assert a.name == "OldA" and index.raw_name("OldA") is a


def test_short_unicode_attribute_does_not_split_on_bare_comma_or_short_delimiter():
    index = GlyphInfoIndex()
    a = merge_custom(index, {"name": "OwnedA", "unicode": "01, 02"})
    assert a.unicodes == ("01, 02",)
    b = merge_custom(index, {"name": "OwnedB", "unicode": "0041,0042"})
    assert b.unicodes == ()


def test_custom_unicode2_is_appended_but_only_first_code_is_finally_indexed():
    index = GlyphInfoIndex()
    a = merge_custom(
        index, {"name": "OwnedA", "unicode": "0041, 0042", "unicode2": "0043"}
    )
    assert a.unicodes == ("0041", "0042", "0043")
    assert index.raw_unicode("0041") is a
    assert index.raw_unicode("0042") is index.raw_unicode("0043") is None


def test_custom_scalar_omissions_preserve_existing_values_and_ignore_description():
    index = GlyphInfoIndex()
    a = record(
        "OwnedA",
        desc="keep",
        category="Letter",
        subCategory="Uppercase",
        script="latin",
        case=1,
        direction=4,
    )
    index.append(a)
    merge_custom(
        index,
        {
            "name": "OwnedA",
            "subCategory": "ignored",
            "description": "ignored",
            "direction": "VTR",
            "case": "other",
        },
    )
    assert (a.desc, a.category, a.subCategory, a.script, a.case, a.direction) == (
        "keep",
        "Letter",
        "Uppercase",
        "latin",
        5,
        12,
    )
    merge_custom(index, {"name": "OwnedA", "category": "Symbol", "subCategory": "Math"})
    assert (a.category, a.subCategory) == ("Symbol", "Math")


def test_custom_array_omission_empty_and_marks_precedence():
    index = GlyphInfoIndex()
    child = new_record("Child")
    a = record(
        "OwnedA",
        anchors=["top"],
        marks=["old"],
        _component_records=[child],
        _component_names=["Child"],
        altNames=["Alias"],
    )
    index.append(a)
    merge_custom(index, {"name": "OwnedA", "accents": "accent, other"})
    assert (a.anchors, a.marks, a._component_names) == (
        ["top"],
        ["accent", "other"],
        ["Child"],
    )
    assert a.altNames is None and index.raw_name("Alias") is a
    merge_custom(
        index,
        {
            "name": "OwnedA",
            "decompose": "",
            "anchors": "",
            "marks": "",
            "accents": "ignored",
        },
    )
    assert a._component_records is None and a._component_names is None
    assert a.anchors is None and a.marks is None


def test_present_deprecated_sets_true_even_when_text_says_false():
    index = GlyphInfoIndex()
    a = merge_custom(index, {"name": "OwnedA", "deprecated": "false"})
    assert a.deprecated is True
    merge_custom(index, {"name": "OwnedA"})
    assert a.deprecated is True


def test_custom_alias_split_is_exact_and_production_does_not_overwrite_key():
    index = GlyphInfoIndex()
    keeper = record("Keeper")
    index.append(keeper)
    a = merge_custom(
        index, {"name": "OwnedA", "production": "Keeper", "altNames": "One, Two,Three"}
    )
    assert index.raw_name("Keeper") is keeper
    assert index.raw_name("One") is a and index.raw_name("Two,Three") is a
    assert index.raw_name("Two") is None


def test_afii_alias_is_indexed_before_stored_production_rewrite():
    index = GlyphInfoIndex()
    a = merge_custom(
        index, {"name": "OwnedA", "unicode": "0041", "production": "afii12345"}
    )
    assert a._production_state.value == "uni0041"
    assert index.raw_name("afii12345") is a and index.raw_name("uni0041") is None


def test_duplicates_are_reported_after_mutation_without_rollback():
    index = GlyphInfoIndex()
    seen, duplicates = set(), set()
    a = merge_custom(
        index,
        {"name": "OwnedA", "production": "Same"},
        seen=seen,
        duplicates=duplicates,
    )
    b = merge_custom(
        index,
        {"name": "OwnedB", "production": "Same"},
        seen=seen,
        duplicates=duplicates,
    )
    assert seen == duplicates == {"Same"}
    assert index.records == [a, b] and index.raw_name("Same") is a
    assert b._production_state.value == "Same" and b._locked is True


def test_nameless_entry_is_ignored_without_touching_indexes_or_tracking_sets():
    index = GlyphInfoIndex()
    seen, duplicates = {"Prior"}, set()
    assert (
        merge_custom(index, {"production": "Ignored"}, seen=seen, duplicates=duplicates)
        is None
    )
    assert index.records == [] and seen == {"Prior"} and duplicates == set()


def test_owned_attribute_dictionaries_are_preserved():
    index = GlyphInfoIndex()
    attrs = {
        "name": "OwnedA",
        "unicode": "0041, 0042",
        "altNames": "Alias, Alias2",
        "anchors": "top, bottom",
        "marks": "mark",
        "case": "upper",
    }
    before = deepcopy(attrs)
    merge_custom(index, attrs)
    assert attrs == before


def test_nonempty_decompose_replaces_resolved_component_container():
    index = GlyphInfoIndex()
    child = new_record("Child")
    a = record("OwnedA", _component_records=[child])
    index.append(a)
    merge_custom(index, {"name": "OwnedA", "decompose": "New, Other"})
    assert a._component_names == ["New", "Other"]
    assert a._component_records is None


def test_shared_fallback_reads_shared_indexes_without_cascading_other_providers():
    other = GlyphInfoIndex()
    a = record("OwnedA", ["0041"])
    other.append(a)
    shared = GlyphInfoIndex(shared=other)
    local = GlyphInfoIndex(shared=shared)
    assert local.raw_name("OwnedA") is None
    assert local.raw_unicode("0041") is None


def test_raw_lookup_preserves_case_and_does_not_normalize_aliases_or_codes():
    index = GlyphInfoIndex()
    a = record("OwnedA", ["00aB"], altNames=["Alias"])
    index.append(a)
    assert index.raw_name("OwnedA") is a and index.raw_unicode("00aB") is a
    assert index.raw_name("owneda") is None and index.raw_unicode("00AB") is None


def test_custom_sort_mirror_and_empty_values_are_exact_and_omission_retains_them():
    index = GlyphInfoIndex()
    a = merge_custom(
        index,
        {
            "name": "OwnedA",
            "sortName": "",
            "sortNameKeep": "Keep",
            "mirror": "Other",
            "script": "",
        },
    )
    merge_custom(index, {"name": "OwnedA"})
    assert (a.sortName, a.sortNameKeep, a.mirror, a.script) == ("", "Keep", "Other", "")


def test_custom_category_does_not_clear_subcategory_when_omitted():
    index = GlyphInfoIndex()
    a = record("OwnedA", category="Letter", subCategory="Old")
    index.append(a)
    merge_custom(index, {"name": "OwnedA", "category": "Symbol"})
    assert a.category == "Symbol" and a.subCategory == "Old"


def test_named_merge_leaves_legacy_index_and_can_remove_another_records_code_key():
    index = GlyphInfoIndex()
    a = record("OwnedA", ["0041", "0042"], unicodeLegacy="0043")
    b = record("OwnedB", ["0042"])
    index.append(a)
    index.append(b)
    assert index.raw_unicode("0042") is b
    merge_custom(index, {"name": "OwnedA"})
    assert index.raw_unicode("0042") is None
    assert index.raw_unicode("0043") is a
    assert index.records == [a, b] and index.raw_name("OwnedB") is b


def test_copy_preserves_unknown_source_markers_without_inventing_production():
    a = new_record("OwnedA")
    a._production_state = None
    a._unavailable_fields = frozenset({"group", "direction"})
    a.unicharString = "cached value"
    b = copy_record(a)
    assert (
        b._production_state is None and b._unavailable_fields == a._unavailable_fields
    )
    assert b.unicharString is None
