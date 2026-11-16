# this_file: tests/ui_doubles_controls.py
"""PythonQt-shaped doubles for vanilla slice 2 controls (see ui_doubles.py).

Each double reproduces the native hazard the translation must handle: exclusive
radio groups refuse to uncheck, ``setPlainText``/``setItem`` emit change
signals, ``QProgressBar`` ignores out-of-range values, ``QTableWidget.selectRow``
replaces an extended selection, and constructors are positional only.
"""

from ui_doubles import LOG, QRect, QWidget, Signal, _AbstractButton, _ints

ITEM_IS_SELECTABLE, ITEM_IS_EDITABLE, ITEM_IS_ENABLED = 0x1, 0x2, 0x20
KEY_DELETE, KEY_BACKSPACE = 0x01000007, 0x01000003
ENUMS = {
    "ItemIsSelectable": ITEM_IS_SELECTABLE,
    "ItemIsEditable": ITEM_IS_EDITABLE,
    "ItemIsEnabled": ITEM_IS_ENABLED,
    "ItemIsUserCheckable": 0x10,
    "Checked": 2,
    "Unchecked": 0,
    "Key_Delete": KEY_DELETE,
    "Key_Backspace": KEY_BACKSPACE,
    "WA_MacShowFocusRect": "WA_MacShowFocusRect",
}


class QButtonGroup:
    """A QObject (not a widget); deleted with its parent widget's tree."""

    __slots__ = ("_buttons", "_deleted", "_exclusive", "_parent", "idClicked")

    def __init__(self, *args):
        if args:
            raise TypeError("doubles accept no constructor arguments")
        self._buttons, self._exclusive, self._parent = {}, True, None
        self._deleted = False
        self.idClicked = Signal(self, "idClicked")
        LOG.append(("create", self))

    def setParent(self, parent):
        if self._parent is not None:
            self._parent._children.remove(self)
        parent._children.append(self)
        self._parent = parent

    def _tree(self):
        yield self

    def setExclusive(self, value):
        if not isinstance(value, bool):
            raise TypeError(f"setExclusive expects bool, got {value!r}")
        self._exclusive = value

    def addButton(self, button, *args, **kwargs):
        if kwargs or len(args) != 1:
            raise TypeError("doubles model only addButton(button, id) positionally")
        _ints(args[0])
        self._buttons[args[0]] = button
        button._group = self

    def checkedId(self):
        return next((i for i, b in self._buttons.items() if b._checked), -1)

    def deleteLater(self):
        self._deleted = True


class QRadioButton(_AbstractButton):
    """Auto-exclusive by default; exclusive groups refuse to uncheck."""

    __slots__ = ("_auto_exclusive", "_checked", "_group")

    def __init__(self):
        super().__init__()
        self._checked, self._auto_exclusive, self._group = False, True, None

    def setAutoExclusive(self, value):
        self._auto_exclusive = bool(value)

    def _peers(self):
        if self._group is not None:
            return list(self._group._buttons.values())
        if self._auto_exclusive and self._parent is not None:
            kids = self._parent._children
            return [
                k for k in kids if isinstance(k, QRadioButton) and k._auto_exclusive
            ]
        return [self]

    def _exclusive(self):
        group = self._group
        return group._exclusive if group is not None else self._auto_exclusive

    def setChecked(self, value):
        self._alive()
        if not value and self._checked and self._exclusive():
            return  # Qt: the checked button of an exclusive group stays checked
        if value and self._exclusive():
            for peer in self._peers():
                peer._checked = False
        self._checked = bool(value)

    def isChecked(self):
        return self._checked

    def user_click(self):
        if not (self._checked and self._exclusive()):
            self.setChecked(not self._checked)
        self.clicked.emit(self._checked)
        if self._group is not None:
            group_id = next(i for i, b in self._group._buttons.items() if b is self)
            self._group.idClicked.emit(group_id)


class QPlainTextEdit(QWidget):
    __slots__ = ("_plain", "_read_only", "textChanged")

    def __init__(self):
        super().__init__()
        self._plain, self._read_only = "", False
        self.textChanged = Signal(self, "textChanged")

    def setPlainText(self, text):
        if not isinstance(text, str):
            raise TypeError(f"setPlainText expects str, got {text!r}")
        self._plain = text
        self.textChanged.emit()  # Qt emits for programmatic changes too

    def toPlainText(self):
        return self._plain

    def setReadOnly(self, value):
        self._read_only = bool(value)

    def user_type(self, text):
        self._plain += text
        self.textChanged.emit()


