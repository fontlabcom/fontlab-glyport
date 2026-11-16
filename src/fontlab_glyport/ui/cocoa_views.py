# this_file: src/fontlab_glyport/ui/cocoa_views.py
"""Qt-backed AppKit views with PyObjC-shaped APIs (R030); controls live in
``cocoa_controls``.

``make_appkit_classes(qt, error_sink=...)`` returns env-bound classes:
``NSView``, ``NSControl``, ``NSTextField``, ``NSSecureTextField``,
``GSSteppingTextField``, ``NSButton``, ``NSSlider``, ``NSPopUpButton``,
``NSProgressIndicator``, ``NSImageView``, ``GSPaletteView``,
``NSUserDefaultsController``, ``NSImage`` (``images``),
``NSStackView`` (``cocoa_containers``), ``NSWindow`` and ``NSPanel``
(``cocoa_window``). Each view owns one Qt widget (``view._qt``). Frames use Cocoa's bottom-left
origin and are converted against the superview height; ``autoresizingMask``
re-lays subviews out on resize (springs and struts, the change split evenly
between flexible parts). Target/action calls the target's method for the
selector with the control as sender (colon arity respected) through the
dispatcher; programmatic value setters never send the action, as in AppKit.
"""

from collections.abc import Callable, MutableMapping
from typing import Any

import fontlabapp.qt.numeric as _qt_numeric
from fontlabapp.core.signals.callbacks import quiet_callbacks
from fontlabapp.core.signals.connections import disconnect_connections, track_connection
from fontlabapp.qt.events.resize import resize_event_handler

from .cocoa import (
    Dispatcher,
    NSMakeRect,
    NSObject,
    NSRect,
    NSZeroRect,
    as_rect,
    perform,
    selector_of,
    unsupported,
)

SLIDER_STEPS = _qt_numeric.STEPS
# NSAutoresizingMaskOptions
NSViewMinXMargin, NSViewWidthSizable, NSViewMaxXMargin = 1, 2, 4
NSViewMinYMargin, NSViewHeightSizable, NSViewMaxYMargin = 8, 16, 32
# NSButtonType values used by the corpus and XIB button cells.
NSMomentaryLightButton, NSSwitchButton, NSRadioButton = 0, 3, 4
NSMomentaryPushInButton = 7
NSOffState, NSOnState, NSMixedState = 0, 1, -1
NSNotFound = 0x7FFFFFFFFFFFFFFF
NSNormalWindowLevel, NSFloatingWindowLevel = 0, 3
# Constants of the NIB classes (cocoa_window, cocoa_containers, cocoa_controls),
# defined here so a session's NS* export reaches scripts.
NSWindowStyleMaskTitled, NSWindowStyleMaskClosable = 1, 2
NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable = 4, 8
NSWindowStyleMaskUtilityWindow = 16
NSUserInterfaceLayoutOrientationHorizontal = 0
NSUserInterfaceLayoutOrientationVertical = 1
NSImageScaleProportionallyDown, NSImageScaleAxesIndependently = 0, 1
NSImageScaleNone, NSImageScaleProportionallyUpOrDown = 2, 3
NSImageInterpolationDefault, NSImageInterpolationNone = 0, 1
NSImageInterpolationLow, NSImageInterpolationHigh, NSImageInterpolationMedium = 2, 3, 4
NSRadioModeMatrix, NSHighlightModeMatrix = 0, 1
NSListModeMatrix, NSTrackModeMatrix = 2, 3
NSSegmentStyleAutomatic, NSSegmentStyleRounded, NSSegmentStyleTexturedRounded = 0, 1, 2
NSSegmentStyleRoundRect, NSSegmentStyleTexturedSquare, NSSegmentStyleCapsule = 3, 4, 5
NSSegmentStyleSmallSquare, NSSegmentStyleSeparated = 6, 8
NSSplitViewDividerStyleThick, NSSplitViewDividerStyleThin = 1, 2
NSSplitViewDividerStylePaneSplitter = 3
NSSegmentSwitchTrackingSelectOne, NSSegmentSwitchTrackingSelectAny = 0, 1
NSSegmentSwitchTrackingMomentary = 2
# NSCellImagePosition and NSLineBreakMode
NSNoImage, NSImageOnly, NSImageLeft, NSImageRight = 0, 1, 2, 3
NSImageBelow, NSImageAbove, NSImageOverlaps = 4, 5, 6
NSImageLeading, NSImageTrailing = 7, 8
NSLineBreakByWordWrapping, NSLineBreakByCharWrapping = 0, 1
NSLineBreakByClipping, NSLineBreakByTruncatingHead = 2, 3
NSLineBreakByTruncatingTail, NSLineBreakByTruncatingMiddle = 4, 5
# macOS NSTextAlignment: left 0, right 1, center 2, justified 3, natural 4.
_ALIGN = {0: "AlignLeft", 1: "AlignRight", 2: "AlignHCenter", 3: "AlignJustify"}
_ALIGN[4] = "AlignLeft"
_BUTTON_WIDGETS = {
    NSMomentaryLightButton: "QPushButton",
    NSMomentaryPushInButton: "QPushButton",
    NSSwitchButton: "QCheckBox",
    NSRadioButton: "QRadioButton",
}


