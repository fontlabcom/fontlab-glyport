# this_file: tests/ui_doubles.py
"""Strict PythonQt-shaped doubles: slotted natives, property getters, logged calls.

They mirror FontLab's PythonQt facts that matter to vanilla translation:
native instances reject new attributes (``__slots__``), Qt properties such as
``text`` or ``geometry`` are plain attributes, ``setGeometry`` takes ints only,
``close()`` dispatches to a Python subclass's ``closeEvent``, and widget
classes live in ``QtGui`` (there is no ``QtWidgets``).
"""

from types import SimpleNamespace


class Log(list):
    """Shared, ordered record of native calls across all doubles."""


LOG = Log()


class Signal:
    __slots__ = ("name", "owner", "slots")

    def __init__(self, owner, name):
        self.owner, self.name, self.slots = owner, name, []

    def connect(self, slot):
        self.slots.append(slot)
        LOG.append(("connect", self.owner, self.name))

    def disconnect(self, slot):
        self.slots.remove(slot)
        LOG.append(("disconnect", self.owner, self.name))

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


class QSize:
    __slots__ = ("_h", "_w")

    def __init__(self, w, h):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h


class QRect(QSize):
    __slots__ = ("_x", "_y")

    def __init__(self, x, y, w, h):
        super().__init__(w, h)
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class QResizeEvent:
    __slots__ = ("_size",)

    def __init__(self, w, h):
        self._size = QSize(w, h)

    def size(self):
        return self._size


def _ints(*values):
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"Qt expects int, got {value!r}")


class QKeyEvent:
    __slots__ = ("_accepted", "_key", "_modifiers")

    def __init__(self, key, modifiers=0):
        self._key, self._accepted, self._modifiers = key, False, modifiers

    def key(self):
        return self._key

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self._accepted = True


