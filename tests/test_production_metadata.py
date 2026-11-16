# this_file: tests/test_production_metadata.py
"""Stored fields and the audited GSGlyphInfo-only helper stay distinct."""

import hashlib
import json
from copy import copy
from importlib.resources import files

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.model.production_metadata import (
    StoredProduction,
    production_name,
    slot_for,
)


def test_slot_when_raw_values_then_preserves_nil_empty_equal_and_explicit():
    records = [{"name": "absent"}] + [
        {"name": f"owned{index}", "production": value}
        for index, value in enumerate((None, "", "owned2", "uniFFFF"))
    ]
    data = glyphdata.GlyphData({r["name"]: r for r in records}, {}, {}, {})
    before = copy(data.names)
    assert [slot_for(data, r).value for r in records] == [
        None,
        None,
        "",
        "owned2",
        "uniFFFF",
    ], "Slots must preserve the raw field, without library inference"
    assert data.names == before, "Reading slots must leave dependency records intact"


def test_slot_when_canonical_alias_and_copied_handle_then_sharing_is_explicit():
    attrs = {"name": "Owned", "unicode": "0041", "script": "latin"}
    data = glyphdata.GlyphData({"Owned": attrs}, {"alias": attrs}, {}, {})
    original = slot_for(data, attrs)
    detached = copy(original)
    alias = slot_for(data, dict(attrs))
    assert alias is original, "Canonical identity must share one stored slot"
    original.value = "Owned"
    assert alias.value == "Owned", "Prior handles must see a later lazy fill"
    assert detached.value is None, (
        "A copied slot retains its independently copied value"
    )
    assert "production" not in attrs, "Shared fill must never modify source attributes"
    alias.value = ""
    assert original.value == "", "An explicitly stored empty value must survive"


def test_slot_when_dataset_replaced_then_old_data_does_not_leak():
    first = glyphdata.GlyphData({"Owned": {"name": "Owned"}}, {}, {}, {})
    second = glyphdata.GlyphData(
        {"Owned": {"name": "Owned", "production": "Replacement"}}, {}, {}, {}
    )
    old = slot_for(first, first.names["Owned"])
    old.value = "Filled"
    new = slot_for(second, second.names["Owned"])
    assert new is not old, "Dataset replacement must create a distinct shared slot"
    assert new.value == "Replacement", (
        "Dataset identity must not be keyed by name alone"
    )
    assert old.value == "Filled", "Cache eviction must not invalidate existing handles"


def test_slot_when_unrequested_record_unreadable_then_creation_is_lazy():
    class Unreadable(dict):
        def get(self, *args):
            raise AssertionError("An unrequested record was read eagerly")

    attrs = {"name": "Owned"}
    data = glyphdata.GlyphData({"Owned": attrs, "other": Unreadable()}, {}, {}, {})
    assert slot_for(data, attrs).value is None, "Only the requested record may be read"


@pytest.mark.parametrize(
    "name,stored,unicode,script,expected",
    [
        ("Owner", "Explicit", None, None, "Explicit"),
        ("Owner", "Owner", "0041", "latin", "Owner"),
        ("Owner", "uniFFFF", "0041", "latin", "uni0041"),
        ("Owner", "uni0041", "0041", "latin", "uni0041"),
        ("Owner", "uni0FFFF", "0041", None, "uni0FFFF"),
        ("Owner", "uniFFF", "0041", None, "uniFFF"),
        ("Owner", "UNIFFFF", "0041", None, "UNIFFFF"),
        ("Owner", "uniFFFF", "10000", None, "uniFFFF"),
        ("Owner", "uniFFFF", None, None, "uniFFFF"),
        ("Owner", "uniFFFF", "", None, "uniFFFF"),
        ("Owner", "uni😀xx", "0041", None, "uni0041"),
        ("Owner", "uni😀xxx", "0041", None, "uni😀xxx"),
        ("Owner", "uni😀x", "0041", None, "uni😀x"),
        ("Owner", "uniFFFF", "004😀", None, "uniFFFF"),
        ("Owner.name", None, "004😀", "latin", "u004😀"),
        ("Owner", "uni\ud800xxx", "0041", None, "uni0041"),
        ("Owner.name", None, "004\ud800", "latin", "uni004\ud800"),
        ("Owner", None, "0041", "latin", "Owner"),
        ("Owner", "", "0041", "latin", "Owner"),
        ("Owner-name", None, "0041", "latin", "uni0041"),
        ("Owner.name", None, "0041", "latin", "uni0041"),
        ("Owner-name", None, "0041", "Latin", "Owner-name"),
        ("Owner-name", None, "0627", "arabic", "Owner-name"),
        ("Owner.name", None, "0627", None, "Owner.name"),
        ("Owner", None, "E000", None, "uniE000"),
        ("Owner", None, "F8FF", None, "uniF8FF"),
        ("Owner", None, "DFFF", None, "Owner"),
        ("Owner", None, "F900", None, "Owner"),
        ("Owner", None, "F0000", None, "uF0000"),
        ("Owner", None, "FFFFD", None, "uFFFFD"),
        ("Owner", None, "FFFFE", None, "Owner"),
        ("Owner", None, "100000", None, "u100000"),
        ("Owner", None, "10FFFD", None, "u10FFFD"),
        ("Owner", None, "10FFFE", None, "Owner"),
        ("Owner", None, "0000E123", None, "u0000E123"),
        ("Owner-name", None, "123", "latin", "uni123"),
        ("Owner.name", None, "10000", "latin", "u10000"),
        ("Owner.name", None, "GGGG", "latin", "uniGGGG"),
        ("Owner-name.test", None, None, None, "Ownername.test"),
        ("Owner-name.test", "", "", "latin", "Ownername.test"),
        ("---", None, None, None, "---"),
        ("", None, None, None, ""),
    ],
)
def test_production_name_when_audited_info_branch_then_returns_helper_only(
    name, stored, unicode, script, expected
):
    slot = StoredProduction(stored)
    assert production_name(name, slot.value, unicode, script) == expected, (
        "GSGlyphInfo helper must preserve raw spelling and its audited branch order"
    )
    assert slot.value == stored, "Helper output must never mutate the stored getter"


