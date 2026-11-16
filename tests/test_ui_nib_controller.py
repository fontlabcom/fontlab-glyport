# this_file: tests/test_ui_nib_controller.py
"""NSArrayController and table bindings from XIB/NIB (R031 corpus:
ExportUFO-Plus binds a table column to arrangedObjects.name). Fixture:
self-authored ``Controller.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from test_ui_nib_table import _layout_free
from ui_doubles import make_qt
from ui_doubles_table import install

from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import NSNotFound, make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Controller.xib", FIXTURES / "Controller.nib"


class Master(NSObject):
    def initWithName_(self, name):
        self._name = name
        return self

    def name(self):
        return self._name


def _load(source):
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

        def setMasters_(self, masters):
            self._masters = masters

    kit = make_appkit_classes(install(make_qt()), error_sink=print)
    owner = ControllerOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_controller_when_xib_and_nib_then_equal_graphs_with_column_nodes():
    xib = _layout_free(graph_from_xib(XIB).to_json())
    nib = _layout_free(graph_from_nib(NIB).to_json())
    assert _canonical(UIGraph.from_json(nib)) == _canonical(UIGraph.from_json(xib))
    data = graph_from_xib(XIB).to_json()
    classes = [n["source_class"] for n in data["nodes"]]
    assert "NSArrayController" in classes and "NSTableColumn" in classes
    ids = {n["node_id"]: n["source_class"] for n in data["nodes"]}
    bindings = sorted(
        (ids[c["owner_id"]], c["selector"], c["argument"])
        for c in data["connections"]
        if c["event"] == "binding"
    )
    assert bindings == [
        ("NSArrayController", "contentArray", "masters"),
        ("NSTableColumn", "value", "arrangedObjects.name"),
        ("NSTableView", "selectionIndexes", "selectionIndexes"),
    ]


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_bound_table_then_rows_follow_the_controller(source):
    kit, owner, instance = _load(source)
    controller, table = owner.items, owner.table
    assert isinstance(controller, kit["NSArrayController"])
    assert [m.name() for m in controller.arrangedObjects()] == ["Light", "Bold"]
    assert table.numberOfRows() == 2 and table._qt.item(1, 0).text() == "Bold"
    controller.addObject_(Master.alloc().initWithName_("Black"))
    assert table.numberOfRows() == 3 and table._qt.item(2, 0).text() == "Black"
    assert list(controller.selectionIndexes()) == [2], "inserted objects are selected"
    assert table.selectedRow() == 2, "the table follows the controller's selection"
    table._qt.user_click(0)
    assert (
        controller.selectionIndex() == 0
        and controller.selectedObjects()[0].name() == "Light"
    )
    owner.willChangeValueForKey_("masters")
    owner._masters = [Master.alloc().initWithName_("Thin")]
    owner.didChangeValueForKey_("masters")
    assert table.numberOfRows() == 1 and table._qt.item(0, 0).text() == "Thin"
    assert instance.diagnostics == []
    kit["close"]()


def test_array_controller_when_used_in_code_then_content_and_selection():
    kit = make_appkit_classes(install(make_qt()), error_sink=print)
    controller = kit["NSArrayController"].alloc().initWithContent_([1, 2, 3])
    controller.setSelectionIndex_(1)
    assert controller.selectedObjects() == [2]
    controller.removeObject_(2)
    assert controller.arrangedObjects() == [1, 3] and controller.selectionIndex() == 1
    controller.setContent_([])
    assert (
        controller.selectedObjects() == [] and controller.selectionIndex() == NSNotFound
    )
    kit["close"]()