class QWidget:
    __slots__ = (
        "_accessible",
        "_children",
        "_deleted",
        "_enabled",
        "_explicit_hidden",
        "_flags",
        "_hint",
        "_max",
        "_min",
        "_modality",
        "_parent",
        "_rect",
        "_title",
        "_tooltip",
        "_visible",
    )

    def __init__(self, *args, **kwargs):
        if args or kwargs:
            raise TypeError("doubles accept no constructor arguments")
        self._parent, self._rect, self._children = None, (0, 0, 100, 30), []
        self._visible, self._explicit_hidden, self._enabled = False, False, True
        self._title, self._flags, self._min, self._max = "", None, None, None
        self._hint, self._deleted, self._tooltip = (80, 22), False, ""
        self._modality, self._accessible = None, ""
        LOG.append(("create", self))

    # Qt properties are attributes in PythonQt.
    @property
    def geometry(self):
        return QRect(*self._rect)

    @property
    def windowTitle(self):
        return self._title

    @property
    def sizeHint(self):
        return QSize(*self._hint)

    @property
    def toolTip(self):
        return self._tooltip

    def setToolTip(self, text):
        if not isinstance(text, str):
            raise TypeError(f"setToolTip expects str, got {text!r}")
        self._tooltip = text

    def setAccessibleName(self, name):
        self._accessible = name

    def raise_(self):
        LOG.append(("raise_", self))

    def activateWindow(self):
        LOG.append(("activateWindow", self))

    def setParent(self, parent):
        if self._parent is not None:
            self._parent._children.remove(self)
        if parent is not None:
            parent._children.append(self)
        self._parent = parent
        LOG.append(("setParent", self, parent))

    def parentWidget(self):
        return self._parent

    def setGeometry(self, x, y, w, h):
        _ints(x, y, w, h)
        old = self._rect
        self._rect = (x, y, w, h)
        LOG.append(("setGeometry", self, (x, y, w, h)))
        if old[2:] != (w, h):
            self.resizeEvent(QResizeEvent(w, h))

    def resize(self, w, h):
        x, y = self._rect[:2]
        self.setGeometry(x, y, w, h)

    def setMinimumSize(self, w, h):
        _ints(w, h)
        self._min = (w, h)

    def setMaximumSize(self, w, h):
        _ints(w, h)
        self._max = (w, h)

    def setWindowTitle(self, title):
        self._title = title

    def setWindowFlags(self, flags):
        self._flags = flags

    def windowFlags(self):
        return self._flags

    def setWindowModality(self, modality):
        self._modality = modality

    def windowModality(self):
        return self._modality

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def setVisible(self, visible):
        self._visible = bool(visible)
        self._explicit_hidden = not visible
        LOG.append(("setVisible", self, bool(visible)))
        if self.isVisible():  # Qt polishes, then sends showEvent down the tree
            for widget in self._tree():
                if isinstance(widget, QWidget) and widget.isVisible():
                    widget._shown()

    def _shown(self):
        """Hook: a widget became visible (QGroupBox polishes here)."""

    def isVisible(self):
        parent = self._parent
        return self._visible and (parent is None or parent.isVisible())

    def setEnabled(self, enabled):
        self._enabled = bool(enabled)

    def isEnabled(self):
        return self._enabled

    def close(self):
        LOG.append(("close", self))
        self.closeEvent(SimpleNamespace())
        self._visible = False
        return True

    def deleteLater(self):
        """Qt deletes the whole child tree with the parent."""
        LOG.append(("deleteLater", self))
        for widget in self._tree():
            widget._deleted = True

    def _tree(self):
        yield self
        for child in self._children:
            yield from child._tree()

    def _alive(self):
        if self._deleted:
            raise RuntimeError("underlying C++ object was deleted")

    def resizeEvent(self, event):
        LOG.append(("native.resizeEvent", self))

    def closeEvent(self, event):
        LOG.append(("native.closeEvent", self))

    def paintEvent(self, event):
        LOG.append(("native.paintEvent", self))

    def showEvent(self, event):
        LOG.append(("native.showEvent", self))

    def keyPressEvent(self, event):
        LOG.append(("native.keyPressEvent", self, event.key()))

    def user_key(self, key, modifiers=0):
        """Deliver a key press the way Qt does when no child accepted it."""
        event = QKeyEvent(key, modifiers)
        self.keyPressEvent(event)
        return event._accepted


ALIGN_LEFT, ALIGN_RIGHT, ALIGN_HCENTER, ALIGN_JUSTIFY = 0x1, 0x2, 0x4, 0x8
ALIGN_VCENTER = 0x80
CHECKED, PARTIALLY_CHECKED = 2, 1
SELECTABLE_BY_MOUSE, SELECTABLE_BY_KEYBOARD = 0x1, 0x2


class _TextWidget(QWidget):
    """Shared text storage only; labels, line edits and buttons are siblings."""

    __slots__ = ("_text",)

    def __init__(self):
        super().__init__()
        self._text = ""

    @property
    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


class _AlignedText(_TextWidget):
    """QLabel and QLineEdit both have alignment; QAbstractButton does not."""

    __slots__ = ("_alignment",)

    def __init__(self):
        super().__init__()
        self._alignment = ALIGN_LEFT | ALIGN_VCENTER

    @property
    def alignment(self):
        return self._alignment

    def setAlignment(self, flags):
        _ints(flags)
        self._alignment = flags


class QLabel(_AlignedText):
    __slots__ = ("_interaction",)

    def __init__(self):
        super().__init__()
        self._interaction = 0

    @property
    def textInteractionFlags(self):
        return self._interaction

    def setTextInteractionFlags(self, flags):
        _ints(flags)
        self._interaction = flags


