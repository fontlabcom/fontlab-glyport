# this_file: tests/test_issue201_native_hooks.py
"""Native canvas painters and Python tools (issue 201 task 6) over doubles.

Native proof: verification/issue-201/glyport-triage.md (FontLab build with
``flCanvas.appendPythonPainter`` and ``flWorkspace.registerPythonTool``).
"""

from types import SimpleNamespace

import pytest
from drawing_doubles import QPointF, QTransform
from plugin_doubles import FakeHost, Layer
from test_drawing_editor import WIDGETS, Canvas, Info, Recorder, Timer, Widget
from ui_doubles import make_qt

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.drawing.editor import EditorPainters
from fontlab_glyport.drawing.events import (
    NSEventModifierFlagShift,
    current_event,
)
from fontlab_glyport.drawing.native_painters import (
    NativeEditorPainters,
    editor_painters,
    has_native_painters,
)
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER, BEFORE_NATIVE_LAYER
from fontlab_glyport.plugins.loader import load_plugin
from fontlab_glyport.plugins.tool_bridge import CanvasView, ToolBridge, overrides
from fontlab_glyport.ui.cocoa_views import make_appkit_classes


# --- native painters -------------------------------------------------------------
class NativeCanvas(Canvas):
    """A canvas with FontLab's Python painter hook; tokens count from 1."""

    def __init__(self, infos, fail_second=False):
        super().__init__(infos)
        self.hooks, self.removed, self._next = {}, [], 0
        self.fail_second = fail_second

    def appendPythonPainter(self, callback, order):
        if self.fail_second and self.hooks:
            raise RuntimeError("native refused")
        self._next += 1
        self.hooks[self._next] = (callback, order)
        return self._next

    def removePythonPainter(self, token):
        self.removed.append(token)
        return self.hooks.pop(token, None) is not None

    def paint(self, order, painter):
        for callback, hook_order in list(self.hooks.values()):
            if hook_order == order:
                callback(painter, self)


class NativeViewport(Widget):
    def height(self):
        return 600


FLCANVAS = SimpleNamespace(UnderOwner=0, OverOwner=1, appendPythonPainter=None)


def _native(infos, fail_second=False):
    WIDGETS.clear()
    window = Widget(name="GlyphWindow")
    viewport = NativeViewport(window)
    WIDGETS.extend([window, viewport])
    canvas = NativeCanvas(infos, fail_second)
    canvas.viewPort = viewport
    workspace = SimpleNamespace(
        getCanvasForViewport=lambda w: canvas if w is viewport else None
    )
    gui = SimpleNamespace(
        QWidget=Widget,
        QApplication=SimpleNamespace(allWidgets=lambda: list(WIDGETS)),
        QTransform=QTransform,
    )
    core = SimpleNamespace(QTimer=Timer, QPointF=QPointF)
    fl = SimpleNamespace(
        flWorkspace=SimpleNamespace(instance=lambda: workspace), flCanvas=FLCANVAS
    )
    errors = []
    painters = editor_painters(
        SimpleNamespace(QtGui=gui, QtCore=core),
        fl,
        error_sink=lambda e, s: errors.append(e),
        layer_resolver=lambda info: f"layer{info.id}",
    )
    return painters, canvas, viewport, errors


def test_editor_painters_when_hook_missing_then_overlay_class():
    assert not has_native_painters(SimpleNamespace())
    painters = editor_painters(None, SimpleNamespace(), error_sink=print)
    assert type(painters) is EditorPainters, "builds without the hook keep R054 overlay"
    assert not getattr(painters, "supports_before_native", False)