class QProgressBar(QWidget):
    __slots__ = ("_maximum", "_minimum", "_text_visible", "_value")

    def __init__(self):
        super().__init__()
        self._minimum, self._maximum, self._value = 0, 100, -1
        self._text_visible = True

    @property
    def value(self):
        return self._value

    @property
    def minimum(self):
        return self._minimum

    @property
    def maximum(self):
        return self._maximum

    def setRange(self, minimum, maximum):
        _ints(minimum, maximum)
        self._minimum, self._maximum = minimum, maximum
        LOG.append(("setRange", self, (minimum, maximum)))

    def setValue(self, value):
        _ints(value)
        if self._minimum <= value <= self._maximum:
            self._value = value  # out-of-range values are ignored, as in Qt

    def setTextVisible(self, visible):
        self._text_visible = bool(visible)

    def repaint(self, *args):
        if args:
            raise TypeError("only the zero-argument repaint() is used")
        LOG.append(("repaint", self))


class QGroupBox(QWidget):
    """contentsRect changes on polish, as natively observed in FontLab 9.

    Before the first show it is the bare frame ``(1, 1, w-2, h-2)``; once
    polished, a titled box reserves the title band ``(1, 21, w-2, h-22)``.
    """

    __slots__ = ("_box_title", "_polished", "_style")
    FRAME, TITLE = 1, 21

    def __init__(self):
        super().__init__()
        self._box_title, self._polished, self._style = "", False, ""

    def setStyleSheet(self, sheet):
        self._style = sheet

    @property
    def title(self):
        return self._box_title

    def setTitle(self, title):
        if not isinstance(title, str):
            raise TypeError(f"setTitle expects str, got {title!r}")
        self._box_title = title

    def contentsRect(self):
        f = self.FRAME
        top = self.TITLE if self._box_title and self._polished else f
        w, h = self._rect[2:]
        return QRect(f, top, w - 2 * f, h - top - f)

    def _shown(self):
        self._polished = True
        self.showEvent(None)


class QHeaderView:
    __slots__ = ("_section", "_stretch", "_visible")

    def __init__(self):
        self._visible, self._stretch, self._section = True, False, 30

    def setDefaultSectionSize(self, size):
        self._section = int(size)

    def defaultSectionSize(self):
        return self._section

    def setVisible(self, visible):
        self._visible = bool(visible)

    def isVisible(self):
        return self._visible

    def setStretchLastSection(self, stretch):
        self._stretch = bool(stretch)


class QAbstractItemView:
    SingleSelection, ExtendedSelection = "SingleSelection", "ExtendedSelection"
    SelectRows = "SelectRows"
    DoubleClicked, EditKeyPressed = 0x2, 0x8


class QTableWidgetItem:
    __slots__ = ("_check_state", "_flags", "_table", "_text")

    def __init__(self, *args, **kwargs):
        if kwargs or len(args) != 1 or not isinstance(args[0], str):
            raise TypeError("doubles model only QTableWidgetItem(str) positionally")
        self._text, self._table, self._check_state = args[0], None, 0
        self._flags = ITEM_IS_SELECTABLE | ITEM_IS_EDITABLE | ITEM_IS_ENABLED

    def checkState(self):
        return self._check_state

    def setCheckState(self, state):
        self._check_state = int(state)
        if self._table is not None:
            self._table.itemChanged.emit(self)

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        if self._table is not None:
            self._table.itemChanged.emit(self)

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        _ints(flags)
        self._flags = flags

    def row(self):
        return self._table._find(self)[0]

    def column(self):
        return self._table._find(self)[1]


class QTableWidgetSelectionRange:
    __slots__ = ("_rows",)

    def __init__(self, *args, **kwargs):
        if kwargs or len(args) != 4:
            raise TypeError("doubles model only the positional 4-int constructor")
        _ints(*args)
        top, _left, bottom, _right = args
        self._rows = (top, bottom)

    def topRow(self):
        return self._rows[0]

    def bottomRow(self):
        return self._rows[1]


