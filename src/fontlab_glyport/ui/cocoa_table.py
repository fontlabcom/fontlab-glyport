# this_file: src/fontlab_glyport/ui/cocoa_table.py
"""Qt-backed ``NSTableView`` (R031): a QTableWidget fed by a data source.

- Cell-based: ``tableView_objectValueForTableColumn_row_`` gives each cell's
  text; an edit in an editable column calls
  ``tableView_setObjectValue_forTableColumn_row_``.
- View-based: the delegate's ``tableView_viewForTableColumn_row_`` returns an
  NSView (usually ``makeViewWithIdentifier_owner_``, which instantiates the
  NIB's prototype cell view graph); its ``objectValue`` is the data source's
  value. Cell views are torn down (slots disconnected, bindings removed)
  before ``reloadData`` lets Qt delete their widgets.
- Selection: rows only; ``tableViewSelectionDidChange_`` reaches the delegate,
  a click sends the action, a double click the ``doubleAction``.

Qt properties (``rowCount``, ``currentRow``) are attributes in PythonQt.
"""

from collections.abc import Iterable
from typing import Any

import fontlabapp.qt.tables.items as _table_items
import fontlabapp.qt.tables.selection as _table_selection

from .cocoa import NSObject, perform, selector_of, unsupported
from .cocoa_views import NSControl, NSNotFound, NSView, release_tree


class NSIndexSet(NSObject):
    """A sorted set of row indexes (the subset tables use)."""

    @classmethod
    def indexSet(cls):
        return cls._of(())

    @classmethod
    def indexSetWithIndex_(cls, index):
        return cls._of((int(index),))

    @classmethod
    def indexSetWithIndexesInRange_(cls, location_length):
        location, length = location_length
        return cls._of(range(int(location), int(location) + int(length)))

    @classmethod
    def _of(cls, indexes: Iterable[int]):
        result = cls.alloc().init()
        result._indexes = sorted(set(indexes))
        return result

    def count(self) -> int:
        return len(self._indexes)

    def firstIndex(self) -> int:
        return self._indexes[0] if self._indexes else NSNotFound

    def lastIndex(self) -> int:
        return self._indexes[-1] if self._indexes else NSNotFound

    def containsIndex_(self, index) -> bool:
        return int(index) in self._indexes

    def __iter__(self):
        return iter(self._indexes)

    def __len__(self) -> int:
        return len(self._indexes)


def _value(obj: Any, key_path: str) -> Any:
    """Key-value lookup on a row object: KVC, a mapping, or an attribute."""
    if hasattr(obj, "valueForKeyPath_"):
        return obj.valueForKeyPath_(key_path)
    for key in key_path.split("."):
        obj = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        obj = obj() if callable(obj) else obj
    return obj


