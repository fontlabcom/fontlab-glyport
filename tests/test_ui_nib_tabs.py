# this_file: tests/test_ui_nib_tabs.py
"""Tab views, number formatters, progress bars and Auto Layout constraints in
XIB/NIB graphs (R049 xib/nib/palette-nib targets). Fixture: the self-authored
``TabsDialog.xib`` and its ``ibtool`` NIBArchive build ``TabsDialog.nib``."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "TabsDialog.xib", FIXTURES / "TabsDialog.nib"


def _nodes(graph):
    return graph.to_json()["nodes"]


def test_xib_and_nib_when_tab_view_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_tab_view_when_parsed_then_pages_with_labels_and_their_controls(source):
    nodes = _nodes(load_graph(source))
    by_id = {n["node_id"]: n for n in nodes}
    (tabs,) = [n for n in nodes if n["source_class"] == "NSTabView"]
    pages = [n for n in nodes if n["parent_id"] == tabs["node_id"]]
    assert [
        (p["properties"]["tabLabel"], p["properties"]["tabIdentifier"]) for p in pages
    ] == [
        ("first", "one"),
        ("second", "two"),
    ]
    inside = {n["source_class"] for n in nodes if by_id.get(n["parent_id"]) in pages}
    assert inside == {"NSTextField", "NSButton", "NSPopUpButton", "NSProgressIndicator"}
    field, note = [n["properties"] for n in nodes if n["source_class"] == "NSTextField"]
    assert field["formatter"] == {"minimum": 0.0, "maximum": 20.0}
    assert note["title"] == "A long note\non two lines" and "formatter" not in note
    (bar,) = [
        n["properties"] for n in nodes if n["source_class"] == "NSProgressIndicator"
    ]
    assert (bar["minValue"], bar["maxValue"], bar["value"], bar["indeterminate"]) == (
        0.0,
        100.0,
        25.0,
        False,
    )


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_constraints_when_parsed_then_one_connection_each(source):
    data = load_graph(source).to_json()
    names = {}
    for n in data["nodes"]:
        props = n["properties"]
        names[n["node_id"]] = (
            props.get("tabLabel") or props.get("title") or n["source_class"]
        )
    found = sorted(
        (names[c["owner_id"]], c["selector"], names[c["target_id"]], c["argument"])
        for c in data["connections"]
        if c["event"] == "constraint"
    )
    assert len(found) == 11
    assert ("Deep", "trailing lessThanOrEqual leading", "3", "1 standard 1000") in found
    assert ("3", "leading equal leading", "first", "1 8 1000") in found
    assert ("3", "width equal notAnAttribute", "3", "1 60 1000") in found
    assert ("Deep", "leading greaterThanOrEqual leading", "first", "1 8 1000") in found
    assert (
        "second",
        "trailing equal trailing",
        "NSProgressIndicator",
        "1 8 1000",
    ) in found
    assert (
        "NSPopUpButton",
        "centerX equal centerX",
        "NSProgressIndicator",
        "0.5 4 1000",
    ) in found
    assert ("NSView", "bottom equal bottom", "NSTabView", "1 0 750") in found


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_tab_view_then_qt_tabs_outlets_and_constraint_report(source):
    objc = make_objc_module({})

    class TabsOwner(NSObject):
        dialog = objc.IBOutlet()
        amountField = objc.IBOutlet()
        deepCheckbox = objc.IBOutlet()
        sourcePopup = objc.IBOutlet()
        progressBar = objc.IBOutlet()

        def init(self):
            self.calls = []
            return self

        @objc.IBAction
        def toggleDeep_(self, sender):
            self.calls.append(("toggleDeep:", sender.state()))

        @objc.IBAction
        def chooseSource_(self, sender):
            self.calls.append(("chooseSource:", sender.indexOfSelectedItem()))

    kit = make_appkit_classes(make_qt(), error_sink=print)
    owner = TabsOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    (tabs,) = owner.dialog.subviews()
    assert type(tabs).__name__ == "NSTabView" and tabs.numberOfTabViewItems() == 2
    assert [i.label() for i in tabs.tabViewItems()] == ["first", "second"]
    assert tabs._qt.tabText(1) == "second" and tabs._qt.count == 2
    assert owner.amountField.superview() is tabs.tabViewItemAtIndex_(0).view()
    assert owner.amountField.formatter().maximum() == 20.0
    assert owner.progressBar.doubleValue() == 25.0
    tabs.selectTabViewItemAtIndex_(1)
    assert tabs.indexOfTabViewItem_(tabs.selectedTabViewItem()) == 1
    assert tabs._qt.currentIndex == 1
    owner.deepCheckbox._qt.user_click()
    owner.sourcePopup._qt.user_choose(0)
    assert owner.calls == [("toggleDeep:", 1), ("chooseSource:", 0)]
    assert any("11 Auto Layout constraints" in d for d in instance.diagnostics)
    kit["close"]()


def test_untranslated_xib_when_presentation_elements_then_counted():
    from fontlab_glyport.ui.nib_graph import untranslated_xib

    report = untranslated_xib(XIB)
    assert report == {"behavior": 2, "color": 4, "font": 5}
