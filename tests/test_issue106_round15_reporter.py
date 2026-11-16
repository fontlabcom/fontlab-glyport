# this_file: tests/test_issue106_round15_reporter.py
"""View-coordinate reporters need registration and an unscaled paint scope."""

from types import SimpleNamespace as NS

from plugin_doubles import FakeHost
from test_drawing import _scope

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin


def test_view_coordinate_reporter_hooks_register_draw_and_release_layer():
    class OverlayHost(FakeHost):
        reporter_background_phase = AFTER_NATIVE_LAYER

    host, calls, errors, diagnostics = OverlayHost(), [], [], []
    def paint_scope(context):
        painter, scope = _scope(base=(2, 0, 0, -2, 5, 80))
        painter.device = lambda: NS(width=lambda: 400, height=lambda: 300)
        return scope

    env = PluginEnv(
        host,
        {},
        error_sink=lambda error, owner: errors.append(error),
        paint_scope=paint_scope,
        diagnostic_sink=diagnostics.append,
    )
    plugins = make_plugins_module(env)
    layer = object()

    class Reporter(plugins.ReporterPlugin):
        def foregroundInViewCoords(self):
            calls.append(
                (
                    "foreground",
                    self.activeLayer(),
                    self.getScale(),
                    self.activePosition(),
                    gc.current().base,
                )
            )

        def backgroundInViewCoords(self):
            calls.append(
                (
                    "background",
                    self.activeLayer(),
                    self.getScale(),
                    self.activePosition(),
                    gc.current().base,
                )
            )

    handle = load_plugin(Reporter, env)
    host.entries("menu")[0][2].fire()
    assert len(handle.painters) == 2
    host.paint(AFTER_NATIVE_LAYER, layer, scale=2)
    assert not errors
    assert {call[0] for call in calls} == {"foreground", "background"}
    assert all(call[1:] == (layer, 2, (5, 220), (1, 0, 0, -1, 0, 300)) for call in calls)
    assert handle.plugin.activeLayer() is None
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "REPORTER_BACKGROUND_AS_OVERLAY"
    ]
    handle.unload()
