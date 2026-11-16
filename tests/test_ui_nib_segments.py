# this_file: tests/test_ui_nib_segments.py
"""NSSegmentedControl and NSSearchField from XIB/NIB (R031 corpus). Fixture:
self-authored ``Segments.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import QLineEdit, QPushButton, make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Segments.xib", FIXTURES / "Segments.nib"


class CheckButton(QPushButton):
    """QPushButton's checkable state (QAbstractButton)."""

    __slots__ = ("_checkable", "_checked")

    def __init__(self):
        super().__init__()
        self._checkable = self._checked = False

    def setCheckable(self, flag):
        self._checkable = bool(flag)

    def setChecked(self, flag):
        self._checked = bool(flag)

    def isChecked(self):
        return self._checked

    def user_click(self):
        if self._checkable:
            self._checked = not self._checked
        self.clicked.emit(self._checked)


class ClearLineEdit(QLineEdit):
    __slots__ = ("clear_button",)

    def __init__(self):
        super().__init__()
        self.clear_button = False

    def setClearButtonEnabled(self, flag):
        self.clear_button = bool(flag)


def _kit():
    qt = make_qt()
    qt.QtGui.QPushButton, qt.QtGui.QLineEdit = CheckButton, ClearLineEdit
    return make_appkit_classes(qt, error_sink=print)


def _load(source):
    objc = make_objc_module({})

    class SegmentsOwner(NSObject):
        dialog = objc.IBOutlet()
        tabs = objc.IBOutlet()
        styles = objc.IBOutlet()
        search = objc.IBOutlet()

        def init(self):
            self.calls = []
            return self

        @objc.IBAction
        def pickTab_(self, sender):
            self.calls.append(("tab", sender.selectedSegment()))

        @objc.IBAction
        def searched_(self, sender):
            self.calls.append(("search", sender.stringValue()))

    kit, owner = _kit(), SegmentsOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_segments_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = {
        n["source_id"]: n["properties"] for n in graph_from_xib(XIB).to_json()["nodes"]
    }
    tabs = nodes["seg"]
    assert tabs["trackingMode"] == 0 and [s["label"] for s in tabs["segments"]] == [
        "Left",
        "Right",
    ]
    assert tabs["segments"][1] == {
        "label": "Right",
        "width": 100.0,
        "selected": True,
        "tag": 1,
        "image": None,
    }
    assert nodes["seg2"]["trackingMode"] == 1
    assert nodes["sf"]["placeholder"] == "Search Groups"
    assert nodes["sf"]["sendsSearchStringImmediately"]


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_segments_and_search_then_selection_and_actions(source):
    kit, owner, instance = _load(source)
    tabs, styles, search = owner.tabs, owner.styles, owner.search
    assert isinstance(tabs, kit["NSSegmentedControl"]) and tabs.segmentCount() == 2
    assert tabs.selectedSegment() == 1 and tabs.labelForSegment_(0) == "Left"
    buttons = [segment._qt for segment in tabs._segments]
    assert buttons[1].isChecked() and not buttons[0].isChecked()
    rect = buttons[1].geometry
    assert (rect.x(), rect.width()) == (100, 100)
    buttons[0].user_click()
    assert owner.calls == [("tab", 0)] and not buttons[1].isChecked()
    buttons[0].user_click()  # select-one: clicking the selected segment keeps it
    assert tabs.selectedSegment() == 0 and buttons[0].isChecked()
    assert [styles.isSelectedForSegment_(i) for i in range(3)] == [True, False, True]
    styles._segments[1]._qt.user_click()
    assert [styles.isSelectedForSegment_(i) for i in range(3)] == [True, True, True]
    assert isinstance(search, kit["NSSearchField"]) and search._qt.clear_button
    assert search.placeholderString() == "Search Groups"
    search._qt.user_type("ab")
    assert owner.calls[-1] == ("search", "ab"), "sends the string immediately"
    assert instance.diagnostics == []
    kit["close"]()
    assert all(b.clicked.slots == [] for b in buttons)


def test_segmented_control_when_built_in_code_then_segments_and_selection():
    kit = _kit()
    control = kit["NSSegmentedControl"].alloc().initWithFrame_(NSMakeRect(0, 0, 90, 24))
    control.setSegmentCount_(3)
    for index, label in enumerate("xyz"):
        control.setLabel_forSegment_(label, index)
    control.setSelectedSegment_(2)
    assert control.selectedSegment() == 2 and control.labelForSegment_(1) == "y"
    assert control.widthForSegment_(0) == 30.0, "equal widths across the frame"
    control.setSegmentCount_(2)
    assert control.segmentCount() == 2 and control.selectedSegment() == -1
    kit["close"]()


def test_segment_when_named_image_then_found_in_resources_or_reported():
    from fontlab_glyport.ui.graph import UIGraph

    class IconCheckButton(CheckButton):
        __slots__ = ("icon",)

        def setIcon(self, icon):
            self.icon = icon

    class Image(NSObject):
        def initWithContentsOfFile_(self, path):
            self.name = Path(path).name
            return self

        def icon(self):
            return ("icon", self.name)

    data = graph_from_xib(XIB).to_json()
    tabs = next(n for n in data["nodes"] if n["source_id"] == "seg")
    tabs["properties"]["segments"][0]["image"] = "Dot"
    tabs["properties"]["segments"][1]["image"] = "Missing"
    qt = make_qt()
    qt.QtGui.QPushButton, qt.QtGui.QLineEdit = IconCheckButton, ClearLineEdit
    kit = make_appkit_classes(qt, error_sink=print)
    kit["NSImage"] = Image
    owner = NSObject.alloc().init()
    instance = instantiate(UIGraph.from_json(data), owner, kit, resources=[FIXTURES])
    control = owner.tabs
    assert control.imageForSegment_(0).name == "Dot.png"
    assert control._segments[0]._qt.icon == ("icon", "Dot.png")
    assert instance.diagnostics == ["image Missing not found"]
    kit["close"]()


def test_segmented_control_when_scripted_like_corpus_plugins_then_style_and_tooltips():
    from fontlab_glyport.ui import cocoa_views

    kit = _kit()
    control = (
        kit["NSSegmentedControl"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 22))
    )
    control.setSegmentCount_(2)
    control.setSegmentStyle_(cocoa_views.NSSegmentStyleRounded)
    control.setTrackingMode_(cocoa_views.NSSegmentSwitchTrackingSelectOne)
    control.setToolTip_forSegment_("Dots", 0)
    control.setSelectedSegmentBezelColor_(object())
    assert control.segmentStyle() == 1 and control.toolTipForSegment_(0) == "Dots"
    assert control._segments[0]._qt.toolTip == "Dots"
    assert cocoa_views.NSSplitViewDividerStyleThin == 2
    kit["close"]()
