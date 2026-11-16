# this_file: tests/test_glyph_categories.py
"""GlyphData categories differ from Unicode categories and letter case.

Literal expectations follow GlyphsInfo GlyphData.xml revision
0fe81a08dee6e7614c0f196e6668a9aafaad0d3e, with documented suffix inheritance.
No oracle calls glyphsLib to generate its own expected values.
"""

import sys

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("A", ("Letter", None)),
        ("a", ("Letter", None)),
        ("acute", ("Mark", "Spacing")),
        ("grave", ("Mark", "Spacing")),
        ("acutecomb", ("Mark", "Nonspacing")),
        ("uni0301", ("Mark", "Nonspacing")),
        ("a.ss01", ("Letter", None)),
        ("acutecomb.case", ("Mark", "Nonspacing")),
        ("one", ("Number", "Decimal Digit")),
        ("Euro", ("Symbol", "Currency")),
        ("_glyportHelper", (None, None)),
        ("glyportUnknownCustomName", (None, None)),
    ],
)
def test_name_metadata_when_draft_or_attached_then_glyphdata_values(
    name, expected, attached
):
    glyph = GSGlyph(name)
    if attached:
        font = Model(FakeBackend()).font
        if name == "A":
            glyph = font.glyphs["A"]
        else:
            font.glyphs.append(glyph)
            glyph = font.glyphs[name]
    assert (glyph.category, glyph.subCategory) == expected, (
        "Category metadata must follow GlyphData rather than Unicode general category"
    )


def test_empty_draft_has_no_category():
    glyph = GSGlyph()
    assert (glyph.category, glyph.subCategory) == (None, None)


def test_name_categories_take_precedence_over_an_alternate_explicit_encoding():
    glyph = GSGlyph("a.ss01")
    glyph.unicode = "0301"
    assert (glyph.category, glyph.subCategory) == ("Letter", None), (
        "A known alternate's name category takes precedence over its encoding"
    )


def test_custom_encoded_name_when_unicode_changed_then_refresh_is_explicit(
    owned_edit_info,
):
    with owned_edit_info._scope():
        glyph = GSGlyph("glyportUnknownCustomName")
        glyph.unicode = "0301"
        assert (glyph.category, glyph.subCategory) == (None, None), (
            "Unicode assignment alone does not set native classifications"
        )
        glyph.updateGlyphInfo(changeName=False)
        assert (glyph.category, glyph.subCategory) == ("Mark", "Nonspacing")
        glyph.unicode = "0031"
        assert (glyph.category, glyph.subCategory) == ("Mark", "Nonspacing"), (
            "Changing encoding must preserve existing classification until refresh"
        )
        glyph.updateGlyphInfo(changeName=False)
        assert (glyph.category, glyph.subCategory) == ("Number", "Decimal Digit")
        glyph.name = "a.ss01"
        assert (glyph.category, glyph.subCategory) == ("Letter", None)


def test_missing_database_fails_explicitly_without_plausible_wrong_categories(
    monkeypatch,
):
    glyph = GSGlyph("acute")
    monkeypatch.setitem(sys.modules, "glyphsLib", None)
    for attribute in ("category", "subCategory"):
        with pytest.raises(UnsupportedCapability, match="glyphsLib") as error:
            getattr(glyph, attribute)
        assert error.value.capability == "GSGlyph.categories.dependency", (
            "Incomplete installations must identify the missing category dependency"
        )
