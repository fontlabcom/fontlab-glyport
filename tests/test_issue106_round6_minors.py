# this_file: tests/test_issue106_round6_minors.py
"""Small compatibility corrections from the round-five review."""

from types import SimpleNamespace

import pytest
from plugin_doubles import FakeHost

from fontlab_glyport.model import GSLayer, Model
from fontlab_glyport.model.backend import (
    ComponentInfo,
    GlyphInfo,
    LayerInfo,
    NodeInfo,
    PathInfo,
)
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin


@pytest.mark.parametrize("layer_id", ["brace-layer", "bracket-layer", "backup-layer"])
def test_l4_component_copy_when_special_layer_has_unique_id_then_use_associated_master(
    layer_id,
):
    class SpecialLayer(GSLayer):
        layerId = property(lambda self: layer_id)
        associatedMasterId = property(lambda self: "master")

    backend = FakeBackend()
    backend.glyph_lists["font"] += (GlyphInfo("base", "base", ()),)
    base = PathInfo("base-path", (NodeInfo("bn1", 2, 4), NodeInfo("bn2", 20, 8)), False)
    backend.layers["base", "master"] = LayerInfo(
        "base-layer", "master", 100, (base,), shape_ids=("base-path",)
    )
    from dataclasses import replace

    backend.layers["glyph", "master"] = replace(
        backend.layers["glyph", "master"],
        components=(ComponentInfo("component", "base", (1, 0, 0, 1, 10, 20)),),
    )
    font = Model(backend).font
    original = font.glyphs[0].layers[0]
    source = font._proxy(SpecialLayer, original._id, original._read)
    clone = source.copy()
    backend.close_font("font")
    clone.decomposeComponents()
    assert not clone.components and clone.paths[-1].nodes[0].position == (12, 24)


@pytest.mark.parametrize("overlay", [False, True])
def test_l6_reporter_when_every_painter_refused_then_repeated_toggles_do_not_grow_diagnostics(
    overlay,
):
    host = FakeHost(unsupported=("painter",))
    if overlay:
        host.reporter_background_phase = AFTER_NATIVE_LAYER
    env = PluginEnv(host, {}, error_sink=lambda *args: None)
    plugins = make_plugins_module(env)

    class Reporter(plugins.ReporterPlugin):
        def background(self, layer):
            pass

        def foreground(self, layer):
            pass

    handle = load_plugin(Reporter, env)
    try:
        item = host.entries("menu")[0][2]
        item.fire()
        expected = list(handle.diagnostics)
        assert len(expected) == (3 if overlay else 2)
        for _ in range(5):
            item.fire()
        assert handle.diagnostics == expected
    finally:
        handle.unload()


def test_l4_component_lookup_when_exact_layer_exists_then_it_has_priority():
    from fontlab_glyport.model.copies import DetachedLayer

    backup, master = DetachedLayer(), DetachedLayer()
    backup._draft = LayerInfo("", "backup", 100)
    master._draft = LayerInfo("", "master", 200)
    from fontlab_glyport.model.proxies import ProxySequence

    layers = ProxySequence(lambda: [backup, master], lambda layer: (layer.layerId,))
    source = SimpleNamespace(
        _font=SimpleNamespace(glyphs={"base": SimpleNamespace(layers=layers)}),
        components=[SimpleNamespace(componentName="base")],
        layerId="backup",
        associatedMasterId="master",
    )
    assert DetachedLayer._snapshot_components(source, {})["base"].width == 100
