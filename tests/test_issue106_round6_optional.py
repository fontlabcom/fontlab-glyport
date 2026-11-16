# this_file: tests/test_issue106_round6_optional.py
"""A sys.path launcher must work with optional packages absent in FontLab."""

import importlib
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.glyph_info import glyph_info
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.copies import DetachedLayer
from fontlab_glyport.model.fake_backend import FakeBackend


def block(monkeypatch, name):
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            monkeypatch.setitem(sys.modules, key, None)
    monkeypatch.setitem(sys.modules, name, None)


@pytest.fixture
def private_tools(tmp_path, monkeypatch):
    """A real private import path with a small handwritten line-only pen."""
    block(monkeypatch, "fontTools")
    package = tmp_path / "fontTools"
    (package / "pens").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "pens" / "__init__.py").write_text("")
    (package / "pens" / "boundsPen.py").write_text(
        "class BoundsPen:\n"
        "    def __init__(self, glyphSet):\n        self.bounds = None\n"
        "    def moveTo(self, point):\n        self.lineTo(point)\n"
        "    def lineTo(self, point):\n"
        "        x, y = point\n"
        "        if self.bounds is None:\n            self.bounds = (x, y, x, y)\n"
        "        else:\n"
        "            a, b, c, d = self.bounds\n"
        "            self.bounds = (min(a,x), min(b,y), max(c,x), max(d,y))\n"
        "    def closePath(self):\n        pass\n"
        "    def endPath(self):\n        pass\n"
    )
    (package / "agl.py").write_text(
        "def toUnicode(name):\n    return '\u00c1' if name == 'uni00C1' else ''\n"
    )
    root = ModuleType("fontlab_private")
    root.__path__ = [str(tmp_path)]
    original = {
        k: v for k, v in sys.modules.items() if k.startswith("fontlab_private.")
    }
    for key in original:
        monkeypatch.delitem(sys.modules, key)
    monkeypatch.setitem(sys.modules, "fontlab_private", root)
    yield
    for key in list(sys.modules):
        if key.startswith("fontlab_private."):
            sys.modules.pop(key)


def test_metadata_declares_glyphdata_and_retains_legacy_optional_extra_names():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())[
        "project"
    ]
    assert "glyphslib>=6.16.1" in project["dependencies"], (
        "Ordinary installed scripts need accurate categories without another extra"
    )
    assert "glyphslib>=6.16.1" in project["optional-dependencies"]["glyphdata"], (
        "The retained installer extra must match the mandatory GlyphData bound"
    )
    assert "fonttools>=4.38" in project["optional-dependencies"]["geometry"]


def test_n1_fonttools_when_both_routes_importable_then_public_module_wins(monkeypatch):
    from fontlab_glyport.fonttools import fonttools_module

    for root in ("fontTools", "fontlab_private.fontTools"):
        module = ModuleType(root)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, root, module)
        bounds = ModuleType(root + ".pens.boundsPen")
        monkeypatch.setitem(sys.modules, bounds.__name__, bounds)
    assert (
        fonttools_module("pens.boundsPen", "test.bounds").__name__
        == "fontTools.pens.boundsPen"
    )


def test_n1_private_fonttools_when_only_bundled_path_exists_then_bounds_and_bearings_work(
    private_tools,
):
    layer = DetachedLayer()
    layer.width = 500
    layer.paths = [GSPath([GSNode((10, 20)), GSNode((110, 70))], closed=False)]
    layer.decomposeComponents()
    assert layer.bounds == ((10, 20), (100, 50))
    assert (layer.LSB, layer.RSB) == (10, 390)
    layer.LSB = 30
    layer.RSB = 60
    assert layer.bounds == ((30, 20), (100, 50)) and layer.width == 190
    assert importlib.import_module(
        "fontlab_private.fontTools.pens.boundsPen"
    ).BoundsPen.__module__.startswith("fontlab_private.")


@pytest.mark.parametrize("member", ["bounds", "LSB", "RSB", "set_LSB", "set_RSB"])
def test_n1_bounds_when_both_fonttools_routes_absent_then_precise_refusal(
    monkeypatch, member
):
    block(monkeypatch, "fontTools")
    block(monkeypatch, "fontlab_private")
    layer = DetachedLayer()
    layer.paths = [GSPath([GSNode((10, 20)), GSNode((110, 70))])]
    with pytest.raises(UnsupportedCapability) as error:
        if member.startswith("set_"):
            setattr(layer, member.removeprefix("set_"), 40)
        else:
            getattr(layer, member)
    assert error.value.capability == "DetachedLayer.bounds.dependency"
    assert "fontTools" in str(error.value) and "fontlab_private.fontTools" in str(
        error.value
    )


def test_glyph_info_when_required_database_missing_then_explicit_dependency_failure(
    monkeypatch,
):
    for name in ("fontTools", "fontlab_private", "glyphsLib"):
        block(monkeypatch, name)
    backend = FakeBackend()
    from dataclasses import replace

    layer = backend.layers["glyph", "master"]
    backend.layers["glyph", "master"] = replace(
        layer, components=(replace(layer.components[0], componentName="acutecomb"),)
    )
    font = Model(backend).font
    assert font.glyphs["A"].unicode == "0041", "Native encoding remains readable"
    with pytest.raises(UnsupportedCapability) as missing:
        glyph_info(font, "A")
    assert missing.value.capability == "GSGlyph.categories.dependency"
    for current in (font, None):
        with pytest.raises(UnsupportedCapability) as error:
            glyph_info(current, "Aacute")
        assert error.value.capability == "GSGlyph.categories.dependency"
        assert isinstance(error.value.__cause__, ImportError)
        assert "declared dependencies" in error.value.recovery_action
        assert "glyphsLib" in str(error.value)


def test_n1_unicode_name_when_raw_database_exists_then_no_agl_is_needed(
    private_tools, monkeypatch, owned_composition_info
):
    from types import SimpleNamespace

    from glyphsLib.glyphdata import GlyphData

    names = {
        name: {"name": name, "unicode": code}
        for name, code in [("Aacute", "00C1"), ("A", "0041"), ("acutecomb", "0301")]
    }
    data = GlyphData(names, {}, {}, {row["unicode"]: row for row in names.values()})

    def get(name):
        return SimpleNamespace(
            unicode={"Aacute": "00C1", "A": "0041", "acutecomb": "0301"}.get(name),
            category="Letter",
            subCategory=None,
            script={"Aacute": "latin", "A": "latin", "acutecomb": None}.get(name),
        )

    fake = ModuleType("glyphsLib")
    fake.glyphdata = SimpleNamespace(get_glyph=get, GLYPHDATA=data)
    monkeypatch.setitem(sys.modules, "glyphsLib", fake)
    info = glyph_info(None, "uni00C1")
    assert info.name == "Aacute" and info.unicode == "00C1"
    assert [c.name for c in info.components] == ["A", "acutecomb"]
    assert info.script == "latin"
    assert [c.script for c in info.components] == ["latin", None]


def test_n1_creation_when_database_misses_then_private_agl_route_is_used(
    private_tools, monkeypatch
):
    from fontlab_glyport.glyphsapp import glyph_info as metadata

    def missing(name, **kwargs):
        raise UnsupportedCapability("owned database miss", capability="owned.miss")

    monkeypatch.setattr(metadata, "_database_glyph", missing)
    assert metadata.creation_unicodes("uni00C1") == ("00C1",)
    assert (
        importlib.import_module("fontlab_private.fontTools.agl").toUnicode("uni00C1")
        == "Á"
    )
