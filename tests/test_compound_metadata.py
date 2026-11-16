# this_file: tests/test_compound_metadata.py
"""Owned compound controls from the retained build4108 field/state contract."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.glyphsapp import GSApplication


@pytest.fixture
def owned(monkeypatch):
    glyphdata.get_glyph("A")

    def install(rows):
        names = {r["name"]: deepcopy(r) for r in rows}
        data = glyphdata.GlyphData(
            names, {}, {}, {r["unicode"]: r for r in names.values() if r.get("unicode")}
        )
        monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
        app = GSApplication(
            SimpleNamespace(font=None), object(), {}, None, lambda *args: None
        )
        return app, data

    return install


def letters(**first):
    rows = [
        {'name': "A", 'unicode': "0041", 'category': "Letter", 'script': "latin"},
        {'name': "B", 'unicode': "0042", 'category': "Letter", 'script': "latin"},
    ]
    rows[0].update(first)
    return rows


def test_compound_when_shared_fill_then_later_component_observes_only_its_own_fill(
    owned,
):
    app, data = owned(letters())
    before = deepcopy(
        (data.names, data.alternative_names, data.production_names, data.unicodes)
    )
    a, b = app.glyphInfoForUnicode("0041"), app.glyphInfoForUnicode("0042")
    result = app.glyphInfoForName("uni00410042")
    assert (result.name, result.productionName, result.unicode) == ("A_B", "A_B", None)
    assert (result.category, result.subCategory, result.script, result.case) == (
        "Letter",
        "Ligature",
        "latin",
        0,
    )
    assert [c.name for c in result.components] == ["A", "B"]
    assert (a.productionName, b.productionName) == ("A", None), (
        "Only first exact-name lookup fills"
    )
    assert result.components[1].productionName is None
    app.glyphInfoForName("B")
    assert result.components[1].productionName == "B", (
        "Shallow component observes shared later fill"
    )
    assert result.productionName == "A_B", (
        "Final production is a detached stored scalar"
    )
    assert (
        data.names,
        data.alternative_names,
        data.production_names,
        data.unicodes,
    ) == before, "Mutable adapters must preserve all public source dictionaries"


def test_compound_when_repeated_indexed_record_then_component_positions_keep_alias_identity(
    owned,
):
    app, _ = owned(letters())
    result = app.glyphInfoForName("uni00410041")
    assert result.name == "A_A" and result.productionName == "A_A"
    assert len(result.components) == 2 and result.components[0] is result.components[1]
    copied = result.components
    copied.clear()
    assert len(result.components) == 2, "Components getter returns its own container"


@pytest.mark.parametrize(
    "raw,expected", [(None, "A"), ("", ""), ("A", "A"), ("Other", "Other")]
)
def test_compound_when_first_raw_production_varies_then_only_nil_is_filled(
    owned, raw, expected
):
    app, _ = owned(letters(production=raw))
    first = app.glyphInfoForUnicode("0041")
    result = app.glyphInfoForName("uni00410042")
    assert first.productionName == expected
    assert result.productionName == ((expected or "A") + "_B")


@pytest.mark.parametrize(
    "reverse,expected", [(False, "uniFFFF0042"), (True, "uni0042FFFF")]
)
def test_compound_when_helpers_mix_then_raw_records_drive_legacy_fallback(
    owned, reverse, expected
):
    app, _ = owned(letters(production="uniFFFF"))
    query = "uni00420041" if reverse else "uni00410042"
    assert app.glyphInfoForName(query).productionName == expected


def test_compound_when_one_legacy_conversion_missing_then_preserves_mixed_separators(
    owned,
):
    rows = letters(production="uniFFFF")
    rows[1].pop("unicode")
    rows[1].update(unicodeLegacy="0042", production="PB")
    app, _ = owned(rows)
    assert app.glyphInfoForName("uni00410042").productionName == "uni0041_PB"


def test_compound_when_production_suffixes_then_accumulates_reverse_component_order(
    owned,
):
    rows = letters(production="PA.x")
    rows[1]["production"] = "PB.y"
    app, _ = owned(rows)
    result = app.glyphInfoForName("uni00410042")
    assert result.productionName == "PA_PB.y.x"
    assert [c.productionName for c in result.components] == ["PA.x", "PB.y"]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("uni00410042.ss01", "PA_PB.y.x.ss01"),
        ("uni00410042.ss01.liga", "PA_PB.y.x.ss01.liga"),
    ],
)
def test_compound_when_component_and_global_suffixes_mix_then_global_follows_reversed_parts(
    owned, query, expected
):
    rows = letters(production="PA.x")
    rows[1]["production"] = "PB.y"
    app, _ = owned(rows)
    assert app.glyphInfoForName(query).productionName == expected


@pytest.mark.parametrize("length,expected", [(61, None), (62, "uni00410042")])
def test_compound_when_production_utf16_length_crosses_62_then_rebuilds_raw_legacies(
    owned, length, expected
):
    rows = letters(production="P" * (length - 2))
    rows[1]["production"] = "Q"
    app, _ = owned(rows)
    assert app.glyphInfoForName("uni00410042").productionName == (
        expected or "P" * (length - 2) + "_Q"
    )


def test_compound_when_long_rebuild_cannot_convert_then_keeps_existing_value(owned):
    rows = letters(production="P" * 60)
    rows[1].pop("unicode")
    rows[1].update(unicodeLegacy="0042", production="Q")
    app, _ = owned(rows)
    assert app.glyphInfoForName("uni00410042").productionName == "P" * 60 + "_Q"


def test_compound_when_name_alias_overrides_decoded_name_then_resolves_names_again(
    owned,
):
    rows = letters() + [
        {'name': "C", 'altNames': "A", 'category': "Mark", 'script': "greek", 'production': "PC"}
    ]
    app, _ = owned(rows)
    result = app.glyphInfoForName("uni00410042")
    assert (result.name, result.category, result.script) == ("C_B", "Mark", "greek")
    assert [c.name for c in result.components] == ["C", "B"]


def test_compound_when_exact_whole_query_and_derived_name_exist_then_only_query_preempts(
    owned,
    owned_info_manager,
    monkeypatch,
):
    rows = letters() + [{'name': "A_B", 'category': "Mark", 'production': "Wrong"}]
    app, _ = owned(rows)
    from fontlab_glyport.glyphsapp import GSGlyphsInfo

    monkeypatch.setattr(GSGlyphsInfo, "_shared", owned_info_manager(rows))
    assert app.glyphInfoForName("uni00410042").productionName == "A_B"
    assert app.glyphInfoForName("A_B").productionName == "Wrong"
    # A nonempty recipe whose only token is absent finalizes to an actual empty
    # array. Empty/missing custom decompose instead retains native nil storage.
    rows.append(
        {
            "name": "uni00410042",
            "category": "Mark",
            "production": "ExactWinner",
            "decompose": "glyportOwnedMissingPhysicalComponent",
        }
    )
    app, _ = owned(rows)
    selected = owned_info_manager(rows)
    monkeypatch.setattr(GSGlyphsInfo, "_shared", selected)
    assert selected.infoFromDataForName_("glyportOwnedMissingPhysicalComponent") is None
    assert selected.glyphInfoForName_("glyportOwnedMissingPhysicalComponent") is None
    selected.updateComponentsInfos()
    result = app.glyphInfoForName("uni00410042")
    assert result.productionName == "ExactWinner" and result.components == []


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ({"category": "Mark"}, {}, ("Mark", None, "latin")),
        ({"subCategory": "Matra"}, {}, ("Letter", "Matra", "latin")),
        ({"script": None}, {"script": "greek"}, ("Letter", "Ligature", "greek")),
        ({}, {"category": "Mark"}, ("Letter", None, "latin")),
        ({"script": "owned"}, {"category": "Mark"}, ("Letter", "Composition", "owned")),
        ({}, {"subCategory": "Halfform"}, ("Letter", "Conjunct", "latin")),
    ],
)
def test_compound_when_ordered_fields_then_preserves_seed_and_exact_count_rules(
    owned, first, second, expected
):
    rows = letters()
    rows[0].update(first)
    rows[1].update(second)
    app, _ = owned(rows)
    result = app.glyphInfoForName("uni00410042")
    assert (result.category, result.subCategory, result.script) == expected


@pytest.mark.parametrize(
    "token,case", [("ss01", 0), ("sc", 3), ("smcp", 3), ("c2sc", 3)]
)
def test_compound_when_global_token_consumed_then_keeps_one_nested_unsuffixed_component(
    owned, token, case
):
    app, _ = owned(letters())
    result = app.glyphInfoForName("uni00410042." + token)
    assert result.name == "A_B." + token and result.productionName == "A_B." + token
    assert result.case == case and result.unicode is None
    assert len(result.components) == 1 and result.components[0].name == "A_B"
    assert [c.name for c in result.components[0].components] == ["A", "B"]


@pytest.mark.parametrize("token", ["liga", "hlig", "dlig", "rlig"])
def test_compound_when_silent_ligature_suffix_then_appends_once_after_normal_suffix(
    owned, token
):
    app, _ = owned(letters())
    result = app.glyphInfoForName("uni00410042.ss01." + token)
    assert result.name == "A_B.ss01." + token
    assert result.productionName == "A_B.ss01." + token
    assert len(result.components) == 1 and result.components[0].name == "A_B"


@pytest.mark.parametrize("encoded", [False, True])
def test_compound_when_base_text_empty_then_legacy_clear_is_conditional(owned, encoded):
    rows = letters()
    for row in rows:
        row["unicodeLegacy"] = row["unicode"]
        if not encoded:
            row.pop("unicode")
    app, _ = owned(rows)
    result = app.glyphInfoForName("uni00410042")
    assert result.unicode is None
    assert result.unicodeLegacy == (None if encoded else "0041")
    assert app.glyphInfoForName("uni00410042.ss01").unicodeLegacy is None


@pytest.mark.parametrize("token", ["1", "+-", "1.2.3"])
def test_compound_when_global_token_is_native_numeric_then_components_remain_flat(
    owned, token
):
    app, _ = owned(letters())
    result = app.glyphInfoForName("uni00410042." + token)
    assert result.name == "A_B." + token
    assert [c.name for c in result.components] == ["A", "B"]


@pytest.mark.parametrize(
    "stored,expected", [("😀" * 29 + "P", None), ("😀" * 30, "uni00410042")]
)
def test_compound_when_supplementary_production_then_length_limit_counts_utf16_units(
    owned, stored, expected
):
    rows = letters(production=stored)
    rows[1]["production"] = "Q"
    app, _ = owned(rows)
    assert app.glyphInfoForName("uni00410042").productionName == (
        expected or stored + "_Q"
    )


@pytest.mark.parametrize(
    "names,expected",
    [
        (["ka-deva", "halant-deva"], "k-deva"),
        (["ra-deva", "halant-deva"], "reph-deva"),
        (["halant-deva", "ra-deva"], "rakar-deva"),
    ],
)
def test_compound_when_indic_names_filter_then_caller_resolves_surviving_record(
    owned, names, expected
):
    rows = [
        {'name': names[0], 'unicode': "0041", 'category': "Letter", 'script': "devanagari"},
        {'name': names[1], 'unicode': "0042", 'category': "Mark", 'script': "devanagari"},
        {
            'name': expected,
            'unicode': "0043",
            'category': "Letter",
            'script': "devanagari",
            'production': "OwnedDonor",
        },
    ]
    app, data = owned(rows)
    before = deepcopy(data.names)
    result = app.glyphInfoForName("uni00410042")
    assert (result.name, result.productionName, result.unicode) == (
        expected,
        "OwnedDonor",
        None,
    )
    assert [c.name for c in result.components] == [expected]
    assert data.names == before


@pytest.mark.parametrize(
    "first,query,expected",
    [
        ("PA.", "uni00410042", "PA_PB"),
        ("PA", "uni00410042.", "PA_PB"),
        ("PA..", "uni00410042", "PA_PB.."),
        (".x", "uni00410042", "_PB.x_"),
        ("PA.init", "uni00410042", "PA_PB"),
    ],
)
def test_compound_when_dot_suffix_has_no_payload_then_preserves_name_but_omits_production_dot(
    owned, first, query, expected
):
    rows = letters(production=first)
    rows[1]["production"] = "PB"
    app, data = owned(rows)
    result = app.glyphInfoForName(query)
    assert result.productionName == expected
    assert result.name == ("A_B." if query.endswith(".") else "A_B")
    assert data.names["A"]["production"] == first


@pytest.mark.parametrize(
    "code,name,sort",
    [
        ("0041", "uni0041", "uni00041"),
        ("0000", "uni0000", "uni00000"),
        ("E000", "uniE000", "uni0E000"),
        ("000041", "uni000041", "uni0000041"),
        ("10000", "u10000", "unj10000"),
        ("1F600", "u1F600", "unj1F600"),
        ("10FFFE", "u10FFFE", "unj10FFFE"),
        ("FFFFFFFF", "uniFFFFFFFF", "uni0FFFFFFFF"),
    ],
)
def test_synthesized_unicode_when_no_data_row_then_keeps_retained_sort_prefix(
    owned, code, name, sort
):
    from fontlab_glyport.model import glyph_metadata

    owned([])
    result = glyph_metadata.unicode_info(code)
    assert (result.name, result.sortName, result.sortNameKeep) == (name, sort, None)
    assert result._production_state.value == name


def test_compound_when_both_components_synthesized_then_sorts_by_synthesized_keys(
    owned,
):
    from fontlab_glyport.model import glyph_metadata

    owned([])
    result = glyph_metadata.name_info("uni00410042")
    assert result.name == "uni0041_uni0042"
    assert result.sortName == "uni00041_uni00042"
    assert result.sortNameKeep == "uni00041_uni00042"
    assert [r.sortName for r in result._component_records] == ["uni00041", "uni00042"]
