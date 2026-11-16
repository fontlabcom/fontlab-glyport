# this_file: tests/test_ui_vanilla_controls.py
"""vanilla slice 2 controls: RadioGroup ... List over PythonQt-shaped doubles."""

import pytest
from ui_doubles import LOG, make_qt
from ui_doubles_controls import (
    ITEM_IS_EDITABLE,
    ITEM_IS_ENABLED,
    ITEM_IS_SELECTABLE,
    KEY_BACKSPACE,
    KEY_DELETE,
)

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.vanilla import SLIDER_STEPS, make_vanilla_module

KEY_RETURN = 0x01000004
READ_ONLY = ITEM_IS_SELECTABLE | ITEM_IS_ENABLED


@pytest.fixture
def env():
    qt = make_qt()
    errors = []
    module = make_vanilla_module(qt, error_sink=lambda exc, s: errors.append((exc, s)))
    return module, qt, errors


def _window(vanilla):
    w = vanilla.Window((300, 200))
    w.open()
    return w


def _geometry(widget):
    rect = widget.geometry
    return rect.x(), rect.y(), rect.width(), rect.height()


def _nodes(w):
    return w.graph.to_json()["nodes"]


def _events(w):
    return [(c["event"], c["selector"]) for c in w.graph.to_json()["connections"]]


@pytest.mark.parametrize(
    ("factory", "keyword"),
    [
        (lambda v: v.RadioGroup((0, 0, 9, 9), ["a"], border=1), "border"),
        (lambda v: v.RadioButton((0, 0, 9, 9), "r", bezel=1), "bezel"),
        (lambda v: v.ComboBox((0, 0, 9, 9), [], formatter=None), "formatter"),
        (lambda v: v.TextEditor((0, 0, 9, 9), "", font=None), "font"),
        (lambda v: v.SquareButton((0, 0, 9, 9), "s", imagePath="x"), "imagePath"),
        (lambda v: v.HelpButton((0, 0, 9, 9), page="p"), "page"),
        (
            lambda v: v.ProgressBar((0, 0, 9, 9), progressStyle="spinner"),
            "progressStyle",
        ),
        (lambda v: v.Box((0, 0, 9, 9), margins=4), "margins"),
        (
            lambda v: v.List((0, 0, 9, 9), [], autohidesScrollers=False),
            "autohidesScrollers",
        ),
    ],
)
def test_new_control_when_unknown_keyword_then_unsupported(env, factory, keyword):
    with pytest.raises(UnsupportedCapability) as caught:
        factory(env[0])
    assert caught.value.capability.endswith("." + keyword)
    assert not any(e[0] == "create" for e in LOG), "rejected before any widget"


def _every_new_control(vanilla):
    return [
        vanilla.RadioGroup((0, 0, 50, 40), ["a", "b"]),
        vanilla.RadioButton((0, 0, 50, 20), "r"),
        vanilla.ComboBox((0, 0, 50, 20), ["x"]),
        vanilla.TextEditor((0, 0, 50, 50)),
        vanilla.SquareButton((0, 0, 50, 20), "s"),
        vanilla.HelpButton((0, 0, 21, 20)),
        vanilla.ProgressBar((0, 0, 50, 10)),
        vanilla.Box((0, 0, 50, 50), "Box"),
        vanilla.List((0, 0, 50, 50), ["x"]),
    ]


def test_new_controls_when_tooltip_enable_show_then_widget_updated(env):
    vanilla = env[0]
    w = _window(vanilla)
    for index, control in enumerate(_every_new_control(vanilla)):
        setattr(w, f"c{index}", control)
        control.setToolTip(f"tip {index}")
        control.enable(False)
        control.show(False)
        view = control.getNSView()
        assert view.toolTip == f"tip {index}"
        assert not view.isEnabled() and not view.isVisible()
    assert [n["source_class"] for n in _nodes(w)[1:]] == [
        f"vanilla.{name}"
        for name in [
            "RadioGroup",
            "RadioButton",
            "ComboBox",
            "TextEditor",
            "SquareButton",
            "HelpButton",
            "ProgressBar",
            "Box",
            "List",
        ]
    ]


