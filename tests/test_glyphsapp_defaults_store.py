# this_file: tests/test_glyphsapp_defaults_store.py
"""Persisted ``Glyphs.defaults`` store (R019): JSON file, explicit conversions."""

import json

import pytest

from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.glyphsapp.defaults import JsonFileStore


def _glyphs(store):
    return make_glyphsapp_module(
        None, object(), defaults=store, error_sink=lambda e, ev: None
    ).Glyphs


def test_json_store_when_written_then_survives_a_new_store(tmp_path):
    path = tmp_path / "glyport" / "defaults.json"
    glyphs = _glyphs(JsonFileStore(path))
    glyphs.defaults["com.example.size"] = 12
    glyphs.boolDefaults["com.example.on"] = True
    glyphs.defaults["com.example.pair"] = (1, (2, 3))
    glyphs.registerDefault("com.example.reg", {"a": [1]})
    again = _glyphs(JsonFileStore(path))
    assert again.defaults["com.example.size"] == 12
    assert again.boolDefaults["com.example.on"] is True
    # Documented conversion: tuples are stored (and read back) as lists.
    assert again.defaults["com.example.pair"] == [1, [2, 3]]
    assert again.defaults["com.example.reg"] == {"a": [1]}
    assert json.loads(path.read_text())["com.example.size"] == 12


def test_json_store_when_value_not_json_then_type_error_and_nothing_written(tmp_path):
    path = tmp_path / "defaults.json"
    store = JsonFileStore(path)
    store["com.example.ok"] = 1
    for bad in ({1: "int key"}, {"x": object()}, b"bytes", float("nan")):
        with pytest.raises(TypeError):
            store["com.example.bad"] = bad
    assert json.loads(path.read_text()) == {"com.example.ok": 1}


def test_json_store_when_deleted_then_removed_from_file(tmp_path):
    path = tmp_path / "defaults.json"
    glyphs = _glyphs(JsonFileStore(path))
    glyphs.defaults["com.example.a"] = "v"
    glyphs.defaults["com.example.a"] = None
    assert json.loads(path.read_text()) == {}
    assert JsonFileStore(path).get("com.example.a") is None


def test_json_store_when_file_corrupt_then_fails_loudly(tmp_path):
    path = tmp_path / "defaults.json"
    path.write_text("{not json")
    with pytest.raises(ValueError):
        JsonFileStore(path)


def test_json_store_when_file_missing_then_empty_and_not_created_by_reads(tmp_path):
    path = tmp_path / "defaults.json"
    store = JsonFileStore(path)
    assert store.get("com.example.x") is None and len(store) == 0
    assert not path.exists()


def test_default_path_when_env_unset_then_glyport_folder_outside_fontlab_9(
    monkeypatch, tmp_path
):
    from fontlab_glyport.glyphsapp.defaults import default_defaults_path

    monkeypatch.delenv("GLYPORT_DEFAULTS", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    path = default_defaults_path()
    assert (
        path == tmp_path / "Library/Application Support/FontLab/Glyport/defaults.json"
    )
    assert not path.parent.exists(), "created lazily, on the first write only"


def test_default_path_when_env_set_then_override(monkeypatch, tmp_path):
    from fontlab_glyport.glyphsapp.defaults import default_defaults_path

    monkeypatch.setenv("GLYPORT_DEFAULTS", str(tmp_path / "x.json"))
    assert default_defaults_path() == tmp_path / "x.json"


def test_color_defaults_when_ns_color_written_then_rgba_stored_and_color_read(tmp_path):
    """R049 custom-nsview (Waterfall): Glyphs.colorDefaults[key] = NSColor;
    stored as an [r, g, b, a] list, read back as an NSColor."""
    from fontlab_glyport.drawing.cocoa_drawing import NSColor

    path = tmp_path / "defaults.json"
    glyphs = _glyphs(JsonFileStore(path))
    glyphs.colorDefaults["com.example.fore"] = NSColor(0, 0.5, 1, 1)
    again = _glyphs(JsonFileStore(path))
    assert again.colorDefaults["com.example.fore"] == NSColor(0, 0.5, 1, 1)
    assert again.defaults["com.example.fore"] == [0, 0.5, 1, 1]
    assert again.colorDefaults["missing"] is None
    with pytest.raises(TypeError):
        glyphs.colorDefaults["com.example.bad"] = "red"
