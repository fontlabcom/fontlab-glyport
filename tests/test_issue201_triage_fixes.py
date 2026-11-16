# this_file: tests/test_issue201_triage_fixes.py
"""Shared API gaps found by the issue 201 native plugin triage.

Native evidence: verification/issue-201/glyport-triage.md.
"""

import pytest
from plugin_doubles import FakeHost
from test_drawing import _scope
from test_glyphsapp_session import _session

from fontlab_glyport import foundation
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import NSStr
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.ui.cocoa import NSMakePoint, NSMakeRect, unsupported


def test_offset_rect_when_moved_then_size_kept():
    moved = foundation.NSOffsetRect(NSMakeRect(1, 2, 30, 40), 5, -2)
    assert tuple(moved[0]) == (6.0, 0.0) and tuple(moved[1]) == (30.0, 40.0)


def test_point_in_rect_when_on_edges_then_half_open_like_cocoa():
    rect = NSMakeRect(0, 0, 10, 10)
    inside = [NSMakePoint(0, 0), NSMakePoint(9.9, 5), (5, 5)]
    outside = [NSMakePoint(10, 5), NSMakePoint(5, 10), NSMakePoint(-0.1, 5)]
    assert all(foundation.NSPointInRect(p, rect) for p in inside)
    assert not any(foundation.NSPointInRect(p, rect) for p in outside)
    assert {"NSOffsetRect", "NSPointInRect"} <= set(foundation.GEOMETRY)


def test_contains_rect_when_enclosed_edge_or_empty_then_cocoa_answer():
    outer = NSMakeRect(0, 0, 10, 10)
    assert foundation.NSContainsRect(outer, NSMakeRect(0, 0, 10, 10))
    assert not foundation.NSContainsRect(outer, NSMakeRect(5, 5, 6, 1))
    assert not foundation.NSContainsRect(outer, NSMakeRect(1, 1, 0, 3)), "empty"
    assert "NSContainsRect" in foundation.GEOMETRY


def test_screens_when_pythonqt_geometry_properties_then_cocoa_frames():
    from types import SimpleNamespace as NS

    from host_doubles import make_host_qt

    def rect(x, y, w, h):
        return NS(x=lambda: x, y=lambda: y, width=lambda: w, height=lambda: h)

    screen = NS(
        geometry=rect(0, 0, 1440, 900), availableGeometry=rect(0, 25, 1440, 875)
    )
    qt = make_host_qt()
    qt.QtGui.QApplication = NS(screens=lambda: [screen])
    main = foundation.qt_names(qt, lambda f: None)["NSScreen"].mainScreen()
    assert main.frame() == ((0, 0), (1440, 900))
    assert main.visibleFrame() == ((0, 0), (1440, 875))


def test_nsstr_when_value_or_empty_then_str_or_none():
    assert NSStr("kern") == "kern" and NSStr(12) == "12"
    assert NSStr("") is None and NSStr(None) is None


def _reporter(log, scale=1.0):
    env = PluginEnv(FakeHost(), {}, error_sink=lambda *a: None, log=log.append)
    reporter = make_plugins_module(env).ReporterPlugin.alloc().init()
    reporter._scale = scale
    return reporter


def test_draw_text_at_point_when_zoomed_then_screen_size():
    log = []
    reporter = _reporter(log, scale=0.5)
    painter, scope = _scope()  # glyph-to-view at zoom 0.5
    with scope:
        reporter.drawTextAtPoint("ab", (0, 0), fontSize=10, align="topright")
    assert next(c for c in painter.calls if c[0] == "font")[1] == 10, "10 screen pt"
    assert any(c[0] == "text" and c[3] == "ab" for c in painter.calls)
    assert log == []


def test_draw_text_at_point_when_drawing_fails_then_logged_like_sdk():
    log = []
    _reporter(log).drawTextAtPoint("ab", (0, 0))  # no paint scope: drawing raises
    assert len(log) == 1 and "drawTextAtPoint" in log[0], log


def test_draw_text_at_point_when_refused_then_raised():
    reporter = _reporter([])

    def refuse():
        raise unsupported("probe")

    reporter.getScale = refuse
    with pytest.raises(UnsupportedCapability):
        reporter.drawTextAtPoint("ab", (0, 0))


