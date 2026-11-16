# this_file: tests/test_ui_nib.py
"""XIB/NIB decoding into one UIGraph and instantiation as Cocoa views (R031).

Fixtures are self-authored: ``DemoDialog.xib`` and its ``ibtool`` builds
(``DemoDialog.nib``: NIBArchive; ``DemoDialog-legacy.nib``: a bundle with a
keyed-archive ``keyedobjects.nib`` and a NIBArchive ``keyedobjects-101300.nib``).
"""

from pathlib import Path

import pytest
from ui_doubles import QCheckBox, make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_archive import NibFormatError, read_nib
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import find_nib, instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB = FIXTURES / "DemoDialog.xib"
NIBS = [
    FIXTURES / "DemoDialog.nib",
    FIXTURES / "DemoDialog-legacy.nib",
    FIXTURES / "DemoDialog-legacy.nib" / "keyedobjects-101300.nib",
]


def _canonical(graph: UIGraph):
    """Order- and id-free view of a graph: nodes and connections by content."""
    data = graph.to_json()
    keys = {}
    for node in data["nodes"]:
        props = node["properties"]
        key = (node["source_class"], props.get("role"), props.get("customClass"))
        keys[node["node_id"]] = key + (tuple(props.get("frame") or ()),)
    nodes = sorted(
        (
            (
                keys[n["node_id"]],
                keys.get(n["parent_id"]),
                sorted(n["properties"].items()),
            )
            for n in data["nodes"]
        ),
        key=repr,
    )
    connections = sorted(
        (
            (
                keys[c["owner_id"]],
                keys[c["target_id"]],
                c["event"],
                c["selector"],
                c["argument"],
            )
            for c in data["connections"]
        ),
        key=repr,
    )
    return nodes, connections


def _props(graph, cls, custom=None):
    return next(
        n["properties"]
        for n in graph.to_json()["nodes"]
        if n["source_class"] == cls and n["properties"].get("customClass") == custom
    )


def test_xib_when_parsed_then_nodes_properties_and_connections():
    graph = graph_from_xib(XIB)
    owner = _props(graph, "NSCustomObject")
    assert owner == {"role": "owner", "className": "DemoFilter"}
    field = _props(graph, "NSTextField", "GSSteppingTextField")
    assert field["frame"] == [104.0, 110.0, 116.0, 22.0]
    assert field["autoresizingMask"] == 2 | 8 and field["editable"] and field["bezeled"]
    assert (field["title"], field["toolTip"]) == ("12", "Width in units")
    popup = _props(graph, "NSPopUpButton")
    assert (popup["items"], popup["selectedIndex"]) == (["Fill", "Outline", "Both"], 1)
    slider = _props(graph, "NSSlider")
    assert (slider["minValue"], slider["maxValue"], slider["value"]) == (-45, 45, 15)
    check = next(
        n["properties"]
        for n in graph.to_json()["nodes"]
        if n["properties"].get("buttonType") == 3
    )
    assert (check["title"], check["state"]) == ("Keep original", 1)
    events = {(c["event"], c["selector"]) for c in graph.to_json()["connections"]}
    assert ("outlet", "widthField") in events and ("action", "apply:") in events
    assert ("binding", "value") in events


@pytest.mark.parametrize(
    "nib", NIBS, ids=["nibarchive", "bundle-keyed", "bundle-101300"]
)
def test_nib_when_decoded_then_graph_equals_xib_graph(nib):
    assert _canonical(graph_from_nib(nib)) == _canonical(graph_from_xib(XIB))


def test_nib_when_not_a_nib_then_format_error(tmp_path):
    bad = tmp_path / "x.nib"
    bad.write_bytes(b"garbage")
    with pytest.raises(NibFormatError):
        read_nib(bad)
    empty = tmp_path / "empty.nib"
    empty.mkdir()
    with pytest.raises(NibFormatError):
        read_nib(empty)


def test_find_nib_when_both_then_compiled_nib_preferred(tmp_path):
    (tmp_path / "Base.lproj").mkdir()
    (tmp_path / "Base.lproj" / "IBdialog.xib").write_text("<document/>")
    assert find_nib("IBdialog", tmp_path).name == "IBdialog.xib"
    (tmp_path / "IBdialog.nib").write_bytes(b"NIBArchive")
    assert find_nib("IBdialog", tmp_path).name == "IBdialog.nib"
    assert find_nib("Missing", tmp_path) is None


