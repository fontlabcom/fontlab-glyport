# this_file: tests/test_production_info_routes.py
"""Raw production fields, shared fills and copied routes remain distinct."""

from copy import copy, deepcopy
from types import SimpleNamespace as NS

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSApplication, GSGlyphInfo


@pytest.fixture
def app(monkeypatch):
    glyphdata.get_glyph("A")
    records = [
        {
            "name": "A",
            "unicode": "0041",
            "altNames": "ownedAlias",
            "script": "latin",
            "category": "Letter",
        },
        {
            "name": "empty-latin",
            "unicode": "00C1",
            "production": "",
            "script": "latin",
            "category": "Letter",
        },
        {
            "name": "owned-ar",
            "unicode": "0627",
            "production": "uniFFFF",
            "script": "arabic",
            "category": "Letter",
        },
        {
            "name": "equal",
            "unicode": "0045",
            "production": "equal",
            "script": "latin",
            "category": "Letter",
        },
        {
            "name": "named",
            "unicode": "004F",
            "production": "OwnedProd",
            "script": "latin",
            "category": "Letter",
        },
    ]
    names = {x["name"]: x for x in records}
    data = glyphdata.GlyphData(
        names,
        {"ownedAlias": records[0]},
        {"uniFFFF": records[2], "OwnedProd": records[4]},
        {x["unicode"]: x for x in records},
    )
    monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
    return GSApplication(NS(font=None), object(), {}, None, lambda *a: None)


def test_production_when_raw_then_exact_name_fills_shared_nil(app):
    raw = app.glyphInfoForUnicode("0041")
    assert raw.productionName is None, "Raw Unicode must not invoke exact-name fill"
    named = app.glyphInfoForName("A")
    assert named.productionName == "A", "Measured equal name is retained"
    assert raw.productionName == "A", "An existing raw handle observes shared fill"


@pytest.mark.parametrize("copier", [copy, deepcopy])
def test_production_when_raw_copy_then_later_shared_fill_does_not_change_copy(
    app, copier
):
    raw = app.glyphInfoForUnicode("0041")
    detached = copier(raw)
    app.glyphInfoForName("A")
    assert raw.productionName == "A"
    assert detached.productionName is None, "Copy preserves stored value at copy time"


@pytest.mark.parametrize(
    "code,name,expected",
    [
        ("00C1", "empty-latin", ""),
        ("0627", "owned-ar", "uniFFFF"),
        ("0045", "equal", "equal"),
    ],
)
def test_production_when_present_then_preserves_empty_explicit_and_equal(
    app, code, name, expected
):
    assert app.glyphInfoForUnicode(code).productionName == expected
    assert app.glyphInfoForName(name).productionName == expected
    assert app.glyphInfoForUnicode(code).productionName == expected


def test_production_when_alias_fills_then_canonical_and_raw_share_value(app):
    raw = app.glyphInfoForUnicode("0041")
    alias = app.glyphInfoForName("ownedAlias")
    assert (alias.name, alias.productionName) == ("A", "A")
    assert raw.productionName == "A"
    explicit = app.glyphInfoForName("OwnedProd")
    assert (explicit.name, explicit.productionName) == ("named", "OwnedProd")


def test_production_when_uni_name_copies_then_retains_pre_fill_value(app):
    raw = app.glyphInfoForUnicode("0041")
    alias = app.glyphInfoForName("uni0041")
    assert (alias.name, alias.productionName) == ("A", None)
    app.glyphInfoForName("A")
    assert raw.productionName == "A"
    assert alias.productionName is None, "uni/u single-scalar route owns a copy"
    assert app.glyphInfoForName("uni0041").productionName == "A"


@pytest.mark.parametrize(
    "code,name",
    [
        ("0378", "uni0378"),
        ("000041", "uni000041"),
        ("00000000", "uni00000000"),
        ("10FFFE", "u10FFFE"),
    ],
)
def test_production_when_unicode_synthesized_then_sets_exact_constructed_name(
    app, code, name
):
    info = app.glyphInfoForUnicode(code)
    assert (info.name, info.productionName) == (name, name)


