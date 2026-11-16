# this_file: tests/test_ui_vanilla.py
"""vanilla core controls build Qt widgets and a UI graph through injected Qt."""

import gc
import weakref

import pytest
from ui_doubles import LOG, QPushButton, make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.ui import vanilla as vanilla_impl
from fontlab_glyport.ui.graph import Connection, Frame
from fontlab_glyport.ui.vanilla import (
    SLIDER_STEPS,
    make_vanilla_module,
    vanilla_provider,
)

EXPORTS = {
    "Window",
    "FloatingWindow",
    "Group",
    "TextBox",
    "EditText",
    "Button",
    "CheckBox",
    "CheckBoxListCell",
    "PopUpButton",
    "Slider",
    "HorizontalLine",
    "VerticalLine",
    "RadioGroup",
    "RadioButton",
    "ComboBox",
    "TextEditor",
    "SquareButton",
    "VanillaBaseObject",
    "ColorWell",
    "SegmentedButton",
    "ActionButton",
    "HelpButton",
    "ProgressBar",
    "ProgressSpinner",
    "Box",
    "List",
    "Tabs",
    "Sheet",
    "Popover",
    "Drawer",
    "ScrollView",
    "VerticalStackView",
    "ImageView",
}


@pytest.fixture(autouse=True)
def _fresh_default_settings():
    vanilla_impl._DEFAULT_SETTINGS.clear()
    yield
    vanilla_impl._DEFAULT_SETTINGS.clear()


@pytest.fixture
def env():
    qt = make_qt()
    errors = []
    module = make_vanilla_module(qt, error_sink=lambda exc, s: errors.append((exc, s)))
    return module, qt, errors


def _geometry(control):
    rect = control.getNSView().geometry
    return rect.x(), rect.y(), rect.width(), rect.height()


def test_module_when_made_then_exports_exactly_core_names(env):
    vanilla = env[0]
    public = {n for n in vars(vanilla) if not n.startswith("_")}
    assert public == EXPORTS
    assert set(vanilla.__all__) == EXPORTS


def test_module_when_unknown_class_then_unsupported_capability(env):
    vanilla = env[0]
    with pytest.raises(UnsupportedCapability) as caught:
        vanilla.LevelIndicator  # noqa: B018
    assert caught.value.capability == "vanilla.LevelIndicator"
    with pytest.raises(AttributeError):
        vanilla.__wrapped__  # noqa: B018


@pytest.mark.parametrize(
    ("factory", "keyword"),
    [
        (lambda v: v.Button((0, 0, 10, 10), "OK", bezelStyle=1), "bezelStyle"),
        (lambda v: v.EditText((0, 0, 10, 10), "x", formatter=None), "formatter"),
        (
            lambda v: v.Window((100, 100), fullSizeContentView=True),
            "fullSizeContentView",
        ),
        (lambda v: v.Slider((0, 0, 10, 10), notAVanillaOption=3), "notAVanillaOption"),
    ],
)
def test_control_when_unsupported_keyword_then_unsupported_capability(
    env, factory, keyword
):
    with pytest.raises(UnsupportedCapability) as caught:
        factory(env[0])
    assert caught.value.capability.endswith("." + keyword)
    assert keyword in str(caught.value)


def test_window_when_controls_assigned_then_parented_and_graph_recorded(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200), "Tool", minSize=(200, 100), maxSize=(600, 400))
    ok = vanilla.Button((10, -30, -10, 20), "OK", sizeStyle="small")
    w.ok = ok
    assert w.ok is ok
    window_view = w.getNSView()
    assert ok.getNSView().parentWidget() is window_view
    assert w.getTitle() == "Tool"
    assert (window_view._min, window_view._max) == ((200, 100), (600, 400))
    nodes = w.graph.to_json()["nodes"]
    assert [(n["source_class"], n["attribute_name"]) for n in nodes] == [
        ("vanilla.Window", None),
        ("vanilla.Button", "ok"),
    ]
    assert nodes[1]["parent_id"] == nodes[0]["node_id"]
    assert nodes[1]["frame"] == Frame(10, -30, -10, 20).to_json()
    assert nodes[1]["properties"] == {"title": "OK", "sizeStyle": "small"}
    assert nodes[0]["properties"]["title"] == "Tool"


