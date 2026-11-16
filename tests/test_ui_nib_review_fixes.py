# this_file: tests/test_ui_nib_review_fixes.py
"""Regression tests for the R031 review findings (reports/R-r031.md)."""

import struct
from pathlib import Path

import pytest
from test_ui_nib_image import FakeImage, PixLabel, Pixmap
from test_ui_nib_scroll import _kit as _scroll_kit
from ui_doubles import LOG, make_qt
from ui_doubles_table import install

from fontlab_glyport.ui import nib_graph
from fontlab_glyport.ui.cocoa import NSMakeRect, NSMakeSize, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.graph import UIGraph
from fontlab_glyport.ui.nib_archive import Archived, NibFormatError
from fontlab_glyport.ui.nib_graph import _decimal, graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph

FIXTURES = Path(__file__).parent / "fixtures" / "nib"


# P1: scroll documents are torn down by dispose
def test_dispose_when_scroll_view_then_document_tree_torn_down_and_unregistered():
    kit = _scroll_kit()
    owner = NSObject.alloc().init()
    instantiate(load_graph(FIXTURES / "Scroll.xib"), owner, kit)
    env = owner.dialog._env
    button = owner.deepButton
    assert button._qt.clicked.slots, "the button is wired"
    owner.dialog.dispose()
    assert button._qt.clicked.slots == [], "the document's controls were disconnected"
    assert owner.document not in env.views and button not in env.views
    kit["close"]()


# P1: windows can be disposed (plugin unload)
def test_dispose_when_window_then_window_and_content_released_without_delegate():
    kit = _scroll_kit()
    events = []

    class Owner(NSObject):
        def windowWillClose_(self, note):
            events.append("will")

    owner = Owner.alloc().init()
    instantiate(load_graph(FIXTURES / "Window.xib"), owner, kit)
    window, field = owner.window, owner.nameField
    env = window._env
    window.makeKeyAndOrderFront_(None)
    window.dispose()
    window.dispose()  # idempotent
    assert events == [] and not window.isVisible()
    assert window not in env.views and field not in env.views
    deleted = [entry[1] for entry in LOG if entry[0] == "deleteLater"]
    assert deleted.count(window._qt) == 1 and field._qt._deleted
    kit["close"]()


# P2: images are fitted in logical pixels, display DPR kept separate
class RetinaLabel(PixLabel):
    __slots__ = ()

    def devicePixelRatioF(self):
        return 2.0


class DprPixmap(Pixmap):
    def scaled(self, width, height, aspect, transform):
        result = DprPixmap(self.scale, (width, height, aspect, transform))
        return result


class DprImage(FakeImage):
    def pixmap(self, scale=1.0):
        return DprPixmap(scale)


def test_image_view_when_fitted_then_logical_size_matches_the_frame():
    qt = make_qt()
    qt.QtGui.QLabel = RetinaLabel
    qt.QtCore.Qt.AlignCenter, qt.QtCore.Qt.IgnoreAspectRatio = 0x84, "ignore"
    qt.QtCore.Qt.SmoothTransformation = "smooth"
    kit = make_appkit_classes(qt, error_sink=print)
    view = kit["NSImageView"].alloc().initWithFrame_(NSMakeRect(0, 0, 64, 40))
    view.setImageScaling_(3)
    view.setImage_(DprImage.alloc().initWithContentsOfFile_("Dot.png"))
    pixmap = view._qt.pixmap
    assert (pixmap.scale, pixmap.dpr) == (8.0, 2.0), "16x8 x4 logical, rendered at 2x"
    view.setImageScaling_(1)
    assert view._qt.pixmap.size == (128, 80, "ignore", "smooth")
    assert view._qt.pixmap.dpr == 2.0
    kit["close"]()


