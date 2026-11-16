# this_file: tests/test_issue106_round30.py
"""Measured in-process MCP tuple sequences and positional native renames."""

import json
from collections import UserList
from pathlib import Path

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model.creation import glyph_json


def native_sequences(value):
    if isinstance(value, dict):
        return {key: native_sequences(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(native_sequences(item) for item in value)
    return value


@pytest.mark.parametrize("envelope", [False, True])
def test_measured_aacute_tuple_payload_normalizes_recursively(envelope):
    data = json.loads(
        (Path(__file__).parent / "fixtures/issue106_Aacute.json").read_text()
    )
    data["lastModified"] = "2026-10-16 12:34:02"
    raw = native_sequences(data)
    assert isinstance(raw["layers"], tuple)
    assert isinstance(raw["layers"][0]["elements"], tuple)
    assert isinstance(raw["layers"][0]["anchors"], tuple)
    result = glyph_json({"glyph": raw} if envelope else raw)
    assert result == data
    result["layers"][0]["elements"].clear()
    assert len(raw["layers"][0]["elements"]) == 2, "Snapshot must be independent"


def test_non_string_sequence_is_accepted_as_json_array():
    assert glyph_json({"layers": UserList([{"anchors": UserList([])}])}) == {
        "layers": [{"anchors": []}]
    }


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_native_rename_rejecting_all_keywords_is_supported(native):
    def rename(record, name, replace, /):
        native.glyph.name = name
        return True

    native.package.renameGlyph = rename
    native.backend.rename_glyph(native.font._id, native.gid, "B.pos")
    assert native.glyph.name == "B.pos"


@pytest.mark.parametrize("unicodes", [[], [0x41], [0x41, 0x391]])
def test_native_rename_preserves_original_unicode_list_in_same_undo_step(
    native, unicodes
):
    record = native.glyph.fgGlyph
    record.unicodes = list(unicodes)

    def rename(record, name, replace=True, **kwargs):
        native.glyph.name = name
        record.unicodes = [0x42]  # FontLab derives a new encoding from the name.
        return True

    native.package.renameGlyph = rename
    with native.font.undo_group("Rename"):
        native.backend.rename_glyph(native.font._id, native.gid, "B")
    assert record.unicodes == unicodes
    assert [call[0] for call in native.calls] == ["Rename", "Rename"]
