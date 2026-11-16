# this_file: tests/test_issue106_round4_plugins.py
"""Plugin lifecycle and reporter fallback regressions, without a native host."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from plugin_doubles import FakeHost

from fontlab_glyport.entrypoints import ExecutionHost, ExecutionOptions, RunHandle
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER, BEFORE_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin
from fontlab_glyport.receipt import ReceiptEnvironment


def test_f10_filters_when_installed_and_unloaded_then_facade_lists_only_loaded_filters():
    filters, errors = {}, []
    host = FakeHost()
    env = PluginEnv(
        host, {}, lambda error, owner: errors.append(error), filters=filters
    )
    module = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=print, filters=filters
    )
    plugins = make_plugins_module(env)

    class Filter(plugins.FilterWithoutDialog):
        def filter(self, layer, inEditView, customParameters):
            pass

    assert module.Glyphs.filters == []
    handle = load_plugin(Filter, env)
    assert module.Glyphs.filters == [handle.plugin]
    handle.unload()
    assert module.Glyphs.filters == [] and not errors


def test_f24_filter_controller_when_tab_active_then_property_and_legacy_call_work():
    backend = FakeBackend()
    font = Model(backend).font
    host = FakeHost([font.glyphs[0].layers[0]])
    host.current_font = lambda: font
    env = PluginEnv(host, {}, error_sink=print)
    plugins = make_plugins_module(env)
    calls = []

    class Filter(plugins.FilterWithoutDialog):
        def filter(self, layer, inEditView, customParameters):
            calls.append(self.controller().className())

    handle = load_plugin(Filter, env)
    assert handle.plugin.controller is None
    tab = font.newTab("A")
    host.entries("menu")[0][2].fire()
    assert calls == ["GSEditViewController"]
    assert handle.plugin.controller.className() == "GSEditViewController"
    handle.plugin.setController_(tab)
    assert handle.plugin.controller is tab and handle.plugin.controller() is tab
    handle.plugin.setController_(None)
    assert handle.plugin.controller is None
    handle.unload()


@pytest.mark.parametrize("inactive", [False, True])
def test_f20_background_when_before_phase_refused_then_overlay_renders_and_receipt_notes_it(
    tmp_path, inactive
):
    class OverlayOnly(FakeHost):
        def register_painter(self, phase, callback, **options):
            if phase == BEFORE_NATIVE_LAYER:
                raise UnsupportedCapability(
                    "before-native refused", capability="host.before_native_layer"
                )
            return super().register_painter(phase, callback, **options)

    ctx = ExecutionContext(tmp_path, "glyphs3")
    host = OverlayOnly()
    env = PluginEnv(
        host,
        {},
        error_sink=print,
        paint_scope=lambda c: nullcontext(),
        diagnostic_sink=ctx.diagnostics.append,
    )
    plugins = make_plugins_module(env)
    drawn = []

    class Reporter(plugins.ReporterPlugin):
        def background(self, layer):
            drawn.append(layer)

    if inactive:
        Reporter.inactiveLayerBackground = Reporter.background
        del Reporter.background
    plugin_handle = load_plugin(Reporter, env)
    host.entries("menu")[0][2].fire()
    layer = object()
    host.paint(
        AFTER_NATIVE_LAYER, layer, layer_filter="inactive" if inactive else "active"
    )
    assert drawn == [layer] and len(plugin_handle.painters) == 1
    run = RunHandle(
        tmp_path / "plugin.py",
        ExecutionHost(
            lambda f: f(), ReceiptEnvironment(None, None, None, None, None, None)
        ),
        ExecutionOptions(),
    )
    run.context = ctx
    note = next(
        d for d in run.receipt.diagnostics if d.code == "REPORTER_BACKGROUND_AS_OVERLAY"
    )
    assert "background drawn as overlay" in note.message and "R054" in note.message
    assert len([d for d in run.receipt.diagnostics if d.code == note.code]) == 1
    plugin_handle.unload()
    assert not host.registered
    ctx.close()


def test_f10_filter_loaded_in_one_session_when_read_from_another_then_visible_until_unload(
    tmp_path,
):
    from ui_doubles_session import make_session

    first, session = make_session(tmp_path)
    second, _ = make_session(tmp_path)

    class SessionHost(FakeHost):
        def close(self):
            for token in list(self.registered):
                self.remove(token)

    session._plugin_host = SessionHost()
    env = session.plugin_env()
    plugins = make_plugins_module(env)

    class Filter(plugins.FilterWithoutDialog):
        pass

    handle = load_plugin(Filter, env)
    try:
        with second:
            app = second.import_module("GlyphsApp").Glyphs
            assert handle.plugin in app.filters
            handle.unload()
            assert handle.plugin not in app.filters
    finally:
        handle.unload()
        first.close()
        second.close()


def test_f20_draw_background_callback_when_subscribed_then_post_native_and_note():
    from fontlab_glyport.glyphsapp.fontlab_bridge import FontLabGlyphsBridge

    registrations, notes, drawn = [], [], []
    painters = SimpleNamespace(
        register=lambda *args, **kwargs: registrations.append((args, kwargs)) or "token"
    )
    bridge = FontLabGlyphsBridge(
        log=lambda message: None,
        version=(3, 3000),
        painters=lambda: painters,
        diagnostic_sink=notes.append,
    )
    bridge.subscribe("DrawBackground", lambda *args: drawn.append(args))
    assert registrations[0][0][0] == AFTER_NATIVE_LAYER
    registrations[0][0][1](SimpleNamespace(layer="layer", scale=2.0))
    assert drawn == [("layer", {"Scale": 2.0, "Black": False})]
    assert notes[0].code == "REPORTER_BACKGROUND_AS_OVERLAY"