def test_register_when_both_phases_then_native_under_and_over_per_canvas():
    painters, canvas, viewport, errors = _native([Info(0, True), Info(60, False)])
    assert (
        isinstance(painters, NativeEditorPainters) and painters.supports_before_native
    )
    seen = []
    under = painters.register(BEFORE_NATIVE_LAYER, lambda c: seen.append(("u", c)))
    painters.register(AFTER_NATIVE_LAYER, lambda c: seen.append(("o", c)), "all")
    assert sorted(o for _, o in canvas.hooks.values()) == [0, 1], "one hook per order"
    assert viewport.updates >= 1, "a new painter repaints the canvas"
    painter = Recorder()
    canvas.paint(0, painter)
    assert [(k, c.phase, c.layer) for k, c in seen] == [
        ("u", BEFORE_NATIVE_LAYER, "layer0")
    ], "Under runs only background painters, for the active glyph"
    seen.clear()
    canvas.paint(1, painter)
    assert [(k, c.is_active_layer) for k, c in seen] == [("o", True), ("o", False)]
    first = seen[0][1]
    full = gc.concat(
        gc.from_qtransform(first.glyph_to_canvas),
        gc.from_qtransform(first.canvas_to_view),
    )
    assert gc.apply(full, 0, 0) == (10.0, 420.0), "same maths as App's overlay"
    assert "end" not in [c[0] for c in painter.calls], "FontLab owns the painter"
    painters.remove(under)
    seen.clear()
    canvas.paint(0, painter)
    assert seen == [] and errors == []


def test_paint_widget_when_native_painter_runs_then_viewport_then_cleared():
    from fontlab_glyport.drawing.native_painters import paint_widget

    painters, canvas, viewport, errors = _native([Info(0, True)])
    seen = []
    painters.register(AFTER_NATIVE_LAYER, lambda c: seen.append(paint_widget()))
    canvas.paint(1, Recorder())
    assert seen == [viewport] and paint_widget() is None and errors == []


def test_paint_when_filtered_or_failing_then_skipped_and_sunk():
    painters, canvas, _, errors = _native([Info(0, True)])
    calls = []

    def bad(context):
        calls.append(context.document_id)
        raise ValueError("plugin broke")

    painters.register(AFTER_NATIVE_LAYER, bad)
    painters.register(AFTER_NATIVE_LAYER, calls.append, document_id=99)
    painters.register(AFTER_NATIVE_LAYER, calls.append, "inactive")
    painter = Recorder()
    canvas.paint(1, painter)
    assert calls == [7], "document and layer filters skip the other painters"
    assert [str(e) for e in errors] == ["plugin broke"]
    assert painter.kinds()[:2] == ["save", "restore"], "state restored after failure"
    canvas.block = None  # textBlocks() now fails: still never raises into FontLab
    canvas.paint(1, painter)
    assert len(errors) == 2


def test_register_when_bad_phase_or_filter_then_value_error():
    painters, canvas, _, _ = _native([])
    for phase, layers in (("middle", "active"), (AFTER_NATIVE_LAYER, "some")):
        with pytest.raises(ValueError, match="bad painter"):
            painters.register(phase, print, layers)
    assert canvas.hooks == {} and painters._timer is None


def test_remove_when_last_then_native_painters_removed_and_slot_disconnected():
    painters, canvas, viewport, _ = _native([Info(0, True)])
    token = painters.register(BEFORE_NATIVE_LAYER, print)
    assert len(viewport.destroyed.slots) == 1
    painters._paint_native(Recorder(), canvas, viewport, BEFORE_NATIVE_LAYER)
    painters.remove(token)
    assert canvas.removed == [1, 2] and canvas.hooks == {}
    assert viewport.destroyed.slots == [] and painters.overlays == {}
    painters._paint_native(Recorder(), canvas, viewport, BEFORE_NATIVE_LAYER)
    assert painters._phases == {}


def test_attach_when_second_hook_fails_then_first_removed_and_error_sunk():
    painters, canvas, _, errors = _native([], fail_second=True)
    painters.register(AFTER_NATIVE_LAYER, print)
    assert canvas.hooks == {} and canvas.removed == [1]
    assert [str(e) for e in errors] == ["native refused"], "poll errors go to the sink"


def test_destroyed_when_canvas_closes_then_entry_forgotten_without_native_calls():
    painters, canvas, viewport, _ = _native([])
    painters.register(AFTER_NATIVE_LAYER, print)
    viewport.destroyed.slots[0]()
    assert painters.overlays == {} and canvas.removed == []


# --- host -----------------------------------------------------------------------
class Workspace:
    def __init__(self):
        self.tools, self.unregistered = {}, []

    def registerPythonTool(self, name, icon, obj):
        self.tools[len(self.tools) + 10] = (name, icon, obj)
        return len(self.tools) + 9

    def unregisterPythonTool(self, token):
        self.unregistered.append(token)
        return True


def _host(fl, painters=None):
    return FontLabPluginHost(
        object(), fl, error_sink=lambda e, s: None, painters=painters
    )


