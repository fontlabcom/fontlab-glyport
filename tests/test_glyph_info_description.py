# this_file: tests/test_glyph_info_description.py
"""Stored descriptions follow the actual selected record, without text synthesis."""

from copy import copy, deepcopy
from types import SimpleNamespace

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSApplication
from fontlab_glyport.glyphsapp.glyph_info import GSGlyphInfo
from fontlab_glyport.model.proxies import GSGlyph


@pytest.fixture
def owned(monkeypatch):
    glyphdata.get_glyph("A")

    def install(rows):
        names = {r["name"]: deepcopy(r) for r in rows}
        data = glyphdata.GlyphData(names, {}, {}, {})
        monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
        app = GSApplication(
            SimpleNamespace(font=None), object(), {}, None, lambda *args: None
        )
        return app, data

    return install


def letters():
    return [
        {
            "name": "A",
            "unicode": "0041",
            "category": "Letter",
            "script": "latin",
            "description": "Owned first",
            "altNames": "OwnedAlias",
            "production": "ProdA",
        },
        {
            "name": "B",
            "unicode": "0042",
            "category": "Letter",
            "script": "latin",
            "description": "Owned second",
        },
    ]


@pytest.mark.parametrize(
    "query", ["A", "OwnedAlias", "ProdA", "uni0041", "u0041", "A.alt"]
)
def test_description_when_name_route_selects_first_record_then_keeps_stored_text(
    owned, query
):
    app, data = owned(letters())
    before = deepcopy(
        (data.names, data.alternative_names, data.production_names, data.unicodes)
    )
    info = app.glyphInfoForName(query)
    assert info.desc == "Owned first", "Descriptions belong to the selected record"
    assert (
        data.names,
        data.alternative_names,
        data.production_names,
        data.unicodes,
    ) == before, "Queries must preserve all source dictionaries"


@pytest.mark.parametrize("text", [None, "", "Owner Ω\ncombining e\u0301\x00tail"])
def test_description_when_nullable_empty_or_unicode_then_returns_exact_stored_value(
    owned, text
):
    rows = letters()
    if text is None:
        del rows[0]["description"]
    else:
        rows[0]["description"] = text
    app, _ = owned(rows)
    assert app.glyphInfoForName("A").desc == text, "Do not substitute Unicode names"


def test_description_when_global_unicode_lookup_then_uses_record_without_name_fill(
    owned,
):
    app, _ = owned(letters())
    info = app.glyphInfoForUnicode("0042")
    assert info.desc == "Owned second"
    assert info.productionName is None, "Description reads must not fill production"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("uni00410042", "Owned first"),
        ("uni00420041", "Owned second"),
        ("uni00410042.ss01", "Owned first"),
    ],
)
def test_description_when_compound_or_wrapper_then_keeps_selected_seed(
    owned, query, expected
):
    app, _ = owned(letters())
    info = app.glyphInfoForName(query)
    assert info.desc == expected, "Do not join component descriptions"
    if query.endswith(".ss01"):
        assert info.components[0].desc == "Owned first", "Nested metadata must survive"


def test_description_when_exact_whole_query_exists_then_preempts_component_seed(owned):
    rows = letters() + [
        {"name": "uni00410042", "category": "Mark", "description": "Exact winner"}
    ]
    app, _ = owned(rows)
    assert app.glyphInfoForName("uni00410042").desc == "Exact winner"


def test_description_when_indic_halfform_seed_replaced_then_takes_selected_donor(owned):
    rows = letters()
    rows[0].update(name="ka-deva", script="devanagari", subCategory="Halfform")
    rows[1].update(name="ga-deva", script="devanagari")
    app, _ = owned(rows)
    assert app.glyphInfoForName("uni00410042").desc == "Owned second", (
        "Use the last eligible Indic seed rather than the first decoded record"
    )


@pytest.mark.parametrize("query", ["uni1234", "u12345"])
def test_description_when_genuine_synthesized_record_then_has_nil_description(
    owned, query
):
    app, _ = owned(letters())
    assert app.glyphInfoForName(query).desc is None, (
        "Never invent a Unicode description"
    )


@pytest.mark.parametrize("name", ["A", "A.alt"])
def test_description_when_model_metadata_resolves_then_exposes_selected_description(
    owned, name
):
    owned(letters())
    glyph = GSGlyph(name)
    assert GSGlyphInfo(glyph).desc == "Owned first", (
        "Model snapshot must preserve the field"
    )


def test_description_when_copied_then_preserves_text_and_refuses_assignment(owned):
    app, _ = owned(letters())
    info = app.glyphInfoForName("A")
    duplicate = copy(info)
    assert duplicate is not info and duplicate.desc == info.desc == "Owned first"
    with pytest.raises(UnsupportedCapability) as caught:
        duplicate.desc = "Changed"
    assert caught.value.capability == "GSGlyphInfo.desc"
    assert duplicate.desc == info.desc == "Owned first"


def test_description_when_external_source_omits_contract_then_refuses_unknown(owned):
    owned(letters())
    raw = SimpleNamespace(
        name="Owned",
        unicode=None,
        category="Letter",
        subCategory=None,
        script="latin",
        case=0,
    )
    info = GSGlyphInfo(raw)
    with pytest.raises(UnsupportedCapability) as caught:
        _ = info.desc
    assert caught.value.capability == "GSGlyphInfo.desc.source", (
        "Unknown is not known nil"
    )


def test_description_when_owned_html_reader_collects_tooltips_then_uses_real_info(
    owned,
):
    app, _ = owned(letters())
    infos = [app.glyphInfoForName(name) for name in ("A", "B")]
    tooltips = {info.name: info.desc for info in infos if info.desc}
    assert tooltips == {"A": "Owned first", "B": "Owned second"}, (
        "The original HTML caller's public description requirement must work"
    )
