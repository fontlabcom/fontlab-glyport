# this_file: tests/test_ui_nib_rereview_fixes.py
"""Regression tests for the R031 re-review findings (reports/RR-r031.md),
with Qt-faithful doubles (ui_doubles_table; fresh signal wrappers below)."""

from pathlib import Path

import pytest
from test_ui_nib_controller import Master
from test_ui_nib_segments import CheckButton, ClearLineEdit
from test_ui_nib_table import _owner_class
from test_ui_nib_text import QPlainTextEdit
from ui_doubles import make_qt
from ui_doubles_table import install

from fontlab_glyport.ui import nib_graph
from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_archive import NibFormatError
from fontlab_glyport.ui.nib_graph import graph_from_nib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"


def _table_kit():
    return make_appkit_classes(install(make_qt()), error_sink=print)


def _registered(view):
    return view in view._env.views


# P1 (1): re-entrant reload and dispose during population
def test_table_when_delegate_reloads_during_population_then_no_live_orphan_cells():
    kit, made = _table_kit(), []
    owner_class = _owner_class()

    class Reentrant(owner_class):
        def tableView_viewForTableColumn_row_(self, table, column, row):
            view = owner_class.tableView_viewForTableColumn_row_(
                self, table, column, row
            )
            if view is not None:
                made.append(view)
                if len(made) == 1:
                    table.reloadData()  # once, from inside the population
            return view

    owner = Reentrant.alloc().init()
    instantiate(load_graph(FIXTURES / "Table.xib"), owner, kit)
    placed = set(map(id, owner.table._cell_views.values()))
    assert len(placed) == 6, "two columns of three rows, from the inner reload"
    assert owner.table._qt.cellWidget(0, 0) is not None
    for view in made:
        if id(view) not in placed:  # replaced or abandoned: fully released
            assert (
                not _registered(view)
                and view.textField()._qt.editingFinished.slots == []
            )
    kit["close"]()


def test_table_when_disposed_during_population_then_population_stops():
    kit, made = _table_kit(), []
    owner_class = _owner_class()

    class Disposer(owner_class):
        def tableView_viewForTableColumn_row_(self, table, column, row):
            view = owner_class.tableView_viewForTableColumn_row_(
                self, table, column, row
            )
            if view is not None:
                made.append(view)
                if len(made) == 2:
                    self.dialog.dispose()
            return view

    owner = Disposer.alloc().init()
    instantiate(load_graph(FIXTURES / "Table.xib"), owner, kit)
    assert len(made) == 2, "no delegate calls after the table was disposed"
    for view in made:
        assert (
            not _registered(view) and view.textField()._qt.editingFinished.slots == []
        )
    kit["close"]()


def test_combo_when_data_source_disposes_it_then_reload_stops():
    kit = make_appkit_classes(make_qt(), error_sink=print)
    combo = kit["NSComboBox"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 20))
    combo.setUsesDataSource_(True)

    class Source(NSObject):
        def numberOfItemsInComboBox_(self, box):
            return 2

        def comboBox_objectValueForItemAtIndex_(self, box, index):
            box.dispose()
            return "x"

    combo.setDataSource_(Source.alloc().init())
    assert combo._qt.count == 0, "the disposed combo was not filled"
    kit["close"]()


# P1 (2): column removal
@pytest.mark.parametrize("first", [True, False])
def test_table_when_column_removed_then_its_cells_released_and_columns_aligned(first):
    kit = _table_kit()
    owner_class = _owner_class()

    class EveryColumn(owner_class):
        def tableView_viewForTableColumn_row_(self, table, column, row):
            if table is not self.table:
                return None
            return table.makeViewWithIdentifier_owner_("Name", self)

    owner = EveryColumn.alloc().init()
    instantiate(load_graph(FIXTURES / "Table.xib"), owner, kit)
    table = owner.table
    name, size = table.tableColumns()
    removed, kept = (name, size) if first else (size, name)
    gone = [
        table.viewAtColumn_row_makeIfNecessary_(table._columns.index(removed), r, False)
        for r in range(3)
    ]
    stay = [
        table.viewAtColumn_row_makeIfNecessary_(table._columns.index(kept), r, False)
        for r in range(3)
    ]
    table.removeTableColumn_(removed)
    assert table.tableColumns() == [kept] and table._qt.columnCount == 1
    assert table._qt._labels == [kept.title()] and removed.tableView() is None
    for view in gone:
        assert (
            not _registered(view) and view.textField()._qt.editingFinished.slots == []
        )
        assert view._qt._deleted
    for row, view in enumerate(stay):
        assert table.viewAtColumn_row_makeIfNecessary_(0, row, False) is view
        assert table._qt.cellWidget(row, 0) is view._qt and not view._qt._deleted
    kit["close"]()