# P2: a non-resizable window resizes when the script asks
def test_window_when_fixed_size_and_content_size_set_then_widget_resizes():
    kit = _scroll_kit()
    owner = NSObject.alloc().init()
    instantiate(load_graph(FIXTURES / "Window.xib"), owner, kit)
    panel = owner.panel
    panel.setContentSize_(NSMakeSize(300, 160))
    assert panel._qt._min == panel._qt._max == (300, 160)
    rect = panel._qt.geometry
    assert (rect.width(), rect.height()) == (300, 160)
    assert tuple(panel.frame().size) == (300, 160)
    assert tuple(panel.contentView().frame().size) == (300, 160)
    kit["close"]()


# P2: stack view distributions
def _stack(kit, distribution, orientation=0):
    stack = kit["NSStackView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 20))
    stack.setOrientation_(orientation)
    stack.setSpacing_(10)
    stack.setDistribution_(distribution)
    views = [
        kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, w, 20)) for w in (10, 30)
    ]
    for view in views:
        stack.addArrangedSubview_(view)
    return [tuple(v.frame()[0]) + tuple(v.frame()[1]) for v in views]


@pytest.mark.parametrize(
    ("distribution", "frames"),
    [
        (-1, [(0, 0, 10, 20), (20, 0, 30, 20)]),  # gravity areas: sizes kept
        (0, [(0, 0, 10, 20), (20, 0, 30, 20)]),  # fill: sizes kept (no priorities)
        (1, [(0, 0, 45, 20), (55, 0, 45, 20)]),  # fill equally
        (2, [(0, 0, 22.5, 20), (32.5, 0, 67.5, 20)]),  # fill proportionally
        (3, [(0, 0, 10, 20), (70, 0, 30, 20)]),  # equal spacing
        (4, [(0, 0, 10, 20), (70, 0, 30, 20)]),  # equal centering, two views
    ],
)
def test_stack_when_distribution_then_layout_follows(distribution, frames):
    kit = make_appkit_classes(make_qt(), error_sink=print)
    assert _stack(kit, distribution) == frames
    kit["close"]()


# P2: decimal limits are bounded
@pytest.mark.parametrize(
    "fields",
    [
        {"NS.length": 9, "NS.mantissa": b"\x01" * 18},
        {"NS.length": 2, "NS.mantissa": b"\x01" * 8192},
        {"NS.length": 1, "NS.mantissa": b"\x01\x00", "NS.exponent": 400},
        {"NS.length": -1, "NS.mantissa": b"\x01\x00"},
    ],
)
def test_decimal_when_malformed_then_nib_format_error(fields):
    with pytest.raises(NibFormatError):
        _decimal(
            Archived("NSDecimalNumberPlaceholder", {"NS.mantissa.bo": 1, **fields})
        )


def test_decimal_when_eight_words_then_decoded():
    data = struct.pack("<8H", 1, 0, 0, 0, 0, 0, 0, 1)
    value = _decimal(
        Archived("NSDecimalNumberPlaceholder", {"NS.length": 8, "NS.mantissa": data})
    )
    assert value == float(1 + (1 << 112))


# P2: matrix cells count against the node budget
def test_matrix_when_cells_exceed_the_node_budget_then_rejected(monkeypatch):
    monkeypatch.setattr(nib_graph, "MAX_NODES", 8)
    with pytest.raises(NibFormatError):
        graph_from_xib(FIXTURES / "Matrix.xib")  # 6 placeholders/views + 6 cells
    with pytest.raises(NibFormatError):
        graph_from_nib(FIXTURES / "Matrix.nib")


def test_matrix_when_cells_do_not_match_rows_and_columns_then_rejected():
    data = graph_from_xib(FIXTURES / "Matrix.xib").to_json()
    radios = next(n for n in data["nodes"] if n["source_id"] == "rad")
    radios["properties"]["rows"] = 40
    kit = make_appkit_classes(make_qt(), error_sink=print)
    with pytest.raises(NibFormatError):
        instantiate(UIGraph.from_json(data), NSObject.alloc().init(), kit)
    kit["close"]()


