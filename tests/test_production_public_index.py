# this_file: tests/test_production_public_index.py
"""Independent raw XML oracles for ordered name and raw-production indices."""

import hashlib
import json
import xml.etree.ElementTree as ET
from importlib.resources import files
from types import SimpleNamespace as NS

from glyphsLib import glyphdata

from fontlab_glyport.glyphsapp import GSApplication


def public(monkeypatch):
    glyphdata.get_glyph("A")
    original = glyphdata.GLYPHDATA
    data = glyphdata.GlyphData(
        original.names,
        original.alternative_names,
        original.production_names,
        original.unicodes,
    )
    monkeypatch.setattr(glyphdata, "GLYPHDATA", data)
    records = []
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
        raw = (files("glyphsLib.data") / filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, "Review changed public data"
        records.extend(item.attrib for item in ET.fromstring(raw))
    assert len(records) == 74247
    app = GSApplication(NS(font=None), object(), {}, None, lambda *a: None)
    return app, records, data


def test_public_names_when_parser_order_applied_then_all_global_queries_match(
    monkeypatch,
):
    app, records, data = public(monkeypatch)
    expected = {}
    aliases = {}
    for row in records:
        expected[row["name"]] = row
        production = row.get("production")
        if production is not None and not production.startswith("uni"):
            expected[production] = row
        for token in row.get("altNames", "").split(","):
            alias = token.strip(" ")
            assert " " not in alias, "Review a public alias with internal spaces"
            if alias:
                aliases[alias] = row["name"]
                expected[alias] = row
    assert aliases == {
        key: value["name"] for key, value in data.alternative_names.items()
    }, "Independent XML tokens must match the maintained structured alias map"
    before = hashlib.sha256(json.dumps(data.names, sort_keys=True).encode()).hexdigest()
    mismatches = []
    for name, row in expected.items():
        info = app.glyphInfoForName(name)
        if info.name != row["name"]:
            mismatches.append((name, row["name"], info.name))
        if "production" in row:
            assert info.productionName == row["production"], name
    assert not mismatches, f"Ordered name index mismatches: {mismatches[:5]}"
    assert (
        hashlib.sha256(json.dumps(data.names, sort_keys=True).encode()).hexdigest()
        == before
    )


def test_public_unicode_when_unfilled_then_every_raw_production_matches_xml(
    monkeypatch,
):
    app, records, data = public(monkeypatch)
    expected = {}
    for row in records:
        for field in ("unicode", "unicodeLegacy"):
            if field in row:
                expected[row[field]] = row
    assert len(expected) == 72131
    before = hashlib.sha256(json.dumps(data.names, sort_keys=True).encode()).hexdigest()
    for code, row in expected.items():
        info = app.glyphInfoForUnicode(code)
        assert (info.name, info.productionName) == (
            row["name"],
            row.get("production"),
        ), code
    assert (
        hashlib.sha256(json.dumps(data.names, sort_keys=True).encode()).hexdigest()
        == before
    )