def test_layout_when_window_resized_then_children_follow_resolve_frame(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.ok = vanilla.Button((10, -30, -10, 20), "OK")
    w.label = vanilla.TextBox((5, 5, "auto", "auto"), "hi")
    assert _geometry(w.ok) == (10, 170, 280, 20)
    assert _geometry(w.label) == (5, 5, 80, 22)  # sizeHint of the double
    w.setPosSize((50, 60, 400, 300))
    assert _geometry(w.ok) == (10, 270, 380, 20)
    assert w.getPosSize() == (50, 60, 400, 300)
    w.getNSView().resize(500, 250)  # host-driven resize event
    assert _geometry(w.ok) == (10, 220, 480, 20)


def test_group_when_nested_then_children_lay_out_inside_group(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    group = vanilla.Group((10, 10, -10, -10))
    group.line = vanilla.HorizontalLine((0, 0, 0, 1))
    w.group = group
    group.check = vanilla.CheckBox((5, -25, -5, 20), "Flag")
    assert group.check.getNSView().parentWidget() is group.getNSView()
    assert _geometry(group) == (10, 10, 280, 180)
    assert _geometry(group.line) == (0, 0, 280, 1)
    assert _geometry(group.check) == (5, 155, 270, 20)
    nodes = w.graph.to_json()["nodes"]
    assert [(n["source_class"], n["parent_id"]) for n in nodes] == [
        ("vanilla.Window", None),
        ("vanilla.Group", "n1"),
        ("vanilla.HorizontalLine", "n2"),
        ("vanilla.CheckBox", "n2"),
    ]
    w.setPosSize((400, 300))
    assert _geometry(group.check) == (5, 255, 370, 20)


def test_floating_window_when_created_then_tool_flag(env):
    vanilla, qt, _ = env
    panel = vanilla.FloatingWindow((10, 20, 200, 100), "Panel")
    assert panel.getNSView().windowFlags() == qt.QtCore.Qt.Tool
    assert panel.graph.to_json()["nodes"][0]["source_class"] == "vanilla.FloatingWindow"
    assert panel.getPosSize() == (10, 20, 200, 100)


def test_values_when_get_set_then_round_trip_for_every_control(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.t = vanilla.TextBox((0, 0, 10, 10), "a")
    w.e = vanilla.EditText((0, 0, 10, 10), "b", placeholder="type", readOnly=True)
    w.b = vanilla.Button((0, 0, 10, 10), "Go")
    w.c = vanilla.CheckBox((0, 0, 10, 10), "C", value=True)
    w.p = vanilla.PopUpButton((0, 0, 10, 10), ["x", "y", "z"])
    w.s = vanilla.Slider((0, 0, 10, 10), minValue=-1.5, maxValue=2.5, value=0.25)
    assert (w.t.get(), w.e.get(), w.c.get(), w.p.get()) == ("a", "b", True, 0)
    w.t.set("A")
    w.e.set("B")
    w.c.set(False)
    w.p.set(2)
    w.b.setTitle("Stop")
    assert (w.t.get(), w.e.get(), w.c.get(), w.p.get()) == ("A", "B", False, 2)
    assert w.b.getTitle() == "Stop"
    assert w.e.getNSView()._placeholder == "type" and w.e.getNSView()._read_only
    assert w.p.getItems() == ["x", "y", "z"]
    w.p.setItems(["only"])
    assert (w.p.getItems(), w.p.get()) == (["only"], 0)
    step = 4.0 / SLIDER_STEPS
    assert abs(w.s.get() - 0.25) <= step
    for value in (-1.5, 2.5, 1.0 / 3.0, 0.123456789):
        w.s.set(value)
        assert abs(w.s.get() - value) <= step
        assert isinstance(w.s.get(), float)


def test_slider_when_range_empty_then_value_error(env):
    with pytest.raises(ValueError, match="maxValue"):
        env[0].Slider((0, 0, 10, 10), minValue=5, maxValue=5)


def test_callbacks_when_user_acts_then_sender_is_vanilla_control(env):
    vanilla = env[0]
    seen = []
    w = vanilla.Window((300, 200))
    w.b = vanilla.Button((0, 0, 10, 10), "Go", callback=seen.append)
    w.c = vanilla.CheckBox((0, 0, 10, 10), "C", callback=seen.append)
    w.e = vanilla.EditText((0, 0, 10, 10), callback=seen.append)
    w.f = vanilla.EditText((0, 0, 10, 10), callback=seen.append, continuous=False)
    w.p = vanilla.PopUpButton((0, 0, 10, 10), ["x", "y"], callback=seen.append)
    w.s = vanilla.Slider((0, 0, 10, 10), callback=seen.append, continuous=False)
    w.b.getNSView().user_click()
    w.c.getNSView().user_click()
    w.e.getNSView().user_type("hey")
    w.f.getNSView().user_type("ignored until finished")
    w.f.getNSView().user_finish()
    w.p.getNSView().user_choose(1)  # emits both Qt 5.15 overloads
    w.s.getNSView().user_drag(10)
    assert seen == [w.b, w.c, w.e, w.f, w.p, w.s]
    assert (w.c.get(), w.e.get(), w.p.get()) == (True, "hey", 1)
    assert w.s.getNSView()._tracking is False


def test_set_when_programmatic_then_callbacks_do_not_fire(env):
    vanilla = env[0]
    seen = []
    w = vanilla.Window((300, 200))
    w.s = vanilla.Slider((0, 0, 10, 10), callback=seen.append)
    w.p = vanilla.PopUpButton((0, 0, 10, 10), ["x", "y"], callback=seen.append)
    w.s.set(75)
    w.p.set(1)
    assert seen == []


def test_callback_when_raises_then_error_sink_gets_it_and_ui_stays_usable(env):
    vanilla, _, errors = env
    w = vanilla.Window((300, 200))

    def boom(sender):
        raise RuntimeError("boom")

    w.b = vanilla.Button((0, 0, 10, 10), "Go", callback=boom)
    w.b.getNSView().user_click()
    w.b.getNSView().user_click()
    assert [(str(e), s) for e, s in errors] == [("boom", w.b), ("boom", w.b)]
    w.b.setTitle("Still alive")
    assert w.b.getTitle() == "Still alive"


def test_graph_when_callbacks_given_then_connections_recorded(env):
    vanilla = env[0]

    def okCallback(sender):
        pass

    w = vanilla.Window((300, 200))
    group = vanilla.Group((0, 0, 0, 0))
    group.b = vanilla.Button((0, 0, 10, 10), "Go", callback=okCallback)
    w.g = group
    w.c = vanilla.CheckBox((0, 0, 10, 10), "C")
    assert w.graph.to_json()["connections"] == [
        vars(Connection("n3", "n1", "action", "okCallback", None))
    ]


def test_controls_when_enable_show_and_pos_size_then_widget_updated(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.b = vanilla.Button((0, 0, 50, 20), "Go")
    w.open()
    view = w.b.getNSView()
    w.b.enable(False)
    assert not view.isEnabled()
    w.b.show(False)
    assert not view.isVisible()
    w.b.show(True)
    assert view.isVisible()
    w.b.setPosSize((5, 6, 70, 30))
    assert w.b.getPosSize() == (5, 6, 70, 30)
    assert _geometry(w.b) == (5, 6, 70, 30)


def test_window_when_open_then_visible_and_children_shown(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.b = vanilla.Button((0, 0, 50, 20), "Go")
    assert not w.isVisible()
    w.open()
    assert w.isVisible() and w.b.getNSView().isVisible()


def _teardown_ops(*controls):
    views = {c.getNSView() for c in controls}
    kinds = {"disconnect", "close", "deleteLater"}
    return [e[0] for e in LOG if e[0] in kinds and e[1] in views]


def test_close_when_called_twice_then_disconnects_first_and_binds_fire_once(env):
    vanilla = env[0]
    closed = []
    w = vanilla.Window((300, 200))
    w.b = vanilla.Button((0, 0, 10, 10), "Go", callback=lambda s: None)
    w.g = vanilla.Group((0, 0, 0, 0))
    w.g.e = vanilla.EditText((0, 0, 10, 10), callback=lambda s: None)
    w.bind("close", closed.append)
    w.open()
    LOG.clear()
    w.close()
    w.close()
    ops = _teardown_ops(w, w.b, w.g, w.g.e)
    assert ops == ["disconnect", "disconnect", "close", "deleteLater"]
    assert closed == [w]
    assert w.b.getNSView().clicked.slots == []
    assert not w.isVisible()


def test_close_when_host_closes_window_then_same_teardown_once(env):
    vanilla, _, errors = env
    closed = []
    w = vanilla.Window((300, 200))
    w.b = vanilla.Button((0, 0, 10, 10), "Go", callback=lambda s: None)
    w.bind("close", closed.append)

    def bad(sender):
        raise ValueError("bind failed")

    w.bind("close", bad)
    w.open()
    LOG.clear()
    w.getNSView().close()  # title-bar close button path
    w.close()
    assert _teardown_ops(w, w.b) == ["close", "disconnect", "deleteLater"]
    assert closed == [w]
    assert [(str(e), s) for e, s in errors] == [("bind failed", w)]


def test_bind_when_unknown_event_then_unsupported_capability(env):
    w = env[0].Window((100, 100))
    with pytest.raises(UnsupportedCapability) as caught:
        w.bind("move", lambda s: None)
    assert caught.value.capability == "vanilla.Window.bind.move"


def test_open_window_when_unreferenced_then_kept_alive_until_closed(env):
    vanilla = env[0]

    def build():
        w = vanilla.Window((100, 100))
        w.open()
        return weakref.ref(w)

    ref = build()
    gc.collect()
    assert ref() is not None
    ref().close()
    gc.collect()
    assert ref() is None


def _script(tmp_path, body):
    path = tmp_path / "main.py"
    path.write_text(body)
    return path


def test_provider_when_plugged_into_context_then_import_vanilla_gets_module(tmp_path):
    qt = make_qt()
    errors = []
    provider = vanilla_provider(qt, lambda exc, s: errors.append(exc))
    ctx = ExecutionContext(tmp_path, "glyphs3", {"vanilla": provider})
    body = (
        "import vanilla\n"
        "w = vanilla.Window((200, 100), 'T')\n"
        "w.ok = vanilla.Button((10, 10, -10, 20), 'OK')\n"
        "from vanilla import *\n"
        "w.box = TextBox((0, 0, 50, 20), 'x')\n"
        "names = vanilla.__all__\n"
    )
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    assert ctx.globals["w"].ok.getTitle() == "OK"
    assert set(ctx.globals["names"]) == EXPORTS
    ctx.close()


def test_provider_when_script_imports_unknown_name_then_unsupported(tmp_path):
    provider = vanilla_provider(make_qt(), lambda exc, s: None)
    ctx = ExecutionContext(tmp_path, "glyphs3", {"vanilla": provider})
    with pytest.raises(UnsupportedCapability) as caught:
        ctx.run(_script(tmp_path, "from vanilla import LevelIndicator\n"))
    assert caught.value.capability == "vanilla.LevelIndicator"
    ctx.close()


def test_attach_when_name_reused_then_old_control_detached_and_closed_cleanly(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.ok = vanilla.Button((0, 0, 10, 10), "Old", callback=lambda s: None)
    old = w.ok
    old_view = old.getNSView()
    w.ok = vanilla.Button((0, 0, 10, 10), "New", callback=lambda s: None)
    assert w.ok is not old
    assert old_view.clicked.slots == []
    assert old_view.parentWidget() is None and old_view._deleted
    w.ok = w.ok  # same object again: no-op
    assert not w.ok.getNSView()._deleted
    w.open()
    w.close()
    assert w.ok.getNSView().clicked.slots == []
    nodes = [n for n in w.graph.to_json()["nodes"] if n["attribute_name"] == "ok"]
    assert [n["properties"].get("detached", False) for n in nodes] == [True, False]
    with pytest.raises(ValueError, match="removed"):
        w.other = old


def test_delattr_when_control_deleted_then_detached_with_subtree(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.g = vanilla.Group((0, 0, 0, 0))
    w.g.e = vanilla.EditText((0, 0, 10, 10), callback=lambda s: None)
    group, edit = w.g, w.g.e
    del w.g
    assert not hasattr(w, "g")
    assert edit.getNSView().textEdited.slots == []
    assert group.getNSView()._deleted and group.getNSView().parentWidget() is None
    detached = [n["properties"].get("detached") for n in w.graph.to_json()["nodes"]]
    assert detached == [None, True, True]
    w.plain = 1
    del w.plain
    w.close()


def test_open_when_closed_then_noop(env):
    w = env[0].Window((100, 100))
    w.close()
    w.open()
    assert not w.isVisible()


def test_close_when_disconnect_fails_then_sink_and_teardown_continues(env):
    vanilla, _, errors = env
    w = vanilla.Window((100, 100))
    w.a = vanilla.Button((0, 0, 10, 10), "A", callback=lambda s: None)
    w.b = vanilla.Button((0, 0, 10, 10), "B", callback=lambda s: None)
    w.a.getNSView().clicked.slots.clear()  # disconnect will raise ValueError
    w.close()
    assert [type(e) for e, _ in errors] == [ValueError]
    assert w.b.getNSView().clicked.slots == []
    assert w.getNSView()._deleted


def test_callbacks_when_wrapped_by_context_then_print_reaches_output(tmp_path):
    qt = make_qt()
    errors = []
    ctx = ExecutionContext(tmp_path, "glyphs3")
    sink = lambda exc, s: errors.append(exc)
    ctx.adapters["vanilla"] = vanilla_provider(qt, sink, wrap=ctx.wrap)
    body = (
        "import vanilla\n"
        "def hit(sender):\n"
        "    import helper\n"
        "    print('clicked', helper.VALUE, sender is w.b)\n"
        "w = vanilla.Window((200, 100))\n"
        "w.b = vanilla.Button((0, 0, 10, 10), 'Go', callback=hit)\n"
    )
    (tmp_path / "helper.py").write_text("VALUE = 5\n")
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    w = ctx.globals["w"]
    w.b.getNSView().user_click()  # after run() returned, context still open
    with ctx:
        w.b.getNSView().user_click()  # while the context is active
    assert "".join(ctx.output.strings) == "clicked 5 True\n" * 2
    assert errors == []
    ctx.close()
    w.b.getNSView().user_click()  # closed context: error routed, not raised
    assert [type(e) for e in errors] == [RuntimeError]


# --- slice 2, task 1: frequent keywords and methods on existing objects ---

KEY_RETURN, KEY_ENTER, KEY_ESCAPE = 0x01000004, 0x01000005, 0x01000000


def test_set_tool_tip_when_called_on_every_control_then_widget_tooltip(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.g = vanilla.Group((0, 0, 0, 0))
    controls = [
        vanilla.TextBox((0, 0, 10, 10), "t"),
        vanilla.EditText((0, 0, 10, 10)),
        vanilla.Button((0, 0, 10, 10), "B"),
        vanilla.CheckBox((0, 0, 10, 10), "C"),
        vanilla.PopUpButton((0, 0, 10, 10), ["x"]),
        vanilla.Slider((0, 0, 10, 10)),
        vanilla.HorizontalLine((0, 0, 10, 1)),
        vanilla.VerticalLine((0, 0, 1, 10)),
        w.g,
    ]
    for index, control in enumerate(controls):
        control.setToolTip(f"tip {index}")
        assert control.getNSView().toolTip == f"tip {index}"
    controls[0].setToolTip(42)  # vanilla passes text through str()
    assert controls[0].getNSView().toolTip == "42"


@pytest.mark.parametrize(
    ("alignment", "flags"),
    [
        ("left", 0x1 | 0x80),
        ("natural", 0x1 | 0x80),
        ("center", 0x4 | 0x80),
        ("right", 0x2 | 0x80),
        ("justified", 0x8 | 0x80),
    ],
)
def test_alignment_when_given_then_qt_flag_values(env, alignment, flags):
    vanilla = env[0]
    box = vanilla.TextBox((0, 0, 10, 10), "t", alignment=alignment)
    edit = vanilla.EditText((0, 0, 10, 10), "e", alignment=alignment)
    assert box.getNSView().alignment == flags
    assert edit.getNSView().alignment == flags
    w = vanilla.Window((100, 100))
    w.box, w.edit = box, edit
    props = [n["properties"] for n in w.graph.to_json()["nodes"][1:]]
    assert [p["alignment"] for p in props] == [alignment, alignment]


def test_alignment_when_default_then_qlabel_default_kept(env):
    box = env[0].TextBox((0, 0, 10, 10), "t")
    assert box.getNSView().alignment == 0x1 | 0x80  # natural == Qt default
    assert box.getNSView().textInteractionFlags == 0


@pytest.mark.parametrize("cls_name", ["TextBox", "EditText"])
@pytest.mark.parametrize("value", ["bogus", None, 3, ["left"]])
def test_alignment_when_unknown_then_unsupported_capability(env, cls_name, value):
    with pytest.raises(UnsupportedCapability) as caught:
        getattr(env[0], cls_name)((0, 0, 10, 10), "t", alignment=value)
    shown = value if isinstance(value, str) else type(value).__name__
    assert caught.value.capability == f"vanilla.{cls_name}.alignment.{shown}"
    assert not any(e[0] == "create" for e in LOG), "no widget built before rejecting"


def test_selectable_when_true_then_mouse_and_keyboard_selection(env):
    vanilla = env[0]
    box = vanilla.TextBox((0, 0, 10, 10), "copy me", selectable=True)
    assert box.getNSView().textInteractionFlags == 0x1 | 0x2
    w = vanilla.Window((100, 100))
    w.box = box
    assert w.graph.to_json()["nodes"][1]["properties"]["selectable"] is True
    plain = vanilla.TextBox((0, 0, 10, 10), "x", selectable=False)
    assert plain.getNSView().textInteractionFlags == 0


def test_edit_text_when_selectable_given_then_unsupported(env):
    with pytest.raises(UnsupportedCapability) as caught:
        env[0].EditText((0, 0, 10, 10), "x", selectable=True)
    assert caught.value.capability == "vanilla.EditText.selectable"


def test_make_key_when_called_then_raise_then_activate(env):
    w = env[0].Window((100, 100))
    w.open()
    LOG.clear()
    w.makeKey()
    view = w.getNSWindow()
    assert [e[0] for e in LOG if e[1] is view] == ["raise_", "activateWindow"]


def test_get_ns_window_when_called_then_top_level_widget(env):
    vanilla = env[0]
    for cls in (vanilla.Window, vanilla.FloatingWindow):
        w = cls((100, 100))
        assert w.getNSWindow() is w.getNSView()
        assert w.getNSWindow().parentWidget() is None


def test_center_when_called_then_centered_on_available_geometry(env):
    w = env[0].Window((40, 50, 300, 200))
    LOG.clear()
    w.center()
    # double's available geometry: (0, 25, 1440, 875)
    assert w.getPosSize() == (570, 362, 300, 200)
    assert ("availableGeometry", w.getNSView()) in LOG
    odd = env[0].Window((301, 200))
    odd.center()
    assert odd.getPosSize()[:2] == (569, 362)


def _default_window(vanilla, seen):
    w = vanilla.Window((300, 200))
    w.cancel = vanilla.Button((0, 0, 10, 10), "Cancel", callback=seen.append)
    w.ok = vanilla.Button((0, 0, 10, 10), "OK", callback=seen.append)
    w.edit = vanilla.EditText((0, 0, 10, 10), callback=seen.append)
    w.open()  # Return reaches only a shown window; hidden defaults are skipped
    return w


def test_set_default_button_when_return_pressed_then_button_activates(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.setDefaultButton(w.ok)
    view = w.getNSWindow()
    assert w.ok.getNSView().isDefault()
    LOG.clear()
    assert view.user_key(KEY_RETURN) is True
    assert view.user_key(KEY_ENTER) is True
    assert seen == [w.ok, w.ok]
    assert [e[0] for e in LOG if e[0] == "click"] == ["click", "click"]
    assert view.user_key(KEY_ESCAPE) is False
    assert ("native.keyPressEvent", view, KEY_ESCAPE) in LOG
    assert ("native.keyPressEvent", view, KEY_RETURN) not in LOG


def test_set_default_button_when_replaced_then_previous_cleared(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.setDefaultButton(w.ok)
    w.setDefaultButton(w.cancel)
    assert not w.ok.getNSView().isDefault()
    assert w.cancel.getNSView().isDefault()
    w.getNSWindow().user_key(KEY_RETURN)
    assert seen == [w.cancel]


def test_set_default_button_when_disabled_then_return_does_nothing(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.setDefaultButton(w.ok)
    w.ok.enable(False)
    w.getNSWindow().user_key(KEY_RETURN)
    assert seen == []


def test_set_default_button_when_hidden_then_return_ignored(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.g = vanilla.Group((0, 0, 0, 0))
    w.g.go = vanilla.Button((0, 0, 10, 10), "Go", callback=seen.append)
    w.setDefaultButton(w.ok)
    w.ok.show(False)
    assert w.getNSWindow().user_key(KEY_RETURN) is False
    w.setDefaultButton(w.g.go)
    w.g.show(False)  # hidden ancestor hides the button too
    assert w.getNSWindow().user_key(KEY_RETURN) is False
    w.g.show(True)
    assert w.getNSWindow().user_key(KEY_RETURN) is True
    assert seen == [w.g.go]


def test_set_default_button_when_button_retired_then_return_ignored(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.g = vanilla.Group((0, 0, 0, 0))
    w.g.go = vanilla.Button((0, 0, 10, 10), "Go", callback=seen.append)
    w.setDefaultButton(w.ok)
    w.ok = vanilla.Button((0, 0, 10, 10), "New OK", callback=seen.append)
    view = w.getNSWindow()
    view.user_key(KEY_RETURN)
    w.setDefaultButton(w.g.go)
    del w.g  # retiring the group deletes the button's widget too
    view.user_key(KEY_RETURN)
    assert seen == []
    assert ("native.keyPressEvent", view, KEY_RETURN) in LOG


def test_set_default_button_when_button_not_attached_here_then_value_error(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    other = vanilla.Window((100, 100))
    other.b = vanilla.Button((0, 0, 10, 10), "B", callback=seen.append)
    loose = vanilla.Button((0, 0, 10, 10), "Loose", callback=seen.append)
    old_ok = w.ok
    w.ok = vanilla.Button((0, 0, 10, 10), "New OK")  # retires old_ok
    LOG.clear()
    for button in (other.b, loose, old_ok):
        with pytest.raises(ValueError, match="not attached"):
            w.setDefaultButton(button)
    assert not any(e[0] == "setDefault" for e in LOG), "no widget touched"
    assert not other.b.getNSView().isDefault()
    assert w.getNSWindow().user_key(KEY_RETURN) is False
    assert seen == []


def test_set_default_button_when_previous_in_deleted_group_then_not_touched(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.g = vanilla.Group((0, 0, 0, 0))
    w.g.go = vanilla.Button((0, 0, 10, 10), "Go", callback=seen.append)
    w.setDefaultButton(w.g.go)
    go_view = w.g.go.getNSView()
    del w.g  # Qt deletes the group's child tree, go_view included
    assert go_view._deleted
    LOG.clear()
    w.setDefaultButton(w.ok)  # the double raises if setDefault hits go_view
    assert [e[1] for e in LOG if e[0] == "setDefault"] == [w.ok.getNSView()]
    w.getNSWindow().user_key(KEY_RETURN)
    assert seen == [w.ok]


def test_set_default_button_when_window_closed_then_value_error(env):
    vanilla = env[0]
    w = _default_window(vanilla, [])
    w.close()
    with pytest.raises(ValueError, match="not attached"):
        w.setDefaultButton(w.ok)


def test_set_default_button_when_window_closed_then_no_activation(env):
    vanilla = env[0]
    seen = []
    w = _default_window(vanilla, seen)
    w.setDefaultButton(w.ok)
    w.open()
    w.close()
    w.getNSWindow().user_key(KEY_RETURN)
    assert seen == []


def test_set_default_button_when_not_push_button_then_type_error(env):
    vanilla = env[0]
    w = vanilla.Window((100, 100))
    w.c = vanilla.CheckBox((0, 0, 10, 10), "C")
    w.t = vanilla.TextBox((0, 0, 10, 10), "T")
    for bad in (w.c, w.t, None, "OK"):
        with pytest.raises(TypeError, match="setDefaultButton"):
            w.setDefaultButton(bad)
    assert not any(e[0] == "setDefault" for e in LOG)


def test_qcheckbox_double_when_set_default_then_missing_like_native():
    assert not hasattr(make_qt().QtGui.QCheckBox(), "setDefault")
    assert hasattr(QPushButton(), "setDefault")
    assert not hasattr(QPushButton(), "setAlignment"), "QAbstractButton has none"


def test_autosave_when_two_windows_share_name_then_frame_round_trips(env):
    vanilla = env[0]
    first = vanilla.Window((10, 20, 300, 200), "A", autosaveName="tool")
    first.setPosSize((40, 50, 320, 210))
    first.getNSView().resize(330, 220)  # host resize saves too
    assert vanilla_impl._DEFAULT_SETTINGS == {"window:tool": [40, 50, 330, 220]}
    first.getNSView().setGeometry(60, 70, 330, 220)  # host move, no resize
    first.close()
    second = vanilla.Window((5, 5, 100, 100), "B", autosaveName="tool")
    assert second.getPosSize() == (60, 70, 330, 220)
    assert second.graph.to_json()["nodes"][0]["properties"]["autosaveName"] == "tool"
    other = vanilla.Window((5, 5, 100, 100), autosaveName="other")
    assert other.getPosSize() == (5, 5, 100, 100)


def test_autosave_when_title_bar_close_then_frame_saved(env):
    vanilla = env[0]
    w = vanilla.FloatingWindow((10, 20, 300, 200), autosaveName="panel")
    w.open()
    w.getNSView().setGeometry(1, 2, 300, 200)
    w.getNSView().close()
    assert vanilla_impl._DEFAULT_SETTINGS["window:panel"] == [1, 2, 300, 200]


def test_autosave_when_constructed_then_nothing_saved_until_change(env):
    env[0].Window((10, 20, 300, 200), autosaveName="quiet")
    assert vanilla_impl._DEFAULT_SETTINGS == {}


def test_autosave_when_no_name_then_settings_untouched(env):
    w = env[0].Window((10, 20, 300, 200))
    w.setPosSize((1, 1, 50, 50))
    w.close()
    assert vanilla_impl._DEFAULT_SETTINGS == {}


def test_autosave_when_mapping_injected_then_isolated_from_default():
    store = {}
    module = make_vanilla_module(make_qt(), error_sink=print, settings=store)
    w = module.Window((10, 20, 300, 200), autosaveName="iso")
    w.setPosSize((1, 2, 30, 40))
    w.close()
    assert store == {"window:iso": [1, 2, 30, 40]}
    assert vanilla_impl._DEFAULT_SETTINGS == {}
    stored = store["window:iso"]
    again = module.Window((0, 0, 10, 10), autosaveName="iso")
    stored[0] = 999  # caller aliasing must not move the window
    assert again.getPosSize() == (1, 2, 30, 40)
    default = make_vanilla_module(make_qt(), error_sink=print)
    assert default.Window((7, 8, 9, 10), autosaveName="iso").getPosSize() == (
        7,
        8,
        9,
        10,
    )


def test_autosave_when_default_settings_then_shared_between_modules():
    a = make_vanilla_module(make_qt(), error_sink=print)
    b = make_vanilla_module(make_qt(), error_sink=print)
    w = a.Window((10, 20, 300, 200), autosaveName="shared")
    w.setPosSize((3, 4, 50, 60))
    w.close()
    assert b.Window((0, 0, 1, 1), autosaveName="shared").getPosSize() == (3, 4, 50, 60)


@pytest.mark.parametrize(
    "stored",
    [
        [1, 2, 3],
        "1 2 3 4",
        [1, 2, 3, "4"],
        [True, 2, 3, 4],
        None,
        [float("nan"), 2, 300, 200],
        [1, float("inf"), 300, 200],
        [1, 2, float("inf"), 200],
        [1, 2, 0, 200],
        [1, 2, 300, -5],
        [1, 2, 0.4, 200],
        [10**400, 2, 300, 200],
        [1, 2, 300, -(10**400)],
        [1e300, 2, 300, 200],
        [1, 2, 16777216, 200],
        [1, -16777216, 300, 200],
    ],
)
def test_autosave_when_stored_value_malformed_then_pos_size_used(stored):
    store = {"window:bad": stored}
    module = make_vanilla_module(make_qt(), error_sink=print, settings=store)
    w = module.Window((10, 20, 300, 200), autosaveName="bad")
    assert w.getPosSize() == (10, 20, 300, 200)


def test_autosave_when_stored_floats_then_rounded_ints(env):
    store = {"window:f": [1.4, 2.6, 300.0, 200.5]}
    module = make_vanilla_module(make_qt(), error_sink=print, settings=store)
    assert module.Window((0, 0, 1, 1), autosaveName="f").getPosSize() == (
        1,
        3,
        300,
        200,
    )


def test_provider_when_settings_given_then_module_uses_them():
    store = {"window:p": [1, 2, 30, 40]}
    module = vanilla_provider(make_qt(), print, settings=store)()
    assert module.Window((0, 0, 1, 1), autosaveName="p").getPosSize() == (1, 2, 30, 40)


# --- integration task 1: context close hooks ---


def test_ctx_close_when_windows_open_then_each_closed_once_with_binds(tmp_path):
    qt = make_qt()
    errors = []
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["vanilla"] = vanilla_provider(
        qt, lambda exc, s: errors.append(exc), wrap=ctx.wrap, on_close=ctx.on_close
    )
    body = (
        "import vanilla\n"
        "def closed(sender):\n"
        "    import helper\n"
        "    print('closed', sender.title, helper.VALUE)\n"
        "windows = []\n"
        "for title in ('a', 'b', 'c'):\n"
        "    w = vanilla.Window((100, 50), title)\n"
        "    w.title = title\n"
        "    w.bind('close', closed)\n"
        "    w.open()\n"
        "    windows.append(w)\n"
        "windows[1].close()\n"
    )
    (tmp_path / "helper.py").write_text("VALUE = 3\n")
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    windows = ctx.globals["windows"]
    ctx.close()
    assert errors == []
    assert all(not w.isVisible() for w in windows)
    lines = "".join(ctx.output.strings).splitlines()
    assert lines[0] == "closed b 3"  # closed by the script itself
    assert sorted(lines[1:]) == ["closed a 3", "closed c 3"]
    assert all(w.getNSView()._deleted for w in windows)


def test_ctx_close_when_glyphs_callbacks_and_windows_then_callbacks_removed_first(
    tmp_path,
):
    from glyphsapp_doubles import FakeGlyphsBridge

    from fontlab_glyport.glyphsapp import glyphsapp_provider
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    order = []

    class Bridge(FakeGlyphsBridge):
        def remove(self, token):
            order.append(("remove", token))
            super().remove(token)

    bridge, errors = Bridge(), []
    ctx = ExecutionContext(tmp_path, "glyphs3")
    sink = lambda exc, s: errors.append(exc)
    ctx.adapters["vanilla"] = vanilla_provider(
        make_qt(), sink, wrap=ctx.wrap, on_close=ctx.on_close
    )
    ctx.adapters["GlyphsApp"] = glyphsapp_provider(
        Model(FakeBackend()),
        bridge,
        defaults={},
        wrap=ctx.wrap,
        error_sink=sink,
        on_close=ctx.on_close,
    )
    body = (
        "from GlyphsApp import Glyphs, UPDATEINTERFACE\n"
        "import vanilla\n"
        "def update(*args): pass\n"
        "def closed(sender):\n"
        "    record('window')\n"
        "    Glyphs.removeCallback(update)\n"
        "w = vanilla.Window((100, 50))\n"
        "w.bind('close', closed)\n"
        "w.open()\n"
        "Glyphs.addCallback(update, UPDATEINTERFACE)\n"
    )
    ctx.globals["record"] = order.append
    ctx.shared_globals = True
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    ctx.close()
    assert errors == []
    assert order == [("remove", "token-1"), "window"]
    assert bridge.subscriptions == {} and bridge.removed == ["token-1"]


def test_close_hook_when_one_window_close_fails_then_others_closed_and_raised():
    hooks = []
    module = make_vanilla_module(make_qt(), error_sink=print, on_close=hooks.append)
    closed = []

    class Stub:
        def __init__(self, error=None):
            self.error = error

        def close(self):
            closed.append(self)
            if self.error:
                raise self.error

    failing, fine = Stub(RuntimeError("native close failed")), Stub()
    module.Window._env.open_windows.update({failing, fine})
    assert len(hooks) == 1
    with pytest.raises(RuntimeError, match="native close failed"):
        hooks[0]()
    assert set(closed) == {failing, fine}


def test_close_hook_when_close_bind_exits_then_other_windows_closed_and_exit_raised():
    hooks = []
    module = make_vanilla_module(make_qt(), error_sink=print, on_close=hooks.append)
    exiting, other = module.Window((100, 50)), module.Window((100, 50))

    def leave(sender):
        raise SystemExit(0)

    exiting.bind("close", leave)
    exiting.open()
    other.open()
    with pytest.raises(SystemExit):
        hooks[0]()
    assert not exiting.isVisible() and not other.isVisible()
    assert module.Window._env.open_windows == set()