def _graphic_view(device):
    from types import SimpleNamespace as NS

    from fontlab_glyport.model.proxies import _GraphicView

    cursor = NS(pos=lambda: "global")
    context = NS(
        glyph_base=None,
        base=(2.0, 0.0, 0.0, -2.0, 10.0, 300.0),  # zoom 2, y up, origin (10, 300)
        painter=NS(device=lambda: device),
        qt=NS(QtGui=NS(QCursor=cursor)),
    )
    return _GraphicView(context)


def test_active_location_when_no_tool_event_then_live_cursor_in_glyph_units():
    from types import SimpleNamespace as NS

    device = NS(
        width=lambda: 400,
        height=lambda: 300,
        mapFromGlobal=lambda p: NS(x=lambda: 30.0, y=lambda: 280.0),
    )
    point = _graphic_view(device).getActiveLocation_(None)
    assert (point.x, point.y) == (10.0, 10.0), "pixel (30, 280) is glyph (10, 10)"


def test_active_location_when_tool_event_then_event_pixels():
    from types import SimpleNamespace as NS

    device = NS(width=lambda: 400, height=lambda: 300)
    point = _graphic_view(device).getActiveLocation_(NS(_widget=(10.0, 300.0)))
    assert (point.x, point.y) == (0.0, 0.0)
    with pytest.raises(UnsupportedCapability, match="getActiveLocation_"):
        _graphic_view(device).getActiveLocation_(None)  # pixmap: no cursor mapping


def test_active_location_when_native_paint_then_viewport_maps_cursor():
    from types import SimpleNamespace as NS

    from fontlab_glyport.drawing import native_painters

    device = NS(width=lambda: 400, height=lambda: 300)  # a bare QPaintDevice
    viewport = NS(mapFromGlobal=lambda p: NS(x=lambda: 30.0, y=lambda: 280.0))
    token = native_painters._PAINT_WIDGET.set(viewport)
    try:
        point = _graphic_view(device).getActiveLocation_(None)
    finally:
        native_painters._PAINT_WIDGET.reset(token)
    assert (point.x, point.y) == (10.0, 10.0)


def test_plugins_module_when_extras_then_star_exported():
    module = make_plugins_module(
        PluginEnv(FakeHost(), {}, error_sink=lambda *a: None), {"NSLog": print}
    )
    assert module.NSLog is print and "NSLog" in module.__all__
    assert "ReporterPlugin" in module.__all__


def test_session_plugins_module_when_star_imported_then_sdk_cocoa_names(tmp_path):
    ctx, _ = _session(tmp_path)
    (tmp_path / "main.py").write_text(
        "from GlyphsApp.plugins import *\n"
        "result = [NSClassFromString, NSMakePoint, NSColor, Glyphs, objc]\n"
        "missing = 'NSUnarchiver' in dir()\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    assert all(value is not None for value in ctx.globals["result"])
    assert ctx.globals["missing"] is False, "absent names stay absent"
    ctx.close()


def test_window_private_handle_when_pythonqt_sizes_then_content_limits():
    from types import SimpleNamespace as NS

    from fontlab_glyport.ui.vanilla import Window, _WindowSizeLimits

    def size(w, h):
        return NS(width=lambda: w, height=lambda: h)

    view = NS(minimumSize=size(200, 100), maximumSize=size(600, 400))  # properties
    limits = _WindowSizeLimits(view)
    assert tuple(limits.contentMinSize()) == (200.0, 100.0)
    assert tuple(limits.contentMaxSize()) == (600.0, 400.0)
    window = Window.__new__(Window)
    window._view = view
    assert tuple(window._window.contentMinSize()) == (200.0, 100.0)


def test_text_field_cell_scrollable_when_edit_or_label_then_qt_behaviour():
    from test_ui_cocoa_button_image import WrapLabel, _kit

    kit = _kit()
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    assert field.cell().isScrollable()
    field.cell().setScrollable_(True)
    with pytest.raises(UnsupportedCapability, match="setScrollable_"):
        field.cell().setScrollable_(False)
    label = kit["NSTextField"]._adopt(WrapLabel())
    assert not label.cell().isScrollable()
    label.cell().setScrollable_(True)
    assert label.cell().isScrollable()
    kit["close"]()