# P2: segment removal with fresh signal wrappers (PythonQt)
class _Wrapper:
    """A bound-signal wrapper: a new object per attribute access, equal by signal."""

    def __init__(self, signal):
        self._signal = signal

    def connect(self, slot):
        self._signal.connect(slot)

    def disconnect(self, slot):
        self._signal.disconnect(slot)

    def emit(self, *args):
        self._signal.emit(*args)

    def __eq__(self, other):
        return isinstance(other, _Wrapper) and other._signal is self._signal

    __hash__ = None


class FreshSignalButton(CheckButton):
    __slots__ = ("_clicked_signal",)

    @property
    def clicked(self):
        return _Wrapper(self._clicked_signal)

    @clicked.setter
    def clicked(self, signal):
        self._clicked_signal = signal


def test_segments_when_shrunk_with_fresh_signal_wrappers_then_exact_slots_removed():
    qt = make_qt()
    qt.QtGui.QPushButton, qt.QtGui.QLineEdit = FreshSignalButton, ClearLineEdit
    kit = make_appkit_classes(qt, error_sink=print)
    control = kit["NSSegmentedControl"].alloc().initWithFrame_(NSMakeRect(0, 0, 90, 20))
    control.setSegmentCount_(3)
    third = control._segments[2]._qt
    control.setSegmentCount_(2)
    assert third._clicked_signal.slots == [], "the removed segment's slot is gone"
    assert len(control._slots) == 2
    assert all(s._qt._clicked_signal.slots for s in control._segments)
    kit["close"]()


# P2: nested prototypes share one depth and object budget
def test_prototypes_when_nested_without_end_then_nib_format_error(monkeypatch):
    root = nib_graph.read_nib(FIXTURES / "Table.nib")
    monkeypatch.setattr(nib_graph, "read_nib_data", lambda data, path="": root)
    with pytest.raises(NibFormatError):
        graph_from_nib(FIXTURES / "Table.nib")  # each prototype holds the table again


def test_prototypes_when_their_objects_exceed_the_budget_then_rejected(monkeypatch):
    total = len(graph_from_nib(FIXTURES / "Table.nib").to_json()["nodes"])
    monkeypatch.setattr(nib_graph, "MAX_NODES", total + 2)  # outer fits, proto doesn't
    with pytest.raises(NibFormatError):
        graph_from_nib(FIXTURES / "Table.nib")


# P2: multiple selection through the selection model
def test_table_when_multiple_rows_selected_then_all_kept_and_one_notification():
    kit = _table_kit()
    owner = _owner_class().alloc().init()
    instantiate(load_graph(FIXTURES / "Table.xib"), owner, kit)
    plain = owner.plainTable
    notes = []
    owner.tableViewSelectionDidChange_ = lambda note: notes.append(
        list(note.object().selectedRowIndexes())
    )
    plain.setDelegate_(owner)
    notes.clear()
    index_set = kit["NSIndexSet"]
    plain.selectRowIndexes_byExtendingSelection_(index_set._of([0, 2]), False)
    assert list(plain.selectedRowIndexes()) == [0, 2]
    assert notes == [[0, 2]], "one notification with the final selection"
    plain.selectRowIndexes_byExtendingSelection_(index_set.indexSetWithIndex_(1), True)
    assert list(plain.selectedRowIndexes()) == [0, 1, 2]
    kit["close"]()


# P2: unbinding and rebinding a table
def _controller_owner():
    objc = make_objc_module({})

    class ControllerOwner(NSObject):
        dialog = objc.IBOutlet()
        table = objc.IBOutlet()
        items = objc.IBOutlet()

        def init(self):
            self._masters = [Master.alloc().initWithName_(n) for n in ("Light", "Bold")]
            return self

        def masters(self):
            return self._masters

    return ControllerOwner.alloc().init()


def _observers(obj):
    return [entry[0] for entry in obj.__dict__.get("_kvo_observers", [])]


def test_table_when_selection_unbound_or_rebound_then_old_observers_removed():
    kit = _table_kit()
    owner = _controller_owner()
    instantiate(load_graph(FIXTURES / "Controller.xib"), owner, kit)
    table, controller = owner.table, owner.items
    table.unbind_("selectionIndexes")
    controller.setSelectionIndex_(1)
    assert table.selectedRow() != 1, "the unbound table ignores the controller"
    other = kit["NSArrayController"].alloc().initWithContent_([1, 2, 3])
    table.bind_toObject_withKeyPath_options_("content", other, "arrangedObjects", None)
    table.bind_toObject_withKeyPath_options_(
        "selectionIndexes", other, "selectionIndexes", None
    )
    table.tableColumns()[0].unbind_("value")
    assert table not in _observers(controller), "nothing observes the first controller"
    assert table.numberOfRows() == 3
    other.setSelectionIndex_(2)
    assert table.selectedRow() == 2
    kit["close"]()


