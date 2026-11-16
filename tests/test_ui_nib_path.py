# this_file: tests/test_ui_nib_path.py
"""NSPathControl from XIB/NIB (R031 corpus: export-folder fields bound to the
defaults). Fixture: self-authored ``Path.xib`` and its ibtool NIB."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Path.xib", FIXTURES / "Path.nib"
PATH, ON, ON2 = "com.glyport.demo.path", "com.glyport.demo.on", "com.glyport.demo.on2"


def _load(source, defaults):
    objc = make_objc_module({})

    class PathOwner(NSObject):
        dialog = objc.IBOutlet()
        folder = objc.IBOutlet()
        shown = objc.IBOutlet()

        def init(self):
            self.calls = []
            return self

        @objc.IBAction
        def openDoc_(self, sender):
            self.calls.append(sender.URL().path())

    kit = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    owner = PathOwner.alloc().init()
    instance = instantiate(load_graph(source), owner, kit)
    return kit, owner, instance


def test_path_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    folder = next(n for n in nodes if n["source_id"] == "pc")["properties"]
    assert folder["url"] == "file://localhost/Applications/"
    assert folder["editable"] and folder["allowedTypes"] == ["public.folder"]
    shown = next(n for n in nodes if n["source_id"] == "ro")["properties"]
    assert not shown["editable"] and "allowedTypes" not in shown


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_path_controls_then_url_bindings_and_action(source):
    defaults = {PATH: "/tmp/export", ON: True, ON2: False}
    kit, owner, instance = _load(source, defaults)
    folder, shown = owner.folder, owner.shown
    assert isinstance(folder, kit["NSPathControl"])
    assert folder.URL().path() == "/tmp/export", "the bound default replaced the URL"
    assert folder._qt.text == "/tmp/export" and not folder._qt.isReadOnly()
    assert not folder.isEnabled(), "enabled and enabled2 are combined (AND)"
    controller = kit["NSUserDefaultsController"].sharedUserDefaultsController()
    controller.setValue_forKeyPath_(True, f"values.{ON2}")
    assert folder.isEnabled()
    folder._qt.user_type("/Users/someone/Out")
    folder._qt.user_finish()
    assert owner.calls == ["/Users/someone/Out"]
    assert defaults[PATH] == "/Users/someone/Out"
    folder._qt.user_finish()  # focus loss without an edit sends nothing
    assert len(owner.calls) == 1
    assert shown.URL().path() == "/Library/Fonts"
    assert shown.URL().absoluteString() == "file:///Library/Fonts/"
    assert shown._qt.isReadOnly() and not shown.isEditable()
    assert instance.diagnostics == []
    kit["close"]()


def test_path_control_when_url_set_in_code_then_text_follows():
    kit = make_appkit_classes(make_qt(), error_sink=print)
    control = kit["NSPathControl"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 20))
    assert control.URL() is None and control._qt.text == ""
    control.setURL_("file:///Users/someone/My%20Fonts/")
    assert control.URL().path() == "/Users/someone/My Fonts"
    assert control.URL().lastPathComponent() == "My Fonts"
    control.setURL_(control.URL())
    assert control.stringValue() == "/Users/someone/My Fonts"
    control.setURL_(None)
    assert control.URL() is None
    kit["close"]()