PUBLIC_CHANGED_NAMES = [
    "descender-cy",
    "tail-cy",
    "hook-cy",
    "kafDotless-ar",
    "kafDotless-ar.fina",
    "tahbelow-ar",
    "dotabove-ar",
    "dotbelow-ar",
    "dotcenter-ar",
    "twodotsverticalabove-ar",
    "twodotsverticalbelow-ar",
    "twodotsverticalcenter-ar",
    "twodotshorizontalabove-ar",
    "twodotshorizontalbelow-ar",
    "twodotshorizontalcenter-ar",
    "threedotsdownabove-ar",
    "threedotsdownbelow-ar",
    "threedotsdowncenter-ar",
    "threedotsupabove-ar",
    "threedotsupbelow-ar",
    "threedotsupcenter-ar",
    "fourdotsabove-ar",
    "fourdotsbelow-ar",
    "fourdotscenter-ar",
    "stroke-ar",
    "fourabove-ar",
    "fourcenter-ar",
    "fourbelow-ar",
    "threeabove-ar",
    "twoabove-ar",
    "ringbelow-ar",
    "wasla-ar",
    "wavyhamzaabove-ar",
    "miniKeheh-ar",
    "gafsarkashabove-ar",
    "gafsarkashcenter-ar",
    "doublestroke-ar",
    "ring-ar",
    "ringcenter-ar",
    "hamzacenter-ar",
    "vbelow-ar",
    "vinvertedbelow-ar",
    "drop-kannada",
    "dot-kannada",
    "hook-kannada",
    "kosmall-hira",
    "kosmall-kata",
    "pusmall-kata",
    "_bar-yezidi",
]


def _fingerprints(data):
    return [
        hashlib.sha256(
            json.dumps(getattr(data, field), sort_keys=True).encode()
        ).hexdigest()
        for field in ("names", "alternative_names", "production_names", "unicodes")
    ]


def test_public_when_all49_changed_fallbacks_then_raw_nil_and_source_unchanged():
    glyphdata.get_glyph("A")
    public = glyphdata.GLYPHDATA
    data = glyphdata.GlyphData(
        public.names, public.alternative_names, public.production_names, public.unicodes
    )
    resource = files("glyphsLib.data")
    expected_hashes = {
        "GlyphData.xml": "0a966c73af0c104a8f402f80bb72a3f9df7bc1e8be7c031c2a5a692ddd7f6ca7",
        "GlyphData_Ideographs.xml": "db4d907031db709c2e9ee709f6075b20812799ef07591071344ba558d60e46ba",
    }
    before = _fingerprints(data)
    assert len(PUBLIC_CHANGED_NAMES) == 49, "Keep the full audited fallback matrix"
    for name in PUBLIC_CHANGED_NAMES:
        attrs = data.names[name]
        assert "production" not in attrs, f"Review changed public field: {name}"
        slot = slot_for(data, attrs)
        assert slot.value is None, f"Raw missing field must remain nil: {name}"
        expected = name.replace("-", "")
        assert (
            production_name(name, None, attrs.get("unicode"), attrs.get("script"))
            == expected
        )
        slot.value = expected
        assert slot_for(data, attrs).value == expected, f"Shared fill was lost: {name}"
    assert _fingerprints(data) == before, (
        "All four public dictionaries must remain intact"
    )
    for filename, digest in expected_hashes.items():
        assert (
            hashlib.sha256((resource / filename).read_bytes()).hexdigest() == digest
        ), f"Public source bytes changed: {filename}"
