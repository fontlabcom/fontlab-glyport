# this_file: tests/test_smallcap_metadata.py
"""Owned small-cap branches from the complete retained helper."""

import pytest

from fontlab_glyport.model.glyph_metadata import _record
from fontlab_glyport.model.smallcap_metadata import apply_smallcaps


def row(name, code=None, category="Letter", **fields):
    value = _record(name, unicode=code, category=category, production=name)
    vars(value).update(fields)
    return value


def run(target, rows, *, name="owned.sc", suffix="sc.alt", upper=(0x41,)):
    calls = []

    def lookup(code):
        calls.append(code)
        return rows.get(code)

    apply_smallcaps(
        target, name, suffix, lookup, uppercase=lambda code: upper, lowercase=str.lower
    )
    return calls


@pytest.mark.parametrize(
    "code,name,upper",
    [
        (None, "owned.sc", (0x41,)),
        ("0041", "owned.sc", (0x41,)),
        ("00DF", "germandbls.alt.sc", (0x53, 0x53)),
    ],
)
def test_smallcaps_when_guard_preserves_components_then_still_sets_case(
    code, name, upper
):
    prior = row("prior")
    target = row("owned", code, _component_records=[prior])
    assert run(target, {}, name=name, upper=upper) == []
    assert target.case == 3 and target._component_records == [prior]


def test_smallcaps_when_upper_donor_has_components_then_copies_names_and_metadata():
    a, mark = row("A"), row("ACUTEcomb", category="Mark")
    donor = row(
        "Aacute",
        "00C1",
        _component_records=[a, mark],
        anchors=["top"],
        marks=["accent"],
    )
    target = row("aacute", "00E1", _component_records=[row("old")])
    state = target._production_state
    assert run(target, {"00C1": donor}, upper=(0xC1,)) == ["00C1"]
    result = target._component_records
    assert [(v.name, v.case) for v in result] == [("a.sc.alt", 3), ("acutecomb", 3)]
    assert result[0] is not a and result[1] is not mark
    assert a.name == "A" and mark.name == "ACUTEcomb"
    assert target.anchors is donor.anchors and target.marks is donor.marks
    assert target._production_state is state and state.value == "aacute"


def test_smallcaps_when_upper_donor_missing_then_replaces_components_without_metadata():
    target = row("a", "0061", _component_records=[row("old")], anchors=["saved"])
    assert run(target, {}) == ["0041"]
    assert target._component_records == [] and target.anchors == ["saved"]


def test_smallcaps_when_one_unit_donor_has_no_components_then_clears_prior_recipe():
    donor = row("A", "0041", anchors=[], marks=None)
    target = row(
        "a",
        "0061",
        _component_records=[row("old")],
        anchors=["saved"],
        marks=["saved-mark"],
    )
    assert run(target, {"0041": donor}) == ["0041"]
    assert target._component_records == []
    assert target.anchors == ["saved"] and target.marks == ["saved-mark"]


def test_smallcaps_when_expansion_contains_marks_then_last_letter_supplies_metadata():
    a = row("A", "0041", anchors=["first"])
    b = row("B", "0042", anchors=["last"], marks=["last-mark"])
    mark = row("MARK", "0301", "Mark", anchors=["wrong"])
    target = row("expand", "FB03")
    assert run(
        target, {"0041": a, "0042": b, "0301": mark}, upper=(0x41, 0x42, 0x301)
    ) == ["0041", "0041", "0042", "0301"]
    assert [v.name for v in target._component_records] == [
        "a.sc.alt",
        "b.sc.alt",
        "mark",
    ]
    assert target.anchors is b.anchors and target.marks is b.marks


def test_smallcaps_when_supplementary_unchanged_then_looks_up_utf16_units():
    high, low = row("HIGH", category="Other"), row("LOW", category="Other")
    target = row("emoji", "1F600", _component_records=[row("old")])
    assert run(target, {"D83D": high, "DE00": low}, upper=(0x1F600,)) == [
        "D83D",
        "D83D",
        "DE00",
    ]
    assert [v.name for v in target._component_records] == ["high", "low"]


def test_smallcaps_when_expansion_lookup_is_nil_then_explicitly_refuses():
    from fontlab_glyport.errors import UnsupportedCapability

    target = row("expand", "FB03")
    with pytest.raises(UnsupportedCapability, match="expansion"):
        run(target, {"0041": row("A")}, upper=(0x41, 0x42))


@pytest.mark.parametrize("token", ["sc", "smcp", "c2sc", "pc", "pcap"])
def test_generic_suffix_when_encoded_then_enters_helper_before_clearing_encoding(
    monkeypatch, token
):
    from fontlab_glyport.model import glyph_metadata as metadata

    a = row("A", "0041")
    acute = row("ACUTEcomb", "0301", "Mark")
    donor = row("Aacute", "00C1", _component_records=[a, acute])
    source = row("aacute", "00E1")
    monkeypatch.setattr(
        metadata, "unicode_info", lambda code: donor if code == "00C1" else None
    )
    result = metadata._suffix(source, "aacute." + token, [token])
    assert result.case == 3 and result.unicode is None and result.unicodeLegacy is None
    assert [v.name for v in result._component_records] == ["a." + token, "acutecomb"]
    assert source.unicode == "00E1" and a.name == "A"


def test_smallcaps_when_component_has_sigma_context_then_maps_copy_before_suffix():
    target = row("a", "0061", _component_records=[row("prior")])
    part = row("AΣ")
    donor = row("A", "0041", _component_records=[part])
    apply_smallcaps(target, "a.sc.alt", "sc.alt", lambda code: donor)
    assert [value.name for value in target._component_records] == ["aς.sc.alt"]
    assert target._component_records[0] is not part and part.name == "AΣ"
    assert target.case == 3 and target.unicode == "0061"
