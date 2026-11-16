# this_file: tests/test_compound_integration.py
"""Owned caller/state oracles for positional and metadata integration."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.glyphsapp import GSApplication
from fontlab_glyport.model import glyph_metadata as gm
from fontlab_glyport.model.compound_metadata import (
    _base_text,
    compose_names,
    copy_record,
)


@pytest.fixture
def owned(monkeypatch):
    glyphdata.get_glyph("A")

    def install(rows):
        names = {row["name"]: deepcopy(row) for row in rows}
        data = glyphdata.GlyphData(
            names,
            {},
            {},
            {row["unicode"]: row for row in names.values() if row.get("unicode")},
        )
        monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
        return GSApplication(
            SimpleNamespace(font=None), object(), {}, None, lambda *args: None
        ), data

    return install


def arabic_rows():
    return [
        {
            'name': "beh-ar",
            'unicode': "0628",
            'category': "Letter",
            'script': "arabic",
            'production': "uni0628",
        },
        {
            'name': "alef-ar",
            'unicode': "0627",
            'category': "Letter",
            'script': "arabic",
            'production': "uni0627",
        },
        {
            'name': "beh-ar.init", 'unicodeLegacy': "FE91", 'category': "Letter", 'script': "arabic"
        },
        {
            'name': "beh-ar.medi", 'unicodeLegacy': "FE92", 'category': "Letter", 'script': "arabic"
        },
        {
            'name': "alef-ar.fina",
            'unicodeLegacy': "FE8E",
            'category': "Letter",
            'script': "arabic",
        },
    ]


@pytest.mark.parametrize(
    "suffix,components",
    [
        ("", ["beh-ar.init", "alef-ar.fina"]),
        (".fina", ["beh-ar.medi", "alef-ar.fina"]),
        (".init", ["beh-ar.init", "alef-ar.fina"]),
        (".medi", ["beh-ar.medi", "alef-ar.fina"]),
    ],
)
def test_arabic_caller_when_position_changes_then_replaces_components_after_saved_production(
    owned, suffix, components
):
    app, data = owned(arabic_rows())
    before = deepcopy(data.names)
    result = app.glyphInfoForName("uni06280627" + suffix)
    assert result.name == "beh_alef-ar" + suffix
    assert result.productionName == "uni06280627" + suffix
    assert [record.name for record in result.components] == components
    assert result.unicode is None and result.unicodeLegacy is None
    assert [record.productionName for record in result.components] == [None, None], (
        "Raw alternate hits must not fill production"
    )
    assert data.names == before


@pytest.mark.parametrize(
    "suffix,expected",
    [("subs", 4), ("sups", 4), ("sinf", 4), ("subs.ss01", 0), ("pc", 0), ("pcap", 0)],
)
def test_compound_case_when_exact_global_string_then_uses_composer_rule(
    owned, suffix, expected
):
    app, _ = owned(
        [
            {'name': "A", 'unicode': "0041", 'category': "Number", 'script': "latin"},
            {'name': "B", 'unicode': "0042", 'category': "Letter", 'script': "latin"},
        ]
    )
    assert app.glyphInfoForName("uni00410042." + suffix).case == expected


def test_distinct_aliases_when_converging_then_component_identity_is_canonical(owned):
    app, _ = owned(
        [
            {'name': "A", 'unicode': "0041", 'category': "Letter"},
            {'name': "B", 'unicode': "0042", 'category': "Letter"},
            {'name': "C", 'altNames': "A,B", 'category': "Letter", 'script': "latin"},
        ]
    )
    result = app.glyphInfoForName("uni00410042")
    assert [row.name for row in result.components] == ["C", "C"]
    assert result.components[0] is result.components[1]


def test_filtered_bases_when_recursive_wrapper_then_preserves_all_original_suffix_slots(
    owned,
):
    rows = [
        {'name': "ka-deva", 'unicode': "0041", 'category': "Letter", 'script': "devanagari"},
        {'name': "halant-deva", 'unicode': "0042", 'category': "Mark", 'script': "devanagari"},
        {'name': "ga-deva", 'unicode': "0043", 'category': "Letter", 'script': "devanagari"},
        {'name': "k-deva", 'category': "Letter", 'script': "devanagari"},
    ]
    owned(rows)
    result = compose_names(["ka-deva.alt", "halant-deva.tail", "ga-deva.x"], ["ss01"])
    assert result.name == "k_ga-deva.alt_tail_x.ss01"
    assert len(result._component_records) == 1
    assert result._component_records[0].name == "k_ga-deva.alt_tail_x"


def test_ligature_anchors_when_at_delimiter_then_expands_anchor_major_without_mutating_source(
    owned,
):
    owned(
        [
            {
                'name': "A",
                'unicode': "0041",
                'category': "Letter",
                'script': "latin",
                'anchors': "top, bottom@accent, odd@x@y",
            },
            {'name': "B", 'unicode': "0042", 'category': "Letter", 'script': "latin"},
        ]
    )
    before = gm._direct("A")
    result = compose_names(["A", "B"])
    assert result.anchors == [
        "top_1",
        "top_2",
        "bottom_1@accent",
        "bottom_2@accent",
        "odd_1@x@y",
        "odd_2@x@y",
    ]
    assert before.anchors == ["top", "bottom@accent", "odd@x@y"]
    assert result.anchors is not before.anchors


@pytest.mark.parametrize(
    "category,expected", [("Mark", None), ("Letter", ["_nukta_1", "_nukta_2"])]
)
def test_nukta_when_after_ligature_expansion_then_copies_nullable_donor_fields(
    owned, category, expected
):
    owned(
        [
            {
                'name': "A",
                'unicode': "0041",
                'category': category,
                'script': "latin",
                'anchors': "_nukta",
                'marks': "OLD",
            },
            {
                'name': "B",
                'unicode': "0042",
                'category': "Letter",
                'script': "latin",
                'marks': "OWNER",
            },
        ]
    )
    result = compose_names(["A", "B"])
    assert result.anchors == expected
    assert result.marks == (["OWNER"] if category == "Mark" else ["OLD"])


@pytest.mark.parametrize(
    "suffix,expected,keep",
    [
        (None, "SA_SB", "SA_SB"),
        (["ss01"], "ss01.SA_SB", "SA_SB.ss01"),
        (["ss01", "liga"], "ss01.SA_SB", "SA_SB.ss01"),
    ],
)
def test_sorting_when_global_suffix_then_captures_raw_sort_and_ignores_silent_token(
    owned, suffix, expected, keep
):
    owned(
        [
            {
                'name': "A",
                'unicode': "0041",
                'category': "Letter",
                'script': "latin",
                'sortName': "SA",
            },
            {
                'name': "B",
                'unicode': "0042",
                'category': "Letter",
                'script': "latin",
                'sortName': "SB",
            },
        ]
    )
    result = compose_names(["A", "B"], suffix)
    assert (result.sortName, result.sortNameKeep) == (expected, keep)


def test_unichar_when_primary_and_arabic_legacy_then_caches_legacy_override():
    row = gm._record(
        "Owned", unicode="0627", unicodeLegacy="FE8D", script="arabic", production=None
    )
    assert _base_text(row) == "\ufe8d" and row.unicharString == "\ufe8d"
    assert (row.unicode, row.unicodeLegacy) == ("0627", "FE8D")


def test_copy_when_metadata_containers_and_cache_then_detaches_only_containers_and_resets_cache():
    row = gm._record("A", unicode="0041", production=None)
    component = gm._record("B", production=None)
    row.anchors, row.marks, row._component_records, row.unicharString = (
        ["top"],
        ["M"],
        [component],
        "old",
    )
    result = copy_record(row)
    assert result.anchors == row.anchors and result.anchors is not row.anchors
    assert result.marks == row.marks and result.marks is not row.marks
    assert (
        result._component_records is not row._component_records
        and result._component_records[0] is component
    )
    assert result.unicharString is None and row.unicharString == "old"


def test_alias_when_canonical_suffix_exists_then_reenters_before_shared_fill_and_retains_empty_list(
    owned,
):
    app, _ = owned(
        [
            {
                'name': "A",
                'altNames': "Alias",
                'unicode': "0041",
                'category': "Letter",
                'script': "latin",
            },
            {'name': "A.alt", 'category': "Mark", 'script': "greek", 'production': "PALT"},
        ]
    )
    before = app.glyphInfoForUnicode("0041")
    result = app.glyphInfoForName("Alias.alt")
    assert (result.name, result.productionName, result.category, result.script) == (
        "A.alt.",
        "PALT.",
        "Mark",
        "greek",
    )
    assert before.productionName is None, (
        "Canonical pending-token hit precedes ordinary shared fill"
    )


def test_final_script_when_seed_tag_maps_then_overrides_only_after_body_stages(owned):
    owned(
        [
            {'name': "owner-deva", 'unicode': "0041", 'category': "Letter", 'script': "latin"},
            {'name': "B", 'unicode': "0042", 'category': "Letter", 'script': "greek"},
        ]
    )
    result = compose_names(["owner-deva", "B"])
    assert result.script == "devanagari" and result.name == "owner_B-deva"
    assert [row.name for row in result._component_records] == ["owner-deva", "B"]


@pytest.mark.parametrize("script,expected", [(None, "ownedtag"), ("latin", "latin")])
def test_generic_suffix_when_script_nil_then_adopts_unknown_literal_tag_only(
    owned, script, expected
):
    owned([{'name': "owner-ownedtag", 'category': "Letter", 'script': script}])
    assert gm.name_info("owner-ownedtag.alt").script == expected


def test_final_arabic_language_mapping_when_initial_latin_then_does_not_retroactively_position(
    owned,
):
    owned(
        [
            {'name': "owner-ar", 'unicode': "0041", 'category': "Letter", 'script': "latin"},
            {'name': "B", 'unicode': "0042", 'category': "Letter", 'script': "latin"},
        ]
    )
    result = compose_names(["owner-ar", "B"])
    assert result.script == "arabic"
    assert [row.name for row in result._component_records] == ["owner-ar", "B"]


def test_later_arabic_script_when_adopted_then_positions_before_base_text(owned):
    owned(
        [
            {'name': "A", 'unicode': "0041", 'category': "Letter"},
            {'name': "beh-ar", 'unicode': "0628", 'category': "Letter", 'script': "arabic"},
        ]
    )
    result = compose_names(["A", "beh-ar"])
    assert result.script == "arabic" and [
        row.name for row in result._component_records
    ] == ["A.init", "beh-ar.fina"]