# P2: unbinding enabledN drops its contribution
def test_enabled_bindings_when_one_unbound_then_the_rest_decide():
    defaults = {"a": True, "b": False}
    kit = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    controller = kit["NSUserDefaultsController"].sharedUserDefaultsController()
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 50, 20))
    field.bind_toObject_withKeyPath_options_("enabled", controller, "values.a", None)
    field.bind_toObject_withKeyPath_options_("enabled2", controller, "values.b", None)
    assert not field.isEnabled()
    field.unbind_("enabled2")
    assert field.isEnabled(), "only enabled is left, and it is true"
    controller.setValue_forKeyPath_(True, "values.a")
    assert field.isEnabled()
    kit["close"]()


# P2: bound paths are paths, not URLs
def test_path_control_when_bound_path_has_url_characters_then_kept():
    path = "/tmp/My#Fonts%20?"
    defaults = {"p": path}
    kit = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    controller = kit["NSUserDefaultsController"].sharedUserDefaultsController()
    control = kit["NSPathControl"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 20))
    control.bind_toObject_withKeyPath_options_("value", controller, "values.p", None)
    assert control.URL().path() == path
    control.setURL_("file:///Users/someone/My%20Fonts/")
    assert control.URL().path() == "/Users/someone/My Fonts", "URL strings decode"
    kit["close"]()


def test_table_when_disposed_with_cell_views_then_cells_released():
    kit = make_appkit_classes(install(make_qt()), error_sink=print)
    from test_ui_nib_table import _owner_class

    owner = _owner_class().alloc().init()
    instantiate(load_graph(FIXTURES / "Table.xib"), owner, kit)
    cell = owner.table.viewAtColumn_row_makeIfNecessary_(0, 0, False)
    env = cell._env
    owner.dialog.dispose()
    assert cell not in env.views and cell.textField()._qt.textEdited.slots == []
    kit["close"]()


@pytest.mark.parametrize("name", ["Unload.xib", "Unload.nib"])
def test_plugin_unload_when_nib_has_window_and_scroll_view_then_all_released(
    name, tmp_path
):
    from plugin_doubles import FakeHost, Layer

    from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
    from fontlab_glyport.plugins.loader import load_plugin

    resources = tmp_path / "Demo.glyphsPlugin" / "Contents" / "Resources"
    resources.mkdir(parents=True)
    source = FIXTURES / name
    (resources / name).write_bytes(source.read_bytes())
    appkit = make_appkit_classes(install(make_qt()), error_sink=print)
    errors = []
    env = PluginEnv(FakeHost([Layer("A", [])]), appkit, lambda e, s: errors.append(e))
    plugins = make_plugins_module(env)
    events = []

    class Demo(plugins.GeneralPlugin):
        def settings(self):
            self.loadNib("Unload", str(resources / "plugin.py"))

        def windowWillClose_(self, note):
            events.append("will")

        def numberOfRowsInTableView_(self, table):
            return 2

        def tableView_objectValueForTableColumn_row_(self, table, column, row):
            return f"row {row}"

        def tableView_viewForTableColumn_row_(self, table, column, row):
            return table.makeViewWithIdentifier_owner_("Name", self)

    handle = load_plugin(Demo, env)
    assert handle.status == "loaded", handle.error
    plugin = handle.plugin
    window, button, dialog = plugin.window, plugin.deepButton, plugin.dialog
    view_env = window._env
    table, split, pane_button = plugin.table, plugin.split, plugin.paneButton
    cell = table.viewAtColumn_row_makeIfNecessary_(0, 1, False)
    assert (
        cell.textField().stringValue() == "row 1" and len(split.arrangedSubviews()) == 2
    )
    window.makeKeyAndOrderFront_(None)
    handle.unload()
    assert handle.status == "unloaded" and errors == [] and events == []
    assert not window.isVisible() and window._qt._deleted and dialog._qt._deleted
    assert button._qt.clicked.slots == [] and button not in view_env.views
    assert window not in view_env.views and plugin.document not in view_env.views
    for view in (table, split, pane_button, cell, cell.textField()):
        assert view not in view_env.views, f"{type(view).__name__} still registered"
    assert pane_button._qt.clicked.slots == []
    assert cell.textField()._qt.editingFinished.slots == []
    assert table._qt.itemSelectionChanged.slots == []
    appkit["close"]()