# --- RadioGroup ---------------------------------------------------------------


def test_radio_group_when_set_then_index_round_trips_including_none(env):
    vanilla = env[0]
    rg = vanilla.RadioGroup((10, 10, 100, 60), ["One", "Two", "Three"])
    assert rg.get() == 0, "NSMatrix radio mode selects the first cell"
    rg.set(2)
    assert rg.get() == 2
    rg.set(-1)  # the exclusive group would refuse a plain uncheck
    assert rg.get() == -1
    rg.set(1)
    assert rg.get() == 1
    with pytest.raises(IndexError):
        rg.set(3)
    assert vanilla.RadioGroup((0, 0, 9, 9), []).get() == -1


def test_radio_group_when_user_clicks_then_callback_sender_and_silent_set(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)

    def radioCallback(sender):
        seen.append((sender, sender.get()))

    w.rg = vanilla.RadioGroup((0, 0, 100, 60), ["a", "b"], callback=radioCallback)
    w.rg.set(1)
    assert seen == []
    buttons = [c for c in w.rg.getNSView()._children if hasattr(c, "_auto_exclusive")]
    buttons[0].user_click()
    buttons[0].user_click()  # clicking the checked radio keeps it checked
    assert seen == [(w.rg, 0), (w.rg, 0)]
    node = _nodes(w)[1]
    assert node["properties"] == {"titles": ["a", "b"], "isVertical": True}
    assert _events(w) == [("action", "radioCallback")]


