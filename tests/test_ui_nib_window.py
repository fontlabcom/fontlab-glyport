# this_file: tests/test_ui_nib_window.py
"""NIB/XIB window templates as Qt-backed NSWindow/NSPanel (R031 corpus: the most
common blocker). Fixture: self-authored ``Window.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import LOG, make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.cocoa import NSMakeSize, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Window.xib", FIXTURES / "Window.nib"


def _owner_class():
    objc = make_objc_module({})

    class WindowOwner(NSObject):
        window = objc.IBOutlet()
        panel = objc.IBOutlet()
        nameField = objc.IBOutlet()

        def init(self):
            self.events, self.allow_close = [], True
            return self

        def windowShouldClose_(self, window):
            self.events.append("should")
            return self.allow_close

        def windowWillClose_(self, notification):
            self.events.append(("will", notification.object()))

    return WindowOwner


def _load(source):
    kit = make_appkit_classes(make_qt(), error_sink=print)
    owner = _owner_class().alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_window_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))


def test_window_when_parsed_then_window_nodes_and_content_views():
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    windows = {n["source_class"]: n for n in nodes if "styleMask" in n["properties"]}
    window, panel = windows["NSWindow"], windows["NSPanel"]
    assert window["properties"]["title"] == "Demo Window"
    assert window["properties"]["styleMask"] == 11, "titled|closable|resizable"
    assert window["properties"]["contentRect"] == [200.0, 300.0, 240.0, 120.0]
    assert panel["properties"]["styleMask"] == 19, "titled|closable|utility"
    contents = [n for n in nodes if n["properties"].get("contentView")]
    assert {n["parent_id"] for n in contents} == {window["node_id"], panel["node_id"]}


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_window_then_hidden_window_with_content_and_delegate(source):
    kit, owner, instance = _load(source)
    window = owner.window
    assert isinstance(window, kit["NSWindow"]) and not window.isVisible()
    assert window.title() == "Demo Window" and window.delegate() is owner
    assert owner.nameField.superview() is window.contentView()
    assert owner.nameField.stringValue() == "hello"
    assert window.contentView()._qt.parentWidget() is window._qt
    content_class = type(window.contentView()._qt)
    assert type(window._qt) is not content_class, "views keep their own Qt subclass"
    rect = window._qt.geometry
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (
        200,
        25 + 875 - 300 - 120,
        240,
        120,
    ), "bottom-left origin"
    assert isinstance(owner.panel, kit["NSPanel"])
    assert owner.panel._qt.windowFlags() == "Tool"
    assert owner.panel._qt._min == owner.panel._qt._max == (150, 80), "not resizable"
    assert window in instance.top_level and owner.panel in instance.top_level
    assert instance.diagnostics == []
    kit["close"]()


def test_window_when_resized_then_content_view_and_subviews_follow():
    kit, owner, _instance = _load(XIB)
    owner.window.setContentSize_(NSMakeSize(340, 120))
    assert owner.window.contentView().frame().size.width == 340
    assert owner.nameField.frame().size.width == 300, "width-sizable field grew"
    kit["close"]()


def test_window_when_ordered_front_and_closed_then_delegate_asked_and_told():
    kit, owner, _instance = _load(NIB)
    window = owner.window
    window.makeKeyAndOrderFront_(None)
    assert window.isVisible()
    owner.allow_close = False
    window.performClose_(None)
    assert window.isVisible() and owner.events == ["should"]
    owner.allow_close = True
    window.performClose_(None)
    assert not window.isVisible()
    assert owner.events == ["should", "should", ("will", window)]
    kit["close"]()


def test_window_when_environment_closed_then_no_delegate_and_one_delete():
    kit, owner, _instance = _load(XIB)
    window, content = owner.window, owner.window.contentView()
    kit["close"]()
    deleted = [entry[1] for entry in LOG if entry[0] == "deleteLater"]
    assert window._qt in deleted and content._qt not in deleted
    assert window._qt._deleted and content._qt._deleted, "content goes with the window"
    assert owner.events == []


def test_window_when_unknown_custom_class_then_blocked_unless_provided():
    data = graph_from_xib(XIB).to_json()
    window = next(n for n in data["nodes"] if n["source_class"] == "NSWindow")
    window["properties"]["customClass"] = "ShelfWindow"
    kit = make_appkit_classes(make_qt(), error_sink=print)
    with pytest.raises(UnsupportedCapability) as info:
        instantiate(UIGraph.from_json(data), _owner_class().alloc().init(), kit)
    assert info.value.capability == "nib.ShelfWindow"
    shelf = type("ShelfWindow", (kit["NSWindow"],), {})
    owner = _owner_class().alloc().init()
    instantiate(UIGraph.from_json(data), owner, kit, classes={"ShelfWindow": shelf})
    assert type(owner.window) is shelf
    kit["close"]()


class _CloseEvent:
    def __init__(self):
        self.ignored = False

    def ignore(self):
        self.ignored = True


def test_window_when_title_bar_close_then_delegate_can_veto():
    kit, owner, _instance = _load(XIB)
    window = owner.window
    window.makeKeyAndOrderFront_(None)
    owner.allow_close = False
    event = _CloseEvent()
    window._qt.closeEvent(event)
    assert event.ignored and owner.events == ["should"]
    owner.allow_close = True
    event = _CloseEvent()
    window._qt.closeEvent(event)
    assert not event.ignored
    assert owner.events == ["should", "should", ("will", window)]
    owner.allow_close = False
    window.close()  # a script close does not ask
    assert owner.events[-1] == ("will", window) and owner.events.count("should") == 2
    kit["close"]()
