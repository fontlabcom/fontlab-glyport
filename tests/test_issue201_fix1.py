# this_file: tests/test_issue201_fix1.py
"""Issue 201 task 6, review fix round 1: tool bridge containment, painter
fallback and teardown, paint-time ``editViewController``, cursor fallback,
synthetic ``Glyphs.currentEvent()`` and ``GlyphsToolSelect``.

Native evidence: verification/issue-201/glyport-triage.md.
"""

from types import SimpleNamespace

import pytest
from drawing_doubles import QPointF
from test_drawing_editor import Info, Recorder
from test_glyphsapp_session import _session
from test_issue201_native_hooks import QT, Key, Mouse, _native, make_plugins
from test_issue201_triage_fixes import _reporter

from fontlab_glyport.drawing.events import NSEvent, current_event, event_scope
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER, BEFORE_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin
from fontlab_glyport.plugins.tool_bridge import CanvasView, ToolBridge


@pytest.fixture
def plugins():
    return make_plugins()


CURSOR_QT = SimpleNamespace(
    QtCore=QT.QtCore,
    QtGui=SimpleNamespace(QCursor=SimpleNamespace(pos=lambda: QPointF(570, 815))),
)


class Boom:
    """An event (or viewport) whose every method raises."""

    def __getattr__(self, name):
        raise RuntimeError(f"boom {name}")


def _all_overriding_tool(module):
    class Tool(module.SelectTool):
        def mouseDown_(self, event):
            pass

        mouseDragged_ = mouseMoved_ = mouseUp_ = mouseDoubleDown_ = mouseDown_
        keyDown_ = keyUp_ = mouseDown_

    return Tool.alloc().init()


def _sinking_bridge(tool, **kw):
    painters, canvas, _, _ = _native([Info(0, True)])
    sunk = []
    bridge = ToolBridge(
        CURSOR_QT, tool, painters, sink=lambda e, o: sunk.append((str(e), o)), **kw
    )
    return bridge, canvas, sunk


# --- HIGH 1: no exception reaches FontLab ---------------------------------------
@pytest.mark.parametrize(
    "name",
    [
        "mousePressed",
        "mouseMoved",
        "mouseReleased",
        "mouseDoubleClicked",
        "keyPressed",
        "keyReleased",
    ],
)
def test_bridge_event_callback_when_event_raises_then_sunk_and_false(plugins, name):
    _, _, module, _ = plugins
    tool = _all_overriding_tool(module)
    bridge, canvas, sunk = _sinking_bridge(tool)  # guard=None: nothing else guards
    assert getattr(bridge, name)(Boom(), canvas) is False
    assert len(sunk) == 1 and sunk[0][0].startswith("boom") and sunk[0][1] is tool


def test_bridge_when_viewport_height_raises_then_sunk_not_raised(plugins):
    _, _, module, _ = plugins
    tool = _all_overriding_tool(module)
    bridge, _, sunk = _sinking_bridge(tool)
    canvas = SimpleNamespace(viewPort=Boom())
    assert bridge.mousePressed(Mouse(1, 2), canvas) is False
    assert bridge.keyPressed(Key("a", 0), canvas) is False
    assert len(sunk) == 2 and "_edit_view" not in tool.__dict__


@pytest.mark.parametrize("name", ["activate", "deactivate"])
def test_bridge_activation_when_callback_raises_then_sunk_and_none(plugins, name):
    _, _, module, _ = plugins
    tool = _all_overriding_tool(module)

    def fail():
        raise ValueError("loader refused")

    bridge, _, sunk = _sinking_bridge(tool, activate=fail, deactivate=fail)
    assert getattr(bridge, name)() is None
    assert sunk == [("loader refused", tool)]


def test_bridge_when_no_sink_then_traceback_printed(plugins, capsys):
    _, _, module, _ = plugins
    painters, canvas, _, _ = _native([Info(0, True)])
    bridge = ToolBridge(QT, _all_overriding_tool(module), painters)
    assert bridge.mousePressed(Boom(), canvas) is False
    assert "boom localPos" in capsys.readouterr().err


