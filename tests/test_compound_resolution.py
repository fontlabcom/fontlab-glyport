# this_file: tests/test_compound_resolution.py
"""Owned seed, full-name and raw language fallback ordering."""

import pytest

from fontlab_glyport.model import glyph_metadata as gm
from fontlab_glyport.model.compound_metadata import _compose_parts
from fontlab_glyport.model.compound_position import positional_alternate


@pytest.mark.parametrize("stored", [None, "", "BaseRaw"])
def test_base_alternate_when_first_component_has_raw_variant_then_copies_without_filling(
    stored,
):
    base = gm._record("Base", unicode="0041", unicodeLegacy="E001", production=stored)
    first, second, alternate = [
        gm._record(name, production=None) for name in ("One", "Two", "One.alt")
    ]
    base._component_records = [first, second]
    index = {"Base": base, "One.alt": alternate}
    result = positional_alternate("Base.alt", index.get)
    assert result is not base and result.name == "Base.alt" and result.unicode is None
    assert result.unicodeLegacy == "E001"
    assert result._production_state.value == (
        None if stored is None else stored + ".alt"
    )
    assert (
        result._component_records[0] is alternate
        and result._component_records[1] is second
    )
    assert (
        base.name == "Base"
        and base._component_records[0] is first
        and first._production_state.value is None
    )


@pytest.mark.parametrize("name", ["Missing.alt", "Base", "Base.alt"])
def test_base_alternate_when_needed_data_missing_then_does_not_construct_partial_components(
    name,
):
    base = gm._record("Base", production=None)
    assert positional_alternate(name, {"Base": base}.get) is None


def test_later_component_when_full_name_misses_then_uses_seed_language_raw_fallback(
    monkeypatch,
):
    a = gm._record("A-deva", category="Letter", script="devanagari", production=None)
    owner = gm._record("owner", category="Mark", production=None)
    a._locked = owner._locked = True
    rows, events = {"A-deva": a, "owner": owner}, []

    def direct(name):
        events.append(("raw", name))
        return rows.get(name)

    def full(name, **kwargs):
        events.append(("full", name))

    monkeypatch.setattr(gm, "_direct", direct)
    monkeypatch.setattr(gm, "name_info", full)
    result = _compose_parts(["A-deva", "owner-deva"], [], None)
    assert [record.name for record in result._component_records] == ["A-deva", "owner"]
    assert owner._production_state.value is None, (
        "Last raw language fallback must not fill"
    )
    assert events.index(("full", "owner-deva")) < events.index(("raw", "owner"))


def test_farsi_seed_when_raw_arabic_fallback_exists_then_preempts_full_unsuffixed_fill(
    monkeypatch,
):
    seed = gm._record("owner-ar", category="Letter", script="arabic", production=None)
    other = gm._record("B", category="Letter", production=None)
    seed._locked = other._locked = True
    rows, events = {"owner-ar": seed, "B": other}, []
    monkeypatch.setattr(gm, "_direct", rows.get)

    def full(name, **kwargs):
        events.append(name)

    monkeypatch.setattr(gm, "name_info", full)
    result = _compose_parts(["owner-farsi", "B"], [], None)
    assert result.name == "owner_B-ar"
    assert seed._production_state.value is None and "owner" not in events


def test_composition_when_no_base_then_returns_genuine_miss():
    assert _compose_parts([], [], None) is None


def test_base_alternate_when_physical_recipe_unknown_then_explicit_source_refusal():
    from fontlab_glyport.errors import UnsupportedCapability

    base = gm._record("Base", production=None)
    base._unavailable_fields = frozenset({"components"})
    with pytest.raises(UnsupportedCapability) as caught:
        positional_alternate("Base.alt", {"Base": base}.get)
    assert caught.value.capability == "GSGlyphInfo.components.source"
    assert base._component_records is None and base._component_names is None
