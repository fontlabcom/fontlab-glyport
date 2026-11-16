# this_file: tests/test_unicode_index.py
"""Public XML and owned collisions independently pin the retained parser index."""

import hashlib
import json
import xml.etree.ElementTree as ET
from importlib.resources import files
from types import SimpleNamespace as NS

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import glyph_metadata


class Unreadable:
    def __getattribute__(self, name):
        raise AssertionError("Global Unicode lookup must never inspect the active font")


@pytest.fixture
def app():
    return make_glyphsapp_module(
        NS(font=Unreadable()),
        object(),
        profile="glyphs3",
        defaults={},
        error_sink=lambda *args: None,
    ).Glyphs


@pytest.fixture(scope="module")
def public_index():
    expected = {}
    primary, legacy = {}, {}
    paths = files("glyphsLib.data")
    for filename, digest in [
        (
            "GlyphData.xml",
            "0a966c73af0c104a8f402f80bb72a3f9df7bc1e8be7c031c2a5a692ddd7f6ca7",
        ),
        (
            "GlyphData_Ideographs.xml",
            "db4d907031db709c2e9ee709f6075b20812799ef07591071344ba558d60e46ba",
        ),
    ]:
        raw = (paths / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, "Review changed public input"
        for element in ET.fromstring(raw):
            attrs = element.attrib
            for field, separate in [("unicode", primary), ("unicodeLegacy", legacy)]:
                if field in attrs:
                    expected[attrs[field]] = attrs
                    separate[attrs[field]] = attrs
    assert (len(primary), len(legacy), len(expected)) == (71401, 730, 72131)
    relation = sorted((code, attrs["name"]) for code, attrs in expected.items())
    # Same independently pinned JSON encoding as the completed public contract.
    digest = hashlib.sha256(
        json.dumps(relation, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == "2bfce5c9914c1cfbbb28e654b7b5f42edbe23382f7ebea8994e7112124236cfe"
    return expected, primary, legacy


def fields(record):
    return record.name, record.unicode, record.unicodeLegacy


def expected_fields(attrs):
    return attrs["name"], attrs.get("unicode"), attrs.get("unicodeLegacy")


def test_shared_unicode_when_all_public_keys_then_matches_pinned_xml(public_index):
    expected, _, _ = public_index
    mismatches = []
    for code, attrs in expected.items():
        record = glyph_metadata.unicode_info(code)
        if record is None or fields(record) != expected_fields(attrs):
            mismatches.append(
                (code, attrs["name"], None if record is None else fields(record))
            )
    assert not mismatches, (
        f"{len(mismatches)} shared index mismatches: {mismatches[:5]}"
    )


def test_global_unicode_when_all_public_keys_then_preserves_primary_and_legacy(
    app, public_index
):
    expected, _, _ = public_index
    mismatches = []
    for code, attrs in expected.items():
        record = app.glyphInfoForUnicode(code)
        if record is None or fields(record) != expected_fields(attrs):
            mismatches.append(
                (code, attrs["name"], None if record is None else fields(record))
            )
    assert not mismatches, (
        f"{len(mismatches)} snapshot index mismatches: {mismatches[:5]}"
    )


@pytest.mark.parametrize(
    "code,name", [("FE8D", "alef-ar.isol"), ("FE80", "hamza-ar.isol"), ("0000", "NULL")]
)
def test_unicode_when_known_legacy_then_metadata_is_not_synthesized(app, code, name):
    info = app.glyphInfoForUnicode(code)
    direct = app.glyphInfoForName(name)
    assert fields(info) == fields(direct) == (name, None, code)
    assert (info.category, info.subCategory, info.script, info.case) == (
        direct.category,
        direct.subCategory,
        direct.script,
        direct.case,
    ), "Legacy records retain their own metadata without promoting the lookup key"


def owned_data(monkeypatch, records):
    glyphdata.get_glyph("A")
    names = {record["name"]: record for record in records}
    primary = {record["unicode"]: record for record in records if "unicode" in record}
    data = glyphdata.GlyphData(names, {}, {}, primary)
    monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
    return data


@pytest.mark.parametrize("last_field", ["unicode", "unicodeLegacy"])
def test_unicode_when_primary_and_legacy_collide_then_last_record_wins(
    app, monkeypatch, last_field
):
    first_field = "unicodeLegacy" if last_field == "unicode" else "unicode"
    records = [
        {"name": "ownedFirst", "category": "Letter", first_field: "E123"},
        {"name": "ownedLast", "category": "Symbol", last_field: "E123"},
    ]
    data = owned_data(monkeypatch, records)
    before = json.dumps([data.names, data.unicodes], sort_keys=True)
    expected = expected_fields(records[-1])
    assert fields(glyph_metadata.unicode_info("E123")) == expected
    assert fields(app.glyphInfoForUnicode("E123")) == expected
    assert json.dumps([data.names, data.unicodes], sort_keys=True) == before


def test_unicode_when_data_identity_replaced_then_rebuilds_index(app, monkeypatch):
    first = owned_data(
        monkeypatch,
        [{"name": "ownedOne", "category": "Letter", "unicodeLegacy": "E123"}],
    )
    assert app.glyphInfoForUnicode("E123").name == "ownedOne"
    second = owned_data(
        monkeypatch,
        [{"name": "ownedTwo", "category": "Symbol", "unicodeLegacy": "E123"}],
    )
    assert first is not second, "Memoization must be keyed by the actual data identity"
    assert app.glyphInfoForUnicode("E123").name == "ownedTwo"
    monkeypatch.setattr(glyphdata, "GLYPHDATA", first)
    assert app.glyphInfoForUnicode("E123").name == "ownedOne"


def test_legacy_raw_view_and_copy_preserve_canonical_component_identity(
    app,
    monkeypatch,
    owned_info_manager,
):
    from copy import copy

    from fontlab_glyport.glyphsapp import GSGlyphsInfo

    selected = owned_info_manager(
        [
            {"name": "A", "unicode": "0041", "category": "Letter"},
            {
                "name": "acutecomb",
                "unicode": "0301",
                "category": "Mark",
                "subCategory": "Nonspacing",
            },
            {
                "name": "Aacute",
                "unicode": "00C1",
                "category": "Letter",
                "decompose": "A, acutecomb",
            },
        ]
    )
    # This controlled raw-index field models the bundled parser's independent
    # legacy key. Custom XML merging itself does not parse unicodeLegacy.
    record = selected._index.raw_name("Aacute")
    record.unicodeLegacy = "E123"
    selected._index.unicodes["E123"] = record
    selected.updateComponentsInfos()
    monkeypatch.setattr(GSGlyphsInfo, "_shared", selected)
    first, second = app.glyphInfoForUnicode("E123"), app.glyphInfoForUnicode("E123")
    assert fields(first) == ("Aacute", "00C1", "E123")
    assert first is second, "Raw manager hits preserve canonical public-view identity"
    frozen = copy(first)
    assert frozen is not first and fields(frozen) == fields(first)
    assert [part.name for part in first.components] == ["A", "acutecomb"]
    assert all(a is b for a, b in zip(first.components, frozen.components)), (
        "Native record copying retains shallow component references"
    )
    first.components.clear()
    assert [part.name for part in frozen.components] == ["A", "acutecomb"]
    with pytest.raises(UnsupportedCapability):
        first.unicodeLegacy = "changed"
    record.unicodeLegacy = "E124"
    assert fields(first) == ("Aacute", "00C1", "E124")
    assert fields(frozen) == ("Aacute", "00C1", "E123"), (
        "Explicit copy freezes scalars while the raw view observes its record"
    )


def test_unicode_when_raw_spelling_differs_then_only_exact_uppercase_key_matches(app):
    assert fields(app.glyphInfoForUnicode("fe8d")) == ("alef-ar.isol", None, "FE8D")
    assert fields(app.glyphInfoForUnicode("0FE8D")) == ("uni0FE8D", "0FE8D", None)
    assert app.glyphInfoForUnicode("000").name != "NULL", (
        "Do not zero-pad before lookup"
    )
    assert app.glyphInfoForUnicode("00") is None, "Retain the minimum UTF16 gate"
    assert fields(glyph_metadata.unicode_info("fe8d")) == ("unife8d", "fe8d", None)
    assert fields(app.glyphInfoForName(0xFE8D, font=Unreadable())) == (
        "alef-ar.isol",
        None,
        "FE8D",
    )


def test_unicode_when_dependency_missing_then_refuses_without_synthesis(
    app, monkeypatch
):
    import sys

    monkeypatch.setitem(sys.modules, "glyphsLib", None)
    with pytest.raises(UnsupportedCapability) as error:
        app.glyphInfoForUnicode("FE8D")
    assert error.value.capability == "GSGlyph.categories.dependency"


def test_unicode_when_full_public_queries_finish_then_dependency_bytes_unchanged(
    app, public_index
):
    glyphdata.get_glyph("A")
    data = glyphdata.GLYPHDATA
    before = json.dumps(
        [data.names, data.alternative_names, data.production_names, data.unicodes],
        sort_keys=True,
    )
    for code in public_index[2]:
        app.glyphInfoForUnicode(code)
    assert (
        json.dumps(
            [data.names, data.alternative_names, data.production_names, data.unicodes],
            sort_keys=True,
        )
        == before
    )
