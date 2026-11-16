# this_file: tests/test_glyph_info_legacy.py
"""Legacy encodings remain separate in owned Glyph Info snapshots."""

from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.application import GSApplication
from fontlab_glyport.glyphsapp.glyph_info import GSGlyphInfo
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


def app():
    return GSApplication(NS(font=None), object(), {}, None, lambda *args: None)


@pytest.mark.parametrize(
    "name, canonical, primary, legacy",
    [
        ("A", "A", "0041", None),
        ("alef-ar", "alef-ar", "0627", None),
        ("alef-ar.isol", "alef-ar.isol", None, "FE8D"),
        ("aleffinalarabic", "alef-ar.fina", None, "FE8E"),
    ],
)
def test_global_info_when_database_has_legacy_then_keeps_separate_encoding(
    name, canonical, primary, legacy
):
    info = app().glyphInfoForName(name)
    assert (info.name, info.unicode, info.unicodeLegacy) == (
        canonical,
        primary,
        legacy,
    ), "Legacy encoding must not replace the primary database encoding"


@pytest.mark.parametrize("legacy", [None, "", "fe8d", "unparsed owned value"])
def test_snapshot_when_legacy_changes_then_preserves_exact_original_value(legacy):
    source = NS(
        name="owned",
        unicode=None,
        unicodeLegacy=legacy,
        category="Letter",
        subCategory=None,
        script="arabic",
        case=0,
    )
    info = GSGlyphInfo(source)
    source.unicodeLegacy = "changed"
    assert info.unicodeLegacy == legacy
    with pytest.raises(UnsupportedCapability) as error:
        info.unicodeLegacy = "FE8D"
    assert error.value.capability == "GSGlyphInfo.unicodeLegacy"
    assert info.unicodeLegacy == legacy, "Owned snapshots are read-only"


def test_snapshot_when_source_omits_legacy_then_reports_none():
    source = NS(
        name="owned", unicode=None, category=None, subCategory=None, script=None, case=0
    )
    assert GSGlyphInfo(source).unicodeLegacy is None


@pytest.mark.parametrize("attached", [False, True])
def test_model_snapshot_when_known_isolated_name_then_resolves_legacy(attached):
    glyph = GSGlyph("alef-ar.isol")
    if attached:
        font = Model(FakeBackend()).font
        glyph = font.glyphs.append(glyph)
    info = GSGlyphInfo(glyph)
    assert (info.name, info.unicode, info.unicodeLegacy) == (
        "alef-ar.isol",
        None,
        "FE8D",
    )
    assert glyph.unicodes == [], "Snapshot construction must not encode the glyph"


def test_local_snapshot_when_overrides_change_then_preserves_existing_fields():
    font = Model(FakeBackend()).font
    glyph = font.glyphs.append(GSGlyph("alef-ar.isol"))
    glyph.script = "owned-script"
    glyph.case = 5
    info = GSGlyphInfo(glyph)
    glyph.script = "changed"
    assert (info.script, info.case, info.unicode, info.unicodeLegacy) == (
        "owned-script",
        5,
        None,
        "FE8D",
    )


@pytest.mark.parametrize("name", ["alef-ar.isol.owned", "unknown-owned"])
def test_model_snapshot_when_legacy_is_not_resolved_then_does_not_inherit(name):
    glyph = GSGlyph(name)
    assert GSGlyphInfo(glyph).unicodeLegacy is None


@pytest.mark.parametrize("code", ["0041", "FE8D"])
def test_detached_snapshot_when_postprocessing_has_no_record_then_retains_primary(code):
    glyph = GSGlyph("alef-ar.isol")
    glyph.unicode = code
    info = GSGlyphInfo(glyph)
    assert info.unicode == code
    assert info.unicodeLegacy is None, (
        "Detached Arabic postprocessing still refuses even after a legacy index hit"
    )
    assert glyph.unicodes == [code]


def test_global_snapshot_when_active_font_has_unsupported_data_then_ignores_it():
    application = app()

    class Unreadable:
        def __getattribute__(self, name):
            raise AssertionError("Global lookup must not read the active font")

    application._model.font = Unreadable()
    for args, kwargs in [
        (("alef-ar.isol",), {}),
        (("alef-ar.isol", None), {}),
        (("alef-ar.isol",), {"font": None}),
    ]:
        assert application.glyphInfoForName(*args, **kwargs).unicodeLegacy == "FE8D"
    # All pinned wrappers consult an explicitly supplied font, independently of
    # the implicit active-font boundary established by the calls above.
    with pytest.raises(AssertionError, match="Global lookup must not read"):
        application.glyphInfoForName("alef-ar.isol", application._model.font)