class QTableWidget(QWidget):
    __slots__ = (
        "_attributes",
        "_cells",
        "_column_count",
        "_edit_triggers",
        "_headers",
        "_labels",
        "_mode",
        "_selected",
        "_widths",
        "cellDoubleClicked",
        "itemChanged",
        "itemSelectionChanged",
    )

    def __init__(self):
        super().__init__()
        self._cells, self._column_count, self._selected = [], 0, set()
        self._labels, self._widths, self._attributes = [], {}, {}
        self._mode, self._edit_triggers = QAbstractItemView.ExtendedSelection, 0
        self._headers = (QHeaderView(), QHeaderView())
        self.itemChanged = Signal(self, "itemChanged")
        self.itemSelectionChanged = Signal(self, "itemSelectionChanged")
        self.cellDoubleClicked = Signal(self, "cellDoubleClicked")

    rowCount = property(lambda self: len(self._cells))
    columnCount = property(lambda self: self._column_count)

    def horizontalHeader(self):
        return self._headers[0]

    def verticalHeader(self):
        return self._headers[1]

    def setColumnCount(self, count):
        _ints(count)
        self._column_count = count

    def setRowCount(self, count):
        _ints(count)
        self._cells = self._cells[:count]
        self._cells += [
            [None] * self._column_count for _ in range(count - len(self._cells))
        ]
        self._set_selection({r for r in self._selected if r < count})

    def removeRow(self, row):
        _ints(row)
        del self._cells[row]
        shifted = {r - (r > row) for r in self._selected if r != row}
        self._set_selection(shifted)

    def setHorizontalHeaderLabels(self, labels):
        self._labels = list(labels)

    def setColumnWidth(self, column, width):
        _ints(column, width)
        self._widths[column] = width

    def setSelectionBehavior(self, behavior):
        if behavior != QAbstractItemView.SelectRows:
            raise AssertionError("vanilla lists select whole rows")

    def setSelectionMode(self, mode):
        self._mode = mode

    def setEditTriggers(self, triggers):
        _ints(triggers)
        self._edit_triggers = triggers

    def setAlternatingRowColors(self, value):
        pass

    def setAttribute(self, attribute, on):
        self._attributes[attribute] = bool(on)

    def setItem(self, row, column, item):
        _ints(row, column)
        if not isinstance(item, QTableWidgetItem):
            raise TypeError("setItem expects a QTableWidgetItem")
        item._table = self
        self._cells[row][column] = item
        self.itemChanged.emit(item)  # dataChanged -> itemChanged, as in Qt

    def item(self, row, column):
        return self._cells[row][column]

    def _find(self, item):
        for r, cells in enumerate(self._cells):
            if item in cells:
                return r, cells.index(item)
        raise RuntimeError("item is not in the table")

    def _set_selection(self, rows):
        if rows != self._selected:
            self._selected = set(rows)
            self.itemSelectionChanged.emit()

    def clearSelection(self):
        self._set_selection(set())

    def selectRow(self, row):
        """ExtendedSelection without modifiers: clear and select (the trap)."""
        self._set_selection({row})

    def setRangeSelected(self, selection_range, select):
        if not isinstance(selection_range, QTableWidgetSelectionRange):
            raise TypeError("setRangeSelected expects a QTableWidgetSelectionRange")
        top, bottom = selection_range._rows
        rows = set(range(top, bottom + 1))
        chosen = self._selected | rows if select else self._selected - rows
        self._set_selection(chosen)

    def selectedRanges(self):
        return tuple(QTableWidgetSelectionRange(r, 0, r, 0) for r in self._selected)

    def user_select(self, rows):
        self._set_selection(set(rows))

    def user_double_click(self, row, column):
        self.cellDoubleClicked.emit(row, column)

    def user_edit(self, row, column, text):
        item = self._cells[row][column]
        if not item._flags & ITEM_IS_EDITABLE:
            raise AssertionError("the cell is not editable")
        item.setText(text)


CONTROL_DOUBLES = {
    "QButtonGroup": QButtonGroup,
    "QRadioButton": QRadioButton,
    "QPlainTextEdit": QPlainTextEdit,
    "QProgressBar": QProgressBar,
    "QGroupBox": QGroupBox,
    "QAbstractItemView": QAbstractItemView,
    "QHeaderView": QHeaderView,
    "QTableWidget": QTableWidget,
    "QTableWidgetItem": QTableWidgetItem,
    "QTableWidgetSelectionRange": QTableWidgetSelectionRange,
}
