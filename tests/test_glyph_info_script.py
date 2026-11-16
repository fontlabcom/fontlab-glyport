# this_file: tests/test_glyph_info_script.py
"""Glyph Info snapshots preserve the script supplied by their metadata source."""

from types import SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.glyphsapp.glyph_info import GSGlyphInfo
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def app():
    return make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    ).Glyphs


@pytest.mark.parametrize(
    "name, expected",
    [
        ("A", "latin"),
        ("uni0041", "latin"),
        ("f_f_i", "latin"),
        ("acutecomb", None),
        ("alef-ar", "arabic"),
        ("ka-deva", "devanagari"),
        ("Alpha", "greek"),
        ("alpha", "greek"),
        ("A-cy", "cyrillic"),
    ],
)
def test_global_glyph_info_script_comes_from_database(app, name, expected):
    assert app.glyphInfoForName(name).script == expected


def test_global_script_ignores_active_glyph_override(app):
    glyph = app.font.glyphs["A"]
    glyph.script = "custom-script"
    assert glyph.script == "custom-script"
    assert app.glyphInfoForName("A").script == "latin"
    assert app.glyphInfoForName("A", None).script == "latin"
    assert glyph.script == "custom-script"


def test_font_metadata_script_is_snapshotted(app):
    font = app.font
    glyph = font.glyphs["A"]
    glyph.script = "custom-script"
    info = GSGlyphInfo(glyph)
    glyph.script = "replacement"
    assert info.script == "custom-script"
    assert GSGlyphInfo(glyph).script == "replacement"


@pytest.mark.parametrize("script", [None, "", "latin"])
def test_script_snapshot_preserves_scalar_and_is_read_only(script):
    glyph = SimpleNamespace(
        name="A",
        unicode="0041",
        category="Letter",
        subCategory=None,
        script=script,
        case=1,
    )
    info = GSGlyphInfo(glyph)
    glyph.script = "changed"
    assert info.script == script
    with pytest.raises(UnsupportedCapability) as error:
        info.script = "greek"
    assert error.value.capability == "GSGlyphInfo.script"
    assert info.script == script
