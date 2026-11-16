# this_file: tests/test_issue106_round5_reporter.py
"""The native overlay fallback is known before a reporter's first toggle."""

from plugin_doubles import FakeHost

from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin


def test_f20_reporter_when_loaded_on_overlay_host_then_receipt_note_precedes_toggle(
    tmp_path,
):
    class OverlayHost(FakeHost):
        reporter_background_phase = FontLabPluginHost.reporter_background_phase

    ctx = ExecutionContext(tmp_path, "glyphs3")
    host = OverlayHost()
    env = PluginEnv(host, {}, error_sink=print, diagnostic_sink=ctx.add_diagnostic)
    plugins = make_plugins_module(env)

    class Reporter(plugins.ReporterPlugin):
        def background(self, layer):
            pass

        def inactiveLayerBackground(self, layer):
            pass

    handle = load_plugin(Reporter, env)
    try:
        assert not handle.painters
        assert len(ctx.diagnostics) == 1
        assert ctx.diagnostics[0].code == "REPORTER_BACKGROUND_AS_OVERLAY"
        assert "background drawn as overlay" in ctx.diagnostics[0].message
        for _ in range(4):
            host.entries("menu")[0][2].fire()
            if handle.painters:
                assert all(
                    entry[1] == AFTER_NATIVE_LAYER for entry in host.entries("painter")
                )
        assert len(ctx.diagnostics) == 1 and len(handle.diagnostics) == 1
    finally:
        handle.unload()
        ctx.close()
