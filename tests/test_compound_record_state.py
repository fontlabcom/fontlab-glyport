# this_file: tests/test_compound_record_state.py
"""Observe owned locked/unlocked metadata objects through actual composition."""

import pytest

from fontlab_glyport.model import glyph_metadata
from fontlab_glyport.model.compound_metadata import _base_text, compose_names


@pytest.fixture
def records(monkeypatch):
    def install(*, locked=True, script="latin", category="Letter", unicode=True):
        rows = {
            name: glyph_metadata._record(
                name,
                production=None,
                category=category,
                script=script,
                unicode=f"{ord(name):04X}" if unicode else None,
            )
            for name in ("A", "B", "C")
        }
        for record in rows.values():
            record._locked = locked
        monkeypatch.setattr(glyph_metadata, "_direct", rows.get)
        monkeypatch.setattr(
            glyph_metadata,
            "name_info",
            lambda name, **kw: glyph_metadata._fill_production(rows[name])
            if name in rows
            else None,
        )
        return rows

    return install


@pytest.mark.parametrize("locked", [False, True])
def test_seed_when_locked_or_unlocked_then_final_copy_keeps_prior_mutation_distinct(
    records, locked
):
    rows = records(locked=locked)
    source = rows["A"]
    result = compose_names(["A", "B"])
    assert result is not source
    assert result.name == "A_B" and result._production_state.value == "A_B"
    assert source.name == ("A" if locked else "A_B")
    assert source.unicode == ("0041" if locked else None)
    assert result._component_records[0] is source
    result._production_state.value = "detached"
    assert source._production_state.value == ("A" if locked else "A_B")


@pytest.mark.parametrize("count,expected", [(1, ""), (2, "\u200d")])
def test_runic_empty_components_when_separator_trimmed_then_still_clears_legacy(
    records, count, expected
):
    rows = records(script="runic", unicode=False)
    rows["A"].unicodeLegacy = "OldLegacy"
    result = compose_names(["A"] * count)
    assert result.baseString == expected and result.unicodeLegacy is None
    assert result.unicharString is None
    assert rows["A"].unicodeLegacy == "OldLegacy"


@pytest.mark.parametrize("code", ["0000", "10FFFF", "-1", "malformed"])
def test_base_text_when_primary_outside_native_character_gate_then_preserves_empty(
    code,
):
    row = glyph_metadata._record("Owned", unicode=code, production=None)
    assert _base_text(row) == ""


def test_base_text_when_empty_cache_exists_then_does_not_regenerate_primary():
    row = glyph_metadata._record("Owned", unicode="0041", production=None)
    row.unicharString, row.baseString = "", "SavedBase"
    assert _base_text(row) == "SavedBase"


def test_mark_components_when_same_missing_suffix_then_consolidates_global_text(
    records,
):
    rows = records(category="Mark")
    result = compose_names(["A.alt", "B.alt"])
    assert result.name == "A_B.alt" and result._production_state.value == "A_B.alt"
    assert [record.name for record in result._component_records] == ["A.alt", "B.alt"]
    assert (rows["A"].name, rows["B"].name) == ("A", "B")


def test_unlocked_component_when_renamed_then_production_uses_prior_helper_strings(
    records,
):
    rows = records(locked=False)
    result = compose_names(["A.alt", "B.alt"])
    assert result.name == "A_B.alt_alt"
    assert result._production_state.value == "A_B.alt_alt", (
        "Helper values precede component renames"
    )
    assert rows["B"].name == "B.alt" and rows["B"]._production_state.value is None


def test_indic_halfform_seed_when_last_surviving_letter_then_takes_last_metadata(
    records,
):
    rows = records(script="devanagari")
    rows["A"].subCategory = "Halfform"
    rows["B"].case, rows["C"].case = 2, 1
    rows["C"].category = "Letter"
    result = compose_names(["A", "B", "C"])
    assert result.case == 1 and result.category == "Letter"
    assert result.name == "A_B_C" and result.unicode is None


def test_short_naming_window_when_native_range_outside_string_then_does_not_clip():
    from fontlab_glyport.model.compound_production import join_names

    with pytest.raises(ValueError, match="UTF16"):
        join_names(["ra", "halant"])


@pytest.mark.parametrize(
    "first,global_suffix,silent,second_code,expected",
    [
        ("P" * 55, ".alt", None, "0042", "P" * 55 + "_Q.alt"),
        ("P" * 56, ".alt", None, "0042", "uni00410042"),
        ("P" * 52, ".x", "liga", "0042", "P" * 52 + "_Q.x.liga"),
        ("P" * 53, ".x", "liga", "0042", "uni00410042"),
        ("P" * 56, ".alt", None, None, "P" * 56 + "_Q.alt"),
        ("\U0001f600" * 28 + "P", ".x", None, "0042", "\U0001f600" * 28 + "P_Q.x"),
        ("\U0001f600" * 28 + "PP", ".x", None, "0042", "uni00410042"),
        ("P" * 56, ".alt", "liga", None, "P" * 56 + "_Q.alt.liga"),
        ("uniFFFF", ".alt", None, "0042", "uniFFFF0042.alt"),
        ("uniFFFF", ".alt", None, None, "uni0041_Q.alt"),
    ],
)
def test_production_when_global_or_silent_crosses_utf16_limit_then_uses_whole_raw_list(
    first, global_suffix, silent, second_code, expected
):
    from fontlab_glyport.model.compound_production import compound_production
    from fontlab_glyport.model.production_metadata import production_name

    records = [
        glyph_metadata._record("A", unicode="0041", script="latin", production=first),
        glyph_metadata._record(
            "B",
            unicode=second_code,
            unicodeLegacy="0042",
            script="latin",
            production="Q",
        ),
    ]
    before = [
        (r.name, r.unicode, r.unicodeLegacy, r._production_state.value) for r in records
    ]
    helpers = [
        production_name(r.name, r._production_state.value, r.unicode, r.script)
        for r in records
    ]
    assert (
        compound_production(
            records, helpers, global_suffix=global_suffix, silent=silent
        )
        == expected
    )
    assert [
        (r.name, r.unicode, r.unicodeLegacy, r._production_state.value) for r in records
    ] == before


@pytest.mark.parametrize(
    "prefix", ["ABCDEFGHIJ\U0001f600", "ABCDEFGHI\U0001f600K", "ABCDEFGHIJ\ud800"]
)
def test_join_when_fixed_utf16_window_splits_pair_then_preserves_full_text(prefix):
    from fontlab_glyport.model.compound_production import join_names

    names = [prefix, "a", "halant"]
    assert join_names(names) == "_".join(names)


@pytest.mark.parametrize(
    "names,expected",
    [
        (["ra", "halant", "\U0001f600"], "rakar_\U0001f600"),
        (["a", "halant", "\U0001f600"], "_\U0001f600"),
    ],
)
def test_join_when_fixed_window_rewrites_ascii_then_keeps_adjacent_character(
    names, expected
):
    from fontlab_glyport.model.compound_production import join_names

    assert join_names(names) == expected
