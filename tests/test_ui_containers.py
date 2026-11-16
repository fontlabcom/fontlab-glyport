# this_file: tests/test_ui_containers.py
"""vanilla Tabs and Sheet over PythonQt-shaped doubles."""

import pytest
from ui_doubles import LOG, make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.vanilla import make_vanilla_module


@pytest.fixture
def env():
    qt = make_qt()
    errors = []
    module = make_vanilla_module(qt, error_sink=lambda exc, s: errors.append((exc, s)))
    return module, qt, errors


def _geometry(widget):
    rect = widget.geometry
    return rect.x(), rect.y(), rect.width(), rect.height()


def test_tabs_when_built_then_pages_titles_and_children_laid_out(env):
    vanilla, _, _ = env
    w = vanilla.Window((400, 300))
    w.tabs = vanilla.Tabs((10, 10, -10, -10), ["One", "Two"])
    first = w.tabs[0]
    first.edit = vanilla.EditText((5, 5, -5, 22), "x")
    w.open()
    view = w.tabs.getNSView()
    assert [view.tabText(i) for i in range(view.count)] == ["One", "Two"]
    assert _geometry(view) == (10, 10, 380, 280)
    page = view.widget(0)
    assert _geometry(page) == (0, 0, 372, 250), "the tab widget sizes its pages"
    assert _geometry(first.edit.getNSView()) == (5, 5, 362, 22)
    assert first.edit.getNSView().parentWidget() is page


def test_tabs_when_window_resized_then_tab_children_relaid(env):
    vanilla, _, _ = env
    w = vanilla.Window((400, 300))
    w.tabs = vanilla.Tabs((0, 0, -0, -0), ["A"])
    w.tabs[0].box = vanilla.TextBox((0, 0, -0, 20), "t")
    w.open()
    w.setPosSize((500, 300))
    assert _geometry(w.tabs[0].box.getNSView())[2] == 500 - 8


def test_tabs_get_set_and_callback_fire_on_user_and_programmatic(env):
    vanilla, _, _ = env
    seen = []
    w = vanilla.Window((300, 200))
    w.tabs = vanilla.Tabs((0, 0, -0, -0), ["A", "B", "C"], callback=seen.append)
    w.open()
    assert w.tabs.get() == 0
    w.tabs.getNSView().user_select(2)
    assert w.tabs.get() == 2
    w.tabs.set(1)
    assert w.tabs.get() == 1
    assert seen == [w.tabs, w.tabs], "NSTabView delegates report set() too"


def test_tabs_when_index_out_of_range_then_index_error(env):
    vanilla, _, _ = env
    tabs = vanilla.Tabs((0, 0, 10, 10), ["A"])
    with pytest.raises(IndexError):
        tabs[1]
    with pytest.raises(IndexError):
        tabs.set(3)
    assert len(tabs) == 1


def test_tabs_when_show_tabs_false_then_bar_hidden(env):
    vanilla, _, _ = env
    tabs = vanilla.Tabs((0, 0, 10, 10), ["A"], showTabs=False)
    assert not tabs.getNSView().tabBar().isVisible()


def test_tabs_when_registered_then_graph_has_tab_nodes_and_children(env):
    vanilla, _, _ = env
    w = vanilla.Window((300, 200))
    tabs = vanilla.Tabs((0, 0, -0, -0), ["A", "B"], callback=lambda s: None)
    tabs[1].ok = vanilla.Button((0, 0, 50, 20), "OK", callback=lambda s: None)
    w.tabs = tabs
    nodes = w.graph.to_json()["nodes"]
    classes = [(n["source_class"], n["attribute_name"]) for n in nodes]
    assert classes == [
        ("vanilla.Window", None),
        ("vanilla.Tabs", "tabs"),
        ("vanilla.Tab", "0"),
        ("vanilla.Tab", "1"),
        ("vanilla.Button", "ok"),
    ]
    tab_b = nodes[3]
    assert (tab_b["parent_id"], tab_b["properties"]["title"]) == ("n2", "B")
    assert nodes[4]["parent_id"] == "n4"
    events = [(c["owner_id"], c["event"]) for c in w.graph.to_json()["connections"]]
    assert events == [("n2", "action"), ("n5", "action")]


def test_tabs_when_window_closed_then_tab_children_disconnected(env):
    vanilla, _, _ = env
    w = vanilla.Window((300, 200))
    w.tabs = vanilla.Tabs((0, 0, -0, -0), ["A"], callback=lambda s: None)
    w.tabs[0].ok = vanilla.Button((0, 0, 50, 20), "OK", callback=lambda s: None)
    w.open()
    button = w.tabs[0].ok.getNSView()
    w.close()
    assert ("disconnect", button, "clicked") in LOG
    assert ("disconnect", w.tabs.getNSView(), "currentChanged") in LOG


