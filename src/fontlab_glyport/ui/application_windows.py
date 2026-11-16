# this_file: src/fontlab_glyport/ui/application_windows.py
"""Explicit Cocoa reads over existing Qt windows and menus; no widget creation."""

import fontlabapp.qt.properties as _qt_properties
from fontlabapp.qt.safe import qt_list

from .._strict import caller_location
from ..errors import UnsupportedAttribute
from .cocoa import NSObject


class ProbeObject(NSObject):
    _prefix = "NSApp"

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        raise UnsupportedAttribute(
            f"Unsupported capability: {self._prefix}.{name}",
            capability=f"{self._prefix}.{name}",
            location=caller_location(),
        )


def qt_value(obj, name):
    """Read one known Qt property (PythonQt) or zero-arg accessor (doubles)."""
    return _qt_properties.value(obj, name)


class WindowController(ProbeObject):
    _prefix = "NSWindowController"

    def __init__(self, document):
        self._document = document

    def document(self):
        return self._document()


class WindowProxy(ProbeObject):
    _prefix = "NSWindow"

    def __init__(self, widget, document):
        self._widget = widget
        self._controller = WindowController(document)
        self._responder = None

    def title(self):
        return str(qt_value(self._widget, "windowTitle"))

    def isVisible(self):
        return bool(self._widget.isVisible())

    def alphaValue(self):
        return float(qt_value(self._widget, "windowOpacity"))

    def setAlphaValue_(self, value):
        self._widget.setWindowOpacity(float(value))

    def firstResponder(self):
        widget = self._widget.focusWidget()
        if widget is None:
            self._responder = None
            return None
        if self._responder is None or self._responder._widget is not widget:
            self._responder = ResponderProxy(widget)
        return self._responder

    def windowController(self):
        return self._controller


class ResponderProxy(ProbeObject):
    """Opaque focused Qt responder; unsupported Cocoa methods remain probe-safe."""

    _prefix = "NSResponder"

    def __init__(self, widget):
        self._widget = widget


class MenuProxy(ProbeObject):
    _prefix = "NSMenu"

    def __init__(self, menu):
        self._menu = menu

    def itemArray(self):
        return [MenuItemProxy(action) for action in qt_list(self._menu.actions)]

    def numberOfItems(self):
        return len(self.itemArray())

    def itemAtIndex_(self, index):
        return self.itemArray()[index]

    def itemWithTitle_(self, title):
        return next((item for item in self.itemArray() if item.title() == title), None)


class MenuItemProxy(ProbeObject):
    _prefix = "NSMenuItem"

    def __init__(self, action):
        self._action = action

    def title(self):
        return str(qt_value(self._action, "text")).replace("&", "")

    def submenu(self):
        menu = self._action.menu()
        return None if menu is None else MenuProxy(menu)
