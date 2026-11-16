# this_file: src/fontlab_glyport/ui/application.py
"""NSApp's shared session proxy over the existing QApplication.

Uses known accessors only. Widget/action lists go through qtsafe; appearance
observers disconnect before session teardown. Private Glyphs controllers and
application-wide modal loops have no FontLab equivalent and remain explicit.
"""

from fontlabapp.qt.safe import qt_list

from .application_windows import MenuProxy, ProbeObject, WindowProxy
from .cocoa import Dispatcher, NSObject, unsupported

NSAppearanceNameAqua = "NSAppearanceNameAqua"
NSAppearanceNameDarkAqua = "NSAppearanceNameDarkAqua"


class Appearance(ProbeObject):
    _prefix = "NSAppearance"

    def __init__(self, dark):
        self._name = NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua

    def name(self):
        return self._name

    def bestMatchFromAppearancesWithNames_(self, names):
        return self._name if self._name in names else None


def application_class(qt, *, glyphs, main_window, on_close, wrap, error_sink) -> type:
    """Create the application class and one shared proxy for this session."""
    shared = []
    dispatch = Dispatcher(error_sink, wrap)

    class NSApplication(ProbeObject):
        def init(self):
            self._windows, self._signal, self._slot = [], None, None
            self._closed = False
            on_close(self.close)
            return self

        @classmethod
        def sharedApplication(cls):
            if not shared:
                shared.append(cls.alloc().init())
            return shared[0]

        def __call__(self):
            return self

        def delegate(self):
            return glyphs()

        def _window(self, widget):
            if widget is None:
                return None
            for native, proxy in self._windows:
                if native is widget:
                    return proxy
            document = lambda: (
                glyphs().currentDocument if widget is main_window() else None
            )
            proxy = WindowProxy(widget, document)
            self._windows.append((widget, proxy))
            return proxy

        def windows(self):
            return [
                self._window(w) for w in qt_list(qt.QtGui.QApplication.topLevelWidgets)
            ]

        def keyWindow(self):
            return self._window(qt.QtGui.QApplication.activeWindow())

        def mainWindow(self):
            return self._window(main_window())

        def firstResponder(self):
            window = self.keyWindow()
            return None if window is None else window.firstResponder()

        def mainMenu(self):
            window = main_window()
            return None if window is None else MenuProxy(window.menuBar())

        def updateWindows(self):
            for window in qt_list(qt.QtGui.QApplication.topLevelWidgets):
                window.update()

        def effectiveAppearance(self):
            color = qt.QtGui.QApplication.palette().color(qt.QtGui.QPalette.Window)
            return Appearance(color.lightnessF() < 0.5)

        def currentEvent(self):
            from ..drawing.events import current_event

            return current_event()

        def addObserver_forKeyPath_options_context_(
            self, observer, keyPath, options, context
        ):
            if self._closed:
                raise RuntimeError("Application proxy is closed")
            if keyPath != "effectiveAppearance":
                raise unsupported(f"NSApp.observe.{keyPath}")
            if self._signal is None:
                signal = qt.QtGui.QApplication.instance().paletteChanged
                self._appearance = self.effectiveAppearance()
                slot = lambda *args: dispatch.call(
                    self._appearance_changed, self, *args
                )
                signal.connect(slot)
                self._signal, self._slot = signal, slot
            NSObject.addObserver_forKeyPath_options_context_(
                self, observer, keyPath, options, context
            )

        def _appearance_changed(self, *args):
            old, self._appearance = self._appearance, self.effectiveAppearance()
            if old.name() != self._appearance.name():
                self._kvo_notify("effectiveAppearance", old)

        def removeObserver_forKeyPath_(self, observer, keyPath):
            NSObject.removeObserver_forKeyPath_(self, observer, keyPath)
            if not self.__dict__.get("_kvo_observers"):
                self._disconnect()

        def _disconnect(self):
            if self._signal is not None:
                self._signal.disconnect(self._slot)
                self._signal = self._slot = None

        def close(self):
            self._disconnect()
            self.__dict__.get("_kvo_observers", []).clear()
            self._windows.clear()
            self._closed = True

        def nextEventMatchingMask_untilDate_inMode_dequeue_(
            self, mask, date, mode, dequeue
        ):
            qt.QtGui.QApplication.processEvents()

        def sendEvent_(self, event):
            if event is not None:
                raise unsupported("NSApp.sendEvent_")

        def runModalForWindow_(self, window):
            raise unsupported("NSApp.runModalForWindow_")

        def stopModal(self):
            raise unsupported("NSApp.stopModal")

    return NSApplication