# P2: array controllers are disposed on unload and environment close
def test_array_controller_when_environment_closed_then_source_unbound():
    kit = _table_kit()
    owner = _controller_owner()
    instantiate(load_graph(FIXTURES / "Controller.xib"), owner, kit)
    controller = owner.items
    assert controller in _observers(owner)
    controller.dispose()
    controller.dispose()  # idempotent
    assert controller not in _observers(owner) and controller._source is None
    owner2 = _controller_owner()
    instantiate(load_graph(FIXTURES / "Controller.xib"), owner2, kit)
    kit["close"]()
    assert owner2.items not in _observers(owner2), "environment close disposes it"


# P2: row property changes reach bound columns
def test_table_when_row_property_changes_then_bound_cell_updates():
    kit = _table_kit()
    owner = _controller_owner()
    instantiate(load_graph(FIXTURES / "Controller.xib"), owner, kit)
    light = owner.masters()[0]
    light.willChangeValueForKey_("name")
    light._name = "Thin"
    light.didChangeValueForKey_("name")
    assert owner.table._qt.item(0, 0).text() == "Thin"
    owner.items.removeObject_(light)
    assert owner.table not in _observers(light), "a removed row is no longer observed"
    kit["close"]()


# P2: text selectability reaches Qt
class FlagTextEdit(QPlainTextEdit):
    __slots__ = ("flags",)

    def __init__(self):
        super().__init__()
        self.flags = None

    def setTextInteractionFlags(self, flags):
        self.flags = int(flags)


def test_text_view_when_selectable_and_editable_change_then_interaction_flags_follow():
    qt = make_qt()
    qt.QtGui.QPlainTextEdit = FlagTextEdit
    qt.QtCore.Qt.NoTextInteraction, qt.QtCore.Qt.TextEditorInteraction = 0, 19
    kit = make_appkit_classes(qt, error_sink=print)
    view = kit["NSTextView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 40))
    assert view._qt.flags == 19, "editable and selectable"
    view.setEditable_(False)
    assert view._qt.flags == 3, "selectable by mouse and keyboard"
    view.setSelectable_(False)
    assert view._qt.flags == 0 and not view.isSelectable()
    view.setEditable_(True)
    assert view._qt.flags == 19 and view.isSelectable(), "editable implies selectable"
    kit["close"]()


# P2: split dividers after the first count the earlier handles
def test_split_when_second_divider_moved_then_preceding_handles_counted():
    from test_ui_nib_panes import _kit

    kit = _kit()
    split = kit["NSSplitView"].alloc().initWithFrame_(NSMakeRect(0, 0, 108, 50))
    split.setVertical_(True)
    split.setDividerStyle_(1)  # thick: 9-point dividers
    for _ in range(3):
        split.addSubview_(
            kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 30, 50))
        )
    split.setPosition_ofDividerAtIndex_(70, 1)
    assert split._qt.sizes() == [30, 31, 29], "pane 2 ends at 70 = 30 + 9 + 31"
    kit["close"]()


# --- Round 2 (reports/RR2-r031.md) ---


class _Row(NSObject):
    """A row object with observable ``name``, ``ready`` and ``master``."""

    def initWithName_(self, name):
        self._name, self._ready, self._master = name, True, None
        return self

    def name(self):
        return self._name

    def setName_(self, name):
        self._name = name

    def ready(self):
        return self._ready

    def setReady_(self, flag):
        self._ready = flag

    def master(self):
        return self._master

    def setMaster_(self, master):
        self._master = master


