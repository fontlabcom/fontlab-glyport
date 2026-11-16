# this_file: tests/test_composed_layers.py
"""Task3M aliases and pair workflows with owned source-only model fixtures."""

import importlib
import sys
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from test_bootstrap import host as bootstrap_host
from test_fontlab_backend_lazy import TextBlock
from test_fontlab_backend_lazy import native as backend_double

import fontlab_glyport as glyport
from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import glyphsapp_provider, make_glyphsapp_module
from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import (
    EditViewInfo,
    GlyphInfo,
    KerningClassInfo,
    LayerInfo,
    MasterInfo,
)
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def font():
    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
    )
    backend.glyph_lists["font"] += (GlyphInfo("other", "V", ("0056",)),)
    backend.layers["other", "master"] = LayerInfo("v-regular", "master", 600)
    backend.layers["glyph", "bold"] = LayerInfo("a-bold", "bold", 700)
    backend.layers["other", "bold"] = LayerInfo("v-bold", "bold", 800)
    backend.edit_views["font"] = EditViewInfo(
        (("V", "A", "V"), (), ("A",)), "V", "Regular", "tab"
    )
    return Model(backend).font


@pytest.mark.parametrize("master,name", [("master", "Regular"), ("bold", "Bold")])
def test_composed_layers_when_read_then_order_repetition_live_identity_and_no_edits(
    font, master, name
):
    backend = font._model._backend
    backend.edit_views[font.id] = replace(backend.edit_views[font.id], master=name)
    tab = font.currentTab
    expected = [font.glyphs[g].layers[master] for g in ("V", "A", "V", "A")]
    before, revision = deepcopy(dict(backend.layers)), backend.revision(font.id)
    layers = tab.composedLayers
    assert layers == tab.layers == expected, "Preserve displayed order and repetitions"
    assert all(a is b for a, b in zip(layers, expected, strict=True)), (
        "Reuse live model handles"
    )
    assert layers[0] is layers[2] and layers[1] is layers[3], (
        "Repeated glyphs retain identity"
    )
    layers.clear()
    assert tab.composedLayers == expected, "Each read returns a fresh sequence"
    assert backend.layers == before and backend.revision(font.id) == revision
    assert backend.undo_events == [] and backend.edit_texts == [], (
        "Reads have no edit effects"
    )
    expected[0].width = 631
    assert tab.composedLayers[0].width == 631, "Returned layers are live, not copies"


def test_composed_layers_when_text_master_or_native_stream_changes_then_current(
    font, monkeypatch
):
    backend, tab = font._model._backend, font.currentTab
    retained = tab.composedLayers[0]

    def set_text(font_id, lines):
        backend.edit_views[font_id] = replace(backend.edit_views[font_id], lines=lines)

    monkeypatch.setattr(backend, "set_edit_glyphs", set_text)
    tab.text = "AA\nV"
    assert tab.composedLayers == [
        font.glyphs[g].layers["master"] for g in ("A", "A", "V")
    ]
    backend.edit_views[font.id] = replace(backend.edit_views[font.id], master="Bold")
    assert tab.composedLayers == [
        font.glyphs[g].layers["bold"] for g in ("A", "A", "V")
    ]
    assert retained is font.glyphs["V"].layers["master"], (
        "Master switches retain old live handles"
    )
    backend.edit_views[font.id] = replace(backend.edit_views[font.id], lines=(("V",),))
    assert tab.composedLayers == [font.glyphs["V"].layers["bold"]], (
        "Use the current backend stream"
    )


def test_composed_layers_when_native_api_double_then_display_stream_not_symbol_input(
    monkeypatch,
):
    module, _calls, package, _other = backend_double.__wrapped__(monkeypatch)
    package.master = "Master 3"
    block = TextBlock(package, ["glyph2", "glyph0", "glyph2"], lines=[0, 0, 1])
    block.symbolList = lambda: SimpleNamespace(
        symbols=lambda: [SimpleNamespace(cr=True)]
    )
    workspace = module.flWorkspace.instance()
    workspace.getActiveTextBlock = lambda: block
    module.flWorkspace = SimpleNamespace(instance=lambda: workspace)
    font = Model(FontLabBackend()).fonts[0]
    layers = font.currentTab.composedLayers
    assert [layer.parent.name for layer in layers] == ["glyph2", "glyph0", "glyph2"], (
        "Use getAllGlyphs, retaining order and repetition"
    )
    assert all(layer.associatedMasterId == font.masters[3].id for layer in layers)
    assert layers[0] is layers[2] is font.glyphs["glyph2"].layers[font.masters[3].id]


@pytest.mark.parametrize("lines", [(), ((),), ((), (), ())])
def test_composed_layers_when_empty_then_empty_fresh_read_only_sequence(font, lines):
    backend = font._model._backend
    backend.edit_views[font.id] = replace(backend.edit_views[font.id], lines=lines)
    tab = font.currentTab
    assert tab.composedLayers == [] and tab.composedLayers is not tab.composedLayers
    with pytest.raises(UnsupportedCapability):
        tab.composedLayers = [font.glyphs["A"].layers[0]]
    assert backend.edit_texts == [], "The deprecated alias has no setter"


