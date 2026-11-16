# this_file: src/fontlab_glyport/plugins/tool_bridge.py
"""A Glyphs ``SelectTool`` as a FontLab Python tool (``registerPythonTool``).

FontLab calls the bridge with Qt events of a glyph canvas viewport:
``mousePressed/Moved/Released/DoubleClicked(event, canvas)``,
``keyPressed/Released(event, canvas)`` and ``activate``/``deactivate``. The
bridge makes the Glyphs call: ``mouseDown_``, ``mouseDragged_`` (a move with
a button down) or ``mouseMoved_``, ``mouseUp_``, ``mouseDoubleDown_`` (else
``mouseDown_`` with ``clickCount() == 2``), ``keyDown_`` and ``keyUp_``.

The ``NSEvent`` is copied eagerly: FontLab invalidates the Qt event after the
call. While a call runs, ``Glyphs.currentEvent()`` is that event, and
``tool.editViewController().graphicView()`` maps it to glyph units of the
active glyph (``getActiveLocation_``) through App's paint-context maths.

A mouse event is handled (FontLab's own tool skips it) only when the plugin
overrides the method. Keys are delivered but never claimed: FontLab also
sends ``ShortcutOverride`` as ``keyPressed``, and claiming it would swallow
every menu shortcut while the tool is active.

``activate``/``deactivate`` run the loader's callbacks (which add and remove
the tool's foreground/background painters) and the SDK's
``willActivate``/``willDeactivate``. Every plugin call goes through ``guard``,
and no exception from any callback reaches FontLab: it goes to ``sink``.
"""

import functools
import traceback
from collections.abc import Callable
from functools import cached_property
from typing import Any

import fontlabapp.contours.affine as affine  # noqa: PLR0402 - see fontlabapp.qt.painting.editor
from fontlabapp.qt.properties import value as qt_value

from ..drawing.events import NSEvent, event_scope, modifier_flags
from ..ui.cocoa import NSMakePoint


def overrides(tool: Any, name: str) -> bool:
    """True when ``tool``'s class defines ``name`` beyond Glyport's no-op."""
    method = getattr(type(tool), name, None)
    return callable(method) and not getattr(method, "glyport_default", False)


def _print_error(error: Exception, owner: object) -> None:
    traceback.print_exception(error)


class CanvasView:
    """``editViewController()`` and its ``graphicView()`` for one canvas, or
    for one paint call (``context``: the ``PaintContext`` being painted)."""

    def __init__(self, painters: Any, canvas: Any, qt: Any = None, context: Any = None):
        self._painters, self._canvas, self._qt = painters, canvas, qt
        if context is not None:
            self.__dict__["_active"] = context

    @cached_property
    def _active(self) -> Any:
        """The active glyph's ``PaintContext`` (computed on first use)."""
        contexts = self._painters._contexts(
            self._canvas, self._canvas.viewPort, None, None
        )
        return next((c for c in contexts if c.is_active_layer), None)

    def graphicView(self) -> "CanvasView":
        return self

    def activeLayer(self) -> Any:
        return None if self._active is None else self._active.layer

    def scale(self) -> float:
        return 1.0 if self._active is None else self._active.scale

    def _cursor(self) -> tuple[float, float]:
        """The live cursor in viewport pixels (an event without a point)."""
        from ..drawing.native_painters import paint_widget

        widget = self._canvas.viewPort if self._canvas is not None else paint_widget()
        if widget is None or self._qt is None:
            from ..ui.cocoa import unsupported

            raise unsupported("SelectTool.getActiveLocation_ without a canvas")
        point = widget.mapFromGlobal(self._qt.QtGui.QCursor.pos())
        return point.x(), point.y()

    def getActiveLocation_(self, event: Any) -> Any:
        """The event point (else the cursor) in glyph units of the active glyph."""
        context = self._active
        if context is None:
            return None
        full = affine.concat(
            affine.from_qtransform(context.glyph_to_canvas),
            affine.from_qtransform(context.canvas_to_view),
        )
        pixel = getattr(event, "_widget", None) or self._cursor()
        return NSMakePoint(*affine.apply(affine.invert(full), *pixel))

    def convertPoint_fromView_(self, point: Any, view: Any) -> Any:
        """Identity: ``locationInWindow`` is already in this view's coordinates,
        viewport points with y up (not glyph units)."""
        return point