def _bound_table(kit, key_path, rows):
    table = kit["NSTableView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 60))
    column = kit["NSTableColumn"].alloc().initWithIdentifier_("c")
    table.addTableColumn_(column)
    controller = kit["NSArrayController"].alloc().initWithContent_(rows)
    column.bind_toObject_withKeyPath_options_("value", controller, key_path, None)
    return table, controller


def test_table_when_cell_value_setter_reloads_then_no_live_orphan_cells():
    kit = _table_kit()
    table = kit["NSTableView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 60))
    table.addTableColumn_(kit["NSTableColumn"].alloc().initWithIdentifier_("c"))
    made = []

    class Reloading(kit["NSTextField"]):
        def setObjectValue_(self, value):
            kit["NSTextField"].setObjectValue_(self, value)
            if len(made) == 1:
                table.reloadData()  # a value setter reaches user code

    class Source(NSObject):
        def numberOfRowsInTableView_(self, t):
            return 2

        def tableView_objectValueForTableColumn_row_(self, t, column, row):
            return f"row {row}"

        def tableView_viewForTableColumn_row_(self, t, column, row):
            view = Reloading.alloc().initWithFrame_(NSMakeRect(0, 0, 50, 20))
            made.append(view)
            return view

    source = Source.alloc().init()
    table.setDelegate_(source)
    table.setDataSource_(source)
    placed = list(table._cell_views.values())
    assert len(placed) == 2
    for view in made:
        if view not in placed:
            assert not _registered(view) and view._slots == [], "an orphan stays live"
    kit["close"]()


@pytest.mark.parametrize("count", [0, 2])
def test_combo_when_disposed_in_its_count_callback_then_nothing_more_runs(count):
    kit = make_appkit_classes(make_qt(), error_sink=print)
    combo = kit["NSComboBox"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 20))
    combo.setUsesDataSource_(True)
    calls = []
    combo._items = lambda values: calls.append(("items", values))

    class Source(NSObject):
        def numberOfItemsInComboBox_(self, box):
            box.dispose()
            return count

        def comboBox_objectValueForItemAtIndex_(self, box, index):
            calls.append(("value", index))
            return "x"

    combo.setDataSource_(Source.alloc().init())
    assert calls == [], "no item callback and no widget update after disposal"
    kit["close"]()


def _notify(obj, key, value):
    obj.willChangeValueForKey_(key)
    obj.__dict__[f"_{key}"] = value
    obj.didChangeValueForKey_(key)


def test_table_when_key_path_hops_change_then_cells_update_and_reobserve():
    kit = _table_kit()
    light = _Row.alloc().initWithName_("Light")
    row = _Row.alloc().initWithName_("row")
    row._master = light
    table, _controller = _bound_table(kit, "arrangedObjects.master.name", [row])
    assert table._qt.item(0, 0).text() == "Light"
    _notify(light, "name", "Thin")
    assert table._qt.item(0, 0).text() == "Thin", "the last hop is observed"
    bold = _Row.alloc().initWithName_("Bold")
    _notify(row, "master", bold)
    assert table._qt.item(0, 0).text() == "Bold", "an intermediate hop is observed"
    _notify(light, "name", "Gone")
    assert table._qt.item(0, 0).text() == "Bold", "the old master is no longer watched"
    assert table not in _observers(light) and not light.__dict__.get("_kvo_observers")
    _notify(bold, "name", "Black")
    assert table._qt.item(0, 0).text() == "Black"
    kit["close"]()


def test_table_when_control_binding_and_column_watch_the_same_key_then_both_work():
    kit = _table_kit()
    row = _Row.alloc().initWithName_("row")
    table, _controller = _bound_table(kit, "arrangedObjects.ready", [row])
    table.bind_toObject_withKeyPath_options_("enabled", row, "ready", None)
    assert table.isEnabled() and table._qt.item(0, 0).text() == "True"
    _notify(row, "ready", False)
    assert table._qt.item(0, 0).text() == "False"
    assert not table.isEnabled(), "the inherited enabled binding still hears it"
    table.unbind_("enabled")
    _notify(row, "ready", True)
    assert table._qt.item(0, 0).text() == "True" and not table.isEnabled()
    kit["close"]()


def test_text_view_when_editable_made_unselectable_then_no_interaction():
    qt = make_qt()
    qt.QtGui.QPlainTextEdit = FlagTextEdit
    qt.QtCore.Qt.NoTextInteraction, qt.QtCore.Qt.TextEditorInteraction = 0, 19
    kit = make_appkit_classes(qt, error_sink=print)
    view = kit["NSTextView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 40))
    view.setSelectable_(False)
    assert view._qt.flags == 0, "not selectable means no interaction at all"
    assert not view.isEditable() and not view.isSelectable()
    kit["close"]()


# --- Round 3 (reports/RR3-r031.md) ---


def test_table_when_observation_discovery_reloads_then_newer_observations_kept():
    """A getter called while the outer pass discovers its observations replaces
    the controller's content (which reloads): the outer pass must not install
    its stale observation set over the newer one."""
    kit = _table_kit()
    new = _Row.alloc().initWithName_("New")
    calls = None  # armed below, after setup

    class Tricky(_Row):
        def name(self):
            if calls is not None:
                calls.append(1)
                if len(calls) == 2:  # call 1: the cell value; call 2: discovery
                    controller.setContent_([new])
            return self._name

    tricky = Tricky.alloc().initWithName_("Old")
    table, controller = _bound_table(kit, "arrangedObjects.name", [])
    controller.setContent_([tricky])
    calls = []
    table.reloadData()
    assert len(calls) >= 2, "the replay reached observation discovery"
    assert table._qt.item(0, 0).text() == "New"
    assert not tricky.__dict__.get("_kvo_observers"), "the stale row is not observed"
    _notify(new, "name", "Newer")
    assert table._qt.item(0, 0).text() == "Newer", "the shown row is observed"
    kit["close"]()
