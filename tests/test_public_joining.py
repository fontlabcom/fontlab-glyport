# this_file: tests/test_public_joining.py
"""Versioned public joining facts retain exact calibrated and unknown domains."""

import hashlib
import json
import xml.etree.ElementTree as ET
from importlib.resources import files
from pathlib import Path

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import public_joining
from fontlab_glyport.model.public_joining import positional_kind


@pytest.mark.parametrize(
    "name,expected",
    [
        ("alef-ar", "R"),
        ("alef-ar.fina.alt", "R"),
        ("beh-ar", "D"),
        ("beh-ar.alt", "D"),
        ("hamza-ar", "D"),
        ("A", "D"),
    ],
)
def test_public_name_when_calibrated_then_classifies_only_right_versus_other(
    name, expected
):
    assert positional_kind(name) == expected


@pytest.mark.parametrize(
    "name",
    ["OwnedUnrepresented", "alaph-syriac", "alefBottomrightkasraattached-ar", ""],
)
def test_name_when_outside_complete_right_set_then_takes_retained_nonright_branch(name):
    assert positional_kind(name) == "D", (
        "Complete R-set equivalence proves the non-R default"
    )


def test_public_table_when_all_encoded_names_checked_then_matches_independent_unicode_facts():
    data = Path(__file__).parent / "data/ArabicShaping-17.0.0.txt"
    raw = data.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "39afa01e680e27d0fd10b67a9b27be13fbaa3d0efecfb5be45991de9a0d267d0"
    )
    right = {
        int(parts[0].strip(), 16)
        for line in raw.decode().splitlines()
        if (parts := line.split("#", 1)[0].split(";"))
        and len(parts) == 4
        and parts[2].strip() == "R"
    }
    records = {}
    expected = {
        "GlyphData.xml": "0a966c73af0c104a8f402f80bb72a3f9df7bc1e8be7c031c2a5a692ddd7f6ca7",
        "GlyphData_Ideographs.xml": "db4d907031db709c2e9ee709f6075b20812799ef07591071344ba558d60e46ba",
    }
    for name, digest in expected.items():
        source = (files("glyphsLib.data") / name).read_bytes()
        assert hashlib.sha256(source).hexdigest() == digest
        records.update(
            {node.attrib["name"]: node.attrib for node in ET.fromstring(source)}
        )
    calibration = json.loads(
        files("fontlab_glyport")
        .joinpath("data", "unicode17_positional_right.json")
        .read_text()
    )
    excluded = set(calibration["unicode_right_names_outside_retained_predicate"])
    assert len(excluded) == 49
    checked = 0
    for name in sorted({name.split(".", 1)[0] for name in records}):
        row = records.get(name)
        if row is None or not row.get("unicode"):
            continue
        actual = positional_kind(name)
        assert actual == (
            "R" if int(row["unicode"], 16) in right and name not in excluded else "D"
        ), name
        checked += 1
    assert checked == 69900


@pytest.mark.parametrize("payload", [None, b"{}"])
def test_resource_when_missing_or_changed_then_refuses_instead_of_defaulting_every_name(
    monkeypatch, payload
):
    class BrokenResource:
        def joinpath(self, *parts):
            return self

        def read_bytes(self):
            if payload is None:
                raise OSError("owned missing fixture")
            return payload

    public_joining._right_names.cache_clear()
    monkeypatch.setattr(
        public_joining.resources, "files", lambda name: BrokenResource()
    )
    try:
        with pytest.raises(UnsupportedCapability) as error:
            positional_kind("alef-ar")
        assert error.value.capability == "GSGlyphInfo.compound.joiningData"
    finally:
        public_joining._right_names.cache_clear()


def test_positional_kind_when_nontext_then_keeps_input_boundary_explicit():
    with pytest.raises(TypeError, match="string"):
        positional_kind(None)
