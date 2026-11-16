# this_file: tests/test_production_checkpoint_routes.py
"""Suffix classification consumes only remaining tokens and keeps cap contexts apart."""

from types import SimpleNamespace

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.glyphsapp import GSApplication


def owned_app(monkeypatch, rows):
    names = {row["name"]: row for row in rows}
    data = glyphdata.GlyphData(
        names, {}, {}, {row["unicode"]: row for row in rows if row.get("unicode")}
    )
    monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
    return GSApplication(
        SimpleNamespace(font=None), object(), {}, None, lambda *args: None
    )


@pytest.mark.parametrize(
    "consumed", ["osf", "tosf", "sc", "smcp", "pc", "subs", "sups"]
)
def test_global_when_named_prefix_consumes_case_token_then_remaining_alt_preserves_case(
    monkeypatch, consumed
):
    base = "owned." + consumed
    app = owned_app(
        monkeypatch,
        [
            {"name": base, "unicode": "0041", "category": "Letter", "case": "upper"},
        ],
    )
    result = app.glyphInfoForName(base + ".alt")
    assert result.case == 1, (
        "Consumed canonical-name tokens cannot reclassify a derived record"
    )
    assert result.productionName == base + ".alt"


@pytest.mark.parametrize("consumed", ["dnom", "numr"])
def test_global_when_named_prefix_consumes_fraction_token_then_remaining_alt_preserves_subcategory(
    monkeypatch, consumed
):
    base = "owned." + consumed
    app = owned_app(
        monkeypatch,
        [
            {
                "name": base,
                "category": "Letter",
                "subCategory": "Other",
                "case": "upper",
            },
        ],
    )
    info = app.glyphInfoForName(base + ".alt")
    assert info.subCategory == "Other", (
        "A consumed fraction token must not leak into remaining suffix rules"
    )


def test_global_when_cap_is_not_last_context_then_does_not_promote_lowercase(
    monkeypatch,
):
    app = owned_app(
        monkeypatch,
        [
            {"name": "a", "unicode": "0061", "category": "Letter", "case": "lower"},
        ],
    )
    raw = app.glyphInfoForUnicode("0061")
    cap = app.glyphInfoForName("a.cap")
    assert cap.case == 1 and raw.productionName is None, (
        "Global terminal cap context copies before fill"
    )
    generic = app.glyphInfoForName("a.cap.alt")
    assert generic.case == 2, "Generic suffix handling does not interpret cap as case"
    assert raw.productionName == "a", (
        "The ordinary global base lookup still fills its shared record"
    )


def test_model_when_encoded_font_base_has_cap_suffix_then_preserves_lowercase(
    monkeypatch,
    owned_info_manager,
):
    from fontlab_glyport.glyphsapp import GSGlyphInfo
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    owned_app(
        monkeypatch,
        [
            {
                "name": "a",
                "unicode": "0061",
                "case": "lower",
                "category": "Letter",
                "script": "latin",
            }
        ],
    )
    font = Model(FakeBackend()).font
    font.glyphs.append(GSGlyph("a"))
    glyph = font.glyphs.append(GSGlyph("a.cap"))
    assert glyph.case == 1 and glyph.storeCase is False, (
        "Stored snapshots and resolved Info are distinct"
    )
    font.parent._local_glyph_info = owned_info_manager()
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.case == 2, "Explicit refresh follows the encoded local-base resolver"
    assert GSGlyphInfo(glyph).case == 2, (
        "Font-base suffix handling has no global terminal-cap promotion"
    )


@pytest.mark.parametrize("encoded", [False, True])
def test_model_when_font_base_encoding_eligibility_differs_then_global_shared_fill_follows_lookup(
    monkeypatch, encoded
):
    from fontlab_glyport.glyphsapp import GSGlyphInfo
    from fontlab_glyport.model import GSGlyph, Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    font = Model(backend).font
    base = font.glyphs.append(GSGlyph("a"))
    if not encoded:
        base.unicodes = []
    glyph = font.glyphs.append(GSGlyph("a.alt"))
    state = {
        "com.fontlab.glyport.case": 2,
        "com.schriftgestaltung.Glyphs.category": "Letter",
        "com.schriftgestaltung.Glyphs.subCategory": None,
        "com.schriftgestaltung.Glyphs.script": "latin",
    }
    backend.set_lib(glyph._id, state.copy())
    backend.set_lib(base._id, state.copy())
    # New immutable data identity isolates the lookup from constructor-time fills.
    app = owned_app(
        monkeypatch,
        [
            {
                "name": "a",
                "unicode": "0061",
                "case": "lower",
                "category": "Letter",
                "script": "latin",
            }
        ],
    )
    raw = app.glyphInfoForUnicode("0061")
    assert raw.productionName is None, "The fresh shared record starts unfilled"
    info = GSGlyphInfo(glyph)
    assert info.productionName == "a.alt"
    assert raw.productionName == (None if encoded else "a"), (
        "An unencoded font base is ineligible, so fallback uses global exact-name fill"
    )
    assert base.unicodes == (["0061"] if encoded else [])
    assert glyph.storeCase is False and glyph.case == 2, (
        "Resolution preserves snapshots and disabled store flags"
    )
