# this_file: src/fontlab_glyport/ui/vanilla.py
"""vanilla core controls as real Qt widgets plus a recorded UI graph.

Qt arrives through an injected ``qt`` namespace exposing ``QtCore`` and
``QtGui`` (FontLab's PythonQt keeps widgets in ``QtGui``); nothing here imports
a Qt binding. Each window owns a ``UIGraph``; controls become graph nodes when
they join a window, and callbacks become graph connections. ``getNSView()``
returns the underlying Qt widget as the compatibility handle for now.

Window ``autosaveName`` frames live in an injected ``settings`` mapping (default:
the process-wide in-memory ``_DEFAULT_SETTINGS``); nothing is written to FontLab
preferences or files.
"""

import math
import traceback
from collections.abc import Callable, MutableMapping, Sequence
from types import ModuleType
from typing import Any
from weakref import WeakValueDictionary

import fontlabapp.qt.numeric as _qt_numeric
from fontlabapp.core.signals.callbacks import quiet_callbacks
from fontlabapp.core.signals.connections import disconnect_connections, track_connection
from fontlabapp.qt.events.key import key_press_handler
from fontlabapp.qt.events.resize import resize_event_handler

from ..errors import UnsupportedCapability
from ..receipt import SourceLocation
from .graph import AUTO, Frame, UIGraph, resolve_frame

SLIDER_STEPS = _qt_numeric.STEPS
ErrorSink = Callable[[Exception, object], object]
Wrap = Callable[[Callable], Callable]
Settings = MutableMapping[str, Any]
# Close-hook registrar such as ``ExecutionContext.on_close``.
OnClose = Callable[[Callable[[], object]], object]

# Process-wide autosave store shared by modules made without ``settings=``.
_DEFAULT_SETTINGS: dict[str, Any] = {}
_AUTOSAVE_PREFIX = "window:"
# vanilla alignment -> horizontal Qt flag; VCenter keeps QLabel/QLineEdit default.
_ALIGNMENTS = {
    "left": "AlignLeft",
    "natural": "AlignLeft",
    "center": "AlignHCenter",
    "right": "AlignRight",
    "justified": "AlignJustify",
}
_RETURN_KEYS = ("Key_Return", "Key_Enter")


def _unsupported(subject: str, names: Sequence[str]) -> UnsupportedCapability:
    capability = f"{subject}.{names[0]}"
    return UnsupportedCapability(
        f"Unsupported capability: {subject}: {', '.join(names)}",
        capability=capability,
    )


def _properties(cls_name: str, options: dict[str, Any], **known: Any) -> dict:
    """Return JSON-ready node properties; reject any keyword not listed."""
    extra = sorted(set(options) - {"sizeStyle"})
    if extra:
        raise _unsupported(f"vanilla.{cls_name}", extra)
    return {**known, **options}


def _ints(values: Sequence[float]) -> list[int]:
    return [round(v) for v in values]


def _selector(callback: Callable) -> str:
    return getattr(callback, "__name__", None) or type(callback).__name__


def _alignment_flags(qt: Any, cls_name: str, alignment: Any) -> Any:
    """Map a vanilla alignment name to Qt flags; unknown names are unsupported."""
    name = _ALIGNMENTS.get(alignment) if isinstance(alignment, str) else None
    if name is None:
        shown = alignment if isinstance(alignment, str) else type(alignment).__name__
        raise _unsupported(f"vanilla.{cls_name}.alignment", [shown])
    flags = qt.QtCore.Qt
    return getattr(flags, name) | flags.AlignVCenter


def _stored_frame(value: Any) -> list[int] | None:
    """Parse an autosaved ``[x, y, w, h]`` (finite, positive size); else None."""
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    if not all(_finite_number(v) for v in value):
        return None
    frame = _ints(value)
    return frame if frame[2] > 0 and frame[3] > 0 else None


_QT_WIDGET_LIMIT = 16777215  # QWIDGETSIZE_MAX; larger values are not valid frames