def test_production_when_suffix_then_helper_normalizes_only_derived_output(app):
    original = app.glyphInfoForUnicode("0627")
    info = app.glyphInfoForName("owned-ar.ss01.alt")
    assert (info.name, info.productionName) == ("owned-ar.ss01.alt", "uni0627.ss01.alt")
    assert original.productionName == "uniFFFF", "Helper does not overwrite raw field"


def test_production_when_assigned_then_owned_info_remains_read_only(app):
    info = app.glyphInfoForName("A")
    with pytest.raises(UnsupportedCapability) as exc:
        info.productionName = "changed"
    assert exc.value.capability == "GSGlyphInfo.productionName"
    assert info.productionName == "A"


def test_production_when_source_is_unavailable_then_does_not_invent_nil():
    info = GSGlyphInfo(
        NS(
            name="owned",
            unicode=None,
            category=None,
            subCategory=None,
            script=None,
            case=0,
        )
    )
    with pytest.raises(UnsupportedCapability) as exc:
        _ = info.productionName
    assert exc.value.capability == "GSGlyphInfo.productionName.source"


def install(monkeypatch, records):
    names = {row["name"]: row for row in records}
    monkeypatch.setattr(
        glyphdata,
        "GLYPHDATA",
        glyphdata.GlyphData(
            names, {}, {}, {row["unicode"]: row for row in records if "unicode" in row}
        ),
    )
    return GSApplication(NS(font=None), object(), {}, None, lambda *a: None)


@pytest.mark.parametrize("alias", ["uni0041", "unicorn", "uni"])
def test_name_index_when_production_starts_uni_then_does_not_shadow_exact_name(
    monkeypatch, alias
):
    app = install(
        monkeypatch,
        [
            {"name": alias, "production": "Exact", "category": "Letter"},
            {"name": "other", "production": alias, "category": "Letter"},
        ],
    )
    assert app.glyphInfoForName(alias).name == alias, (
        "Only a production alias is excluded, not a stored primary name"
    )


@pytest.mark.parametrize("alias", ["OwnedProd", "u1F600", "Uni0041"])
def test_name_index_when_later_production_alias_then_overwrites_earlier_exact(
    monkeypatch, alias
):
    app = install(
        monkeypatch,
        [
            {"name": alias, "category": "Letter"},
            {"name": "later", "production": alias, "category": "Letter"},
        ],
    )
    assert app.glyphInfoForName(alias).name == "later", (
        "Retained parser uses one last-write dictionary"
    )


def test_name_index_when_later_alt_overwrites_exact_then_raw_unicode_stays_original(
    monkeypatch,
):
    app = install(
        monkeypatch,
        [
            {"name": "A", "unicode": "0041", "category": "Letter"},
            {"name": "later", "altNames": "A", "category": "Letter"},
        ],
    )
    assert app.glyphInfoForName("A").name == "later"
    assert app.glyphInfoForUnicode("0041").name == "A", (
        "Raw Unicode cannot re-resolve through a shadowed canonical name"
    )


def test_name_index_when_production_only_uni_alias_then_decodes_raw_copy(app):
    info = app.glyphInfoForName("uniFFFF")
    assert (info.name, info.productionName) == ("uniFFFF", "uniFFFF")
    assert app.glyphInfoForUnicode("0627").name == "owned-ar"


@pytest.mark.parametrize("text", ["é", "😀", "\ud83d\ude00"])
def test_name_when_bare_character_then_reads_raw_shared_record(monkeypatch, text):
    scalar = "00E9" if text == "é" else "1F600"
    app = install(
        monkeypatch,
        [{"name": "ownedCharacter", "unicode": scalar, "category": "Letter"}],
    )
    info = app.glyphInfoForName(text)
    assert info.productionName is None
    app.glyphInfoForName("ownedCharacter")
    assert info.productionName == "ownedCharacter", (
        "Bare character access does not take the uni/u copy"
    )


