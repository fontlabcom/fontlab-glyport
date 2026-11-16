# this_file: tests/test_compound_scripts.py
"""Owned exceptional-name rules derived independently from retained sources."""

from copy import deepcopy

import pytest

from fontlab_glyport.model.compound_production import is_number, join_names


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),
        ("", True),
        (".", True),
        ("+-", True),
        (".1", True),
        ("1.2.3", True),
        ("١", False),
        (" 1", False),
        ("1e2", False),
    ],
)
def test_number_predicate_when_membership_is_unusual_then_preserves_native_charset(
    value, expected
):
    assert is_number(value) is expected


@pytest.mark.parametrize(
    "names,expected",
    [
        (["ra-owner", "halant-owner"], "rakar-owner"),
        (["ra-malayalam", "halant-malayalam"], "r-malayalam"),
        (["halant-kannada", "ka-kannada"], "ka-kannada.below"),
        (["halant-kannada.alt", "ka-kannada.x"], "ka-kannada.alt_x.below"),
        (["A", "B-owner"], "A_B-owner"),
        (["A-owner", "B-other"], "A-owner_B-other"),
        (["A-owner", "B-owner"], "A_B-owner"),
        (["longprefixowner", "a", "halant"], "longprefixowner_a_halant"),
    ],
)
def test_joined_names_when_native_fixed_window_or_language_grouping_then_retains_order(
    names, expected
):
    before = list(names)
    assert join_names(names) == expected
    assert names == before


@pytest.mark.parametrize(
    "names,expected",
    [
        (["ka-deva", "halant-deva"], ["k-deva"]),
        (["ra-deva", "halant-deva"], ["reph-deva"]),
        (["halant-deva", "ra-deva"], ["rakar-deva"]),
        (["ra-kannada", "halant-kannada"], ["r-kannada"]),
        (["halant-kannada", "ra-kannada"], ["halant-kannada", "ra-kannada"]),
        (["ka-deva", "halant-deva", "ga-deva"], ["k-deva", "ga-deva"]),
        (["ka-deva", "halant-deva", "ra-deva"], ["ka-deva", "rakar-deva"]),
        (["ra-deva", "halant-deva", "halant-deva"], ["reph-deva", "halant-deva"]),
        (["ka-deva"], ["ka-deva"]),
        ([], []),
    ],
)
def test_indic_names_when_filter_rewrites_then_preserves_native_skip_and_scan_order(
    names, expected
):
    from fontlab_glyport.model.compound_scripts import filter_halant

    before = deepcopy(names)
    assert filter_halant(names) == expected
    assert names == before, "Filter works on its own input container"