def _number_text(value: float) -> str:
    """Cocoa-like number display: ``12.0`` -> ``"12"``, ``0.5`` -> ``"0.5"``."""
    value = float(value)
    return str(int(value)) if value.is_integer() else repr(value)


def _leading_number(text: str) -> float:
    """``NSString.doubleValue``: the leading decimal number, else 0.0."""
    text, end = text.strip(), 0
    for end in range(len(text), 0, -1):
        try:
            return float(text[:end])
        except ValueError:
            continue
    return 0.0


def _flex(start: float, size: float, total: float, delta: float, mask: tuple):
    """Springs and struts on one axis: split ``delta`` evenly between flex parts."""
    parts = [start, size, total - start - size]
    flexible = [i for i, flag in enumerate(mask) if flag]
    for i in flexible:
        parts[i] += delta / len(flexible)
    return parts[0], parts[1]


class _Env:
    """Qt, the callback dispatcher, defaults and every live view for teardown."""

    def __init__(self, qt, dispatcher: Dispatcher, defaults: MutableMapping):
        self.qt, self.dispatch, self.defaults = qt, dispatcher, defaults
        self.views: list = []
        self.widget_classes: dict[tuple, type] = {}
        self.defaults_controller = None
        self.objects: list = []  # non-view objects with dispose() (controllers)
        self.classes: dict[str, Any] = {}  # the bound classes, by name

    def subclass(self, name: str, factory: Callable[[type], type]) -> type:
        """The Qt class ``name`` subclassed by ``factory`` (made once per pair)."""
        key = (name, factory)
        if key not in self.widget_classes:
            self.widget_classes[key] = factory(getattr(self.qt.QtGui, name))
        return self.widget_classes[key]

    def close(self) -> None:
        """Disconnect slots, unbind and release targets, then delete top-level
        widgets (R027). Every view is attempted; the first failure is re-raised."""
        failures = []
        for obj in list(self.objects):
            try:
                obj.dispose()
            except Exception as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        for view in list(self.views):
            try:
                view._teardown()
            except Exception as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        for view in self.views:  # embedded views (window content, scroll
            # documents) are deleted with the widget holding them
            if view._superview is None and "_embedded" not in view.__dict__:
                view._qt.deleteLater()
        self.views.clear()
        if failures:
            raise failures[0]


def _container_class(base: type) -> type:
    """QWidget subclass: resizes autoresize subviews; paint and mouse events
    reach a Python NSView subclass's ``drawRect_``/``mouseDown_``/... (R032)."""

    class Container(base):
        _owner = None

        resizeEvent = resize_event_handler(base, lambda widget: widget._owner, "_qt_resized")

        def paintEvent(self, event):
            owner = self._owner
            if owner is None or not owner._custom("drawRect_"):
                base.paintEvent(self, event)
                return
            owner._paint(event)

        def mousePressEvent(self, event):
            if not self._mouse("mouseDown_", event):
                base.mousePressEvent(self, event)

        def mouseMoveEvent(self, event):
            if not self._mouse("mouseDragged_", event):
                base.mouseMoveEvent(self, event)

        def mouseReleaseEvent(self, event):
            if not self._mouse("mouseUp_", event):
                base.mouseReleaseEvent(self, event)

        def _mouse(self, selector, event) -> bool:
            owner = self._owner
            if owner is None or not owner._custom(selector):
                return False
            owner._mouse(selector, event)
            event.accept()
            return True

    return Container


