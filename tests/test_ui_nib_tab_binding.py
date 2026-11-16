# this_file: tests/test_ui_nib_tab_binding.py
"""An NSTabView ``selectedIndex`` binding to the user defaults (R031 corpus:
ItalicExtremes). Fixture: self-authored ``TabBinding.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.cocoa import NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "TabBinding.xib", FIXTURES / "TabBinding.nib"
KEY = "com.glyport.demo.tab"


def _load(source, defaults):
    objc = make_objc_module({})

    class TabOwner(NSObject):
        dialog = objc.IBOutlet()
        tabs = objc.IBOutlet()

    kit = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    owner = TabOwner.alloc().init()
    instantiate(load_graph(source), owner, kit)
    return kit, owner.tabs


def test_tab_binding_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_tab_binding_when_loaded_then_selection_follows_defaults_both_ways(source):
    defaults = {KEY: 1}
    kit, tabs = _load(source, defaults)
    assert tabs._qt.currentIndex == 1, "the bound default selected the tab"
    tabs._qt.user_select(0)
    assert defaults[KEY] == 0, "a user tab change wrote the default"
    controller = kit["NSUserDefaultsController"].sharedUserDefaultsController()
    controller.setValue_forKeyPath_(1, f"values.{KEY}")
    assert tabs._qt.currentIndex == 1, "a default change selected the tab"
    kit["close"]()
    assert tabs._qt.currentChanged.slots == [], "close disconnected the tab signal"
    controller.setValue_forKeyPath_(0, f"values.{KEY}")
    assert tabs._qt.currentIndex == 1, "close removed the observer"


def test_tab_binding_when_default_unset_then_selection_kept_and_written_on_change():
    defaults = {}
    _kit, tabs = _load(XIB, defaults)
    assert tabs._qt.currentIndex == 0
    tabs.selectTabViewItemAtIndex_(1)
    assert defaults[KEY] == 1


def test_tab_binding_when_unknown_binding_then_unsupported():
    kit = make_appkit_classes(make_qt(), error_sink=print)
    tabs = kit["NSTabView"].alloc().init()
    controller = kit["NSUserDefaultsController"].sharedUserDefaultsController()
    with pytest.raises(UnsupportedCapability):
        tabs.bind_toObject_withKeyPath_options_("value", controller, "values.x", None)