# --- MEDIUM 2: tool painters fall back to an overlay ------------------------------
def test_tool_activate_when_background_refused_then_overlay_and_foreground(plugins):
    host, env, module, _ = plugins
    original = host.register_painter

    def register(phase, callback, **kw):
        if phase == BEFORE_NATIVE_LAYER:
            raise UnsupportedCapability("no hook", capability="host.before")
        return original(phase, callback, **kw)

    host.register_painter = register

    class Tool(module.SelectTool):
        def foreground(self, layer):
            pass

        def background(self, layer):
            pass

    handle = load_plugin(Tool, env)
    ((*_, activate, deactivate),) = host.entries("tool")
    activate()
    assert [e[1] for e in host.entries("painter")] == [AFTER_NATIVE_LAYER] * 2
    assert "REPORTER_BACKGROUND_AS_OVERLAY" in handle.diagnostics[0]
    deactivate()
    activate()  # a second activation does not repeat the note
    assert sum("BACKGROUND_AS_OVERLAY" in d for d in handle.diagnostics) == 1


def test_tool_activate_when_host_has_no_before_phase_then_overlay_noted(plugins):
    host, env, module, _ = plugins
    host.reporter_background_phase = AFTER_NATIVE_LAYER

    class Tool(module.SelectTool):
        def background(self, layer):
            pass

    handle = load_plugin(Tool, env)
    host.entries("tool")[0][3]()
    assert [e[1] for e in host.entries("painter")] == [AFTER_NATIVE_LAYER]
    assert any("BACKGROUND_AS_OVERLAY" in d for d in handle.diagnostics)


def test_tool_activate_when_both_phases_refused_then_diagnosed(plugins):
    _, env, module, _ = plugins
    env.host.unsupported.add("painter")

    class Tool(module.SelectTool):
        def foreground(self, layer):
            pass

        def background(self, layer):
            pass

    handle = load_plugin(Tool, env)
    env.host.entries("tool")[0][3]()
    assert handle.painters == []
    assert handle.diagnostics == [
        "drawBackgroundForLayer_options_: no painter; overlay: no painter",
        "drawForegroundForLayer_options_: no painter",
    ], "the background refusal does not stop the foreground attempt"


# --- MEDIUM 4: attach records first; detach attempts every step --------------------
class _FailingSignal:
    def __init__(self):
        self.disconnects = 0

    def connect(self, slot):
        raise RuntimeError("connect refused")

    def disconnect(self, slot):
        self.disconnects += 1
        raise RuntimeError("disconnect refused")


def test_attach_when_connect_fails_then_entry_kept_and_not_reattached():
    painters, canvas, viewport, errors = _native([Info(0, True)])
    viewport.destroyed = _FailingSignal()
    token = painters.register(AFTER_NATIVE_LAYER, print)
    assert [str(e) for e in errors] == ["connect refused"]
    assert len(canvas.hooks) == 2 and len(painters.overlays) == 1
    painters._attach_all()  # the next poll sees the recorded entry
    assert len(canvas.hooks) == 2, "a failed connect does not leak a pair per poll"
    with pytest.raises(RuntimeError, match="disconnect refused"):
        painters.remove(token)
    assert canvas.hooks == {} and canvas.removed == [1, 2], "painters still removed"
    assert viewport.destroyed.disconnects == 1 and painters.overlays == {}


def test_detach_when_first_removal_fails_then_second_still_removed():
    painters, canvas, viewport, _ = _native([Info(0, True)])
    token = painters.register(AFTER_NATIVE_LAYER, print)
    original = canvas.removePythonPainter

    def remove(t):
        if t == 1:
            raise RuntimeError("first refused")
        return original(t)

    canvas.removePythonPainter = remove
    with pytest.raises(RuntimeError, match="first refused"):
        painters.remove(token)
    assert canvas.removed == [2] and viewport.destroyed.slots == []


def test_overlay_entry_when_attached_then_holds_python_callbacks():
    painters, canvas, viewport, _ = _native([Info(0, True)])
    painters.register(AFTER_NATIVE_LAYER, print)
    ((tokens, callbacks), *_rest) = painters.overlays[id(viewport)]
    assert tokens == (1, 2)
    assert [canvas.hooks[t][0] for t in tokens] == list(callbacks), "strong refs"


# --- MEDIUM 5/6: editViewController in paint; cursor fallback ----------------------
def _cursor_viewport(viewport):
    viewport.mapFromGlobal = lambda p: QPointF(p.x() - 100, p.y() - 50)


