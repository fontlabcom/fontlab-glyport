# this_file: tests/ui_doubles_table.py
"""QTableWidget doubles shaped like FontLab's PythonQt (probed natively:
verification/issue-101-ecosystem/evidence/glyport-r031/impl/12-table/probe_table.py).
``rowCount``/``columnCount``/``currentRow`` are properties; ``setRowCount``,
``setColumnCount`` and ``removeColumn`` delete the cell widgets they drop, and
``selectRow`` replaces the selection, as Qt does (impl/12-table/probe_select.py)."""

from types import SimpleNamespace

from ui_doubles import QWidget, Signal

ITEM_SELECTABLE, ITEM_EDITABLE, ITEM_ENABLED = 1, 2, 32
SELECTION_ENUMS = SimpleNamespace(Select=2, Rows=0x20, ClearAndSelect=3)  # QtGui
VIEW_ENUMS = SimpleNamespace(
    SelectRows=1,
    SingleSelection=1,
    ExtendedSelection=3,
    NoEditTriggers=0,
    AllEditTriggers=31,
)


class QHeaderView:
    def __init__(self):
        self.visible, self.section = True, 30

    def setVisible(self, flag):
        self.visible = bool(flag)

    def setDefaultSectionSize(self, size):
        self.section = size


class QTableWidgetItem:
    def __init__(self, text=""):
        if not isinstance(text, str):
            raise TypeError(f"QTableWidgetItem expects str, got {text!r}")
        self._text, self._flags = text, ITEM_SELECTABLE | ITEM_EDITABLE | ITEM_ENABLED

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        self._flags = int(flags)


class _Index:
    def __init__(self, row):
        self._row = row

    def row(self):
        return self._row


class QTableWidget(QWidget):
    __slots__ = (
        "_behavior",
        "_columns",
        "_header",
        "_items",
        "_labels",
        "_mode",
        "_rows",
        "_selected",
        "_triggers",
        "_vheader",
        "_widgets",
        "_widths",
        "cellChanged",
        "cellClicked",
        "cellDoubleClicked",
        "itemSelectionChanged",
    )

    def __init__(self):
        super().__init__()
        self._rows = self._columns = 0
        self._items, self._widgets, self._selected = {}, {}, []
        self._labels, self._widths = [], {}
        self._header, self._vheader = QHeaderView(), QHeaderView()
        self._mode = self._behavior = self._triggers = None
        for name in (
            "itemSelectionChanged",
            "cellClicked",
            "cellDoubleClicked",
            "cellChanged",
        ):
            setattr(self, name, Signal(self, name))

    @property
    def rowCount(self):
        return self._rows

    @property
    def columnCount(self):
        return self._columns

    @property
    def currentRow(self):
        return self._selected[0] if self._selected else -1

    def setColumnCount(self, count):
        for column in range(count, self._columns):  # Qt deletes those cells
            self._drop_column(column)
        self._columns = count

    def _drop_column(self, column):
        for (r, c), widget in list(self._widgets.items()):
            if c == column:
                for w in widget._tree():
                    w._deleted = True
                del self._widgets[(r, c)]
        self._items = {k: v for k, v in self._items.items() if k[1] != column}

    def removeColumn(self, column):
        """Qt: deletes the column's cell widgets and shifts later columns left."""
        self._drop_column(column)

        def shift(cells):
            return {(r, c - 1 if c > column else c): v for (r, c), v in cells.items()}

        self._widgets, self._items = shift(self._widgets), shift(self._items)
        self._columns -= 1

    def setRowCount(self, count):
        for (row, column), widget in list(self._widgets.items()):
            if row >= count:
                for w in widget._tree():
                    w._deleted = True
                del self._widgets[(row, column)]
        self._items = {k: v for k, v in self._items.items() if k[0] < count}
        self._rows = count
        kept = [r for r in self._selected if r < count]
        if kept != self._selected:
            self._selected = kept
            self.itemSelectionChanged.emit()

    def setHorizontalHeaderLabels(self, labels):
        self._labels = list(labels)

    def horizontalHeader(self):
        return self._header

    def verticalHeader(self):
        return self._vheader

    def setColumnWidth(self, column, width):
        self._widths[column] = width

    def columnWidth(self, column):
        return self._widths.get(column, 100)

    def setSelectionBehavior(self, behavior):
        self._behavior = behavior

    def setSelectionMode(self, mode):
        self._mode = mode

    def setEditTriggers(self, triggers):
        self._triggers = triggers

    def setItem(self, row, column, item):
        self._items[(row, column)] = item
        self.cellChanged.emit(row, column)  # Qt's model reports the new data

    def item(self, row, column):
        return self._items.get((row, column))

    def setCellWidget(self, row, column, widget):
        old = self._widgets.get((row, column))
        if old is not None:
            for w in old._tree():
                w._deleted = True
        widget.setParent(self)
        self._widgets[(row, column)] = widget

    def cellWidget(self, row, column):
        return self._widgets.get((row, column))

    def selectRow(self, row):
        """Qt (probed natively, impl/12-table/probe_select.py): without keyboard
        modifiers selectRow replaces the selection, even in ExtendedSelection."""
        if [row] != self._selected:
            self._selected = [row]
            self.itemSelectionChanged.emit()

    def model(self):
        return SimpleNamespace(index=lambda row, column: _Index(row))

    def _model_select(self, index, flags):
        if not flags & SELECTION_ENUMS.Select:
            raise AssertionError("doubles model only Select")
        rows = sorted({*self._selected, index.row()})
        if rows != self._selected:
            self._selected = rows
            self.itemSelectionChanged.emit()

    def clearSelection(self):
        if self._selected:
            self._selected = []
            self.itemSelectionChanged.emit()

    def selectionModel(self):
        return SimpleNamespace(
            selectedRows=lambda: [_Index(r) for r in self._selected],
            select=self._model_select,
        )

    # User actions
    def user_click(self, row, column=0):
        self._selected = []
        self.selectRow(row)
        self.cellClicked.emit(row, column)

    def user_double_click(self, row, column=0):
        self.cellDoubleClicked.emit(row, column)

    def user_edit(self, row, column, text):
        self._items[(row, column)].setText(text)
        self.cellChanged.emit(row, column)


def install(qt):
    """Add the table (and scroll area, splitter) doubles and enums to a
    ``make_qt()`` namespace; tables in NIBs sit in scroll views."""
    from test_ui_nib_panes import QSplitter
    from test_ui_nib_scroll import QScrollArea

    qt.QtGui.QScrollArea, qt.QtGui.QSplitter = QScrollArea, QSplitter
    for name in ("ScrollBarAsNeeded", "ScrollBarAlwaysOff", "ScrollBarAlwaysOn"):
        setattr(qt.QtCore.Qt, name, name)
    qt.QtGui.QTableWidget, qt.QtGui.QTableWidgetItem = QTableWidget, QTableWidgetItem
    qt.QtGui.QAbstractItemView = VIEW_ENUMS
    qt.QtGui.QItemSelectionModel = SELECTION_ENUMS
    qt.QtCore.Qt.ItemIsSelectable = ITEM_SELECTABLE
    qt.QtCore.Qt.ItemIsEditable = ITEM_EDITABLE
    qt.QtCore.Qt.ItemIsEnabled = ITEM_ENABLED
    return qt