def test_reporter_background_phase_when_native_painters_then_before():
    native = SimpleNamespace(supports_before_native=True)
    assert _host(object(), native).reporter_background_phase == BEFORE_NATIVE_LAYER
    assert _host(object(), object()).reporter_background_phase == AFTER_NATIVE_LAYER


def test_register_tool_when_hook_present_then_bridge_registered_and_removed():
    workspace = Workspace()
    fl = SimpleNamespace(
        flWorkspace=SimpleNamespace(registerPythonTool=None, instance=lambda: workspace)
    )
    host = _host(fl, "painters")
    tool = SimpleNamespace(title=lambda: "Knife")
    token = host.register_tool(tool, guard="g", activate="a", deactivate="d")
    ((name, icon, bridge),) = workspace.tools.values()
    assert (name, icon) == ("Knife", None)
    assert isinstance(bridge, ToolBridge) and bridge.tool is tool
    assert (bridge.painters, bridge._guard, bridge._on) == ("painters", "g", ("a", "d"))
    assert bridge._sink == host.sink, "bridge errors go to the host error sink"
    host.remove(token)
    assert workspace.unregistered == [10]


def test_register_tool_when_hook_missing_then_unsupported():
    with pytest.raises(UnsupportedCapability, match="registerPythonTool"):
        _host(SimpleNamespace(flWorkspace=SimpleNamespace())).register_tool(object())


# --- tool bridge --------------------------------------------------------------------
class Mouse:
    def __init__(self, x, y, buttons=0, modifiers=0):
        self._p, self._b, self._m = QPointF(x, y), buttons, modifiers

    def localPos(self):
        return self._p

    def buttons(self):
        return self._b

    def modifiers(self):
        return self._m


class Key(Mouse):
    def __init__(self, text, code, modifiers=0):
        super().__init__(0, 0, modifiers=modifiers)
        self._t, self._c = text, code

    def text(self):
        return self._t

    def nativeVirtualKey(self):
        return self._c


QT = SimpleNamespace(
    QtCore=SimpleNamespace(
        Qt=SimpleNamespace(
            ShiftModifier=1, MetaModifier=2, AltModifier=4, ControlModifier=8
        )
    )
)


def make_plugins():
    host = FakeHost([Layer("A", [])])
    errors = []
    env = PluginEnv(
        host,
        make_appkit_classes(make_qt(), error_sink=print),
        lambda e, s: errors.append(e),
    )
    return host, env, make_plugins_module(env), errors


plugins = pytest.fixture(make_plugins, name="plugins")


def _bridge(tool, guard=None, **kw):
    painters, canvas, _, _ = _native([Info(0, True), Info(60, False)])
    return ToolBridge(QT, tool, painters, guard=guard, **kw), canvas


def test_tool_when_mouse_methods_overridden_then_cocoa_events_and_handled(plugins):
    _, env, module, _ = plugins
    log = []

    class Tool(module.SelectTool):
        def mouseDown_(self, event):
            view = self.editViewController().graphicView()
            location = view.getActiveLocation_(event)
            log.append(
                (
                    "down",
                    event.clickCount(),
                    event.locationInWindow().y,
                    round(location.x, 6),
                    round(location.y, 6),
                    view.activeLayer(),
                    view.scale(),
                    current_event() is event,
                    bool(event.modifierFlags() & NSEventModifierFlagShift),
                )
            )

        def mouseDragged_(self, event):
            log.append(("drag",))

        def mouseUp_(self, event):
            log.append(("up",))

    tool = Tool.alloc().init()
    bridge, canvas = _bridge(tool, guard=env.guard)
    # glyph (0, 0) is widget (10, 420) and the scale is 0.4 px per unit
    assert bridge.mousePressed(
        Mouse(10 + 0.4 * 25, 420 - 0.4 * 50, modifiers=1), canvas
    )
    assert log[0] == (
        "down",
        1,
        600 - 400,
        25.0,
        50.0,
        "layer0",
        pytest.approx(0.4),
        True,
        True,
    )
    assert bridge.mouseMoved(Mouse(0, 0, buttons=1), canvas) and log[-1] == ("drag",)
    assert not bridge.mouseMoved(Mouse(0, 0), canvas), "hover: not overridden"
    assert bridge.mouseReleased(Mouse(0, 0), canvas) and log[-1] == ("up",)
    assert bridge.mouseDoubleClicked(Mouse(10, 420), canvas)
    assert log[-1][:2] == ("down", 2), "no mouseDoubleDown_: mouseDown_ with two clicks"
    assert "_edit_view" not in tool.__dict__ and current_event() is None