def test_edit_view_controller_when_tool_paints_then_paint_context_view(plugins):
    _, env, module, _ = plugins
    env.host.qt = CURSOR_QT
    seen = []

    class Tool(module.SelectTool):
        def foreground(self, layer):
            view = self.editViewController().graphicView()
            location = view.getActiveLocation_(None)
            seen.append((view.activeLayer(), view.scale(), location.x, location.y))

    tool = Tool.alloc().init()
    painters, canvas, viewport, errors = _native([Info(0, True)])
    _cursor_viewport(viewport)
    # the loader's painter puts the paint context on the tool while it paints

    def paint(context):
        tool.__dict__["_paint_context"] = context
        try:
            tool.drawForegroundForLayer_options_(context.layer, {})
        finally:
            del tool.__dict__["_paint_context"]

    painters.register(AFTER_NATIVE_LAYER, paint)
    canvas.paint(1, Recorder())
    # cursor (570, 815) global is viewport (470, 765): glyph (1150, -862.5)
    assert errors == [] and seen == [
        ("layer0", pytest.approx(0.4), pytest.approx(1150.0), pytest.approx(-862.5))
    ]


def test_loader_painter_when_tool_paints_then_context_set_and_restored(plugins):
    host, env, module, _ = plugins
    seen = []

    class Tool(module.SelectTool):
        def foreground(self, layer):
            seen.append(self.editViewController().activeLayer())

    handle = load_plugin(Tool, env)
    host.entries("tool")[0][3]()
    callback = host.entries("painter")[0][2]
    callback(SimpleNamespace(layer="L", scale=2.0, painter=Recorder()))
    assert seen == ["L"] and "_paint_context" not in handle.plugin.__dict__
    with pytest.raises(UnsupportedCapability, match="editViewController"):
        handle.plugin.editViewController()


def test_canvas_view_when_paint_view_has_no_widget_then_unsupported():
    view = CanvasView(None, None, CURSOR_QT, SimpleNamespace(layer="L", scale=1))
    with pytest.raises(UnsupportedCapability, match="getActiveLocation_"):
        view._cursor()


@pytest.mark.parametrize("event", [None, SimpleNamespace(), NSEvent.alloc().init()])
def test_active_location_when_no_or_foreign_event_then_cursor(event):
    painters, canvas, viewport, _ = _native([Info(0, True)])
    _cursor_viewport(viewport)
    view = CanvasView(painters, canvas, CURSOR_QT)
    location = view.getActiveLocation_(event)
    assert (location.x, location.y) == (pytest.approx(1150.0), pytest.approx(-862.5))


def test_active_location_when_zoom_and_scroll_change_and_glyph_not_first(plugins):
    _, _, module, _ = plugins
    seen = []

    class Tool(module.SelectTool):
        def mouseDown_(self, event):
            view = self.editViewController().graphicView()
            location = view.getActiveLocation_(event)
            seen.append((view.activeLayer(), view.scale(), location.x, location.y))

    painters, canvas, _, _ = _native([Info(0, False), Info(60, True)])
    canvas.mapToViewportF = lambda p: QPointF(p.x() * 8 - 30, p.y() * 8 + 5)
    bridge = ToolBridge(QT, Tool.alloc().init(), painters)
    # glyph (25, 50) of the second glyph: canvas (62.5, 95) -> viewport (470, 765)
    assert bridge.mousePressed(Mouse(470, 765), canvas)
    assert seen == [
        ("layer60", pytest.approx(0.8), pytest.approx(25.0), pytest.approx(50.0))
    ]


# --- LOW 11: nested dispatch restores the outer view ----------------------------
def test_dispatch_when_nested_then_outer_edit_view_restored(plugins):
    _, _, module, _ = plugins
    painters, outer_canvas, _, _ = _native([Info(0, True)])
    inner_canvas = SimpleNamespace(viewPort=SimpleNamespace(height=600))
    views = []

    class Tool(module.SelectTool):
        def mouseDown_(self, event):
            outer = self.editViewController()
            bridge.mouseReleased(Mouse(0, 0), inner_canvas)
            views.append((outer, self.editViewController()))

        def mouseUp_(self, event):
            views.append(self.editViewController()._canvas)

    tool = Tool.alloc().init()
    bridge = ToolBridge(QT, tool, painters)
    assert bridge.mousePressed(Mouse(0, 0), outer_canvas)
    assert views[0] is inner_canvas and views[1][0] is views[1][1]
    assert views[1][0]._canvas is outer_canvas and "_edit_view" not in tool.__dict__