def _finite_number(value: Any) -> bool:
    """True for a real number within Qt's widget size limit (never raises)."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and abs(value) <= _QT_WIDGET_LIMIT
    except OverflowError:  # int too large for float conversion
        return False


class _Env:
    """Per-module state: injected Qt, error sink, graph factory, open windows."""

    def __init__(
        self,
        qt: Any,
        error_sink: ErrorSink,
        graph_factory: Callable,
        wrap: Wrap | None,
        settings: Settings,
    ):
        self.qt, self.sink, self.graph_factory = qt, error_sink, graph_factory
        self.wrap, self.settings = wrap, settings
        self.open_windows: set = set()
        self.window_widget = _window_widget_class(qt.QtGui.QWidget)
        self.widget_classes: dict[str, type] = {}  # lazily built Python subclasses
        self._appkit: dict[str, Any] | None = None
        self.control_handles = WeakValueDictionary()

    @property
    def appkit(self) -> dict[str, Any]:
        """Qt-backed AppKit classes for native handles (built on first use)."""
        if self._appkit is None:
            from .cocoa_views import make_appkit_classes

            self._appkit = make_appkit_classes(
                self.qt, error_sink=self.sink, wrap=self.wrap
            )
        return self._appkit

    def close_windows(self) -> None:
        """Context close hook: close every open window, then re-raise.

        A process exit from a close bind is re-raised in preference to errors.
        """
        failures = []
        for window in list(self.open_windows):
            try:
                getattr(window, "_close_context", window.close)()
            except BaseException as error:  # noqa: BLE001 - re-raised below
                failures.append(error)
        if failures:
            exits = [e for e in failures if not isinstance(e, Exception)]
            raise (exits or failures)[0]

    def report(self, callback: Callable, sender: object) -> None:
        """Run a script callback (through ``wrap`` when given); errors go to the sink."""
        try:
            (self.wrap(callback) if self.wrap else callback)(sender)
        except Exception as exc:  # noqa: BLE001 - the sink is the error route
            self.sink(exc, sender)


def _window_widget_class(base: type) -> type:
    """Python subclass so resize/close reach the vanilla Window (PythonQt-safe)."""

    class WindowWidget(base):
        resizeEvent = resize_event_handler(
            base, lambda widget: widget._owner, "_resized"
        )

        def changeEvent(self, event):
            base.changeEvent(self, event)
            owner = self._owner
            if owner is not None and not owner._closed:
                kind = event.type()
                events = owner._env.qt.QtCore.QEvent
                name = "became key" if kind == events.WindowActivate else None
                if name:
                    for callback in tuple(owner._event_binds.get(name, ())):
                        owner._env.report(callback, owner)

        def closeEvent(self, event):
            owner = self._owner
            if owner is not None and not owner._closed:
                owner._teardown(view_closing=True)
            base.closeEvent(self, event)

        # QWidget windows have no dialog default-button handling: preserve the
        # caller's Return/Enter policy while sharing only accept/base routing.
        keyPressEvent = key_press_handler(
            base,
            lambda widget, event: (
                (owner := widget._owner) is not None
                and owner._press_default(event.key())
            ),
        )

    return WindowWidget


class _Container:
    """Attribute assignment of a control adds it as a child node and widget."""

    _graph: UIGraph | None = None
    _node = None
    _root_id: str | None = None
    _size: tuple | None = None

    def __setattr__(self, name: str, value: Any) -> None:
        if isinstance(value, _Control) and not name.startswith("_"):
            self._attach(name, value)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self._children:
            self._children.pop(name)._retire()
        object.__delattr__(self, name)

    def _attach(self, name: str, control: "_Control") -> None:
        if self._children.get(name) is control:
            return
        if control._retired:
            raise ValueError(f"{name}: control was removed from its parent")
        if control._parent is not None:
            raise ValueError(f"{name}: control already belongs to a parent")
        if name in self._children:
            self._children.pop(name)._retire()
        control._parent = self
        self._children[name] = control
        control._view.setParent(self._host_view())
        if self._size is not None and control._pos_size != AUTO:
            control._place(*self._size)
        if not control._hidden:
            control._view.show()
        if self._graph is not None:
            control._register(self._graph, self._node.node_id, name, self._root_id)

    def _host_view(self) -> Any:
        """The widget children are parented to (a Box's inner content widget)."""
        return self._view

    def _relayout(self) -> None:
        rules = self.__dict__.get("_auto_rules", ())
        constrained = {name for equation, _ in rules for name, _ in equation}
        for name, child in self._children.items():
            if child._pos_size != AUTO or name not in constrained:
                child._place(*self._size)
        if self.__dict__.get("_auto_rules"):
            from .vanilla_layout import apply_rules

            apply_rules(self, self._auto_rules)

    def addAutoPosSizeRules(self, rules, metrics=None):
        from .vanilla_layout import apply_rules, prepare_rules

        prepared = [
            *self.__dict__.get("_auto_rules", ()),
            *prepare_rules(self, rules, metrics or {}),
        ]
        if self._size is not None:
            apply_rules(self, prepared)
        self._auto_rules = prepared

    def _disconnect_children(self) -> None:
        for child in self._children.values():
            child._disconnect()


class _ActionTarget:
    """vanilla's ``_target``: forwards the native action to the script callback."""

    def __init__(self, control: "_Control"):
        self._control = control

    def action_(self, sender) -> None:
        callback = self._control._events.get("action")
        if callback is not None:
            self._control._env.report(callback, self._control)


class _Control:
    """Common vanilla control behavior over one Qt widget."""

    _env: _Env
    _qt_class = "QWidget"
    _quiet = False
    _retired = False

    def __init__(self, posSize: Sequence, properties: dict) -> None:
        self._frame = Frame.from_pos_size(posSize)
        self._pos_size = AUTO if posSize == AUTO else tuple(posSize)
        self._properties = properties
        self._view = self._make_view()
        self._parent = self._node = self._size = None
        self._hidden = False
        self._slots: list[tuple[Any, Callable]] = []
        self._events: dict[str, Callable] = {}  # graph event -> script callback

    def _make_view(self) -> Any:
        return getattr(self._env.qt.QtGui, self._qt_class)()

    def _wire(
        self,
        signal_name: str,
        callback: Callable | None,
        *,
        source: Any = None,
        event: str = "action",
        accept: Callable[[tuple], bool] | None = None,
    ) -> None:
        """Report ``callback`` when ``source.<signal_name>`` fires (not while quiet)."""
        if callback is None:
            return
        self._events[event] = callback
        check = self._accept if accept is None else accept

        def slot(*args):
            if not self._quiet and check(args):
                self._env.report(callback, self)

        view = self._view if source is None else source
        signal = getattr(view, signal_name)
        self._track(signal, slot)
        self.__dict__.setdefault("_event_slots", {}).setdefault(event, []).append(
            (signal, slot)
        )

    def _track(self, signal: Any, slot: Callable) -> None:
        """Connect and remember the pair so teardown can disconnect it."""
        track_connection(self._slots, signal, slot)

    def _accept(self, args: tuple) -> bool:
        return True

    def _disconnect(self) -> None:
        disconnect_connections(self._slots, lambda error: self._env.sink(error, self))
        handle = self.__dict__.get("_ns")
        if handle is not None:
            handle._teardown()

    # Native handles: vanilla's private ``_nsObject``/``_target`` and getNS*().
    _ns_class: str | None = None

    @property
    def _nsObject(self) -> Any:
        """The Qt-backed Cocoa control over this widget (created on first use)."""
        if self._ns_class is None:
            raise _unsupported(f"vanilla.{type(self).__name__}", ["_nsObject"])
        handle = self.__dict__.get("_ns")
        if handle is None:
            handle = self._env.appkit[self._ns_class]._adopt(self._view, owner=self)
            self.__dict__["_ns"] = handle
        return handle

    @property
    def _target(self) -> Any:
        """vanilla's action target: ``action_(sender)`` reports the callback."""
        target = self.__dict__.get("_action_target")
        if target is None:
            target = self.__dict__["_action_target"] = _ActionTarget(self)
        return target

    def _yield_action(self) -> None:
        """A script set the native target/action: drop vanilla's own route."""
        for signal, slot in self.__dict__.get("_event_slots", {}).pop("action", []):
            self._slots.remove((signal, slot))
            signal.disconnect(slot)

    def _retire(self) -> None:
        """Detach a replaced/deleted control: disconnect, unparent, deleteLater."""
        self._disconnect()
        self._mark_detached()
        self._retired, self._parent = True, None
        self._view.setParent(None)
        self._view.deleteLater()

    def _mark_detached(self) -> None:
        # Graph ids are sequential and nodes immutable; flag instead of removing.
        if self._node is not None:
            self._node.properties["detached"] = True

    def _register(self, graph: UIGraph, parent_id: str, name: str, root_id: str):
        self._node = graph.add_node(
            f"vanilla.{type(self).__name__}",
            parent_id=parent_id,
            frame=self._frame,
            properties=self._properties,
            attribute_name=name,
        )
        for event, callback in self._events.items():
            graph.connect(self._node.node_id, root_id, event, _selector(callback))

    def _place(self, width: float, height: float) -> None:
        hint = (0, 0)
        if AUTO in (self._frame.width, self._frame.height):
            size = self._view.sizeHint
            hint = (max(0, size.width()), max(0, size.height()))
        x, y, w, h = resolve_frame(self._frame, width, height, size_hint=hint)
        self._view.setGeometry(*_ints((x, y, w, h)))
        self._size = (w, h)

    def enable(self, onOff: bool) -> None:
        self._view.setEnabled(bool(onOff))

    def show(self, onOff: bool) -> None:
        self._hidden = not onOff
        self._view.setVisible(bool(onOff))

    def getPosSize(self) -> tuple:
        if self._pos_size == AUTO:
            rect = self._view.geometry
            return rect.x(), rect.y(), rect.width(), rect.height()
        return self._pos_size

    def setPosSize(self, posSize: Sequence) -> None:
        self._frame = Frame.from_pos_size(posSize)
        self._pos_size = AUTO if posSize == AUTO else tuple(posSize)
        if self._parent is not None and self._parent._size is not None:
            self._place(*self._parent._size)

    def getNSView(self) -> Any:
        """Return the Qt widget; keep a weak route to its lifecycle owner."""
        self._env.control_handles[id(self._view)] = self
        return self._view

    def setToolTip(self, text) -> None:
        self._view.setToolTip(str(text))

    def _live_in(self, window: "Window") -> bool:
        """True while this control and every ancestor up to ``window`` is attached."""
        node: Any = self
        while isinstance(node, _Control):
            if node._retired:
                return False
            node = node._parent
        return node is window


class Group(_Container, _Control):
    def __init__(self, posSize, **options):
        _Control.__init__(self, posSize, _properties("Group", options))
        self._children: dict[str, _Control] = {}

    def _register(self, graph, parent_id, name, root_id):
        _Control._register(self, graph, parent_id, name, root_id)
        self._graph, self._root_id = graph, root_id
        for child_name, child in self._children.items():
            child._register(graph, self._node.node_id, child_name, root_id)

    def _place(self, width, height):
        _Control._place(self, width, height)
        self._relayout()

    def _disconnect(self):
        _Control._disconnect(self)
        self._disconnect_children()

    def _mark_detached(self):
        _Control._mark_detached(self)
        for child in self._children.values():
            child._mark_detached()


class TextBox(_Control):
    _qt_class = "QLabel"
    _ns_class = "NSTextField"

    def getNSTextField(self) -> Any:
        return self._nsObject

    def __init__(
        self, posSize, text="", alignment="natural", selectable=False, **options
    ):
        known = {"text": str(text), "alignment": alignment}
        props = _properties("TextBox", options, selectable=selectable, **known)
        align = self._alignment(alignment)  # validate before creating the widget
        super().__init__(posSize, props)
        self.set(text)
        self._view.setAlignment(align)
        if selectable:
            qt_flags = self._env.qt.QtCore.Qt
            flags = qt_flags.TextSelectableByMouse | qt_flags.TextSelectableByKeyboard
            self._view.setTextInteractionFlags(flags)

    def _alignment(self, alignment) -> Any:
        return _alignment_flags(self._env.qt, type(self).__name__, alignment)

    def get(self) -> str:
        return self._view.text

    def set(self, value) -> None:
        self._view.setText(str(value))


class EditText(TextBox):
    def set(self, value):
        if value is None:
            raise TypeError("EditText requires a string, not None")
        super().set(value)

    _qt_class = "QLineEdit"

    def __init__(
        self,
        posSize,
        text="",
        callback=None,
        placeholder=None,
        readOnly=False,
        continuous=True,
        alignment="natural",
        **options,
    ):
        known = {"text": str(text), "placeholder": placeholder, "readOnly": readOnly}
        known.update(continuous=continuous, alignment=alignment)
        props = _properties("EditText", options, **known)
        align = self._alignment(alignment)
        self._continuous = bool(continuous)
        _Control.__init__(self, posSize, props)
        self.set("" if text is None else text)
        self._view.setAlignment(align)
        if placeholder is not None:
            self._view.setPlaceholderText(str(placeholder))
        self._view.setReadOnly(bool(readOnly))
        self._setCallback(callback)  # vanilla's hook; subclasses override it

    def _setCallback(self, callback) -> None:
        self._wire("textEdited" if self._continuous else "editingFinished", callback)

    def getPlaceholder(self):
        from .application_windows import qt_value

        return str(qt_value(self._view, "placeholderText"))

    def _make_view(self) -> Any:
        """A QLineEdit, or the widget of a supported ``nsTextFieldClass``."""
        ns_class = getattr(type(self), "nsTextFieldClass", None)
        if ns_class is None:
            return _Control._make_view(self)
        from .cocoa_controls import NSTextField

        if not (isinstance(ns_class, type) and issubclass(ns_class, NSTextField)):
            name = getattr(ns_class, "__name__", type(ns_class).__name__)
            raise _unsupported("vanilla.EditText.nsTextFieldClass", [name])
        bound = self._env.appkit[ns_class.__name__]
        cls = ns_class if issubclass(ns_class, bound) else bound
        handle = cls._adopt(None, owner=self)
        # As in vanilla, the field's own action (a step) goes to vanilla's target.
        handle._target, handle._action = self._target, "action:"
        self.__dict__["_ns"] = handle
        return handle._qt


class Button(_Control):
    _qt_class = "QPushButton"
    _ns_class = "NSButton"

    def getNSButton(self) -> Any:
        return self._nsObject

    def bind(self, key: str, modifiers: Sequence[str] | None = None) -> None:
        """Vanilla key equivalent through QAbstractButton's owned shortcut."""
        keys = {
            "help": "Help",
            "home": "Home",
            "end": "End",
            "pageup": "PgUp",
            "pagedown": "PgDown",
            "forwarddelete": "Del",
            "leftarrow": "Left",
            "rightarrow": "Right",
            "uparrow": "Up",
            "downarrow": "Down",
            "\r": "Return",
            "\n": "Return",
            "\x1b": "Escape",
            "\t": "Tab",
            "\b": "Backspace",
        }
        mapped = {
            "command": "Ctrl",
            "control": "Meta",
            "option": "Alt",
            "shift": "Shift",
        }
        modifiers = () if modifiers is None else modifiers
        unknown = [name for name in modifiers if name not in mapped]
        if unknown:
            raise _unsupported("vanilla.Button.bind.modifiers", unknown)
        if not isinstance(key, str) or (len(key) != 1 and key not in keys):
            raise _unsupported("vanilla.Button.bind", ["key"])
        sequence = "+".join([*(mapped[m] for m in modifiers), keys.get(key, key)])
        self._view.setShortcut(self._env.qt.QtGui.QKeySequence(sequence))

    def __init__(self, posSize, title, callback=None, **options):
        super().__init__(
            posSize, _properties(type(self).__name__, options, title=title)
        )
        self.setTitle(title)
        self._wire("clicked", callback)

    def setTitle(self, title) -> None:
        self._view.setText(str(title))

    def getTitle(self) -> str:
        return self._view.text


class CheckBox(Button):
    _qt_class = "QCheckBox"

    def __init__(self, posSize, title, callback=None, value=False, **options):
        super().__init__(posSize, title, callback, **options)
        self._properties["value"] = bool(value)
        self.set(value)

    def get(self) -> bool:
        return bool(self._view.isChecked())

    def set(self, value) -> None:
        self._view.setChecked(bool(value))


class PopUpButton(_Control):
    _qt_class = "QComboBox"
    _ns_class = "NSPopUpButton"

    def getNSPopUpButton(self) -> Any:
        return self._nsObject

    def __init__(self, posSize, items, callback=None, **options):
        items = [str(item) for item in items]
        super().__init__(posSize, _properties("PopUpButton", options, items=items))
        self.setItems(items)
        self._wire("activated", callback)

    def _accept(self, args):
        # Qt 5.15 also emits activated(QString); keep only the index overload.
        return not (args and isinstance(args[0], str))

    def get(self) -> int:
        return self._view.currentIndex

    def set(self, index: int) -> None:
        self._view.setCurrentIndex(int(index))

    def getItem(self):
        index = self.get()
        return self._items[index] if 0 <= index < len(self._items) else None

    def setItem(self, item):
        if item in self._items:
            self.set(self._items.index(item))

    def getItems(self) -> list[str]:
        return list(self._items)

    def setItems(self, items) -> None:
        self._items = [str(item) for item in items]
        self._view.clear()
        self._view.addItems(self._items)


class Slider(_Control):
    _qt_class = "QSlider"
    _ns_class = "NSSlider"

    def getNSSlider(self) -> Any:
        return self._nsObject

    def __init__(
        self,
        posSize,
        minValue=0,
        maxValue=100,
        value=50,
        callback=None,
        continuous=True,
        tickMarkCount=None,
        stopOnTickMarks=False,
        **options,
    ):
        if maxValue <= minValue:
            raise ValueError(f"maxValue {maxValue!r} must exceed minValue {minValue!r}")
        known = {"minValue": minValue, "maxValue": maxValue, "value": value}
        known.update(continuous=continuous, steps=SLIDER_STEPS)
        if tickMarkCount is not None:
            known.update(
                tickMarkCount=tickMarkCount, stopOnTickMarks=bool(stopOnTickMarks)
            )
        super().__init__(posSize, _properties("Slider", options, **known))
        self._min, self._span = float(minValue), float(maxValue - minValue)
        ticks = int(tickMarkCount or 0)
        # Values snap to ticks only when asked and there are at least two.
        self._ticks = ticks if stopOnTickMarks and ticks > 1 else 0
        self._view.setOrientation(self._env.qt.QtCore.Qt.Horizontal)
        _qt_numeric.set_step_range(self._view.setRange, SLIDER_STEPS)
        if ticks > 1:
            interval = SLIDER_STEPS // (ticks - 1)
            self._view.setTickPosition(
                getattr(self._env.qt.QtGui.QSlider, "TicksBelow", 2)
            )
            self._view.setTickInterval(interval)
            if self._ticks:
                self._view.setSingleStep(interval)
                self._view.setPageStep(interval)
        self._view.setTracking(bool(continuous))
        self.set(value)
        self._wire("valueChanged", callback)

    def _snap(self, value: float) -> float:
        if not self._ticks:
            return value
        step = self._span / (self._ticks - 1)
        return self._min + round((value - self._min) / step) * step

    def get(self) -> float:
        return self._snap(
            _qt_numeric.value_at(self._min, self._view.value, self._span, SLIDER_STEPS)
        )

    def set(self, value) -> None:
        with quiet_callbacks(self):
            value = self._snap(float(value))
            steps = _qt_numeric.position(
                float(value), self._min, self._span, SLIDER_STEPS
            )
            _qt_numeric.set_position(self._view.setValue, steps)


class HorizontalLine(_Control):
    _qt_class = "QFrame"
    _shape = "HLine"

    def __init__(self, posSize, **options):
        super().__init__(posSize, _properties(type(self).__name__, options))
        frame_class = self._env.qt.QtGui.QFrame
        self._view.setFrameShape(getattr(frame_class, self._shape))
        self._view.setFrameShadow(frame_class.Sunken)


class VerticalLine(HorizontalLine):
    _shape = "VLine"


class _WindowSizeLimits:
    """``Window._window``: Qt's minimum/maximum size as NSWindow content sizes."""

    def __init__(self, view):
        self._view = view

    def _size(self, name):
        from .application_windows import qt_value
        from .cocoa import NSMakeSize

        size = qt_value(self._view, name)
        return NSMakeSize(size.width(), size.height())

    def contentMinSize(self):
        return self._size("minimumSize")

    def contentMaxSize(self):
        return self._size("maximumSize")


class Window(_Container):
    """Top-level QWidget; children re-lay out with resolve_frame on resize."""

    _env: _Env
    _tool = False
    _autosave_key: str | None = None
    _default_button: Button | None = None

    def __init__(
        self,
        posSize,
        title="",
        minSize=None,
        maxSize=None,
        closable=True,
        autosaveName=None,
        **options,
    ):
        if options:
            raise _unsupported(f"vanilla.{type(self).__name__}", sorted(options))
        self._view = self._env.window_widget()
        self._view._owner = None
        self._children, self._binds, self._closed = {}, [], False
        self._event_binds = {}
        self._sheets: set = set()  # open Sheets; closed before this window
        props = {"title": str(title), "closable": bool(closable)}
        props.update(minSize=_size(minSize), maxSize=_size(maxSize))
        props["autosaveName"] = autosaveName
        posSize = self._restored(autosaveName) or posSize
        self._graph = self._env.graph_factory()
        frame = Frame.from_pos_size(posSize)
        self._node = self._graph.add_node(
            f"vanilla.{type(self).__name__}", frame=frame, properties=props
        )
        self._root_id = self._node.node_id
        self._configure(title, minSize, maxSize)
        self._view._owner = self
        self.setPosSize(posSize)
        if autosaveName is not None:  # only after construction: save changes
            self._autosave_key = _AUTOSAVE_PREFIX + str(autosaveName)

    def _restored(self, autosaveName) -> list[int] | None:
        if autosaveName is None:
            return None
        key = _AUTOSAVE_PREFIX + str(autosaveName)
        return _stored_frame(self._env.settings.get(key))

    def _save_frame(self) -> None:
        if self._autosave_key is not None:
            self._env.settings[self._autosave_key] = list(self.getPosSize())

    def _configure(self, title, minSize, maxSize) -> None:
        self.setTitle(title)
        if self._tool:
            self._view.setWindowFlags(self._env.qt.QtCore.Qt.Tool)
        if minSize is not None:
            self._view.setMinimumSize(*_ints(minSize))
        if maxSize is not None:
            self._view.setMaximumSize(*_ints(maxSize))

    @property
    def graph(self) -> UIGraph:
        return self._graph

    def _resized(self, width: int, height: int) -> None:
        self._size = (width, height)
        self._relayout()
        self._save_frame()

    def open(self) -> None:
        if self._closed:
            return
        self._relayout()
        self._env.open_windows.add(self)  # keep unreferenced open windows alive
        self._view.show()

    def _close_context(self):
        Window.close(self)

    def close(self) -> None:
        """Disconnect every tracked connection, then close and deleteLater once."""
        if not self._closed:
            self._teardown(view_closing=False)

    def _teardown(self, *, view_closing: bool) -> None:
        self._closed = True
        self._default_button = None
        try:
            for sheet in list(self._sheets):
                sheet._close_context()
            self._save_frame()
            for callback in self._binds:
                self._env.report(callback, self)
        finally:
            self._disconnect_children()
            if not view_closing:
                self._view.close()
            self._view.deleteLater()
            self._env.open_windows.discard(self)
            self._view._owner = None

    def bind(self, event: str, callback: Callable) -> None:
        if event == "close":
            self._binds.append(callback)
        elif event == "became key":
            self._event_binds.setdefault(event, []).append(callback)
        else:
            raise _unsupported(f"vanilla.{type(self).__name__}.bind", [event])

    def isVisible(self) -> bool:
        return not self._closed and bool(self._view.isVisible())

    def getPosSize(self) -> tuple:
        rect = self._view.geometry
        return rect.x(), rect.y(), rect.width(), rect.height()

    def setPosSize(self, posSize: Sequence) -> None:
        frame = Frame.from_pos_size(posSize)
        if len(posSize) == 4:
            self._view.setGeometry(*_ints(posSize))
        else:
            self._view.resize(*_ints(posSize))
        self._resized(frame.width, frame.height)

    def resize(self, width, height, animate=True):
        """Resize while retaining the window origin; Qt applies the final frame."""
        x, y, _, _ = self.getPosSize()
        self.setPosSize((x, y, width, height))

    def setTitle(self, title) -> None:
        self._view.setWindowTitle(str(title))

    def getTitle(self) -> str:
        return self._view.windowTitle

    def getNSView(self) -> Any:
        """Return the top-level Qt widget (compatibility handle)."""
        return self._view

    def getNSWindow(self) -> Any:
        """Return the top-level Qt widget; the compatibility handle for NSWindow."""
        return self._view

    @property
    def _window(self) -> Any:
        """vanilla's private NSWindow: only the content size limits (mekkablue's
        shared helper clamps windows with them)."""
        return _WindowSizeLimits(self._view)

    def makeKey(self) -> None:
        self._view.raise_()
        self._view.activateWindow()

    def center(self) -> None:
        """Center on the available geometry of the screen showing the window."""
        screen = self._env.qt.QtGui.QApplication.desktop().availableGeometry(self._view)
        rect = self._view.geometry
        width, height = rect.width(), rect.height()
        x = screen.x() + (screen.width() - width) // 2
        y = screen.y() + (screen.height() - height) // 2
        self._view.setGeometry(x, y, width, height)
        self._save_frame()

    def setDefaultButton(self, button) -> None:
        """Make a push Button the one Return/Enter activates; clear the old one.

        The button must be attached (through live ancestors) to this open
        window; otherwise ValueError, and no widget is touched.
        """
        if not isinstance(button, Button) or isinstance(button, CheckBox):
            raise TypeError(f"setDefaultButton expects a vanilla Button: {button!r}")
        if self._closed or not button._live_in(self):
            raise ValueError("setDefaultButton: button is not attached to this window")
        previous = self._default_button
        if previous is not None and previous is not button and previous._live_in(self):
            previous._view.setDefault(False)
        self._default_button = button
        button._view.setDefault(True)

    def _press_default(self, key) -> bool:
        button = self._default_button
        qt_keys = self._env.qt.QtCore.Qt
        if button is None or key not in [getattr(qt_keys, k) for k in _RETURN_KEYS]:
            return False
        view = button._view
        if not button._live_in(self) or not view.isEnabled() or not view.isVisible():
            return False
        button._view.click()
        return True


class FloatingWindow(Window):
    _tool = True


def _size(value: Sequence | None) -> list | None:
    return None if value is None else list(value)


_CORE_CLASSES = (
    Window,
    FloatingWindow,
    Group,
    TextBox,
    EditText,
    Button,
    CheckBox,
    PopUpButton,
    Slider,
    HorizontalLine,
    VerticalLine,
)


def _classes() -> tuple[type, ...]:
    """Core classes plus later controls (imported late: they subclass these)."""
    from .vanilla_auxiliary import Popover, ScrollView
    from .vanilla_containers import CONTAINER_CLASSES
    from .vanilla_controls import CONTROL_CLASSES
    from .vanilla_extra import EXTRA_CLASSES

    return (
        _CORE_CLASSES
        + CONTROL_CLASSES
        + CONTAINER_CLASSES
        + EXTRA_CLASSES
        + (Popover, ScrollView)
    )


def _missing(name: str) -> Any:
    """Module __getattr__: dunders stay AttributeError, the rest is unsupported."""
    if name.startswith("__"):
        raise AttributeError(name)
    frame = traceback.extract_stack()[-2]
    location = SourceLocation(frame.filename, frame.lineno, (frame.colno or 0) + 1)
    capability = f"vanilla.{name}"
    raise UnsupportedCapability(
        f"Unsupported capability: {capability}",
        capability=capability,
        location=location,
    )


def test_module():
    """Import compatibility for Vanilla's demonstration class; never fake tests."""
    from .cocoa import unsupported

    module = ModuleType("vanilla.test.testAll")

    class Test:
        def __init__(self, *args, **kwargs):
            raise unsupported("vanilla.test.Test")

    module.Test = Test
    module.__all__ = ["Test"]
    module.__path__ = []
    return module


def make_vanilla_module(
    qt: Any,
    *,
    error_sink: ErrorSink,
    graph_factory: Callable = UIGraph,
    wrap: Wrap | None = None,
    settings: Settings | None = None,
    on_close: OnClose | None = None,
) -> ModuleType:
    """Return a fresh ``vanilla`` module bound to ``qt`` and ``error_sink``.

    ``wrap`` (e.g. ``ExecutionContext.wrap``) is applied to every callback call
    so output and imports inside callbacks follow the execution context.
    ``settings`` stores autosaved state (Window frames under ``"window:<name>"``);
    it defaults to the process-wide in-memory ``_DEFAULT_SETTINGS``.
    ``on_close`` (e.g. ``ExecutionContext.on_close``) receives a hook that
    closes every window this module still has open.
    """
    store = _DEFAULT_SETTINGS if settings is None else settings
    env = _Env(qt, error_sink, graph_factory, wrap, store)
    if on_close is not None:
        on_close(env.close_windows)
    module = ModuleType("vanilla", "glyport vanilla core controls on Qt")
    classes = _classes()
    for cls in classes:
        bound = type(cls.__name__, (cls,), {"_env": env, "__module__": "vanilla"})
        setattr(module, cls.__name__, bound)
    from .vanilla_controls import CheckBoxListCell

    module.CheckBoxListCell = CheckBoxListCell
    from .vanilla_auxiliary import Drawer

    module.Drawer = Drawer
    module.__all__ = [cls.__name__ for cls in classes] + ["CheckBoxListCell", "Drawer"]
    module.__getattr__ = _missing
    return module


def vanilla_provider(
    qt: Any,
    error_sink: ErrorSink,
    *,
    wrap: Wrap | None = None,
    settings: Settings | None = None,
    on_close: OnClose | None = None,
) -> Callable[[], ModuleType]:
    """Zero-argument provider for an ExecutionContext ``vanilla`` adapter.

    Route callbacks through the context and close its windows with it:
    ``ctx.adapters["vanilla"] = vanilla_provider(qt, sink, wrap=ctx.wrap,
    on_close=ctx.on_close)``.
    """

    def provide() -> ModuleType:
        return make_vanilla_module(
            qt, error_sink=error_sink, wrap=wrap, settings=settings, on_close=on_close
        )

    return provide