def test_radio_group_when_laid_out_then_rows_or_equal_columns(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.v = vanilla.RadioGroup((10, 10, 100, 60), ["a", "b", "c"], sizeStyle="small")
    w.h = vanilla.RadioGroup((10, 80, 150, 20), ["a", "b", "c"], isVertical=False)
    radios = lambda rg: [c for c in rg.getNSView()._children if hasattr(c, "_group")]
    assert [_geometry(b) for b in radios(w.v)] == [
        (0, 0, 100, 15),
        (0, 17, 100, 15),
        (0, 34, 100, 15),
    ]
    assert [_geometry(b) for b in radios(w.h)] == [
        (0, 0, 50, 20),
        (50, 0, 50, 20),
        (100, 0, 50, 20),
    ]
    assert [b.text for b in radios(w.h)] == ["a", "b", "c"]


def test_radio_group_when_retired_then_disconnected_and_group_deleted(env):
    vanilla = env[0]
    w = _window(vanilla)
    w.rg = vanilla.RadioGroup((0, 0, 100, 60), ["a", "b"], callback=lambda s: None)
    view = w.rg.getNSView()
    group = next(c for c in view._children if hasattr(c, "idClicked"))
    del w.rg
    assert group.idClicked.slots == [] and group._deleted and view._deleted


# --- RadioButton ---------------------------------------------------------------


def test_radio_button_when_siblings_then_independent_and_set_false_works(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    w.a = vanilla.RadioButton((0, 0, 50, 20), "A", value=True, callback=seen.append)
    w.b = vanilla.RadioButton((0, 20, 50, 20), "B")
    assert (w.a.get(), w.b.get(), w.a.getTitle()) == (True, False, "A")
    w.b.set(True)
    assert w.a.get() is True, "standalone vanilla radios are not auto-exclusive"
    w.a.set(False)
    assert w.a.get() is False
    w.b.getNSView().user_click()  # checked radio: click keeps it on
    assert w.b.get() is True
    w.a.getNSView().user_click()
    assert w.a.get() is True and seen == [w.a]
    assert _nodes(w)[1]["properties"] == {"title": "A", "value": True}
    w.close()  # the always-on clicked slot is disconnected even without callback
    assert w.a.getNSView().clicked.slots == [] and w.b.getNSView().clicked.slots == []


def test_radio_button_when_set_default_button_then_type_error(env):
    vanilla = env[0]
    w = _window(vanilla)
    w.r = vanilla.RadioButton((0, 0, 50, 20), "R")
    with pytest.raises(TypeError, match="setDefaultButton"):
        w.setDefaultButton(w.r)
    assert not hasattr(w.r.getNSView(), "setDefault")


# --- ComboBox -----------------------------------------------------------------


def test_combo_box_when_created_then_editable_empty_text_and_no_insert(env):
    vanilla = env[0]
    combo = vanilla.ComboBox((0, 0, 100, 20), ["a", "b"], completes=False)
    view = combo.getNSView()
    assert combo.get() == "" and combo.getItems() == ["a", "b"]
    assert view.lineEdit() is not None and view._insert_policy == "NoInsert"
    assert view._completer is None
    assert vanilla.ComboBox((0, 0, 9, 9), ["a"]).getNSView()._completer == "default"


def test_combo_box_when_set_and_set_items_then_text_kept_and_silent(env):
    vanilla = env[0]
    seen = []
    combo = vanilla.ComboBox(
        (0, 0, 100, 20), ["a"], callback=seen.append, continuous=True
    )
    combo.set("typed")
    assert combo.get() == "typed"
    combo.setItems(["x", "y"])
    assert (combo.get(), combo.getItems()) == ("typed", ["x", "y"])
    combo.set(12)
    assert combo.get() == "12"
    assert seen == []


def test_combo_box_when_continuous_then_user_edits_and_picks_fire_once(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    w.c = vanilla.ComboBox(
        (0, 0, 100, 20), ["a", "b"], callback=seen.append, continuous=True
    )
    view = w.c.getNSView()
    view.user_type("x")
    view.user_choose(1)
    assert seen == [w.c, w.c] and w.c.get() == "b"
    view.setCurrentIndex(0)  # programmatic: editTextChanged fires, callback not
    view.user_focus_out()
    view.user_return()
    assert seen == [w.c, w.c] and w.c.get() == "a"
    w.close()
    slots = (view.activated, view.editTextChanged, view.lineEdit().textEdited)
    assert [s.slots for s in slots] == [[], [], []]


def _commit_combo(vanilla, seen):
    w = _window(vanilla)
    w.c = vanilla.ComboBox(
        (0, 0, 100, 20), ["Regular", "Bold"], callback=lambda s: seen.append(s.get())
    )
    return w, w.c.getNSView()


def test_combo_box_when_typed_then_return_and_focus_out_report_once(env):
    seen = []
    w, view = _commit_combo(env[0], seen)
    view.user_type("Light")
    assert seen == []
    view.user_return()  # no matching item
    view.user_focus_out()  # Qt 5.15 emits editingFinished again
    assert seen == ["Light"]
    assert w.c.getItems() == ["Regular", "Bold"], "NoInsert"
    view.user_type("Bold")
    view.user_return()  # match: Qt selects it and emits activated, then ours
    view.user_focus_out()
    assert seen == ["Light", "Bold"]


def test_combo_box_when_popup_pick_or_focus_without_edit_then_once_or_never(env):
    seen = []
    _w, view = _commit_combo(env[0], seen)
    view.user_focus_out()  # focus in/out without an edit
    assert seen == []
    view.user_choose(1)
    view.user_focus_out()
    assert seen == ["Bold"]
    view.user_type("Bo")  # typed, then picked from the popup before Return
    view.user_choose(0)
    view.user_focus_out()
    assert seen == ["Bold", "Regular"]


def test_combo_box_when_programmatic_index_or_set_then_silent(env):
    seen = []
    w, view = _commit_combo(env[0], seen)
    view.setCurrentIndex(1)  # native call, not through vanilla
    view.user_focus_out()
    w.c.set("Light")
    w.c.setItems(["X"])
    view.user_return()
    view.user_focus_out()
    assert seen == []
    w.close()
    assert view.activated.slots == [] and view.lineEdit().editingFinished.slots == [
        view._editing_finished
    ], "only Qt's own handler stays"


# --- TextEditor ---------------------------------------------------------------


def test_text_editor_when_set_and_typed_then_text_and_callback(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    w.t = vanilla.TextEditor(
        (0, 0, 100, 100), "line 1\nline 2", callback=seen.append, readOnly=True
    )
    view = w.t.getNSView()
    assert w.t.get() == "line 1\nline 2" and view._read_only
    w.t.set("new")
    assert seen == []
    view.user_type("!")
    assert (seen, w.t.get()) == ([w.t], "new!")
    props = _nodes(w)[1]["properties"]
    assert props == {
        "text": "line 1\nline 2",
        "readOnly": True,
        "checksSpelling": False,
    }
    w.close()
    assert view.textChanged.slots == []


# --- SquareButton / HelpButton ------------------------------------------------


def test_square_and_help_buttons_when_clicked_then_callbacks_and_default(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    w.s = vanilla.SquareButton(
        (0, 0, 50, 20), "Sq", callback=seen.append, sizeStyle="small"
    )
    w.h = vanilla.HelpButton((0, 30, 21, 20), callback=seen.append)
    assert (w.s.getTitle(), w.h.getTitle()) == ("Sq", "?")
    w.s.getNSView().user_click()
    w.h.getNSView().user_click()
    assert seen == [w.s, w.h]
    w.setDefaultButton(w.h)
    w.getNSWindow().user_key(KEY_RETURN)
    assert seen == [w.s, w.h, w.h]
    props = [n["properties"] for n in _nodes(w)[1:]]
    assert props == [{"title": "Sq", "sizeStyle": "small"}, {"title": "?"}]
    w.close()
    assert w.s.getNSView().clicked.slots == [] and w.h.getNSView().clicked.slots == []


# --- ProgressBar --------------------------------------------------------------


def test_progress_bar_when_set_and_increment_then_float_value_clamped(env):
    vanilla = env[0]
    bar = vanilla.ProgressBar((0, 0, 100, 10), minValue=0, maxValue=1)
    view = bar.getNSView()
    assert (view.minimum, view.maximum, bar.get()) == (0, SLIDER_STEPS, 0.0)
    assert view._text_visible is False
    LOG.clear()
    bar.set(0.25)
    assert bar.get() == 0.25 and view.value == SLIDER_STEPS // 4
    assert ("repaint", view) in LOG, "repaint so progress shows in a busy loop"
    bar.increment(0.5)
    assert bar.get() == 0.75
    bar.increment(5)
    assert bar.get() == 1.0 and view.value == SLIDER_STEPS
    bar.set(-3)
    assert bar.get() == 0.0 and view.value == 0
    default = vanilla.ProgressBar((0, 0, 9, 9))
    default.increment()
    assert default.get() == 1.0


def test_progress_bar_when_indeterminate_then_start_busy_and_stop_restores(env):
    vanilla = env[0]
    bar = vanilla.ProgressBar((0, 0, 100, 10), isIndeterminate=True)
    view = bar.getNSView()
    bar.start()
    assert (view.minimum, view.maximum) == (0, 0)
    bar.stop()
    assert (view.minimum, view.maximum) == (0, SLIDER_STEPS)
    determinate = vanilla.ProgressBar((0, 0, 100, 10))
    LOG.clear()
    determinate.start()
    determinate.stop()
    assert not any(e[0] == "setRange" for e in LOG)
    with pytest.raises(ValueError, match="maxValue"):
        vanilla.ProgressBar((0, 0, 9, 9), minValue=3, maxValue=3)


# --- Box ----------------------------------------------------------------------


def test_box_when_children_added_then_laid_out_in_content_area(env):
    vanilla = env[0]
    w = vanilla.Window((300, 300))
    w.box = vanilla.Box((10, 205, 200, 80), "Options")
    w.box.check = vanilla.CheckBox((5, 5, -5, 20), "Flag")
    view, check = w.box.getNSView(), w.box.check.getNSView()
    content = check.parentWidget()
    assert content.parentWidget() is view
    assert _geometry(content) == (1, 1, 198, 78), "before polish: bare frame"
    w.open()  # polish moves the content below the title
    assert view.contentsRect().y() == 21
    assert _geometry(content) == (1, 21, 198, 58)
    assert _geometry(check) == (5, 5, 188, 20)
    w.setPosSize((300, 400))
    w.box.setPosSize((10, 10, 220, 100))
    assert (_geometry(content), _geometry(check)) == ((1, 21, 218, 78), (5, 5, 208, 20))
    w.box.setTitle("")  # the title band goes away
    assert _geometry(content) == (1, 1, 218, 98)
    w.box.setTitle("Other")
    assert (w.box.getTitle(), view.title) == ("Other", "Other")
    assert _geometry(content) == (1, 21, 218, 78)


def test_box_when_attached_after_open_then_content_follows_polish(env):
    vanilla = env[0]
    w = _window(vanilla)
    w.box = vanilla.Box((0, 0, 100, 100), "Late")
    w.box.b = vanilla.Button((0, 0, -0, 20), "Go")
    content = w.box.b.getNSView().parentWidget()
    assert _geometry(content) == (1, 21, 98, 78)
    untitled = vanilla.Box((0, 0, 100, 100))
    w.plain = untitled
    assert untitled.getTitle() == ""
    nodes = _nodes(w)
    assert [(n["source_class"], n["parent_id"]) for n in nodes] == [
        ("vanilla.Window", None),
        ("vanilla.Box", "n1"),
        ("vanilla.Button", "n2"),
        ("vanilla.Box", "n1"),
    ]
    assert nodes[1]["properties"] == {"title": "Late"}
    view = w.box.getNSView()
    w.close()
    assert view._owner is None


def test_box_when_deleted_then_subtree_detached_and_disconnected(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))
    w.box = vanilla.Box((0, 0, 100, 100), "B")
    w.box.b = vanilla.Button((0, 0, 50, 20), "Go", callback=lambda s: None)
    button = w.box.b.getNSView()
    del w.box
    assert button.clicked.slots == [] and button._deleted
    assert [n["properties"].get("detached") for n in _nodes(w)] == [None, True, True]


# --- List ---------------------------------------------------------------------


def _cells(control):
    view = control.getNSView()
    return [
        [view.item(r, c).text() for c in range(view.columnCount)]
        for r in range(view.rowCount)
    ]


def test_list_when_plain_items_then_sequence_api(env):
    vanilla = env[0]
    lst = vanilla.List((0, 0, 100, 100), ["a", "b"])
    view = lst.getNSView()
    assert (lst.get(), len(lst), lst[1]) == (["a", "b"], 2, "b")
    lst.append("c")
    lst.extend(["d", 5])
    lst.remove("b")
    assert lst.get() == ["a", "c", "d", 5]
    assert _cells(lst) == [["a"], ["c"], ["d"], ["5"]]
    assert lst[0:2] == ["a", "c"] and lst[::-1][0] == 5
    lst.set(["z"])
    assert lst.get() == ["z"] and _cells(lst) == [["z"]]
    assert not view.horizontalHeader().isVisible(), "no titles without columns"
    assert not view.verticalHeader().isVisible(), "no row numbers"
    assert view.item(0, 0).flags() == READ_ONLY


def test_list_when_column_descriptions_then_dict_items_copied(env):
    vanilla = env[0]
    source = {"name": "A", "count": 1}
    columns = [
        {"title": "Name", "key": "name", "width": 80.4},
        {"title": "count"},  # key defaults to title
    ]
    lst = vanilla.List(
        (0, 0, 200, 100), [source, {"name": None}], columnDescriptions=columns
    )
    view = lst.getNSView()
    assert _cells(lst) == [["A", "1"], ["", ""]]
    assert view._labels == ["Name", "count"] and view._widths == {0: 80}
    assert view.horizontalHeader().isVisible()
    assert lst[0] == source and lst[0] is not source
    hidden = vanilla.List(
        (0, 0, 9, 9), [], columnDescriptions=columns, showColumnTitles=False
    )
    assert not hidden.getNSView().horizontalHeader().isVisible()


def test_list_when_column_description_has_unknown_cell_then_unsupported(env):
    vanilla = env[0]
    with pytest.raises(UnsupportedCapability) as caught:
        vanilla.List(
            (0, 0, 9, 9), [], columnDescriptions=[{"title": "T", "cell": object()}]
        )
    assert caught.value.capability == "vanilla.List.columnDescriptions.cell"
    assert vanilla.CheckBoxListCell().title is None


def test_list_when_set_selection_then_multiple_rows_and_callback_once(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    w.l = vanilla.List((0, 0, 100, 100), list("abcd"), selectionCallback=seen.append)
    view = w.l.getNSView()
    assert view._mode == "ExtendedSelection"
    w.l.setSelection([2, 0])
    assert w.l.getSelection() == [0, 2]
    assert seen == [w.l], "vanilla's KVO observer fires on setSelection"
    view.user_select([3])
    assert w.l.getSelection() == [3] and seen == [w.l, w.l]
    w.l.set(["x"])  # drops the selection without a callback
    w.l.append("y")
    assert w.l.getSelection() == [] and len(seen) == 2


def test_list_when_single_selection_or_no_empty_then_modes(env):
    vanilla = env[0]
    single = vanilla.List((0, 0, 9, 9), ["a"], allowsMultipleSelection=False)
    assert single.getNSView()._mode == "SingleSelection"
    assert single.getSelection() == []
    firm = vanilla.List((0, 0, 9, 9), ["a", "b"], allowsEmptySelection=False)
    assert firm.getSelection() == [0]
    focus = vanilla.List((0, 0, 9, 9), ["a"], drawFocusRing=False)
    assert focus.getNSView()._attributes == {"WA_MacShowFocusRect": False}


def test_list_when_user_edits_then_item_updated_and_edit_callback(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    source = {"name": "A", "fixed": "x"}
    columns = [
        {"title": "Name", "key": "name"},
        {"title": "F", "key": "fixed", "editable": False},
    ]
    w.l = vanilla.List(
        (0, 0, 100, 100), [source], columnDescriptions=columns, editCallback=seen.append
    )
    view = w.l.getNSView()
    assert view.item(0, 0).flags() == READ_ONLY | ITEM_IS_EDITABLE
    assert view.item(0, 1).flags() == READ_ONLY
    assert view._edit_triggers == 0x2 | 0x8
    view.user_edit(0, 0, "B")
    assert w.l[0] == {"name": "B", "fixed": "x"} and source["name"] == "A"
    assert seen == [w.l]
    w.l.set([{"name": "C"}])
    assert seen == [w.l], "programmatic set does not fire editCallback"


def test_list_when_editable_column_without_callback_then_edit_stored(env):
    vanilla = env[0]
    lst = vanilla.List(
        (0, 0, 9, 9),
        [{"k": "v"}],
        columnDescriptions=[{"title": "k", "editable": True}],
    )
    lst.getNSView().user_edit(0, 0, "new")
    assert lst.get() == [{"k": "new"}]
    plain = vanilla.List((0, 0, 9, 9), ["a"], editCallback=lambda s: None)
    plain.getNSView().user_edit(0, 0, "b")
    assert plain.get() == ["b"]


def test_list_when_double_clicked_then_callback_unless_cell_editable(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    columns = [{"title": "A", "key": "a", "editable": True}, {"title": "B", "key": "b"}]
    w.l = vanilla.List(
        (0, 0, 100, 100),
        [{"a": 1, "b": 2}],
        columnDescriptions=columns,
        doubleClickCallback=seen.append,
    )
    view = w.l.getNSView()
    view.user_double_click(0, 0)  # editable cell: Qt edits, AppKit sends no action
    view.user_double_click(0, 1)
    assert seen == [w.l]


def test_list_when_delete_key_then_rows_removed_only_if_enabled(env):
    vanilla = env[0]
    seen = []
    w = _window(vanilla)
    w.l = vanilla.List(
        (0, 0, 100, 100), list("abcd"), enableDelete=True, selectionCallback=seen.append
    )
    w.k = vanilla.List((0, 0, 100, 100), list("ab"))
    w.l.setSelection([1, 3])
    LOG.clear()
    assert w.l.getNSView().user_key(KEY_BACKSPACE) is True
    assert (w.l.get(), w.l.getSelection()) == (["a", "c"], [])
    assert seen == [w.l, w.l]
    assert w.l.getNSView().user_key(KEY_DELETE) is False, "nothing selected"
    w.k.setSelection([0])
    assert w.k.getNSView().user_key(KEY_DELETE) is False
    assert w.k.get() == ["a", "b"]
    assert ("native.keyPressEvent", w.k.getNSView(), KEY_DELETE) in LOG


def test_list_when_callbacks_then_graph_events_and_properties(env):
    vanilla = env[0]
    w = vanilla.Window((300, 200))

    def selected(sender):
        pass

    def doubled(sender):
        pass

    def edited(sender):
        pass

    w.l = vanilla.List(
        (0, 0, 100, 100),
        ["a", "b"],
        selectionCallback=selected,
        doubleClickCallback=doubled,
        editCallback=edited,
    )
    assert _events(w) == [
        ("selection", "selected"),
        ("doubleClick", "doubled"),
        ("edit", "edited"),
    ]
    props = _nodes(w)[1]["properties"]
    assert props == {
        "columns": None,
        "itemCount": 2,
        "showColumnTitles": True,
        "allowsMultipleSelection": True,
        "allowsEmptySelection": True,
        "drawFocusRing": True,
        "enableDelete": False,
    }


def test_list_when_window_closed_then_every_signal_disconnected(env):
    vanilla, _, errors = env
    w = _window(vanilla)
    w.l = vanilla.List(
        (0, 0, 100, 100),
        ["a"],
        selectionCallback=lambda s: None,
        doubleClickCallback=lambda s: None,
        editCallback=lambda s: None,
        enableDelete=True,
    )
    view = w.l.getNSView()
    w.close()
    signals = (view.itemChanged, view.itemSelectionChanged, view.cellDoubleClicked)
    assert [s.slots for s in signals] == [[], [], []]
    assert view._owner is None
    assert view.user_key(KEY_DELETE) is False and errors == []


def test_list_when_callback_raises_then_error_sink(env):
    vanilla, _, errors = env
    w = _window(vanilla)

    def boom(sender):
        raise RuntimeError("boom")

    w.l = vanilla.List((0, 0, 100, 100), ["a"], selectionCallback=boom)
    w.l.getNSView().user_select([0])
    assert [(str(e), s) for e, s in errors] == [("boom", w.l)]


def test_color_well_when_set_clicked_and_picked_then_value_callback_and_cleanup():
    """R049 custom-nsview (Waterfall): ColorWell(posSize, color=, callback=)
    with get()/set(); a click opens a non-modal QColorDialog whose selection
    becomes the value and reports the callback; closing disconnects it."""
    from types import SimpleNamespace

    from ui_doubles import Signal

    from fontlab_glyport.drawing.cocoa_drawing import NSColor

    opened = []

    class QColorDialog:
        def __init__(self, color, parent):
            self.initial, self.colorSelected = color, Signal(self, "colorSelected")
            opened.append(self)

        def open(self):
            self.shown = True

        def deleteLater(self):
            self.deleted = True

    qt = make_qt()
    qt.QtGui.QColorDialog = QColorDialog
    qt.QtGui.QColor = lambda r, g, b, a: (r, g, b, a)
    vanilla = make_vanilla_module(qt, error_sink=lambda e, s: None)
    seen = []
    w = _window(vanilla)
    w.fore = vanilla.ColorWell(
        (0, 0, 30, 20), color=NSColor(1, 0, 0, 1), callback=seen.append
    )
    assert w.fore.get() == NSColor(1, 0, 0, 1)
    w.fore.set(NSColor(0, 0, 1, 1))
    assert "rgba(0, 0, 255" in w.fore.getNSView()._style
    w.fore.getNSView().click()
    (dialog,) = opened
    assert dialog.initial == (0, 0, 255, 255) and dialog.shown
    picked = SimpleNamespace(
        redF=lambda: 0.0, greenF=lambda: 1.0, blueF=lambda: 0.0, alphaF=lambda: 1.0
    )
    dialog.colorSelected.emit(picked)
    assert w.fore.get() == NSColor(0, 1, 0, 1) and seen == [w.fore]
    w.close()
    assert dialog.colorSelected.slots == [] and dialog.deleted


def test_segmented_button_when_clicked_then_one_selected_callback_and_tooltip():
    """R049 general-plugin (Context Manager): SegmentedButton(posSize,
    [{"title": "+"}, {"title": "-"}], callback=...); get() is the selected
    index; getNSSegmentedButton().setToolTip_ works."""
    qt = make_qt()
    vanilla = make_vanilla_module(qt, error_sink=lambda e, s: None)
    seen = []
    w = _window(vanilla)
    w.seg = vanilla.SegmentedButton(
        (0, 0, 40, 20), [{"title": "+"}, {"title": "-"}], callback=seen.append
    )
    buttons = w.seg.getNSView()._children
    assert [b.text for b in buttons] == ["+", "-"] and w.seg.get() == -1
    assert [_geometry(b) for b in buttons] == [(0, 0, 20, 20), (20, 0, 20, 20)]
    buttons[1].click()
    assert w.seg.get() == 1 and seen == [w.seg]
    buttons[0].click()
    assert w.seg.get() == 0 and [b.isChecked() for b in buttons] == [True, False]
    w.seg.set(1)
    assert w.seg.get() == 1 and len(seen) == 2, "set() does not report"
    w.seg.getNSSegmentedButton().setToolTip_("Add")
    assert w.seg.getNSView().toolTip == "Add"
    w.close()


def test_action_button_when_item_chosen_then_its_callback():
    """Context Manager's ActionButton(posSize, items): a gear button whose
    menu lists the items; choosing one reports its callback."""
    from ui_doubles import Signal

    class QMenu:
        def __init__(self, parent=None):
            self.items = []

        def addAction(self, title):
            action = type("A", (), {})()
            action.text, action.triggered = title, Signal(action, "triggered")
            self.items.append(action)
            return action

        def addSeparator(self):
            self.items.append(None)

    qt = make_qt()
    qt.QtGui.QMenu = QMenu
    vanilla = make_vanilla_module(qt, error_sink=lambda e, s: None)
    chosen = []
    w = _window(vanilla)
    w.gear = vanilla.ActionButton(
        (0, 0, 30, 18),
        [{"title": "Export", "callback": chosen.append}, "----", {"title": "Import"}],
    )
    menu = w.gear.getNSView().menu()
    assert [a.text if a else None for a in menu.items] == ["Export", None, "Import"]
    menu.items[0].triggered.emit(False)
    assert chosen == [w.gear]
    w.close()
    assert menu.items[0].triggered.slots == []


def test_box_when_fill_border_and_radius_then_group_box_style():
    """R049 general-plugin (Context Manager): Box(posSize, cornerRadius=6,
    fillColor=NSColor, borderColor=NSColor)."""
    from fontlab_glyport.drawing.cocoa_drawing import NSColor

    vanilla = make_vanilla_module(make_qt(), error_sink=lambda e, s: None)
    w = _window(vanilla)
    w.box = vanilla.Box(
        (10, 18, 170, 170),
        cornerRadius=6,
        fillColor=NSColor(0, 0, 0, 0.05),
        borderColor=NSColor(0, 0, 0, 0.1),
    )
    style = w.box.getNSView()._style
    assert "background-color: rgba(0, 0, 0, 13)" in style
    assert "border: 1px solid rgba(0, 0, 0, 26)" in style
    assert "border-radius: 6px" in style
    w.close()


def test_slider_when_tick_marks_and_stop_on_them_then_values_snap():
    """R049 general-plugin (Context Manager): Slider(..., tickMarkCount=n,
    stopOnTickMarks=True) only takes tick values."""
    from ui_doubles import QSlider

    vanilla = make_vanilla_module(make_qt(), error_sink=lambda e, s: None)
    w = _window(vanilla)
    w.s = vanilla.Slider(
        (0, 0, 100, 20),
        minValue=0,
        maxValue=10,
        value=3.4,
        tickMarkCount=11,
        stopOnTickMarks=True,
    )
    view = w.s.getNSView()
    assert isinstance(view, QSlider) and view._tick_interval == SLIDER_STEPS // 10
    assert w.s.get() == 3.0
    view.setValue(round(SLIDER_STEPS * 0.57))  # dragged between ticks
    assert w.s.get() == 6.0
    w.close()


def test_list_when_row_height_then_row_section_size():
    vanilla = make_vanilla_module(make_qt(), error_sink=lambda e, s: None)
    w = _window(vanilla)
    w.items = vanilla.List((0, 0, 100, 100), ["a"], rowHeight=17)
    assert w.items.getNSView().verticalHeader().defaultSectionSize() == 17
    w.close()