class NSView(NSObject):
    """A Qt widget with a Cocoa frame; subviews follow ``autoresizingMask``."""

    _env: _Env
    _qt_class = "QWidget"
    _container = True
    _adopted = False  # wraps a widget vanilla owns and lays out (top-left frames)

    @classmethod
    def _wrap_widget(cls, widget):
        """An NSView facade for an existing vanilla-owned Qt widget."""
        view = cls.alloc()
        view._superview, view._subviews, view._mask, view._slots = None, [], 0, []
        view._qt, view._adopted, view._container = widget, True, False
        rect = widget.geometry
        view._frame = NSMakeRect(rect.x(), rect.y(), rect.width(), rect.height())
        return view

    def initWithFrame_(self, frame):
        self._frame = as_rect(frame)
        self._superview, self._subviews, self._mask = None, [], 0
        self._slots: list = []
        self._qt = self._make_widget()
        self._env.views.append(self)
        self._apply_geometry()
        return self

    def init(self):
        return self.initWithFrame_(NSZeroRect)

    def _make_widget(self) -> Any:
        if self._container:
            widget = self._env.subclass(self._qt_class, _container_class)()
            widget._owner = self
            return widget
        return getattr(self._env.qt.QtGui, self._qt_class)()

    def _track(self, signal: Any, slot: Callable) -> None:
        track_connection(self._slots, signal, slot)

    def _disconnect(self) -> None:
        disconnect_connections(
            self._slots, lambda error: self._env.dispatch.sink(error, self)
        )
        if self._container:
            self._qt._owner = None

    def _teardown(self) -> None:
        """Disconnect Qt slots and release Cocoa references (bindings, targets)."""
        self._disconnect()
        self._release()

    def _release(self) -> None:
        """Subclasses drop observers and targets here."""

    def dispose(self) -> None:
        """Tear this view tree down and delete its widget once (plugin unload)."""
        if self.__dict__.get("_disposed"):
            return
        self.__dict__["_disposed"] = True
        release_tree(self)
        if self._superview is not None:
            self.removeFromSuperview()
        self._qt.deleteLater()

    def _owned_views(self) -> list:
        """Views whose widgets go with this one: subviews, and the embedded
        views of scroll views (document) and tables (cell views)."""
        return list(self._subviews)

    def isFlipped(self) -> bool:
        return False

    def frame(self) -> NSRect:
        return self._frame

    def bounds(self) -> NSRect:
        return NSMakeRect(0, 0, *self._frame.size)

    def setFrame_(self, frame) -> None:
        old = self._frame.size
        self._frame = as_rect(frame)
        self._apply_geometry()
        if old != self._frame.size:
            self._autoresize(old, self._frame.size)

    def setFrameSize_(self, size) -> None:
        self.setFrame_(NSMakeRect(*self._frame.origin, *size))

    def setFrameOrigin_(self, point) -> None:
        self.setFrame_(NSMakeRect(*point, *self._frame.size))

    def _qt_rect(self) -> tuple[int, int, int, int]:
        (x, y), (w, h) = self._frame
        parent = self._superview
        if parent is not None and not parent.isFlipped():
            y = parent._frame.size.height - y - h
        return round(x), round(y), round(w), round(h)

    def _apply_geometry(self) -> None:
        if self.__dict__.get("_managed"):  # a tab page: its QTabWidget lays it out
            return
        x, y, w, h = self._qt_rect()
        adopted_child = self._adopted and self._qt.parentWidget() is not None
        if self._superview is None and not adopted_child:
            self._qt.resize(w, h)
        else:  # adopted vanilla controls keep vanilla's top-left frames
            self._qt.setGeometry(x, y, w, h)

    def _qt_resized(self, width: int, height: int) -> None:
        """A Qt resize the script did not make (a panel or window resized us)."""
        old = self._frame.size
        if (round(old.width), round(old.height)) == (width, height):
            return
        self._frame = NSMakeRect(*self._frame.origin, width, height)
        self._autoresize(old, self._frame.size)

    def _autoresize(self, old, new) -> None:
        for view in self._subviews:
            view._superview_resized(old, new)

    def _superview_resized(self, old, new) -> None:
        mask = self._mask
        (x, y), (w, h) = self._frame
        horizontal = (
            mask & NSViewMinXMargin,
            mask & NSViewWidthSizable,
            mask & NSViewMaxXMargin,
        )
        vertical = (
            mask & NSViewMinYMargin,
            mask & NSViewHeightSizable,
            mask & NSViewMaxYMargin,
        )
        if self._superview.isFlipped():
            vertical = vertical[::-1]
        x, w = _flex(x, w, old.width, new.width - old.width, horizontal)
        y, h = _flex(y, h, old.height, new.height - old.height, vertical)
        self.setFrame_(NSMakeRect(x, y, w, h))

    def autoresizingMask(self) -> int:
        return self._mask

    def setAutoresizingMask_(self, mask) -> None:
        self._mask = int(mask)

    def addSubview_(self, view) -> None:
        if view._superview is not None:
            view.removeFromSuperview()
        view._superview = self
        self._subviews.append(view)
        view._qt.setParent(self._qt)
        view._apply_geometry()
        if not view.isHidden():
            view._qt.show()

    def removeFromSuperview(self) -> None:
        parent = self._superview
        if parent is None:
            return
        parent._will_remove_subview(self)
        parent._subviews.remove(self)
        self._superview = None
        self._qt.setParent(None)

    def superview(self):
        return self._superview

    def enclosingScrollView(self):
        """The nearest scroll view holding this view (as its document or above)."""
        view = self._superview or self.__dict__.get("_embedded")
        while view is not None and not hasattr(view, "documentView"):
            view = view._superview or view.__dict__.get("_embedded")
        return view

    def subviews(self) -> list:
        return list(self._subviews)

    def setHidden_(self, hidden) -> None:
        self._qt.setVisible(not hidden)
        self.__dict__["_hidden"] = bool(hidden)
        if self._superview is not None:
            self._superview._subview_hidden(self)

    def _will_remove_subview(self, view) -> None:
        """Hook: ``view`` is leaving this view (a stack view re-arranges)."""

    def _subview_hidden(self, view) -> None:
        """Hook: ``view`` was hidden or shown."""

    def isHidden(self) -> bool:
        return self.__dict__.get("_hidden", False)

    def performSelector_withObject_afterDelay_(self, selector, argument, delay) -> None:
        """Call the selector later on the GUI thread (a single-shot QTimer);
        its exceptions go to the error sink, as other callbacks do."""
        method = getattr(self, str(selector).replace(":", "_"))
        ms = round(max(float(delay), 0.0) * 1000)
        self._env.qt.QtCore.QTimer.singleShot(
            ms, lambda: self._env.dispatch.call(lambda: method(argument), self)
        )

    def setNeedsLayout_(self, flag) -> None:
        """Qt lays widgets out itself: ask for a geometry update."""
        if flag:
            self._qt.updateGeometry()

    def setNeedsDisplay_(self, flag) -> None:
        if flag:
            self._qt.update()

    def setToolTip_(self, text) -> None:
        self._qt.setToolTip(str(text or ""))

    def toolTip(self) -> str:
        tip = self._qt.toolTip
        return str(tip() if callable(tip) else tip)

    # Custom views: a Python subclass's drawRect_ and mouse methods (R032).
    def _custom(self, selector: str) -> bool:
        """True when a subclass (not these base classes) defines ``selector``."""
        for cls in type(self).__mro__:
            if cls.__module__ in (__name__, "fontlab_glyport.ui.cocoa_controls"):
                return False
            if selector in vars(cls):
                return True
        return False

    def _paint(self, event) -> None:
        from ..drawing.context import view_scope

        qt = self._env.qt
        painter = qt.QtGui.QPainter(self._qt)
        try:
            height = self._frame.size.height
            with view_scope(qt, painter, height, flipped=self.isFlipped()):
                self._env.dispatch.call(lambda: self.drawRect_(self.bounds()), self)
        finally:
            painter.end()

    def _mouse(self, selector: str, event) -> None:
        from ..drawing.events import event_scope

        ns_event = self._env.classes["NSEvent"].from_qt(self._env.qt, event, self)
        with event_scope(ns_event):
            self._env.dispatch.call(lambda: getattr(self, selector)(ns_event), self)

    def convertPoint_fromView_(self, point, view):
        """Points from ``locationInWindow`` are already view-local here."""
        if view is not None and view is not self:
            raise unsupported("NSView.convertPoint_fromView_.otherView")
        return point

    def setAccessibilityLabel_(self, text) -> None:
        self._qt.setAccessibleName(str(text or ""))