class NSArrayController(NSObject):
    """Content, arranged objects (no sorting or filtering) and a selection,
    observable for bindings. ``contentArray`` binds to an owner's key path;
    ``dispose()`` (plugin unload, environment close) unbinds it."""

    def init(self):
        return self.initWithContent_([])

    def initWithContent_(self, content):
        self._content = list(content or [])
        self._selection: list = []
        self._selects_inserted, self._avoids_empty = True, False
        self._source = None
        self._env.objects.append(self)  # disposed when the environment closes
        return self

    def dispose(self) -> None:
        """Plugin unload or environment close: stop observing the bound source."""
        self.unbind_("contentArray")
        if self in self._env.objects:
            self._env.objects.remove(self)

    # Content
    def content(self):
        return list(self._content)

    def setContent_(self, content) -> None:
        self._change(lambda: setattr(self, "_content", list(content or [])))

    def arrangedObjects(self) -> list:
        return list(self._content)

    def addObject_(self, obj) -> None:
        self.insertObject_atArrangedObjectIndex_(obj, len(self._content))

    def addObjects_(self, objects) -> None:
        for obj in objects:
            self.addObject_(obj)

    def insertObject_atArrangedObjectIndex_(self, obj, index) -> None:
        def insert():
            self._content.insert(int(index), obj)
            if self._selects_inserted:
                self._selection = [int(index)]

        self._change(insert)

    def removeObject_(self, obj) -> None:
        if obj in self._content:
            self.removeObjectAtArrangedObjectIndex_(self._content.index(obj))

    def removeObjects_(self, objects) -> None:
        for obj in list(objects):
            self.removeObject_(obj)

    def removeObjectAtArrangedObjectIndex_(self, index) -> None:
        self._change(lambda: self._content.pop(int(index)))

    def _change(self, action) -> None:
        keys = ("content", "arrangedObjects", "selectionIndexes", "selectedObjects")
        for key in keys:
            self.willChangeValueForKey_(key)
        action()
        self._selection = [i for i in self._selection if i < len(self._content)]
        for key in keys:  # rows first, so observers select existing rows
            self.didChangeValueForKey_(key)

    # Selection
    def selectionIndexes(self):
        return NSIndexSet._of(self._selection)

    def setSelectionIndexes_(self, indexes) -> bool:
        rows = sorted({int(i) for i in indexes if 0 <= int(i) < len(self._content)})
        if rows != self._selection:
            for key in ("selectionIndexes", "selectedObjects"):
                self.willChangeValueForKey_(key)
            self._selection = rows
            for key in ("selectedObjects", "selectionIndexes"):
                self.didChangeValueForKey_(key)
        return True

    def selectionIndex(self) -> int:
        return self._selection[0] if self._selection else NSNotFound

    def setSelectionIndex_(self, index) -> bool:
        return self.setSelectionIndexes_([int(index)])

    def selectedObjects(self) -> list:
        return [self._content[i] for i in self._selection]

    def setSelectedObjects_(self, objects) -> bool:
        return self.setSelectionIndexes_([self._content.index(o) for o in objects])

    def selectsInsertedObjects(self) -> bool:
        return self._selects_inserted

    def setSelectsInsertedObjects_(self, flag) -> None:
        self._selects_inserted = bool(flag)

    def avoidsEmptySelection(self) -> bool:
        return self._avoids_empty

    def setAvoidsEmptySelection_(self, flag) -> None:
        self._avoids_empty = bool(flag)

    # Bindings
    def bind_toObject_withKeyPath_options_(self, binding, owner, keyPath, options):
        if str(binding) != "contentArray":
            raise unsupported(f"NSArrayController.bind.{binding}")
        self.unbind_("contentArray")
        owner.addObserver_forKeyPath_options_context_(self, str(keyPath), 0, "content")
        self._source = (owner, str(keyPath))
        self.setContent_(owner.valueForKeyPath_(str(keyPath)))

    def unbind_(self, binding) -> None:
        if self._source is not None:
            self._source[0].removeObserver_forKeyPath_(self, self._source[1])
            self._source = None

    def observeValueForKeyPath_ofObject_change_context_(
        self, path, owner, change, context
    ) -> None:
        if context == "content" and self._source is not None:
            self.setContent_(owner.valueForKeyPath_(self._source[1]))


class _Forwarder(NSObject):
    """Observes for a table and hands the change on by context."""

    def initWithTable_(self, table):
        self._table = table
        return self

    def observeValueForKeyPath_ofObject_change_context_(
        self, keyPath, obj, change, context
    ) -> None:
        self._table._observed_change(obj, context)


class _Notification:
    def __init__(self, name: str, obj: Any):
        self._name, self._object = name, obj

    def name(self) -> str:
        return self._name

    def object(self):
        return self._object


