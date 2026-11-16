# this_file: src/fontlab_glyport/ui/cocoa_window.py
"""Qt-backed ``NSWindow`` and ``NSPanel`` (R031: NIB window templates).

A window is a top-level ``QWidget`` holding its content view, which is resized
with the window (subviews follow their autoresizing masks). The content rect
uses Cocoa's bottom-left screen origin, converted against the available
geometry of the desktop. A panel (or a ``utility`` style mask) is a Qt tool
window; a window without the ``resizable`` style keeps a fixed size.

Nothing is shown when a NIB is loaded: scripts call ``makeKeyAndOrderFront_``.
``performClose_`` and the title-bar close button ask the delegate's
``windowShouldClose_`` (``close()`` does not); every close sends
``windowWillClose_`` with a notification
whose ``object()`` is the window. ``close()`` of the AppKit environment tears
windows down without delegate calls.
"""

from typing import Any

from fontlabapp.qt.events.resize import resize_event_handler

from .cocoa import NSMakeRect, NSObject, NSRect, as_rect
from .cocoa_views import (
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskUtilityWindow,
    release_tree,
)


def _window_widget_class(base: type) -> type:
    """QWidget subclass: resizes reach the content view, a title-bar close the
    delegate (PythonQt: call the native handler explicitly, no ``super()``)."""

    class WindowWidget(base):
        _owner = None

        resizeEvent = resize_event_handler(
            base, lambda widget: widget._owner, "_qt_resized"
        )

        def closeEvent(self, event):
            owner = self._owner
            if owner is not None and not owner._title_bar_close():
                event.ignore()
                return
            base.closeEvent(self, event)

    return WindowWidget


class _Notification:
    def __init__(self, name: str, obj: Any):
        self._name, self._object = name, obj

    def name(self) -> str:
        return self._name

    def object(self):
        return self._object


class NSWindow(NSObject):
    """A top-level Qt window with a Cocoa content view and delegate."""

    _env: Any
    _tool = False

    def initWithContentRect_styleMask_backing_defer_(self, rect, style, backing, defer):
        self._rect, self._style = as_rect(rect), int(style)
        self._delegate = self._content = None
        self._superview, self._subviews = None, []  # env.close treats it as a root
        self._qt = self._env.subclass("QWidget", _window_widget_class)()
        if self._tool or self._style & NSWindowStyleMaskUtilityWindow:
            self._qt.setWindowFlags(self._env.qt.QtCore.Qt.Tool)
        self._place()
        self._qt._owner = self
        self._env.views.append(self)
        view = self._env.classes["NSView"].alloc()
        self.setContentView_(view.initWithFrame_(NSMakeRect(0, 0, *self._rect.size)))
        return self

    def init(self):
        return self.initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 480, 270), NSWindowStyleMaskTitled, 2, False
        )

    def _place(self) -> None:
        (x, y), (w, h) = self._rect
        screen = self._env.qt.QtGui.QApplication.desktop().availableGeometry(self._qt)
        top = screen.y() + screen.height() - round(y) - round(h)
        self._qt.setGeometry(round(x), top, round(w), round(h))
        if not self._style & NSWindowStyleMaskResizable:
            self._qt.setMinimumSize(round(w), round(h))
            self._qt.setMaximumSize(round(w), round(h))

    def _qt_resized(self, width: int, height: int) -> None:
        self._rect = NSMakeRect(*self._rect.origin, width, height)
        if self._content is not None:
            self._content.setFrame_(NSMakeRect(0, 0, width, height))

    def contentView(self):
        return self._content

    def setContentView_(self, view) -> None:
        old = self._content
        if old is not None:
            old.__dict__.pop("_embedded", None)
            old._qt.setParent(None)
        self._content = view
        view.__dict__["_embedded"] = self  # deleted with the window widget
        view._qt.setParent(self._qt)
        view.setFrame_(NSMakeRect(0, 0, *self._rect.size))
        view._qt.setGeometry(
            0, 0, round(self._rect.size.width), round(self._rect.size.height)
        )
        view._qt.show()

    def styleMask(self) -> int:
        return self._style

    def title(self) -> str:
        return self._qt.windowTitle

    def setTitle_(self, title) -> None:
        self._qt.setWindowTitle(str(title or ""))

    def frame(self) -> NSRect:
        return self._rect

    def setContentSize_(self, size) -> None:
        width, height = round(size[0]), round(size[1])
        if not self._style & NSWindowStyleMaskResizable:  # move the fixed size
            self._qt.setMinimumSize(width, height)
            self._qt.setMaximumSize(width, height)
        self._qt.resize(width, height)
        rect = self._qt.geometry  # what Qt allowed
        self._qt_resized(rect.width(), rect.height())  # Qt defers events while hidden

    def delegate(self):
        return self._delegate

    def setDelegate_(self, delegate) -> None:
        self._delegate = delegate

    def isVisible(self) -> bool:
        return bool(self._qt.isVisible())

    def makeKeyAndOrderFront_(self, sender) -> None:
        self._qt.show()
        self._qt.raise_()
        self._qt.activateWindow()

    def orderFront_(self, sender) -> None:
        self._qt.show()
        self._qt.raise_()

    def orderOut_(self, sender) -> None:
        self._qt.hide()

    def center(self) -> None:
        screen = self._env.qt.QtGui.QApplication.desktop().availableGeometry(self._qt)
        rect = self._qt.geometry
        x = screen.x() + (screen.width() - rect.width()) // 2
        y = screen.y() + (screen.height() - rect.height()) // 2
        self._qt.setGeometry(x, y, rect.width(), rect.height())

    def performClose_(self, sender) -> None:
        if self._should_close():
            self.close()

    def _should_close(self) -> bool:
        should = getattr(self._delegate, "windowShouldClose_", None)
        answer = [True]
        if should is not None:  # an exception in the delegate keeps the window
            answer[0] = False
            self._env.dispatch.call(lambda: answer.__setitem__(0, should(self)), self)
        return bool(answer[0])

    def close(self) -> None:
        """Close without asking the delegate (AppKit ``close``)."""
        self._closing = True
        try:
            if self._qt.isVisible():
                self._qt.close()
            else:
                self._will_close()
        finally:
            self._closing = False

    def _title_bar_close(self) -> bool:
        """Qt closeEvent: a script close goes ahead; the title-bar button asks
        ``windowShouldClose_`` first. True when the window closes."""
        if not self.__dict__.get("_closing") and not self._should_close():
            return False
        self._will_close()
        return True

    def _will_close(self) -> None:
        will = getattr(self._delegate, "windowWillClose_", None)
        if will is not None:
            note = _Notification("NSWindowWillCloseNotification", self)
            self._env.dispatch.call(lambda: will(note), self)

    def _teardown(self) -> None:
        """Environment close: no delegate calls; the content view tears down itself."""
        self._qt._owner = None
        self._delegate = None

    def _owned_views(self) -> list:
        return [] if self._content is None else [self._content]

    def dispose(self) -> None:
        """Plugin unload: release the content tree, hide and delete the window
        once, without delegate calls."""
        if self.__dict__.get("_disposed"):
            return
        self.__dict__["_disposed"] = True
        release_tree(self)  # the window and its content; widgets go with it
        self._qt.hide()
        self._qt.deleteLater()


class NSPanel(NSWindow):
    """A utility window (Qt tool window)."""

    _tool = True


WINDOW_CLASSES = (NSWindow, NSPanel)