def release_tree(root) -> None:
    """Disconnect, unbind and unregister ``root`` and every view it owns
    (without deleting widgets: their holder does that)."""
    env, stack = root._env, [root]
    while stack:
        view = stack.pop()
        stack.extend(view._owned_views())
        view._teardown()
        if view in env.views:
            env.views.remove(view)


class NSControl(NSView):
    """Target/action, enabled state, tags and the value accessors.

    ``_adopt`` wraps a widget another layer (vanilla) already owns: the
    wrapper connects its own signals only once a script sets a target or
    action on it, and then the owner's own callback route yields to it, as
    replacing an NSControl's target does in vanilla.
    """

    _container = False
    _quiet = False
    _owner = None
    _wired = True
    _binding_only = False  # adopted: wired for bindings, vanilla keeps the action

    def initWithFrame_(self, frame):
        self._control_state()
        NSView.initWithFrame_(self, frame)
        self._connect()
        return self

    def setFont_(self, font):
        if font is None:
            qfont = self._env.qt.QtGui.QFont()
        else:
            qfont = font.qfont(self._env.qt, font.pointSize())
            qfont.setPointSizeF(float(font.pointSize()))
        self._qt.setFont(qfont)
        self._font = font

    def font(self):
        from ..drawing.cocoa_drawing import NSFont
        from .application_windows import qt_value

        if self.__dict__.get("_font") is not None:
            return self._font
        font = qt_value(self._qt, "font")
        size = qt_value(font, "pointSizeF")
        if size <= 0:
            size = qt_value(font, "pixelSize") * 72 / self._qt.logicalDpiY()
        return NSFont.fontWithName_size_(qt_value(font, "family"), size)

    def _control_state(self) -> None:
        self._target = self._action = None
        self._continuous, self._tag = False, 0
        self._bindings: dict = {}

    @classmethod
    def _adopt(cls, widget: Any = None, owner: Any = None):
        """Wrap ``widget`` (or a new one of this class) owned by ``owner``."""
        self = cls.alloc()
        self._control_state()
        self._superview, self._subviews, self._mask, self._slots = None, [], 0, []
        self._owner, self._wired, self._adopted = owner, False, True
        self._qt = self._make_widget() if widget is None else widget
        rect = self._qt.geometry
        self._frame = NSMakeRect(rect.x(), rect.y(), rect.width(), rect.height())
        self._adopted_state()
        return self

    def _adopted_state(self) -> None:
        """Subclass state an adopted widget needs (initWithFrame_ sets it otherwise)."""

    def _take_route(self) -> None:
        """A native target/action replaces vanilla's own callback route."""
        if self._wired and not self._binding_only:
            return
        if self._owner is not None:
            self._owner._yield_action()
        if not self._wired:
            self._connect()
        self._wired, self._binding_only = True, False

    def _bind_route(self) -> None:
        """Bindings need the control's own signals; vanilla keeps its callback."""
        if not self._wired:
            self._connect()
            self._wired, self._binding_only = True, True

    def _connect(self) -> None:
        """Subclasses wire their Qt signals to ``_send``."""

    def _send(self) -> None:
        if self._quiet:
            return
        self._push_bindings()
        target, action = self._target, self._action
        if self._binding_only or target is None or action is None:
            return
        args = (self,) if action.count(":") else ()
        self._env.dispatch.call(lambda: perform(target, action, *args), self)

    def setTarget_(self, target) -> None:
        self._target = target
        self._take_route()

    def target(self):
        return self._target

    def setAction_(self, action) -> None:
        selector = None if action is None else selector_of(action)
        if selector is not None and selector.count(":") > 1:
            raise TypeError(f"an action takes at most the sender: {selector}")
        self._action = selector
        self._take_route()

    def action(self):
        return self._action

    def setContinuous_(self, flag) -> None:
        self._continuous = bool(flag)

    def isContinuous(self) -> bool:
        return self._continuous

    def setEnabled_(self, flag) -> None:
        self._qt.setEnabled(bool(flag))

    def isEnabled(self) -> bool:
        return bool(self._qt.isEnabled())

    def setTag_(self, tag) -> None:
        self._tag = int(tag)

    def tag(self) -> int:
        return self._tag

    def performClick_(self, sender) -> None:
        self._send()

    def _quietly(self, action: Callable[[], None]) -> None:
        with quiet_callbacks(self):
            action()

    # Value accessors over objectValue; subclasses define _get/_set.
    def objectValue(self):
        return self._get()

    def setObjectValue_(self, value) -> None:
        self._quietly(lambda: self._set(value))

    def stringValue(self) -> str:
        value = self._get()
        return value if isinstance(value, str) else _number_text(value)

    def setStringValue_(self, value) -> None:
        self.setObjectValue_("" if value is None else str(value))

    def doubleValue(self) -> float:
        value = self._get()
        return _leading_number(value) if isinstance(value, str) else float(value)

    floatValue = doubleValue

    def intValue(self) -> int:
        return int(self.doubleValue())

    integerValue = intValue

    def setDoubleValue_(self, value) -> None:
        self.setObjectValue_(float(value))

    setFloatValue_ = setDoubleValue_

    def setIntValue_(self, value) -> None:
        self.setObjectValue_(int(value))

    setIntegerValue_ = setIntValue_

    # Bindings: owner keyPath -> control; "value"/"selectedIndex" also push back.
    def _binding_setter(self, binding: str) -> Callable | None:
        if (
            binding.startswith("enabled")
            and binding[7:].isdigit()
            or binding == "enabled"
        ):
            return lambda value: self._enabled_part(binding, value)
        setters = {
            "value": self.setObjectValue_,
            "hidden": lambda value: self.setHidden_(bool(value)),
        }
        return setters.get(binding)

    def _enabled_part(self, binding: str, value) -> None:
        """``enabled``, ``enabled2``, ...: enabled only when all are true (AND)."""
        parts = self.__dict__.setdefault("_enabled_parts", {})
        parts[binding] = bool(value)
        self.setEnabled_(all(parts.values()))

    def bind_toObject_withKeyPath_options_(
        self, binding, owner, keyPath, options
    ) -> None:
        binding, keyPath = str(binding), str(keyPath)
        if self._binding_setter(binding) is None:
            raise unsupported(f"{type(self).__name__}.bind.{binding}")
        self.unbind_(binding)
        self._bind_route()
        owner.addObserver_forKeyPath_options_context_(self, keyPath, 0, binding)
        self._bindings[binding] = (owner, keyPath)
        self._pull_binding(binding)

    def unbind_(self, binding) -> None:
        entry = self._bindings.pop(binding, None)
        if entry is not None:
            entry[0].removeObserver_forKeyPath_(self, entry[1])
        parts = self.__dict__.get("_enabled_parts", {})
        if binding in parts:  # the remaining enabled bindings decide; with
            del parts[binding]  # none left the state stays, as in AppKit
            if parts:
                self.setEnabled_(all(parts.values()))

    def _release(self) -> None:
        for binding in list(self._bindings):
            self.unbind_(binding)
        self._target = self._action = None

    def observeValueForKeyPath_ofObject_change_context_(
        self, keyPath, owner, change, context
    ) -> None:
        if context in self._bindings and not self._quiet:
            self._pull_binding(context)

    def _pull_binding(self, binding: str) -> None:
        owner, keyPath = self._bindings[binding]
        value = owner.valueForKeyPath_(keyPath)
        if value is not None:
            self._binding_setter(binding)(value)

    def _push_bindings(self) -> None:
        for binding in ("value", "selectedIndex"):
            entry = self._bindings.get(binding)
            if entry is not None:
                owner, keyPath = entry
                write, value = owner.setValue_forKeyPath_, self._get()
                self._quietly(lambda w=write, v=value, k=keyPath: w(v, k))