class NSTableColumn(NSObject):
    def initWithIdentifier_(self, identifier):
        self._identifier, self._title, self._table = identifier, "", None
        self._width, self._min, self._max, self._editable = 100.0, 10.0, 1e6, True
        return self

    def init(self):
        return self.initWithIdentifier_(None)

    def identifier(self):
        return self._identifier

    def setIdentifier_(self, identifier) -> None:
        self._identifier = identifier

    def title(self) -> str:
        return self._title

    def setTitle_(self, title) -> None:
        self._title = str(title or "")
        if self._table is not None:
            self._table._headers()

    def width(self) -> float:
        return self._width

    def setWidth_(self, width) -> None:
        self._width = min(max(float(width), self._min), self._max)
        if self._table is not None:
            self._table._qt.setColumnWidth(
                self._table._columns.index(self), round(self._width)
            )

    def minWidth(self) -> float:
        return self._min

    def setMinWidth_(self, width) -> None:
        self._min = float(width)

    def maxWidth(self) -> float:
        return self._max

    def setMaxWidth_(self, width) -> None:
        self._max = float(width)

    def isEditable(self) -> bool:
        return self._editable

    def setEditable_(self, flag) -> None:
        self._editable = bool(flag)

    def tableView(self):
        return self._table

    def bind_toObject_withKeyPath_options_(self, binding, controller, keyPath, options):
        """``value`` to ``arrangedObjects.<key>`` of an array controller."""
        head, _, key = str(keyPath).partition(".")
        if str(binding) != "value" or head != "arrangedObjects" or not key:
            raise unsupported(f"NSTableColumn.bind.{binding}.{keyPath}")
        self.__dict__["_value_binding"] = (controller, key)
        if self._table is not None:
            self._table._bindings_changed()

    def unbind_(self, binding) -> None:
        if self.__dict__.pop("_value_binding", None) and self._table is not None:
            self._table._bindings_changed()


class NSTableCellView(NSView):
    """A prototype cell's container: ``textField``, ``imageView`` and an
    observable ``objectValue`` (the NIB binds the text field to it)."""

    def initWithFrame_(self, frame):
        self._text_field = self._image_view = self._object_value = None
        return NSView.initWithFrame_(self, frame)

    def textField(self):
        return self._text_field

    def setTextField_(self, field) -> None:
        self._text_field = field

    def imageView(self):
        return self._image_view

    def setImageView_(self, view) -> None:
        self._image_view = view

    def objectValue(self):
        return self._object_value

    def setObjectValue_(self, value) -> None:
        self.willChangeValueForKey_("objectValue")
        self._object_value = value
        self.didChangeValueForKey_("objectValue")