def test_tool_event_when_viewport_height_is_pythonqt_property_then_y_flipped(plugins):
    _, _, module, _ = plugins
    seen = []

    class Tool(module.SelectTool):
        def mouseUp_(self, event):
            seen.append(event.locationInWindow().y)

    bridge, canvas = _bridge(Tool.alloc().init())
    canvas.viewPort.height = 500  # PythonQt exposes QWidget.height as an int
    assert bridge.mouseReleased(Mouse(0, 120), canvas) and seen == [380]


def test_tool_when_double_down_and_keys_then_delivered_keys_unclaimed(plugins):
    _, _, module, _ = plugins
    log = []

    class Tool(module.SelectTool):
        def mouseDoubleDown_(self, event):
            log.append(("double", event.clickCount()))

        def keyDown_(self, event):
            log.append(
                (
                    "key",
                    event.characters(),
                    event.keyCode(),
                    event.charactersIgnoringModifiers(),
                )
            )

    tool = Tool.alloc().init()
    bridge, canvas = _bridge(tool)
    assert bridge.mouseDoubleClicked(Mouse(5, 5), canvas) and log == [("double", 2)]
    assert not bridge.mousePressed(Mouse(5, 5), canvas), (
        "base no-op leaves it to FontLab"
    )
    assert bridge.keyPressed(Key("a", 0), canvas) is False
    assert bridge.keyReleased(Key("a", 0), canvas) is False, "keyUp_ not overridden"
    assert log[-1] == ("key", "a", 0, "a")


def test_tool_when_activated_then_callbacks_in_order_and_errors_guarded(plugins):
    _, env, module, errors = plugins
    log = []

    class Tool(module.SelectTool):
        def activate(self):
            log.append("activate")

        def deactivate(self):
            raise ValueError("bad deactivate")

    tool = Tool.alloc().init()
    bridge, _ = _bridge(
        tool,
        guard=env.guard,
        activate=lambda: log.append("on"),
        deactivate=lambda: log.append("off"),
    )
    bridge.activate()
    bridge.deactivate()
    assert log == ["on", "activate", "off"]
    assert [str(e) for e in errors] == ["bad deactivate"]
    plain, _ = _bridge(tool)
    plain.activate()
    assert log[-1] == "activate", "no guard and no callbacks still works"


def test_canvas_view_when_no_active_glyph_then_neutral_values():
    painters, canvas, _, _ = _native([Info(60, False)])
    view = CanvasView(painters, canvas)
    assert (view.activeLayer(), view.scale()) == (None, 1.0)
    assert view.getActiveLocation_(SimpleNamespace(_widget=(1, 2))) is None
    assert view.convertPoint_fromView_("p", None) == "p"


def test_select_tool_defaults_when_outside_event_then_unsupported_and_noops(plugins):
    _, _, module, _ = plugins
    seen = []

    class Tool(module.SelectTool):
        def foreground(self, layer):
            seen.append(("fg", layer))

    tool = Tool.alloc().init()
    with pytest.raises(UnsupportedCapability, match="editViewController"):
        tool.editViewController()
    assert tool.mouseDown_(None) is None and not overrides(tool, "mouseDown_")
    assert overrides(tool, "foreground") and not overrides(tool, "nothing")
    tool.drawForegroundForLayer_options_("L", {})
    tool.drawBackgroundForLayer_options_("L", {})
    assert seen == [("fg", "L")]


def test_loader_when_tool_activates_then_painters_follow_activation(plugins):
    host, env, module, _ = plugins

    class Tool(module.SelectTool):
        def foreground(self, layer):
            pass

        def background(self, layer):
            pass

    handle = load_plugin(Tool, env)
    ((_, plugin, guard, activate, deactivate),) = host.entries("tool")
    assert plugin is handle.plugin and guard == env.guard
    activate()
    assert sorted(e[1] for e in host.entries("painter")) == [
        AFTER_NATIVE_LAYER,
        BEFORE_NATIVE_LAYER,
    ]
    deactivate()
    assert host.entries("painter") == [] and handle.painters == []