def _contained(default: Any) -> Callable:
    """A FontLab callback that reports any exception to the sink instead."""

    def wrap(method: Callable) -> Callable:
        @functools.wraps(method)
        def call(self: "ToolBridge", *args: Any) -> Any:
            try:
                return method(self, *args)
            except Exception as exc:  # noqa: BLE001 - never raise into FontLab
                try:
                    self._sink(exc, self.tool)
                except Exception as sink_error:  # noqa: BLE001 - nor from the sink
                    _print_error(exc, self.tool)
                    _print_error(sink_error, self._sink)
                return default

        return call

    return wrap


class ToolBridge:
    """The object FontLab's ``registerPythonTool`` calls back."""

    def __init__(
        self,
        qt: Any,
        tool: Any,
        painters: Any,
        *,
        guard: Callable[..., Any] | None = None,
        activate: Callable[[], Any] | None = None,
        deactivate: Callable[[], Any] | None = None,
        sink: Callable[[Exception, object], object] | None = None,
    ):
        self.qt, self.tool, self.painters = qt, tool, painters
        self._guard, self._on = guard, (activate, deactivate)
        self._sink = sink or _print_error
        self._widget = None  # last mouse point, for key events (None: the cursor)

    def _call(self, function: Callable[..., Any], *args: Any) -> Any:
        if self._guard is None:
            return function(*args)
        return self._guard(self.tool, function, *args)

    @_contained(None)
    def activate(self) -> None:
        if self._on[0] is not None:
            self._call(self._on[0])
        self._call(self.tool.willActivate)

    @_contained(None)
    def deactivate(self) -> None:
        try:
            self._call(self.tool.willDeactivate)
        finally:  # the painters go even if willDeactivate (or its sink) fails
            if self._on[1] is not None:
                self._call(self._on[1])

    @_contained(False)
    def mousePressed(self, event: Any, canvas: Any) -> bool:
        return self._mouse("mouseDown_", event, canvas)

    @_contained(False)
    def mouseMoved(self, event: Any, canvas: Any) -> bool:
        name = "mouseDragged_" if int(event.buttons()) else "mouseMoved_"
        return self._mouse(name, event, canvas)

    @_contained(False)
    def mouseReleased(self, event: Any, canvas: Any) -> bool:
        return self._mouse("mouseUp_", event, canvas)

    @_contained(False)
    def mouseDoubleClicked(self, event: Any, canvas: Any) -> bool:
        double = overrides(self.tool, "mouseDoubleDown_")
        return self._mouse(
            "mouseDoubleDown_" if double else "mouseDown_", event, canvas, clicks=2
        )

    @_contained(False)
    def keyPressed(self, event: Any, canvas: Any) -> bool:
        return self._key("keyDown_", event, canvas)

    @_contained(False)
    def keyReleased(self, event: Any, canvas: Any) -> bool:
        return self._key("keyUp_", event, canvas)

    def _event(self, event: Any, canvas: Any, clicks: int = 1) -> NSEvent:
        """A Cocoa event (y up in viewport points) copied from ``event``."""
        ns = NSEvent.alloc().init()
        ns._flags = modifier_flags(self.qt, event.modifiers())
        ns._clicks, ns._widget = clicks, self._widget
        pixel = self._widget or CanvasView(None, canvas, self.qt)._cursor()
        height = qt_value(canvas.viewPort, "height")  # PythonQt: an int property
        ns._location = NSMakePoint(pixel[0], height - pixel[1])
        return ns

    def _dispatch(self, name: str, ns: NSEvent, canvas: Any) -> None:
        state = self.tool.__dict__
        had, previous = "_edit_view" in state, state.get("_edit_view")
        self.tool._edit_view = CanvasView(self.painters, canvas, self.qt)
        try:
            with event_scope(ns):
                self._call(getattr(self.tool, name), ns)
        finally:
            if had:  # a nested dispatch restores the outer event's view
                state["_edit_view"] = previous
            else:
                state.pop("_edit_view", None)

    def _mouse(self, name: str, event: Any, canvas: Any, clicks: int = 1) -> bool:
        point = event.localPos()
        self._widget = (point.x(), point.y())
        if not overrides(self.tool, name):
            return False
        self._dispatch(name, self._event(event, canvas, clicks), canvas)
        return True

    def _key(self, name: str, event: Any, canvas: Any) -> bool:
        if overrides(self.tool, name):
            ns = self._event(event, canvas)
            ns._characters, ns._key_code = event.text(), event.nativeVirtualKey()
            self._dispatch(name, ns, canvas)
        return False  # never claim keys (shortcut negotiation, see module doc)