class QLineEdit(_AlignedText):
    """Qt 5.15: setText clears ``modified``; editingFinished on every focus loss."""

    __slots__ = (
        "_echo",
        "_has_frame",
        "_modified",
        "_placeholder",
        "_read_only",
        "_style",
        "editingFinished",
        "textEdited",
    )
    Normal, Password = "Normal", "Password"

    def __init__(self):
        super().__init__()
        self._placeholder, self._read_only, self._modified = "", False, False
        self._echo, self._has_frame, self._style = self.Normal, True, ""
        self.textEdited = Signal(self, "textEdited")
        self.editingFinished = Signal(self, "editingFinished")

    def setText(self, text):
        self._text, self._modified = text, False

    def isModified(self):
        return self._modified

    def setModified(self, value):
        if not isinstance(value, bool):
            raise TypeError(f"setModified expects bool, got {value!r}")
        self._modified = value

    def user_focus_out(self):
        self.editingFinished.emit()  # Qt 5.15: even without an edit

    def setPlaceholderText(self, text):
        self._placeholder = text

    def setReadOnly(self, value):
        self._read_only = bool(value)

    def isReadOnly(self):
        return self._read_only

    def setFrame(self, value):
        self._has_frame = bool(value)

    def setStyleSheet(self, sheet):
        self._style = sheet

    def setEchoMode(self, mode):
        self._echo = mode

    def user_type(self, text):
        self._text, self._modified = text, True
        self.textEdited.emit(text)

    def user_finish(self):
        self.editingFinished.emit()


class _AbstractButton(_TextWidget):
    """QAbstractButton: QPushButton and QCheckBox share it, not each other."""

    __slots__ = ("clicked",)

    def __init__(self):
        super().__init__()
        self.clicked = Signal(self, "clicked")

    def user_click(self):
        self.clicked.emit(False)

    def click(self):
        LOG.append(("click", self))
        if self._enabled:
            self.user_click()


class QPushButton(_AbstractButton):
    __slots__ = ("_checkable", "_checked", "_default", "_menu", "_style")

    def __init__(self):
        super().__init__()
        self._default, self._style = False, ""
        self._checkable = self._checked = False
        self._menu = None

    def setStyleSheet(self, sheet):
        self._style = sheet

    def setCheckable(self, value):
        self._checkable = bool(value)

    def setChecked(self, value):
        self._checked = bool(value) and self._checkable

    def isChecked(self):
        return self._checked

    def setMenu(self, menu):
        self._menu = menu

    def menu(self):
        return self._menu

    def user_click(self):
        if self._checkable:
            self._checked = not self._checked
        self.clicked.emit(self._checked)

    def setDefault(self, value):
        self._alive()
        if not isinstance(value, bool):
            raise TypeError(f"setDefault expects bool, got {value!r}")
        self._default = value
        LOG.append(("setDefault", self, value))

    def isDefault(self):
        return self._default


class QCheckBox(_AbstractButton):
    __slots__ = ("_checked", "_partial", "_tristate")

    def __init__(self):
        super().__init__()
        self._checked = self._partial = self._tristate = False

    def setChecked(self, value):
        self._checked, self._partial = bool(value), False

    def setTristate(self, value):
        self._tristate = bool(value)

    def setCheckState(self, state):
        if state == PARTIALLY_CHECKED and not self._tristate:
            raise AssertionError("PartiallyChecked needs setTristate(True)")
        self._partial = state == PARTIALLY_CHECKED
        self._checked = state == CHECKED

    def checkState(self):
        return PARTIALLY_CHECKED if self._partial else CHECKED * self._checked

    def isChecked(self):
        return self._checked

    def user_click(self):
        self._checked = not self._checked
        self.clicked.emit(self._checked)


