# this_file: tests/test_ui_nib_combo.py
"""NSComboBox from XIB/NIB (R031 corpus). Fixture: self-authored ``Combo.xib``
and its ibtool NIB: one combo with items, a title and an action, one fed by
a data source."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import QComboBox, make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Combo.xib", FIXTURES / "Combo.nib"


class VisibleCombo(QComboBox):
    __slots__ = ("visible_items",)

    def __init__(self):
        super().__init__()
        self.visible_items = 10

    def setMaxVisibleItems(self, count):
        self.visible_items = count


def _kit():
    qt = make_qt()
    qt.QtGui.QComboBox = VisibleCombo
    return make_appkit_classes(qt, error_sink=print)


def _load(source):
    objc = make_objc_module({})

    class ComboOwner(NSObject):
        dialog = objc.IBOutlet()
        combo = objc.IBOutlet()
        sourced = objc.IBOutlet()

        def init(self):
            self.calls, self.names = [], ["Regular", "Bold"]
            return self

        @objc.IBAction
        def anchorChosen_(self, sender):
            self.calls.append(sender.stringValue())

        def numberOfItemsInComboBox_(self, combo):
            return len(self.names)

        def comboBox_objectValueForItemAtIndex_(self, combo, index):
            return self.names[index]

    kit, owner = _kit(), ComboOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_combo_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    combo = next(n for n in nodes if n["source_id"] == "cb")["properties"]
    assert combo["items"] == ["top", "bottom", "center"] and combo["title"] == "top"
    assert not combo["completes"] and combo["numberOfVisibleItems"] == 7
    sourced = next(n for n in nodes if n["source_id"] == "cb2")["properties"]
    assert sourced["usesDataSource"] and sourced["completes"]


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_combo_boxes_then_items_text_action_and_data_source(source):
    kit, owner, instance = _load(source)
    combo = owner.combo
    assert isinstance(combo, kit["NSComboBox"])
    assert combo.objectValues() == ["top", "bottom", "center"]
    assert combo.stringValue() == "top" and combo.numberOfVisibleItems() == 7
    assert combo._qt.visible_items == 7 and combo._qt._completer is None
    combo._qt.user_choose(2)
    assert owner.calls == ["center"] and combo.indexOfSelectedItem() == 2
    combo._qt.user_type("left")
    combo._qt.user_return()
    assert owner.calls == ["center", "left"] and combo.stringValue() == "left"
    sourced = owner.sourced
    assert sourced.usesDataSource() and sourced.dataSource() is owner
    assert sourced.objectValues() == ["Regular", "Bold"]
    owner.names.append("Black")
    sourced.reloadData()
    assert sourced.numberOfItems() == 3 and sourced.stringValue() == ""
    assert instance.diagnostics == []
    kit["close"]()


def test_combo_when_built_in_code_then_items_and_selection():
    kit = _kit()
    combo = kit["NSComboBox"].alloc().initWithFrame_(NSMakeRect(0, 0, 120, 24))
    combo.addItemsWithObjectValues_(["a", "b"])
    assert combo.stringValue() == "", "adding items keeps the text"
    combo.addItemWithObjectValue_("c")
    combo.selectItemWithObjectValue_("b")
    assert combo.indexOfSelectedItem() == 1 and combo.objectValueOfSelectedItem() == "b"
    assert combo.stringValue() == "b" and combo.itemObjectValueAtIndex_(2) == "c"
    assert combo.indexOfItemWithObjectValue_("zzz") == -1
    combo.setStringValue_("free text")
    assert combo.stringValue() == "free text"
    combo.removeAllItems()
    assert combo.numberOfItems() == 0
    kit["close"]()