@pytest.mark.parametrize("stale", ["closed-tab", "replaced-tab", "closed-font"])
def test_composed_layers_when_stale_then_same_refusal_as_layers(font, stale):
    backend, tab = font._model._backend, font.currentTab
    if stale == "closed-tab":
        del backend.edit_views[font.id]
    elif stale == "replaced-tab":
        backend.edit_views[font.id] = replace(backend.edit_views[font.id], id="another")
    else:
        backend.close_font(font.id)
    for attribute in ("layers", "composedLayers"):
        with pytest.raises(StaleNativeObject):
            getattr(tab, attribute)


def test_ltr_when_scoped_import_and_cleanup_then_public_alias_and_module_restoration(
    font, tmp_path
):
    before = sys.modules.get("GlyphsApp")
    context = ExecutionContext(tmp_path, "glyphs3")
    context.adapters["GlyphsApp"] = glyphsapp_provider(
        font._model, FakeGlyphsBridge(), error_sink=print
    )
    script = tmp_path / "owned_import.py"
    script.write_text(
        "from GlyphsApp import LTR, GSLTR\nfrom GlyphsApp import *\nassert LTR == GSLTR == 0\n"
    )
    try:
        for _ in range(2):
            assert context.run(script).status == "passed", (
                "Scoped explicit and wildcard imports resolve LTR"
            )
            with context:
                module = context.import_module("GlyphsApp")
                assert module.LTR == module.GSLTR == 0, (
                    "The official legacy LTR value is zero"
                )
                assert "LTR" in module.__all__, "Wildcard imports must export the alias"
            assert sys.modules.get("GlyphsApp") is before, (
                "Restore the prior module identity"
            )
    finally:
        context.close()


def test_ltr_when_ordinary_activation_then_explicit_star_import_and_reactivation(
    font, monkeypatch
):
    fixture = bootstrap_host.__wrapped__(monkeypatch)
    modules, _closed = next(fixture)
    modules["GlyphsApp"] = make_glyphsapp_module(
        font._model, FakeGlyphsBridge(), error_sink=print
    )
    before = sys.modules.get("GlyphsApp")
    try:
        for _ in range(2):
            namespace = {}
            handle = glyport.activate(namespace=namespace)
            module = importlib.import_module("GlyphsApp")
            imports = {}
            exec(  # noqa: S102 - ordinary imports from owned literal test source
                "from GlyphsApp import LTR, GSLTR\nfrom GlyphsApp import *", imports
            )
            assert namespace["LTR"] == imports["LTR"] == module.GSLTR == 0
            assert "LTR" in module.__all__, "Ordinary activation exports the alias"
            handle.close()
            assert namespace == {}, "Cleanup restores caller globals"
            assert sys.modules.get("GlyphsApp") is before, (
                "Cleanup restores module identity"
            )
    finally:
        fixture.close()


def test_composed_pair_minimum_width_update_and_remove_across_masters_preserve_other_pairs(
    font,
):
    module = make_glyphsapp_module(font._model, FakeGlyphsBridge(), error_sink=print)
    backend = font._model._backend
    backend.kerning_class_data[font.id] = (
        KerningClassInfo("A-side", ("A",), left=True),
        KerningClassInfo("V-side", ("V",), right=True),
    )
    backend.edit_views[font.id] = replace(
        backend.edit_views[font.id], lines=(("A", "V", "A"),)
    )
    group_pair = ("@MMK_L_A-side", "@MMK_R_V-side")
    for master in font.masters:
        for pair, value in ((group_pair, -70), (("A", "V"), -25), (("V", "A"), -10)):
            font.setKerningForPair(master.id, *pair, value, direction=module.LTR)
    left, right, _ = font.currentTab.composedLayers
    pair = (left.parent.rightKerningKey, right.parent.leftKerningKey)
    assert pair == group_pair, "Use the existing public group-key contract"
    minimum_width = 1200
    font.setKerningForPair(
        left.associatedMasterId,
        *pair,
        minimum_width - left.width - right.width,
        direction=module.LTR,
    )
    assert font.kerningForPair("master", *pair) == 100, (
        "Update only the selected master's key"
    )
    assert font.kerningForPair("bold", *pair) == -70, "Other masters are isolated"
    assert left.nextKerningForLayer_direction_(right, module.LTR) == -25, (
        "Glyph exceptions take precedence"
    )
    for master in font.masters:
        font.removeKerningForPair(master.id, *pair, direction=module.LTR)
        assert font.kerningForPair(master.id, *pair) is None
        assert backend.kerning_data[font.id, master.id] == {
            ("A", "V"): -25,
            ("V", "A"): -10,
        }, "Removing a group pair preserves glyph pairs"


@pytest.mark.parametrize("direction", [1, 2, 4, 8])
@pytest.mark.parametrize(
    "method", ["kerningForPair", "setKerningForPair", "removeKerningForPair"]
)
def test_ltr_alias_does_not_relax_non_ltr_kerning_refusal(font, direction, method):
    font.setKerningForPair("master", "A", "V", -50)
    before = deepcopy(dict(font._model._backend.kerning_data))
    arguments = (
        ("master", "A", "V", -10)
        if method == "setKerningForPair"
        else ("master", "A", "V")
    )
    with pytest.raises(UnsupportedCapability):
        getattr(font, method)(*arguments, direction=direction)
    assert font._model._backend.kerning_data == before, (
        "Unsupported directions never mutate pairs"
    )