def test_unicode_name_when_native_scalar_rejects_then_fallback_is_known_nil(app):
    info = app.glyphInfoForName("u10FFFF")
    assert (info.name, info.unicode, info.productionName) == ("u10FFFF", "10FFFF", None)


def test_model_when_equal_stored_flag_then_only_overlaid_info_detaches(app):
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    first = Model(FakeBackend()).font.glyphs["A"]
    second = Model(FakeBackend()).font.glyphs["A"]
    shared = GSGlyphInfo(first)
    second.case = 0
    second.storeCase = True
    detached = GSGlyphInfo(second)
    assert shared.productionName is None and detached.productionName is None
    app.glyphInfoForName("A")
    assert shared.productionName == "A"
    assert detached.productionName is None, (
        "A true store flag forces native copy even when equal"
    )


def test_model_when_private_use_then_detaches_before_global_fill(monkeypatch):
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    app = install(
        monkeypatch,
        [{"name": "ownedPrivate", "unicode": "E123", "category": "Private Use"}],
    )
    glyph = Model(FakeBackend()).font.glyphs.append(GSGlyph("ownedPrivate"))
    info = GSGlyphInfo(glyph)
    assert info.productionName is None
    app.glyphInfoForName("ownedPrivate")
    assert app.glyphInfoForUnicode("E123").productionName == "uniE123"
    assert info.productionName is None


def test_model_when_arabic_isol_exists_without_unicode_then_fill_and_copy(monkeypatch):
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    app = install(
        monkeypatch,
        [
            {
                "name": "owned-ar",
                "unicode": "0627",
                "script": "arabic",
                "category": "Letter",
            },
            {
                "name": "owned-ar.isol",
                "unicodeLegacy": "FE8D",
                "script": "arabic",
                "category": "Letter",
            },
        ],
    )
    isolated = app.glyphInfoForUnicode("FE8D")
    glyph = Model(FakeBackend()).font.glyphs.append(GSGlyph("owned-ar"))
    info = GSGlyphInfo(glyph)
    assert isolated.productionName == "ownedar.isol", (
        "Additional-Unicode invokes exact-name fill"
    )
    assert info.productionName is None
    app.glyphInfoForName("owned-ar")
    assert info.productionName is None, (
        "A returned nil-Unicode .isol still triggers a copy"
    )


def test_model_when_presentation_only_then_isol_lookup_does_not_fill(monkeypatch):
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    app = install(
        monkeypatch,
        [
            {
                "name": "owned-ar",
                "unicode": "0627",
                "script": "arabic",
                "category": "Letter",
            },
            {
                "name": "owned-ar.isol",
                "unicodeLegacy": "FE8D",
                "script": "arabic",
                "category": "Letter",
            },
        ],
    )
    isolated = app.glyphInfoForUnicode("FE8D")
    font = Model(FakeBackend()).font
    glyph = font.glyphs.append(GSGlyph("owned-ar"))
    glyph.unicodes = []
    font.customParameters["Use Arabic Presentation Form Unicodes"] = True
    info = GSGlyphInfo(glyph)
    assert isolated.productionName is None, (
        "Presentation uses a raw lookup, not exact-name fill"
    )
    assert info.productionName is None


def test_suffix_when_global_vs_font_base_then_only_global_route_fills(app):
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    font = Model(FakeBackend()).font
    glyph = font.glyphs.append(GSGlyph("A.001.ss01..ss01"))
    from fontlab_glyport.model.glyph_metadata import name_info

    raw = app.glyphInfoForUnicode("0041")
    model = name_info(glyph.name, font)
    assert GSGlyphInfo(model).productionName == "A.001.ss01..ss01"
    assert raw.productionName is None
    assert app.glyphInfoForName(glyph.name).productionName == "A.001.ss01..ss01"
    assert raw.productionName == "A"