class NSTabViewItem(NSObject):
    """A tab: identifier, label and the content view its ``NSTabView`` shows."""

    def initWithIdentifier_(self, identifier):
        self._identifier, self._label = identifier, ""
        self._view = self._tab_view = None
        return self

    def init(self):
        return self.initWithIdentifier_(None)

    def identifier(self):
        return self._identifier

    def label(self) -> str:
        return self._label

    def setLabel_(self, label) -> None:
        self._label = str(label or "")
        tabs = self._tab_view
        if tabs is not None:
            tabs._qt.setTabText(tabs._items.index(self), self._label)

    def view(self):
        return self._view

    def setView_(self, view) -> None:
        self._view = view

    def tabView(self):
        return self._tab_view


class NSTabView(NSView):
    """QTabWidget; each item's view is a page laid out by Qt (its subviews
    still follow their frames and autoresizing masks inside the page).
    ``selectedIndex`` binds both ways (a NIB binds it to the user defaults)."""

    _qt_class = "QTabWidget"

    def initWithFrame_(self, frame):
        self._items: list = []
        self._bindings: dict = {}
        self._quiet = False
        NSView.initWithFrame_(self, frame)
        self._track(self._qt.currentChanged, self._selection_changed)
        return self

    def bind_toObject_withKeyPath_options_(
        self, binding, owner, keyPath, options
    ) -> None:
        binding, keyPath = str(binding), str(keyPath)
        if binding != "selectedIndex":
            raise unsupported(f"NSTabView.bind.{binding}")
        self.unbind_(binding)
        owner.addObserver_forKeyPath_options_context_(self, keyPath, 0, binding)
        self._bindings[binding] = (owner, keyPath)
        self._pull_selection()

    def unbind_(self, binding) -> None:
        entry = self._bindings.pop(binding, None)
        if entry is not None:
            entry[0].removeObserver_forKeyPath_(self, entry[1])

    def _release(self) -> None:
        for binding in list(self._bindings):
            self.unbind_(binding)

    def observeValueForKeyPath_ofObject_change_context_(
        self, keyPath, owner, change, context
    ) -> None:
        if context in self._bindings and not self._quiet:
            self._pull_selection()

    def _pull_selection(self) -> None:
        owner, keyPath = self._bindings["selectedIndex"]
        value = owner.valueForKeyPath_(keyPath)
        if value is not None:
            self.selectTabViewItemAtIndex_(int(value))

    def _selection_changed(self, index) -> None:
        entry = self._bindings.get("selectedIndex")
        if entry is None or self._quiet:
            return
        with quiet_callbacks(self):
            entry[0].setValue_forKeyPath_(int(index), entry[1])

    def addSubview_(self, view) -> None:
        """A NIB page arrives as a subview labelled by the loader."""
        label = view.__dict__.get("_tab_label")
        if label is None:
            NSView.addSubview_(self, view)
            return
        item = NSTabViewItem.alloc().initWithIdentifier_(
            view.__dict__.get("_tab_identifier")
        )
        item.setLabel_(label)
        item.setView_(view)
        self.addTabViewItem_(item)

    def addTabViewItem_(self, item) -> None:
        view = item.view()
        view._superview = self
        view.__dict__["_managed"] = True
        self._subviews.append(view)
        item._tab_view = self
        self._items.append(item)
        self._qt.addTab(view._qt, item.label())

    def _autoresize(self, old, new) -> None:
        for view in self._subviews:
            if not view.__dict__.get("_managed"):  # Qt resizes the pages
                view._superview_resized(old, new)

    def tabViewItems(self) -> list:
        return list(self._items)

    def numberOfTabViewItems(self) -> int:
        return len(self._items)

    def tabViewItemAtIndex_(self, index):
        return self._items[index]

    def indexOfTabViewItem_(self, item) -> int:
        return self._items.index(item) if item in self._items else NSNotFound

    def selectTabViewItemAtIndex_(self, index) -> None:
        self._qt.setCurrentIndex(int(index))

    def selectTabViewItem_(self, item) -> None:
        self.selectTabViewItemAtIndex_(self._items.index(item))

    def selectedTabViewItem(self):
        index = self._qt.currentIndex
        index = index() if callable(index) else index
        return self._items[index] if 0 <= index < len(self._items) else None