def _owner_class():
    objc = make_objc_module({})

    class DemoFilter(NSObject):
        dialog = objc.IBOutlet()
        widthField = objc.IBOutlet()
        keepCheckbox = objc.IBOutlet()
        angleSlider = objc.IBOutlet()
        modePopup = objc.IBOutlet()
        titleLabel = objc.IBOutlet()

        def init(self):
            self.calls = []
            return self

        @objc.IBAction
        def setWidth_(self, sender):
            self.calls.append(("setWidth:", sender.floatValue()))

        @objc.IBAction
        def toggleKeep_(self, sender):
            self.calls.append(("toggleKeep:", sender.state()))

        @objc.IBAction
        def setAngle_(self, sender):
            self.calls.append(("setAngle:", sender.floatValue()))

        @objc.IBAction
        def setMode_(self, sender):
            self.calls.append(("setMode:", sender.indexOfSelectedItem()))

        @objc.IBAction
        def apply_(self, sender):
            self.calls.append(("apply:", sender.title()))

    return DemoFilter


@pytest.mark.parametrize("source", [XIB, NIBS[0]], ids=["xib", "nib"])
def test_instantiate_when_owner_given_then_outlets_actions_and_binding(source):
    defaults = {"com.glyport.demo.width": 30}
    kit = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    owner = _owner_class().alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    assert type(owner.dialog).__name__ == "GSPaletteView"
    assert instance.top_level[0] is owner.dialog, "the view tree is retained"
    assert owner.widthField.superview() is owner.dialog
    assert owner.widthField.stringValue() == "30", "the binding pulled the default"
    rect = owner.widthField._qt.geometry
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (104, 18, 116, 22)
    assert (
        isinstance(owner.keepCheckbox._qt, QCheckBox)
        and owner.keepCheckbox.state() == 1
    )
    assert owner.angleSlider.floatValue() == 15
    assert owner.modePopup.titleOfSelectedItem() == "Outline"
    assert not owner.titleLabel.isEditable()
    owner.widthField._qt.user_type("44")
    owner.widthField._qt.user_finish()
    owner.keepCheckbox._qt.user_click()
    owner.modePopup._qt.user_choose(2)
    assert owner.calls == [("setWidth:", 44.0), ("toggleKeep:", 0), ("setMode:", 2)]
    assert defaults["com.glyport.demo.width"] == "44"
    assert instance.diagnostics == []


def test_instantiate_when_unknown_view_class_then_blocked():
    graph = graph_from_xib(XIB)
    data = graph.to_json()
    data["nodes"][-2]["source_class"] = "xib:tableView"
    kit = make_appkit_classes(make_qt(), error_sink=print)
    with pytest.raises(UnsupportedCapability) as info:
        instantiate(UIGraph.from_json(data), NSObject.new(), kit)
    assert info.value.capability == "nib.xib:tableView"


def test_instantiate_when_unknown_custom_class_then_blocked_unless_provided():
    graph = graph_from_xib(XIB)
    data = graph.to_json()
    label = next(n for n in data["nodes"] if n["properties"].get("title") == "Width")
    label["properties"]["customClass"] = "FancyLabel"
    kit = make_appkit_classes(make_qt(), error_sink=print)
    with pytest.raises(UnsupportedCapability) as info:
        instantiate(UIGraph.from_json(data), _owner_class().new(), kit)
    assert info.value.capability == "nib.FancyLabel"

    class FancyLabel(kit["NSTextField"]):
        pass

    owner = _owner_class().new()
    instantiate(UIGraph.from_json(data), owner, kit, classes={"FancyLabel": FancyLabel})
    assert isinstance(owner.titleLabel, FancyLabel)


def test_instantiate_when_action_to_first_responder_then_diagnostic():
    graph = graph_from_xib(XIB)
    data = graph.to_json()
    responder = next(
        n for n in data["nodes"] if n["properties"].get("role") == "firstResponder"
    )
    action = next(c for c in data["connections"] if c["selector"] == "apply:")
    action["target_id"] = responder["node_id"]
    kit = make_appkit_classes(make_qt(), error_sink=print)
    instance = instantiate(UIGraph.from_json(data), _owner_class().new(), kit)
    assert instance.diagnostics == ["action apply: to First Responder: unwired"]