def test_constructed_metadata_when_unqualified_then_production_is_unavailable(app):
    from fontlab_glyport.model.glyph_metadata import name_info

    info = GSGlyphInfo(name_info("A_A"))
    with pytest.raises(UnsupportedCapability) as exc:
        _ = info.productionName
    assert exc.value.capability == "GSGlyphInfo.productionName.source"


@pytest.mark.parametrize("production", [None, "", "uniFFFF"])
def test_canonical_unicode_suffix_when_last_token_consumed_then_preserves_raw_field(
    monkeypatch, production
):
    app = install(
        monkeypatch,
        [
            {"name": "A", "unicode": "0041", "category": "Letter"},
            {
                "name": "A.alt",
                "unicode": "0042",
                "unicodeLegacy": "E001",
                "production": production,
                "category": "Letter",
            },
        ],
    )
    raw = app.glyphInfoForUnicode("0042")
    info = app.glyphInfoForName("uni0041.alt")
    assert (info.name, info.unicode, info.unicodeLegacy, info.productionName) == (
        "A.alt",
        None,
        None,
        production,
    )
    app.glyphInfoForName("A.alt")
    assert info.productionName == production, (
        "Consumed record is copied, not rebound to a later fill"
    )
    assert raw.productionName == ("A.alt" if production is None else production)


def test_canonical_unicode_suffix_when_tokens_remain_then_applies_helper_to_raw_record(
    monkeypatch,
):
    app = install(
        monkeypatch,
        [
            {"name": "A", "unicode": "0041", "category": "Letter"},
            {
                "name": "A.alt",
                "unicode": "0042",
                "production": "uniFFFF",
                "category": "Letter",
            },
        ],
    )
    info = app.glyphInfoForName("uni0041.alt.ss01")
    assert (info.name, info.productionName, info.unicode) == (
        "A.alt.ss01",
        "uni0042.ss01",
        None,
    )
    assert app.glyphInfoForUnicode("0042").productionName == "uniFFFF", (
        "Helper normalization remains separate from raw getter"
    )


def test_suffix_when_alias_changes_base_name_then_uses_canonical_metadata_name(app):
    info = app.glyphInfoForName("ownedAlias.alt")
    assert (info.name, info.productionName) == ("A.alt", "A.alt")


def test_presentation_when_legacy_already_present_then_still_freezes_production(
    monkeypatch,
):
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    app = install(
        monkeypatch,
        [
            {
                "name": "owned-ar",
                "unicode": "0627",
                "unicodeLegacy": "0627",
                "script": "arabic",
                "category": "Letter",
            }
        ],
    )
    font = Model(FakeBackend()).font
    glyph = font.glyphs.append(GSGlyph("owned-ar"))
    glyph.unicodes = []
    font.customParameters["Use Arabic Presentation Form Unicodes"] = True
    info = GSGlyphInfo(glyph)
    assert info.productionName is None
    app.glyphInfoForName("owned-ar")
    assert app.glyphInfoForUnicode("0627").productionName == "owned-ar"
    assert info.productionName is None, (
        "Native copy precedes addUnicode's duplicate no-op"
    )


@pytest.mark.parametrize("suffix", ["case", "cap"])
def test_global_suffix_when_uppercase_context_then_fills_only_detached_copy(
    app, suffix
):
    raw = app.glyphInfoForUnicode("0041")
    info = app.glyphInfoForName("A." + suffix)
    assert (info.case, info.productionName) == (1, "A." + suffix)
    assert raw.productionName is None, (
        "Native suffix context copies before exact nil fill"
    )


def test_name_index_when_public_aliases_have_separator_spaces_then_normalizes_tokens(
    monkeypatch,
):
    app = install(
        monkeypatch,
        [{"name": "canonical", "altNames": "First, Second", "category": "Letter"}],
    )
    assert app.glyphInfoForName("First").name == "canonical"
    assert app.glyphInfoForName("Second").name == "canonical"