class NSTableView(NSControl):
    """QTableWidget with Cocoa columns, data source, delegate and selection."""

    _qt_class = "QTableWidget"

    def initWithFrame_(self, frame):
        self._columns: list = []
        self._data_source = self._delegate = None
        self._prototypes: dict = {}
        self._cell_views: dict = {}
        self._selected: list = []
        self._clicked, self._double_action = (-1, -1), None
        self._multiple, self._row_height = False, 17.0
        self._filling = self._selecting = self._generation = 0
        self._nib_context, self._observed = None, {}
        NSControl.initWithFrame_(self, frame)
        views = self._env.qt.QtGui.QAbstractItemView
        self._qt.setSelectionBehavior(views.SelectRows)
        self._qt.verticalHeader().setVisible(False)
        self.setAllowsMultipleSelection_(False)
        self.setRowHeight_(self._row_height)
        return self

    def _connect(self) -> None:
        self._track(self._qt.itemSelectionChanged, self._selection_changed)
        self._track(self._qt.cellClicked, self._cell_clicked)
        self._track(self._qt.cellDoubleClicked, self._cell_double_clicked)
        self._track(self._qt.cellChanged, self._cell_changed)

    def _load_table(self, props, context) -> None:
        """The NIB's columns, header, selection mode, row height, prototypes."""
        for spec in props.get("columns", []):
            column = NSTableColumn.alloc().initWithIdentifier_(spec.get("identifier"))
            column._title = spec.get("title", "")
            column._min = spec.get("minWidth") or column._min
            column._max = spec.get("maxWidth") or column._max
            column._width = spec.get("width") or column._width
            column._editable = spec.get("editable", True)
            self.addTableColumn_(column)
        self.setHeaderView_(self if props.get("headerVisible", True) else None)
        self.setAllowsMultipleSelection_(props.get("allowsMultipleSelection", False))
        self.setRowHeight_(props.get("rowHeight", 17.0))
        self._prototypes = dict(props.get("prototypes") or {})
        self._nib_context = context

    # Columns
    def tableColumns(self) -> list:
        return list(self._columns)

    def addTableColumn_(self, column) -> None:
        column._table = self
        self._columns.append(column)
        self._qt.setColumnCount(len(self._columns))
        self._headers()
        self._qt.setColumnWidth(len(self._columns) - 1, round(column._width))

    def removeTableColumn_(self, column) -> None:
        """Release the column's cell views, then remove the Qt column (which
        deletes their widgets and shifts later columns left)."""
        index = self._columns.index(column)
        cells = {}
        for (row, col), view in self._cell_views.items():
            if col == index:
                release_tree(view)
            else:
                cells[(row, col - 1 if col > index else col)] = view
        self._cell_views = cells
        self._columns.pop(index)
        column._table = None
        self._qt.removeColumn(index)
        self._headers()
        self._resync(self._generation)  # no reload

    def tableColumnWithIdentifier_(self, identifier):
        return next((c for c in self._columns if c.identifier() == identifier), None)

    def columnWithIdentifier_(self, identifier) -> int:
        column = self.tableColumnWithIdentifier_(identifier)
        return -1 if column is None else self._columns.index(column)

    def _headers(self) -> None:
        self._qt.setHorizontalHeaderLabels([c.title() for c in self._columns])

    def headerView(self):
        return self if self.__dict__.get("_header", True) else None

    def setHeaderView_(self, view) -> None:
        """``None`` hides the column titles; any other value shows them."""
        self.__dict__["_header"] = view is not None
        self._qt.horizontalHeader().setVisible(view is not None)

    def rowHeight(self) -> float:
        return self._row_height

    def setRowHeight_(self, height) -> None:
        self._row_height = float(height)
        self._qt.verticalHeader().setDefaultSectionSize(round(self._row_height))

    # Data
    def dataSource(self):
        return self._data_source

    def setDataSource_(self, source) -> None:
        self._data_source = source
        self._env.dispatch.call(self.reloadData, self)

    def delegate(self):
        return self._delegate

    def setDelegate_(self, delegate) -> None:
        """AppKit asks a new delegate for views: reload when data is there."""
        self._delegate = delegate
        if self._data_source is not None:
            self._env.dispatch.call(self.reloadData, self)

    def numberOfRows(self) -> int:
        rows = self._qt.rowCount
        return rows() if callable(rows) else rows

    # Bindings: content (and column values) from an array controller
    def bind_toObject_withKeyPath_options_(self, binding, controller, keyPath, options):
        binding = str(binding)
        if binding not in ("content", "selectionIndexes"):
            NSControl.bind_toObject_withKeyPath_options_(
                self, binding, controller, keyPath, options
            )
            return
        self.__dict__[f"_{binding}_binding"] = controller  # replaces an old one
        self._bindings_changed()
        if binding == "selectionIndexes":
            self._pull_selection(controller)

    def unbind_(self, binding) -> None:
        binding = str(binding)
        if binding in ("content", "selectionIndexes"):
            if self.__dict__.pop(f"_{binding}_binding", None) is not None:
                self._bindings_changed()
            return
        NSControl.unbind_(self, binding)

    def _bindings_changed(self) -> None:
        """Content may come from elsewhere now: reload (which re-observes)."""
        if not self.__dict__.get("_dead"):
            self.reloadData()

    def _wanted_observations(self) -> dict:
        """(object, key, context) the table's own bindings need: controllers'
        arranged objects and selection, and every hop of each bound column's
        key path on the shown rows (``master.name``: the row's ``master`` and
        that master's ``name``)."""
        wanted, controllers = {}, []
        content = self.__dict__.get("_content_binding")
        if content is not None:
            controllers.append(content)
        bound = [c.__dict__.get("_value_binding") for c in self._columns]
        controllers += [b[0] for b in bound if b]
        for controller in controllers:
            key = (id(controller), "arrangedObjects", "arrangedObjects")
            wanted[key] = (controller, "arrangedObjects", "arrangedObjects")
        selection = self.__dict__.get("_selectionIndexes_binding")
        if selection is not None:
            key = (id(selection), "selectionIndexes", "selectionIndexes")
            wanted[key] = (selection, "selectionIndexes", "selectionIndexes")
        for controller, path in [b for b in bound if b]:
            for obj in controller.arrangedObjects():
                for part in path.split("."):
                    if obj is None:
                        break
                    if hasattr(obj, "addObserver_forKeyPath_options_context_"):
                        wanted[(id(obj), part, "row")] = (obj, part, "row")
                    obj = _value(obj, part)
        return wanted

    def _sync_observations(self, wanted: dict) -> None:
        """Observe through a forwarder of its own, so these observations never
        collide with the control's inherited bindings (``enabled`` to a row's
        key): each side keeps its own registrations and contexts."""
        forwarder = self.__dict__.get("_forwarder")
        if forwarder is None:
            forwarder = self.__dict__["_forwarder"] = _Forwarder.alloc().initWithTable_(
                self
            )
        for key in [k for k in self._observed if k not in wanted]:
            obj, path, _context = self._observed.pop(key)
            obj.removeObserver_forKeyPath_(forwarder, path)
        for key, (obj, path, context) in wanted.items():
            if key not in self._observed:
                obj.addObserver_forKeyPath_options_context_(forwarder, path, 0, context)
                self._observed[key] = (obj, path, context)

    def _pull_selection(self, controller) -> None:
        rows = list(controller.selectionIndexes())
        if rows == self._selected:
            return
        self.__dict__["_syncing"] = True  # do not push the change back
        try:
            self._select(rows, extend=False)
        finally:
            self.__dict__["_syncing"] = False

    def _observed_change(self, obj, context) -> None:
        """From the forwarder: one of the table's own observations fired."""
        if self.__dict__.get("_dead"):
            return
        if context == "arrangedObjects":
            self.reloadData()
        elif context == "selectionIndexes":
            self._pull_selection(obj)
        elif context == "row":
            self._rows_changed()

    def _rows_changed(self) -> None:
        """A hop of a bound key path changed: refresh the bound cells and
        observe the hops again (an intermediate object may be new)."""
        generation = self._generation
        for row, obj in enumerate(self._bound_rows() or []):
            for index, column in enumerate(list(self._columns)):
                binding = column.__dict__.get("_value_binding")
                if not binding:
                    continue
                value = _value(obj, binding[1])
                if self._stale(generation):
                    return
                view = self._cell_views.get((row, index))
                if view is not None:
                    if hasattr(view, "setObjectValue_"):
                        view.setObjectValue_(value)
                        if self._stale(generation):
                            return
                    continue
                item = self._qt.item(row, index)
                if item is not None:
                    self._filling += 1  # not a user edit
                    try:
                        item.setText("" if value is None else str(value))
                    finally:
                        self._filling -= 1
        self._resync(generation)

    def _bound_rows(self):
        """Rows from the content binding or a bound column, else None."""
        controller = self.__dict__.get("_content_binding")
        if controller is None:
            bound = [c.__dict__.get("_value_binding") for c in self._columns]
            controller = next((b[0] for b in bound if b), None)
        return None if controller is None else controller.arrangedObjects()

    def _bound_value(self, column, obj):
        binding = column.__dict__.get("_value_binding")
        return obj if binding is None else _value(obj, binding[1])

    def reloadData(self) -> None:
        """Fill the rows again. A data source or delegate callback may reload or
        dispose the table: each pass has a generation, and a pass that finds a
        newer one (or a disposed table) stops and releases what it was given."""
        if self.__dict__.get("_dead"):
            return
        self._generation += 1
        generation = self._generation
        source, delegate = self._data_source, self._delegate
        count = getattr(source, "numberOfRowsInTableView_", None)
        value_of = getattr(source, "tableView_objectValueForTableColumn_row_", None)
        objects = self._bound_rows() if count is None else None
        rows = int(count(self)) if count is not None else len(objects or ())
        if self._stale(generation):
            return
        if objects is not None:

            def value_of(table, column, row):
                return self._bound_value(column, objects[row])

        view_of = getattr(delegate, "tableView_viewForTableColumn_row_", None)
        editable = hasattr(source, "tableView_setObjectValue_forTableColumn_row_")
        selected = [r for r in self._selected if r < rows]
        self._release_cells()
        self._filling += 1
        try:
            self._qt.setRowCount(0)
            self._qt.setRowCount(rows)
            for row in range(rows):
                for index, column in enumerate(list(self._columns)):
                    value = None if value_of is None else value_of(self, column, row)
                    if self._stale(generation):
                        return
                    view = None if view_of is None else view_of(self, column, row)
                    if self._stale(generation):
                        self._discard(view)
                        return
                    if view is not None:
                        has_value = value_of is not None
                        if not self._place_view(row, index, view, value, has_value):
                            return
                        if self._stale(generation):  # the value setter reloaded
                            return
                    else:
                        self._place_item(
                            row, index, value, editable and column._editable
                        )
            self._select(selected, extend=False)
        finally:
            self._filling -= 1
        self._resync(generation)

    def _resync(self, generation: int) -> None:
        """Observe what the bindings need now. Discovery calls getters, which
        may reload (or dispose) the table: a set found by a stale pass is
        discarded, since the newer pass installed its own."""
        if self._stale(generation):
            return
        wanted = self._wanted_observations()
        if not self._stale(generation):
            self._sync_observations(wanted)

    def _stale(self, generation: int) -> bool:
        return generation != self._generation or bool(self.__dict__.get("_dead"))

    def _discard(self, view) -> None:
        """A view a callback returned to a pass that no longer places it."""
        if view is not None and view not in self._cell_views.values():
            release_tree(view)
            view._qt.deleteLater()

    def _place_item(self, row: int, index: int, value, editable: bool) -> None:
        _table_items.place_text(
            self._env.qt, lambda: self._qt, row, index, value, editable
        )

    def _place_view(self, row, index, view, value, has_value) -> bool:
        """Give the view its value, then place it; False (and the view
        released) when the value setter reloaded or disposed the table."""
        generation = self._generation
        if has_value and hasattr(view, "setObjectValue_"):
            view.setObjectValue_(value)  # observers and bindings run user code
            if self._stale(generation):
                self._discard(view)
                return False
        old = self._cell_views.get((row, index))
        if old is not None and old is not view:
            release_tree(old)  # Qt deletes the widget it replaces
        view.__dict__["_embedded"] = self  # the table widget deletes it
        self._qt.setCellWidget(row, index, view._qt)
        self._cell_views[(row, index)] = view
        return True

    def _release_cells(self) -> None:
        """Tear cell views down before Qt deletes their widgets."""
        for view in self._cell_views.values():
            release_tree(view)
        self._cell_views.clear()

    def _owned_views(self) -> list:
        return NSView._owned_views(self) + list(self._cell_views.values())

    def _release(self) -> None:
        NSControl._release(self)
        self.__dict__["_dead"] = True  # stops a population in progress
        self._generation += 1
        self._sync_observations({})
        self._data_source = self._delegate = None

    def viewAtColumn_row_makeIfNecessary_(self, column, row, make):
        return self._cell_views.get((int(row), int(column)))

    def makeViewWithIdentifier_owner_(self, identifier, owner):
        """A new copy of the NIB's prototype cell view (``None`` if unknown)."""
        graph = self._prototypes.get(identifier)
        if graph is None:
            return None
        from .graph import UIGraph
        from .nib_loader import instantiate

        appkit, classes, resources = self._nib_context or (self._env.classes, {}, ())
        instance = instantiate(
            UIGraph.from_json(graph),
            owner,
            appkit,
            classes=classes,
            resources=resources,
        )
        views = [obj for obj in instance.top_level if isinstance(obj, NSView)]
        return views[0] if views else None

    # Selection
    def allowsMultipleSelection(self) -> bool:
        return self._multiple

    def setAllowsMultipleSelection_(self, flag) -> None:
        self._multiple = bool(flag)
        views = self._env.qt.QtGui.QAbstractItemView
        self._qt.setSelectionMode(
            views.ExtendedSelection if self._multiple else views.SingleSelection
        )

    def selectedRow(self) -> int:
        return self._selected[0] if self._selected else -1

    def selectedRowIndexes(self):
        return NSIndexSet._of(self._selected)

    def numberOfSelectedRows(self) -> int:
        return len(self._selected)

    def isRowSelected_(self, row) -> bool:
        return int(row) in self._selected

    def selectRowIndexes_byExtendingSelection_(self, indexes, extend) -> None:
        rows = [indexes] if isinstance(indexes, int) else list(indexes)
        self._select(rows, extend=bool(extend))

    def deselectAll_(self, sender) -> None:
        self._qt.clearSelection()

    def _select(self, rows: list, *, extend: bool) -> None:
        """Select rows through the selection model (Qt's selectRow would replace
        the selection); bindings and the delegate hear the result once."""
        flags = self._env.qt.QtGui.QItemSelectionModel
        self._selecting += 1
        try:
            _table_selection.select_model_rows(
                self._qt, rows, flags, self.numberOfRows, extend=extend
            )
        finally:
            self._selecting -= 1
        self._selection_changed()

    def _selection_changed(self, *args) -> None:
        if self._selecting:
            return
        rows = _table_selection.selected_model_rows(self._qt)
        if rows == self._selected:
            return
        self._selected = rows
        bound = self.__dict__.get("_selectionIndexes_binding")
        if (
            bound is not None
            and not self._filling
            and not self.__dict__.get("_syncing")
        ):
            bound.setSelectionIndexes_(rows)
        changed = getattr(self._delegate, "tableViewSelectionDidChange_", None)
        if changed is not None and not self._filling:
            note = _Notification("NSTableViewSelectionDidChangeNotification", self)
            self._env.dispatch.call(lambda: changed(note), self)

    # Clicks and edits
    def clickedRow(self) -> int:
        return self._clicked[0]

    def clickedColumn(self) -> int:
        return self._clicked[1]

    def doubleAction(self):
        return self._double_action

    def setDoubleAction_(self, action) -> None:
        self._double_action = None if action is None else selector_of(action)

    def _cell_clicked(self, row, column) -> None:
        self._clicked = (int(row), int(column))
        self._send()

    def _cell_double_clicked(self, row, column) -> None:
        self._clicked = (int(row), int(column))
        target, action = self._target, self._double_action
        if target is not None and action is not None:
            args = (self,) if action.count(":") else ()
            self._env.dispatch.call(lambda: perform(target, action, *args), self)

    def _cell_changed(self, row, column) -> None:
        if self._filling:
            return
        setter = getattr(
            self._data_source, "tableView_setObjectValue_forTableColumn_row_", None
        )
        item = self._qt.item(row, column)
        if setter is None or item is None:
            return
        text = item.text() if callable(item.text) else item.text
        column_object = self._columns[int(column)]
        self._env.dispatch.call(
            lambda: setter(self, str(text), column_object, int(row)), self
        )

    def _get(self) -> int:
        return self.selectedRow()

    def _set(self, value) -> None:
        self._select([int(value)], extend=False)


TABLE_CLASSES = (NSArrayController, NSTableCellView, NSTableView)