class QComboBox(QWidget):
    """Popup or editable combo, following Qt 5.15 ``qcombobox.cpp``.

    Editable: ``setEditable`` connects the combo's own editingFinished handler
    first (``_q_editingFinished``: a typed text matching another item selects
    it and emits ``activated``). ``setCurrentIndex`` rewrites the line edit text
    only when it differs (``setText`` clears ``modified``) and never emits
    ``activated``. With NoInsert, ``_q_returnPressed`` does nothing.
    """

    __slots__ = (
        "_completer",
        "_index",
        "_insert_policy",
        "_items",
        "_line_edit",
        "activated",
        "editTextChanged",
        "textActivated",
    )
    NoInsert, InsertAtBottom = "NoInsert", "InsertAtBottom"

    def __init__(self):
        super().__init__()
        self._items, self._index, self._line_edit = [], -1, None
        self._insert_policy, self._completer = self.InsertAtBottom, "default"
        self.activated = Signal(self, "activated")
        self.editTextChanged = Signal(self, "editTextChanged")
        self.textActivated = Signal(self, "textActivated")

    @property
    def currentIndex(self):
        return self._index

    @property
    def count(self):
        return len(self._items)

    @property
    def currentText(self):
        if self._line_edit is not None:
            return self._line_edit._text
        return self._items[self._index] if self._index >= 0 else ""

    def setEditable(self, editable):
        if editable is not True:
            raise TypeError("doubles model only setEditable(True)")
        self._line_edit = QLineEdit()
        self._line_edit.setParent(self)
        self._line_edit.editingFinished.connect(self._editing_finished)

    def _editing_finished(self):
        text = self._line_edit._text
        current = self._items[self._index] if self._index >= 0 else None
        if text and text != current and text in self._items:
            self.setCurrentIndex(self._items.index(text))
            self._emit_activated()

    def _emit_activated(self):
        text = self._items[self._index]
        self.activated.emit(self._index)
        self.activated.emit(text)  # Qt 5.15 overload fires too
        self.textActivated.emit(text)

    def lineEdit(self):
        return self._line_edit

    def setInsertPolicy(self, policy):
        self._insert_policy = policy

    def setCompleter(self, completer):
        if completer is not None:
            raise TypeError("doubles model only setCompleter(None)")
        self._completer = None

    def _set_edit_text(self, text):
        if self._line_edit is not None and self._line_edit._text != text:
            self._line_edit.setText(text)
            self.editTextChanged.emit(text)

    def setEditText(self, text):
        if not isinstance(text, str):
            raise TypeError(f"setEditText expects str, got {text!r}")
        self._set_edit_text(text)

    def addItem(self, text):
        self.addItems([text])

    def addItems(self, texts):
        self._items.extend(texts)
        if self._index < 0 and self._items:
            self.setCurrentIndex(0)  # Qt selects the first item, copying its text

    def clear(self):
        self._items, self._index = [], -1
        self._set_edit_text("")

    def itemText(self, index):
        return self._items[index]

    def setCurrentIndex(self, index):
        _ints(index)
        self._index = index
        if 0 <= index < len(self._items):
            self._set_edit_text(self._items[index])

    def user_choose(self, index):
        """Popup pick: select the item, then activated (user-only)."""
        self.setCurrentIndex(index)
        self._emit_activated()

    def user_type(self, text):
        self._line_edit.user_type(text)
        self.editTextChanged.emit(text)

    def user_return(self):
        """Return: QLineEdit emits editingFinished; NoInsert adds nothing."""
        if self._insert_policy != self.NoInsert:
            self._items.append(self._line_edit._text)
        self._line_edit.editingFinished.emit()

    def user_focus_out(self):
        self._line_edit.user_focus_out()


