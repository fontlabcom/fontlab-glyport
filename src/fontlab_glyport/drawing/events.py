# this_file: src/fontlab_glyport/drawing/events.py
"""``NSEvent`` for custom views and tools, built from Qt mouse events (R032).

``locationInWindow()`` is the point in the receiving view's own Cocoa
coordinates (y up unless the view is flipped), so the corpus idiom
``view.convertPoint_fromView_(event.locationInWindow(), None)`` yields view
coordinates. Modifier flags use AppKit's bits; on macOS Qt reports Command
as ``ControlModifier`` and Control as ``MetaModifier``.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from ..ui.cocoa import NSMakePoint, NSObject

NSEventModifierFlagShift = 1 << 17
NSEventModifierFlagControl = 1 << 18
NSEventModifierFlagOption = 1 << 19
NSEventModifierFlagCommand = 1 << 20
_QT_MODIFIERS = (
    ("ShiftModifier", NSEventModifierFlagShift),
    ("MetaModifier", NSEventModifierFlagControl),
    ("AltModifier", NSEventModifierFlagOption),
    ("ControlModifier", NSEventModifierFlagCommand),
)
_CURRENT_EVENT = ContextVar("glyport_cocoa_event", default=None)


def current_event():
    return _CURRENT_EVENT.get()


@contextmanager
def event_scope(event):
    token = _CURRENT_EVENT.set(event)
    try:
        yield
    finally:
        _CURRENT_EVENT.reset(token)


def modifier_flags(qt, modifiers):
    flags = 0
    for name, bit in _QT_MODIFIERS:
        if int(modifiers) & int(getattr(qt.QtCore.Qt, name)):
            flags |= bit
    return flags


class _ModifierFlags:
    """Cocoa has two methods with this selector: class and instance."""

    def __get__(self, event, owner):
        return (lambda: event._flags) if event is not None else owner._current_flags


class NSEvent(NSObject):
    _qt_module = None
    _flags = 0
    modifierFlags = _ModifierFlags()

    @classmethod
    def _qt(cls):
        if cls._qt_module is not None:
            return cls._qt_module
        try:
            import PythonQt
        except ImportError as error:
            from ..errors import HostUnavailable

            raise HostUnavailable("NSEvent requires PythonQt") from error
        return PythonQt

    @classmethod
    def _current_flags(cls):
        qt = cls._qt()
        query = getattr(qt.QtGui.QApplication, "queryKeyboardModifiers", None)
        return modifier_flags(qt, (query or qt.QtGui.QApplication.keyboardModifiers)())

    @classmethod
    def synthetic(cls):
        """An event outside tool events: live modifiers, and ``locationInWindow``
        is the cursor in the active window's points with y up, as in Cocoa
        (no active window: screen points, y up). No view point: a graphic
        view's ``getActiveLocation_`` reads the cursor instead."""
        from fontlabapp.qt.properties import value as qt_value

        self = cls.alloc().init()
        self._flags, self._clicks = cls._current_flags(), 1
        gui = cls._qt().QtGui
        cursor = gui.QCursor.pos()
        window = gui.QApplication.activeWindow()
        if window is not None:
            point, height = window.mapFromGlobal(cursor), qt_value(window, "height")
        else:
            screen = qt_value(gui.QApplication.primaryScreen(), "geometry")
            point, height = cursor, qt_value(screen, "height")
        self._location = NSMakePoint(point.x(), height - point.y())
        return self

    @classmethod
    def from_qt(cls, qt: Any, event: Any, view: Any):
        """Wrap a QMouseEvent delivered to ``view``'s widget."""
        self = cls.alloc().init()
        position = event.localPos()
        x, y = position.x(), position.y()
        if not view.isFlipped():
            y = view.frame().size.height - y
        self._location = NSMakePoint(x, y)
        self._flags = modifier_flags(qt, event.modifiers())
        double = qt.QtCore.QEvent.MouseButtonDblClick
        self._clicks = 2 if int(event.type()) == int(double) else 1
        return self

    def locationInWindow(self):
        return self._location

    def clickCount(self) -> int:
        return self._clicks

    _characters, _key_code = "", 0  # set for key events (tool bridge)

    def characters(self) -> str:
        return self._characters

    def charactersIgnoringModifiers(self) -> str:
        return self._characters

    def keyCode(self) -> int:
        """The macOS virtual key code (Qt ``nativeVirtualKey``)."""
        return self._key_code