# --- MEDIUM 7: Glyphs.currentEvent() never None -----------------------------------
def _synthetic_qt(window):
    screen = SimpleNamespace(geometry=SimpleNamespace(height=lambda: 900))
    return SimpleNamespace(
        QtCore=QT.QtCore,
        QtGui=SimpleNamespace(
            QApplication=SimpleNamespace(
                keyboardModifiers=lambda: 1 | 8,
                activeWindow=lambda: window,
                primaryScreen=lambda: screen,
            ),
            QCursor=SimpleNamespace(pos=lambda: QPointF(112, 134)),
        ),
    )


def test_synthetic_event_when_no_active_window_then_screen_points_y_up(monkeypatch):
    monkeypatch.setattr(NSEvent, "_qt_module", _synthetic_qt(None))
    assert tuple(NSEvent.synthetic().locationInWindow()) == (112, 900 - 134)


def test_current_event_when_outside_tool_event_then_synthetic(tmp_path, monkeypatch):
    # a window at global (100, 100), 400 high (a PythonQt int property)
    window = SimpleNamespace(
        mapFromGlobal=lambda p: QPointF(p.x() - 100, p.y() - 100), height=400
    )
    monkeypatch.setattr(NSEvent, "_qt_module", _synthetic_qt(window))
    ctx, _ = _session(tmp_path)
    (tmp_path / "main.py").write_text(
        "from GlyphsApp import Glyphs\nresult = Glyphs.currentEvent\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    current = ctx.globals["result"]
    event = current()
    assert isinstance(event, NSEvent) and event.clickCount() == 1
    assert event.modifierFlags() == (1 << 17) | (1 << 20), "Shift + Command"
    assert tuple(event.locationInWindow()) == (12, 400 - 34), "window points, y up"
    assert not hasattr(event, "_widget"), "no view point: views read the cursor"
    marker = object()
    with event_scope(marker):
        assert current() is marker
    assert current_event() is None
    ctx.close()


def test_nsevent_when_no_pythonqt_then_host_unavailable(monkeypatch):
    import sys

    from fontlab_glyport.errors import HostUnavailable

    monkeypatch.setattr(NSEvent, "_qt_module", None)
    monkeypatch.setitem(sys.modules, "PythonQt", None)
    with pytest.raises(HostUnavailable, match="PythonQt"):
        NSEvent.synthetic()


# --- LOW 8/9 ----------------------------------------------------------------------
def test_glyphs_tool_select_when_class_from_string_then_select_tool_kind(tmp_path):
    ctx, _ = _session(tmp_path)
    (tmp_path / "main.py").write_text(
        "from Foundation import NSClassFromString\n"
        "result = NSClassFromString('GlyphsToolSelect'), "
        "NSClassFromString('GlyphsToolText')\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    select, text = ctx.globals["result"]
    from fontlab_glyport.model.proxies import _EditorTool

    tool = _EditorTool()
    assert select is not None and text is None
    assert tool.isKindOfClass_(select) and not tool.isKindOfClass_(text)
    ctx.close()


def test_draw_text_at_point_when_unknown_align_then_logged():
    log = []
    _reporter(log).drawTextAtPoint("ab", (0, 0), align="middle")
    assert any("unknown align 'middle'" in line for line in log), log


# --- fix round 2 ----------------------------------------------------------------
def test_bridge_when_sink_raises_then_both_printed_and_false(plugins, capsys):
    _, _, module, _ = plugins
    painters, canvas, _, _ = _native([Info(0, True)])

    def bad_sink(error, owner):
        raise OSError("sink broke")

    bridge = ToolBridge(QT, _all_overriding_tool(module), painters, sink=bad_sink)
    assert bridge.mousePressed(Boom(), canvas) is False
    err = capsys.readouterr().err
    assert "boom localPos" in err and "sink broke" in err


def test_key_when_no_mouse_event_yet_then_cursor_not_widget_origin(plugins):
    _, _, module, _ = plugins
    seen = []

    class Tool(module.SelectTool):
        def keyDown_(self, event):
            view = self.editViewController().graphicView()
            location = view.getActiveLocation_(event)
            seen.append((tuple(event.locationInWindow()), location.x, location.y))

    painters, canvas, viewport, _ = _native([Info(0, True)])
    _cursor_viewport(viewport)
    bridge = ToolBridge(CURSOR_QT, Tool.alloc().init(), painters)
    assert bridge.keyPressed(Key("a", 0), canvas) is False
    # cursor (570, 815) global is viewport (470, 765), not (0, 0)
    assert seen == [((470, 600 - 765), pytest.approx(1150.0), pytest.approx(-862.5))]
