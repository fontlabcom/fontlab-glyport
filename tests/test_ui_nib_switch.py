# this_file: tests/test_ui_nib_switch.py
"""NSSwitch, Glyphs' GSMouseOverButton and button images from XIB/NIB (R031
corpus). Fixture: self-authored ``Switch.xib``, its ibtool NIB and ``Dot.png``."""

from pathlib import Path

import pytest
from test_ui_cocoa_button_image import IconButton
from test_ui_nib import _canonical
from ui_doubles import QCheckBox, make_qt

from fontlab_glyport.ui.cocoa import NSObject, NSSize
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Switch.xib", FIXTURES / "Switch.nib"
KEY = "com.glyport.demo.switch"


class Image(NSObject):
    def initWithContentsOfFile_(self, path):
        self.path = path
        return self

    def size(self):
        return NSSize(16, 8)

    def icon(self):
        return ("icon", Path(self.path).name)


def _load(source, defaults):
    objc = make_objc_module({})

    class SwitchOwner(NSObject):
        dialog = objc.IBOutlet()
        toggle = objc.IBOutlet()
        hover = objc.IBOutlet()
        pictured = objc.IBOutlet()

        def init(self):
            self.calls = []
            return self

        @objc.IBAction
        def toggled_(self, sender):
            self.calls.append(("toggled", sender.state()))

        @objc.IBAction
        def hovered_(self, sender):
            self.calls.append(("hovered", None))

    qt = make_qt()
    qt.QtGui.QPushButton = IconButton
    qt.QtGui.QIcon = lambda: "no icon"
    kit = make_appkit_classes(qt, error_sink=print, defaults=defaults)
    kit["NSImage"] = Image
    owner = SwitchOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit, resources=[FIXTURES])
    return kit, owner, instance


def test_switch_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = {n["source_id"]: n for n in graph_from_xib(XIB).to_json()["nodes"]}
    assert nodes["sw"]["source_class"] == "NSSwitch"
    assert nodes["sw"]["properties"]["state"] == 1
    hover = nodes["mo"]["properties"]
    assert hover["customClass"] == "GSMouseOverButton" and hover["image"] == "Dot"
    assert hover["imagePosition"] == 1 and not hover["bordered"]
    pictured = nodes["pb"]["properties"]
    assert pictured["imagePosition"] == 2 and pictured["bordered"]


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_switch_and_image_buttons_then_state_binding_and_images(
    source,
):
    defaults = {KEY: 0}
    kit, owner, instance = _load(source, defaults)
    toggle = owner.toggle
    assert isinstance(toggle, kit["NSSwitch"]) and isinstance(toggle._qt, QCheckBox)
    assert toggle.state() == 0, "the bound default overrides the NIB's on state"
    toggle._qt.user_click()
    assert owner.calls == [("toggled", 1)] and defaults[KEY] == 1
    hover = owner.hover
    assert isinstance(hover, kit["GSMouseOverButton"]) and not hover.isBordered()
    assert hover._qt.icon == ("icon", "Dot.png") and hover._qt.text == ""
    assert hover._qt.flat and hover.toolTip() == "Hover me"
    hover._qt.user_click()
    assert owner.calls[-1] == ("hovered", None)
    pictured = owner.pictured
    assert pictured.imagePosition() == 2 and pictured._qt.text == "Update"
    assert pictured.isBordered() and not pictured._qt.flat
    assert instance.diagnostics == []
    kit["close"]()