def test_tabs_when_deleted_then_children_detached(env):
    vanilla, _, _ = env
    w = vanilla.Window((300, 200))
    w.tabs = vanilla.Tabs((0, 0, -0, -0), ["A"])
    w.tabs[0].ok = vanilla.Button((0, 0, 50, 20), "OK")
    del w.tabs
    nodes = w.graph.to_json()["nodes"]
    assert all(n["properties"].get("detached") for n in nodes[1:])


def test_tabs_default_button_inside_tab_is_live(env):
    vanilla, qt, _ = env
    hits = []
    w = vanilla.Window((300, 200))
    w.tabs = vanilla.Tabs((0, 0, -0, -0), ["A"])
    w.tabs[0].ok = vanilla.Button((0, 0, 50, 20), "OK", callback=hits.append)
    w.open()
    w.setDefaultButton(w.tabs[0].ok)
    assert w.getNSView().user_key(qt.QtCore.Qt.Key_Return)
    assert hits == [w.tabs[0].ok]


def test_tabs_when_unknown_keyword_then_unsupported(env):
    vanilla, _, _ = env
    with pytest.raises(UnsupportedCapability):
        vanilla.Tabs((0, 0, 10, 10), ["A"], tabStyle="x")


def test_sheet_when_opened_then_window_modal_child_of_parent(env):
    vanilla, qt, _ = env
    parent = vanilla.Window((400, 300), "Parent")
    parent.open()
    sheet = vanilla.Sheet((200, 100), parent)
    sheet.ok = vanilla.Button((10, -30, -10, 20), "OK")
    sheet.open()
    view = sheet.getNSWindow()
    assert view.parentWidget() is parent.getNSWindow()
    assert view.windowFlags() == qt.QtCore.Qt.Sheet
    assert view.windowModality() == qt.QtCore.Qt.WindowModal
    assert _geometry(sheet.ok.getNSView()) == (10, 70, 180, 20)
    assert sheet.graph.to_json()["nodes"][0]["source_class"] == "vanilla.Sheet"


def test_sheet_when_parent_closes_then_sheet_closed_first(env):
    vanilla, _, _ = env
    parent = vanilla.Window((400, 300))
    parent.open()
    closed = []
    sheet = vanilla.Sheet((200, 100), parentWindow=parent)
    sheet.ok = vanilla.Button((0, 0, 50, 20), "OK", callback=lambda s: None)
    sheet.bind("close", closed.append)
    sheet.open()
    button = sheet.ok.getNSView()
    parent.close()
    assert closed == [sheet]
    assert not sheet.isVisible()
    disconnect = LOG.index(("disconnect", button, "clicked"))
    assert disconnect < LOG.index(("deleteLater", parent.getNSWindow()))


def test_sheet_when_parent_not_a_window_then_type_error(env):
    vanilla, _, _ = env
    with pytest.raises(TypeError):
        vanilla.Sheet((200, 100), object())


def test_sheet_when_closed_then_parent_forgets_it(env):
    vanilla, _, _ = env
    parent = vanilla.Window((400, 300))
    sheet = vanilla.Sheet((200, 100), parent)
    sheet.open()
    sheet.close()
    parent.close()
    assert LOG.count(("close", sheet.getNSWindow())) == 1


def test_sheet_when_parent_closes_before_sheet_opened_then_sheet_torn_down(env):
    vanilla, _, _ = env
    parent = vanilla.Window((400, 300))
    parent.open()
    sheet = vanilla.Sheet((200, 100), parent)
    sheet.ok = vanilla.Button((0, 0, 50, 20), "OK", callback=lambda s: None)
    button = sheet.ok.getNSView()
    parent.close()
    disconnect = LOG.index(("disconnect", button, "clicked"))
    assert disconnect < LOG.index(("deleteLater", parent.getNSWindow()))
    assert button.clicked.slots == [] and not sheet.isVisible()
    sheet.open()
    assert not sheet.isVisible(), "a torn-down sheet cannot reopen"


def test_sheet_when_parent_already_closed_then_value_error(env):
    vanilla, _, _ = env
    parent = vanilla.Window((400, 300))
    parent.close()
    with pytest.raises(ValueError):
        vanilla.Sheet((200, 100), parent)
