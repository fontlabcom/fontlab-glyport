# this_file: tests/test_ui_nib_table.py
"""NSTableView from XIB/NIB (R031 corpus). Fixture: self-authored ``Table.xib``
and its ibtool NIB: a view-based table whose prototype cell view is its own
graph (instantiated per row by makeViewWithIdentifier_owner_), and a
cell-based table fed by a data source."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt
from ui_doubles_table import install

from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Table.xib", FIXTURES / "Table.nib"
ROWS = [("alpha", 1), ("beta", 22), ("gamma", 333)]


def _layout_free(graph_json):
    """Drop what ibtool lays out again: frames and column widths."""
    for node in graph_json["nodes"]:
        props = node["properties"]
        props.pop("frame", None)
        for column in props.get("columns") or []:
            column.pop("width")
        for identifier, proto in (props.get("prototypes") or {}).items():
            props["prototypes"][identifier] = _canonical(
                UIGraph.from_json(_layout_free(proto))
            )
    return graph_json


def _owner_class():
    objc = make_objc_module({})

    class TableOwner(NSObject):
        dialog = objc.IBOutlet()
        table = objc.IBOutlet()
        plainTable = objc.IBOutlet()

        def init(self):
            self.rows, self.events = [list(r) for r in ROWS], []
            return self

        def numberOfRowsInTableView_(self, table):
            return len(self.rows)

        def tableView_objectValueForTableColumn_row_(self, table, column, row):
            index = 0 if column.identifier() in ("Name", "Only") else 1
            return self.rows[row][index]

        def tableView_setObjectValue_forTableColumn_row_(
            self, table, value, column, row
        ):
            self.events.append(("set", value, column.identifier(), row))

        def tableView_viewForTableColumn_row_(self, table, column, row):
            if table is not self.table:
                return None
            return table.makeViewWithIdentifier_owner_("Name", self)

        def tableViewSelectionDidChange_(self, notification):
            self.events.append(("selection", notification.object().selectedRow()))

        @objc.IBAction
        def renameItem_(self, sender):
            self.events.append(("rename", sender.stringValue()))

    return TableOwner


def _load(source):
    kit = make_appkit_classes(install(make_qt()), error_sink=print)
    owner = _owner_class().alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_table_when_xib_and_nib_then_equal_graphs_up_to_ibtool_layout():
    xib = _layout_free(graph_from_xib(XIB).to_json())
    nib = _layout_free(graph_from_nib(NIB).to_json())
    assert _canonical(UIGraph.from_json(nib)) == _canonical(UIGraph.from_json(xib))
    table = next(n for n in xib["nodes"] if n["source_id"] == "tv")["properties"]
    assert [c["identifier"] for c in table["columns"]] == ["Name", "Size"]
    assert [c["title"] for c in table["columns"]] == ["Name", "Size"]
    assert table["headerVisible"] and not table["allowsMultipleSelection"]
    assert table["rowHeight"] == 24.0 and list(table["prototypes"]) == ["Name"]
    plain = next(n for n in xib["nodes"] if n["source_id"] == "tv2")["properties"]
    assert not plain["headerVisible"] and plain["allowsMultipleSelection"]
    assert plain["columns"][0]["editable"] is False and "prototypes" not in plain


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_view_based_table_then_prototype_cells_per_row(source):
    kit, owner, instance = _load(source)
    table = owner.table
    assert isinstance(table, kit["NSTableView"]) and table.dataSource() is owner
    assert table.numberOfRows() == 3, "setting the data source loaded the rows"
    assert [c.identifier() for c in table.tableColumns()] == ["Name", "Size"]
    assert table._qt._labels == ["Name", "Size"] and table._qt._header.visible
    cell = table.viewAtColumn_row_makeIfNecessary_(0, 1, False)
    assert isinstance(cell, kit["NSTableCellView"])
    assert cell.objectValue() == "beta"
    assert cell.textField().stringValue() == "beta", "bound to objectValue"
    assert table._qt.cellWidget(1, 0) is cell._qt
    cell.textField()._qt.user_type("delta")
    cell.textField()._qt.user_finish()
    assert ("rename", "delta") in owner.events, (
        "the prototype's action reached the owner"
    )
    table._qt.user_click(2)
    assert table.selectedRow() == 2 and ("selection", 2) in owner.events
    old_text = cell.textField()._qt
    owner.rows.pop()
    table.reloadData()
    assert table.numberOfRows() == 2 and old_text._deleted
    assert table.selectedRow() == -1, "the selected row went away"
    assert instance.diagnostics == []
    kit["close"]()


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_cell_based_table_then_items_selection_and_edits(source):
    kit, owner, _instance = _load(source)
    plain = owner.plainTable
    assert plain.numberOfRows() == 3 and not plain._qt._header.visible
    assert plain._qt.item(1, 0).text() == "beta"
    assert not plain._qt.item(1, 0).flags() & 2, "column not editable"
    plain.tableColumns()[0].setEditable_(True)
    plain.reloadData()
    assert plain._qt.item(1, 0).flags() & 2
    plain._qt.user_edit(1, 0, "BETA")
    assert owner.events[-1] == ("set", "BETA", "Only", 1)
    plain.selectRowIndexes_byExtendingSelection_(
        kit["NSIndexSet"].indexSetWithIndex_(0), False
    )
    plain.selectRowIndexes_byExtendingSelection_(
        kit["NSIndexSet"].indexSetWithIndex_(2), True
    )
    assert (
        list(plain.selectedRowIndexes()) == [0, 2] and plain.numberOfSelectedRows() == 2
    )
    plain.deselectAll_(None)
    assert plain.selectedRow() == -1
    kit["close"]()


def test_table_when_double_clicked_then_double_action_sent():
    kit, owner, _instance = _load(NIB)
    calls = []
    owner.opened_ = lambda sender: calls.append(sender.clickedRow())
    table = owner.plainTable
    table.setTarget_(owner)
    table.setDoubleAction_("opened:")
    table._qt.user_double_click(1)
    assert calls == [1]
    kit["close"]()
