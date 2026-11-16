# this_file: tests/test_glyph_info_case.py
"""Glyph Info case uses database metadata, not Unicode general categories."""

from types import SimpleNamespace

import pytest
from glyphsLib import glyphdata

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.application import GSApplication
from fontlab_glyport.glyphsapp.glyph_info import GSGlyphInfo


@pytest.fixture
def app():
    return GSApplication(
        SimpleNamespace(font=None), object(), {}, None, lambda *args: None
    )


@pytest.mark.parametrize(
    "name, expected",
    [
        ("A", 1),
        ("uni0041", 1),
        ("a", 2),
        ("f_f_i", 2),
        ("acutecomb", 2),
        ("exclam", 1),
        ("less", 2),
        ("alef-ar", 0),
        ("ka-deva", 0),
        ("ordfeminine", 4),
    ],
)
def test_database_case_preserves_non_unicode_classification(app, name, expected):
    assert app.glyphInfoForName(name).case == expected


@pytest.mark.parametrize(
    "label, expected",
    [
        (None, 0),
        ("noCase", 0),
        ("upper", 1),
        ("lower", 2),
        ("smallCaps", 3),
        ("minor", 4),
        ("other", 5),
    ],
)
def test_explicit_database_case_values(app, monkeypatch, label, expected):
    glyphdata.get_glyph("A")
    attrs = dict(glyphdata.GLYPHDATA.names["A"])
    if label is None:
        attrs.pop("case", None)
    else:
        attrs["case"] = label
    data = glyphdata.GLYPHDATA
    names = dict(data.names, A=attrs)
    monkeypatch.setattr(
        glyphdata,
        "GLYPHDATA",
        glyphdata.GlyphData(
            names, data.alternative_names, data.production_names, data.unicodes
        ),
    )
    assert app.glyphInfoForName("A").case == expected


def test_unknown_database_case_is_not_silently_uncased(app, monkeypatch):
    glyphdata.get_glyph("A")
    attrs = dict(glyphdata.GLYPHDATA.names["A"], case="future-case")
    data = glyphdata.GLYPHDATA
    names = dict(data.names, A=attrs)
    monkeypatch.setattr(
        glyphdata,
        "GLYPHDATA",
        glyphdata.GlyphData(
            names, data.alternative_names, data.production_names, data.unicodes
        ),
    )
    with pytest.raises(UnsupportedCapability) as error:
        app.glyphInfoForName("A")
    assert error.value.capability == "GSGlyphInfo.case"


def test_case_snapshot_is_read_only():
    glyph = SimpleNamespace(
        name="A",
        unicode="0041",
        category="Letter",
        subCategory=None,
        script="latin",
        case=5,
    )
    info = GSGlyphInfo(glyph)
    glyph.case = 1
    assert info.case == 5
    with pytest.raises(UnsupportedCapability):
        info.case = 2
    assert info.case == 5


def test_global_case_does_not_read_active_font(app):
    app._model.font = SimpleNamespace(glyphs={"A": SimpleNamespace(case=2)})
    assert app.glyphInfoForName("A").case == 1