class QSlider(QWidget):
    __slots__ = (
        "_down",
        "_maximum",
        "_minimum",
        "_orientation",
        "_page",
        "_single",
        "_tick_interval",
        "_tick_position",
        "_tracking",
        "_value",
        "sliderReleased",
        "valueChanged",
    )

    def __init__(self):
        super().__init__()
        self._minimum, self._maximum, self._value = 0, 99, 0
        self._tracking, self._orientation, self._down = True, None, False
        self._tick_interval = self._tick_position = 0
        self._single, self._page = 1, 10
        self.valueChanged = Signal(self, "valueChanged")
        self.sliderReleased = Signal(self, "sliderReleased")

    def isSliderDown(self):
        return self._down

    def user_press_drag_release(self, *values):
        """Mouse drag: valueChanged while down, then sliderReleased."""
        self._down = True
        for value in values:
            self.setValue(value)
        self._down = False
        self.sliderReleased.emit()

    @property
    def value(self):
        return self._value

    def setOrientation(self, orientation):
        self._orientation = orientation

    def setTracking(self, enabled):
        self._tracking = bool(enabled)

    def setTickInterval(self, interval):
        self._tick_interval = int(interval)

    def setTickPosition(self, position):
        self._tick_position = position

    def setSingleStep(self, step):
        self._single = int(step)

    def setPageStep(self, step):
        self._page = int(step)

    def setRange(self, minimum, maximum):
        _ints(minimum, maximum)
        self._minimum, self._maximum = minimum, maximum

    def setValue(self, value):
        _ints(value)
        value = max(self._minimum, min(self._maximum, value))
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)

    def user_drag(self, value):
        self.setValue(value)


class QFrame(QWidget):
    __slots__ = ("_shadow", "_shape")
    HLine, VLine, Sunken = "HLine", "VLine", "Sunken"

    def __init__(self):
        super().__init__()
        self._shape = self._shadow = None

    def setFrameShape(self, shape):
        self._shape = shape

    def setFrameShadow(self, shadow):
        self._shadow = shadow


class QDesktopWidget:
    __slots__ = ()
    AVAILABLE = (0, 25, 1440, 875)

    def availableGeometry(self, widget):
        if not isinstance(widget, QWidget):
            raise TypeError("doubles model only the widget overload")
        LOG.append(("availableGeometry", widget))
        return QRect(*self.AVAILABLE)


class QApplication:
    """Only the static ``desktop()``; constructing it is forbidden in FontLab."""

    def __init__(self, *args):
        raise AssertionError("never construct a QApplication in the host")

    @staticmethod
    def desktop():
        return QDesktopWidget()


def make_qt():
    """Return a namespace shaped like FontLab's PythonQt (no QtWidgets)."""
    from ui_doubles_containers import CONTAINER_DOUBLES, CONTAINER_ENUMS
    from ui_doubles_controls import CONTROL_DOUBLES, ENUMS
    from ui_doubles_dialogs import DIALOG_DOUBLES

    LOG.clear()
    gui = SimpleNamespace(
        **CONTROL_DOUBLES,
        **CONTAINER_DOUBLES,
        **DIALOG_DOUBLES,
        QWidget=QWidget,
        QLabel=QLabel,
        QLineEdit=QLineEdit,
        QPushButton=QPushButton,
        QCheckBox=QCheckBox,
        QComboBox=QComboBox,
        QSlider=QSlider,
        QFrame=QFrame,
        QApplication=QApplication,
    )
    qt_enums = SimpleNamespace(
        Tool="Tool",
        Horizontal="Horizontal",
        AlignLeft=ALIGN_LEFT,
        AlignRight=ALIGN_RIGHT,
        AlignHCenter=ALIGN_HCENTER,
        AlignJustify=ALIGN_JUSTIFY,
        AlignVCenter=ALIGN_VCENTER,
        TextSelectableByMouse=SELECTABLE_BY_MOUSE,
        TextSelectableByKeyboard=SELECTABLE_BY_KEYBOARD,
        Key_Return=0x01000004,
        Key_Enter=0x01000005,
        Key_Escape=0x01000000,
        Key_Up=0x01000013,
        Key_Down=0x01000015,
        ShiftModifier=0x02000000,
        Vertical="Vertical",
        PartiallyChecked=PARTIALLY_CHECKED,
        **ENUMS,
        **CONTAINER_ENUMS,
    )
    core = SimpleNamespace(Qt=qt_enums)
    return SimpleNamespace(QtGui=gui, QtCore=core)