class GSPaletteView(NSView):
    """Glyphs' palette content view: a plain container whose height sizes the palette."""


class GSInspectorView(NSView):
    """Glyphs' inspector pane (a private NSView subclass): a plain container."""


class _DefaultsValues(NSObject):
    """``controller.values``: KVC over the defaults mapping, observed per key."""

    def __init__(self, mapping: MutableMapping):
        self._mapping = mapping

    def valueForKey_(self, key):
        return self._mapping.get(key)

    def setValue_forKey_(self, value, key) -> None:
        old = self._mapping.get(key)
        if value is None:
            self._mapping.pop(key, None)
        else:
            self._mapping[key] = value
        self._kvo_notify(key, old)


class NSUserDefaultsController(NSObject):
    """Shared controller; ``values.<key>`` reads/writes the injected defaults."""

    _env: _Env

    @classmethod
    def sharedUserDefaultsController(cls):
        env = cls._env
        if env.defaults_controller is None:
            controller = cls.alloc().init()
            controller._values = _DefaultsValues(env.defaults)
            env.defaults_controller = controller
        return env.defaults_controller

    def values(self):
        return self._values

    # "values.<key>": the whole rest is one defaults key (keys may contain dots).
    def valueForKeyPath_(self, path):
        return self._values.valueForKey_(self._key(path))

    def setValue_forKeyPath_(self, value, path) -> None:
        self._values.setValue_forKey_(value, self._key(path))

    @staticmethod
    def _key(path: str) -> str:
        head, _, key = str(path).partition(".")
        if head != "values" or not key:
            raise unsupported(f"NSUserDefaultsController.{path}")
        return key

    def addObserver_forKeyPath_options_context_(
        self, observer, keyPath, options, context
    ) -> None:
        values = self._values
        values.addObserver_forKeyPath_options_context_(
            observer, self._key(keyPath), options, context
        )

    def removeObserver_forKeyPath_(self, observer, keyPath) -> None:
        self._values.removeObserver_forKeyPath_(observer, self._key(keyPath))


_VIEW_CLASSES = (
    NSView,
    NSControl,
    NSTabView,
    GSPaletteView,
    GSInspectorView,
    NSUserDefaultsController,
)


def make_appkit_classes(
    qt: Any,
    *,
    error_sink: Callable[[Exception, object], object],
    wrap: Callable | None = None,
    defaults: MutableMapping | None = None,
) -> dict[str, Any]:
    """Return env-bound AppKit classes and helpers; ``["close"]`` tears down.

    ``defaults`` backs ``NSUserDefaultsController`` (pass the same mapping as
    ``GlyphsApp`` defaults); it defaults to a fresh dict.
    """
    env = _Env(qt, Dispatcher(error_sink, wrap), {} if defaults is None else defaults)
    from ..drawing.events import NSEvent
    from .cocoa_containers import CONTAINER_CLASSES, NSEdgeInsetsMake
    from .cocoa_controls import (  # they subclass NSControl
        CONTROL_CLASSES,
        NSURL,
        NSNumberFormatter,
    )
    from .cocoa_table import (
        TABLE_CLASSES,
        NSIndexSet,
        NSTableColumn,
    )
    from .cocoa_text import TEXT_CLASSES
    from .cocoa_window import WINDOW_CLASSES
    from .images import image_class

    names: dict[str, Any] = {
        "NSEvent": type(
            "NSEvent", (NSEvent,), {"_qt_module": qt, "__module__": "AppKit"}
        ),
        "NSObject": NSObject,
        "NSTabViewItem": NSTabViewItem,
        "NSNumberFormatter": NSNumberFormatter,
        "NSImage": image_class(qt),  # a session binds its resource folders
        "NSURL": NSURL,
        "NSEdgeInsetsMake": NSEdgeInsetsMake,
        "NSIndexSet": NSIndexSet,
        "NSTableColumn": NSTableColumn,
        "close": env.close,
    }

    bound: dict[type, type] = {}
    for cls in (
        _VIEW_CLASSES
        + CONTROL_CLASSES
        + CONTAINER_CLASSES
        + TABLE_CLASSES
        + TEXT_CLASSES
        + WINDOW_CLASSES
    ):  # parents first, so bound classes keep the hierarchy
        parents = tuple(bound[b] for b in cls.__bases__ if b in bound)
        bound[cls] = type(cls.__name__, (cls, *parents), {"_env": env})
        names[cls.__name__] = bound[cls]
    env.classes = names
    return names
