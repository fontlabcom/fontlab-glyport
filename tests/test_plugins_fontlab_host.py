# this_file: tests/test_plugins_fontlab_host.py
"""FontLabPluginHost parts that need no Qt (native proof: native_plugins.py)."""

import pytest

from fontlab_glyport.errors import HostUnavailable, UnsupportedCapability
from fontlab_glyport.plugins.fontlab_host import (
    MENU_TITLES,
    FontLabPluginHost,
    qt_widget,
)


def _host(**kw):
    return FontLabPluginHost(object(), object(), error_sink=lambda e, s: None, **kw)


def test_register_tool_when_called_then_unsupported_r054():
    with pytest.raises(UnsupportedCapability) as info:
        _host().register_tool(object())
    assert info.value.capability == "FontLab.register_tool"


def test_model_calls_when_no_adapter_then_host_unavailable():
    host = _host()
    for call in (host.selected_layers, host.current_font, lambda: host.undo_group("x")):
        with pytest.raises(HostUnavailable):
            call()
    with pytest.raises(HostUnavailable):
        host.register_painter("after_native_layer", lambda c: None)


def test_remove_when_unknown_or_repeated_token_then_noop():
    host, calls = _host(), []
    token = host._token(lambda: calls.append(1))
    host.remove(token)
    host.remove(token)
    host.remove(999)
    assert calls == [1]


def test_menu_titles_and_qt_widget():
    assert MENU_TITLES["SCRIPT_MENU"] == "Script" and "FILTER_MENU" not in MENU_TITLES

    class View:
        _qt = "widget"

    assert qt_widget(View()) == "widget" and qt_widget("raw") == "raw"


# --- with PythonQt-shaped doubles -------------------------------------------------
from host_doubles import VIOLATIONS, MainWindow, QWidget, make_host_qt

from fontlab_glyport.ui.cocoa_menu import NSMenuItem


class Painters:
    def __init__(self):
        self.registered, self.removed = {}, []

    def register(self, phase, callback, layer_filter, document_id=None):
        token = len(self.registered) + 1
        self.registered[token] = (phase, layer_filter, document_id)
        return token

    def remove(self, token):
        self.removed.append(token)


def _qt_host(**kw):
    qt = make_host_qt()
    errors = []
    host = FontLabPluginHost(
        qt,
        object(),
        error_sink=lambda e, s: errors.append(e),
        main_window=MainWindow(),
        **kw,
    )
    return host, qt, errors


def _dialog(host):
    view, closed = QWidget(), []
    token = host.run_dialog(view, "Grow", "Apply", closed.append)
    window = view.parent
    buttons = {b.text: b for b in window.children if hasattr(b, "clicked")}
    return token, window, buttons, closed


@pytest.mark.parametrize(("label", "applied"), [("Apply", True), ("Cancel", False)])
def test_dialog_button_when_clicked_then_teardown_deferred_past_dispatch(
    label, applied
):
    host, _, errors = _qt_host()
    token, window, buttons, closed = _dialog(host)
    buttons[label].click()
    assert closed == [applied] and not window.isVisible()
    assert VIOLATIONS == [], "nothing is disconnected or deleted inside the click"
    assert not window.deleted, "deletion waits for the event loop"
    host._reaper.fire()
    assert window.deleted and buttons[label].clicked.slots == []
    assert VIOLATIONS == [] and errors == []
    host.remove(token)
    assert closed == [applied], "a finished dialog's token does nothing"


def test_dialog_when_title_bar_closes_then_cancelled_once():
    host, _, _ = _qt_host()
    _, window, buttons, closed = _dialog(host)
    window.close()
    window.close()
    assert closed == [False]
    host._reaper.fire()
    assert window.deleted and buttons["Apply"].clicked.slots == []


def test_dialog_when_token_removed_then_cancelled_and_cleaned_on_close():
    host, _, _ = _qt_host()
    token, window, _, closed = _dialog(host)
    host.remove(token)
    assert closed == [False] and not window.isVisible()
    host.close()
    assert window.deleted and host._pending == []


def test_close_when_one_undo_fails_then_others_still_run():
    host, _, _ = _qt_host()
    calls = []
    host._token(lambda: calls.append("a"))
    host._token(lambda: (_ for _ in ()).throw(RuntimeError("bad")))
    host._token(lambda: calls.append("c"))
    with pytest.raises(RuntimeError):
        host.close()
    assert calls == ["c", "a"] and host._tokens == {}


def test_register_painter_when_document_id_then_forwarded_and_removed():
    painters = Painters()
    host, _, _ = _qt_host(painters=painters)
    token = host.register_painter("after_native_layer", print, document_id=7)
    assert painters.registered[1] == ("after_native_layer", "active", 7)
    host.remove(token)
    assert painters.removed == [1]


def test_file_format_when_exported_then_through_guard():
    host, _, _ = _qt_host(model=type("M", (), {"current_font": lambda self: "font"})())
    seen = []

    class Fmt:
        def title(self):
            return "CSV"

        def exportFont_(self, font):
            seen.append(font)

    def guard(owner, function, *args):
        seen.append("guarded")
        return function(*args)

    host.register_file_format(Fmt(), guard=guard)
    file_menu = host._menu("FILE_MENU")
    file_menu.actions()[-1].trigger()
    assert seen == ["guarded", "font"]


def test_menu_when_registered_then_action_in_fontlab_menu_and_removed():
    host, _, _ = _qt_host()
    item = NSMenuItem("Hello", lambda s: None)
    token = host.register_menu("EDIT_MENU", item)
    edit = host._menu("EDIT_MENU")
    assert [a.text for a in edit.actions()] == ["Hello"]
    item.setState_(1)
    assert edit.actions()[0].checked
    host.remove(token)
    assert edit.actions() == [] and item._observers == []


# --- fix round 2 (RR-L2) ------------------------------------------------------


def test_dialog_when_on_close_closes_host_then_nothing_torn_down_in_dispatch():
    host, _, errors = _qt_host()
    view = QWidget()
    host.run_dialog(view, "Grow", "Apply", lambda applied: host.close())
    window = view.parent
    apply = next(b for b in window.children if getattr(b, "text", "") == "Apply")
    apply.click()
    assert VIOLATIONS == [], "close() inside the click must defer its teardown"
    host._reaper.fire()
    assert VIOLATIONS == [] and window.deleted and errors == []
    assert host._tokens == {} and host._pending == []


def test_menu_when_callback_unloads_its_own_item_then_removal_deferred():
    host, _, errors = _qt_host()
    tokens = []
    item = NSMenuItem("Self", lambda sender: host.remove(tokens[0]))
    tokens.append(host.register_menu("EDIT_MENU", item))
    action = host._menu("EDIT_MENU").actions()[0]
    action.trigger()
    assert VIOLATIONS == [] and host._menu("EDIT_MENU").actions() == [action]
    host._reaper.fire()
    assert host._menu("EDIT_MENU").actions() == [] and action.triggered.slots == []
    assert VIOLATIONS == [] and errors == []


def test_dialog_when_view_reopened_before_reaper_then_new_dialog_keeps_it():
    host, _, _ = _qt_host()
    view = QWidget()
    host.run_dialog(view, "A", "Apply", lambda applied: None)
    first = view.parent
    next(b for b in first.children if getattr(b, "text", "") == "Cancel").click()
    token = host.run_dialog(view, "B", "Apply", lambda applied: None)
    second = view.parent
    host._reaper.fire()
    assert first.deleted and not second.deleted
    assert view.parent is second and view.visible, "the reopened dialog keeps its view"
    assert token in host._tokens


# --- fix round 3 (RR2-L2) --------------------------------------------------------


def test_dialog_when_on_close_runs_a_nested_event_loop_tick_then_no_teardown_in_dispatch():
    host, _, errors = _qt_host()
    view = QWidget()

    def on_close(applied):
        host.close()
        host._reaper.fire()  # a nested event-loop tick inside the click

    host.run_dialog(view, "Grow", "Apply", on_close)
    window = view.parent
    next(b for b in window.children if getattr(b, "text", "") == "Apply").click()
    assert VIOLATIONS == [] and not window.deleted, "nothing ran under the click"
    host._reaper.fire()  # the event loop after the click returned
    assert VIOLATIONS == [] and window.deleted and errors == []
    assert host._pending == [] and host._tokens == {}


def test_menu_when_callback_removes_itself_and_ticks_then_returns_without_spinning():
    host, _, errors = _qt_host()
    tokens, ticks = [], []

    def callback(sender):
        host.remove(tokens[0])
        ticks.append(len(host._pending))
        host._reaper.fire()  # nested tick: blocked work stays queued, once
        ticks.append(len(host._pending))

    tokens.append(host.register_menu("EDIT_MENU", NSMenuItem("Self", callback)))
    action = host._menu("EDIT_MENU").actions()[0]
    action.trigger()
    assert ticks == [1, 1], "the drain neither runs nor re-enqueues blocked work"
    assert host._reaper.active, "the outermost slot exit scheduled one drain"
    host._reaper.fire()
    assert host._menu("EDIT_MENU").actions() == [] and host._pending == []
    assert VIOLATIONS == [] and errors == []


def test_file_format_when_icon_names_bundle_resource_then_action_icon(tmp_path):
    resources = tmp_path / "Fmt.glyphsFileFormat/Contents/Resources"
    resources.mkdir(parents=True)
    (resources / "ExportIcon.png").write_bytes(b"x")
    namespace = {"__file__": str(resources / "plugin.py")}
    exec(  # noqa: S102 - a class defined in a plugin file's globals
        "class Fmt:\n"
        "    icon = 'ExportIcon'\n"
        "    def title(self):\n"
        "        return 'CSV'\n"
        "    def exportFont_(self, font):\n"
        "        pass\n",
        namespace,
    )
    host, _, _ = _qt_host()
    seen = []

    class Image:
        def initWithContentsOfFile_(self, path):
            seen.append(path)
            return self

        def icon(self):
            return "qicon"

    from fontlab_glyport.plugins import base

    original = base.image_class
    base.image_class = lambda qt, resources=(): type(
        "I", (), {"alloc": staticmethod(Image)}
    )
    try:
        host.register_file_format(namespace["Fmt"]())
    finally:
        base.image_class = original
    action = host._menu("FILE_MENU").actions()[-1]
    assert seen == [str(resources / "ExportIcon.png")]
    assert action.icon == "qicon"


def test_plugin_image_when_no_resource_then_none_and_nsimage_kept():
    from fontlab_glyport.plugins.base import plugin_image

    class Plain:
        def title(self):
            return "x"

    assert plugin_image(object(), Plain(), "Missing") is None
    ready = type("Ready", (), {"icon": lambda self: "q"})()
    assert plugin_image(object(), Plain(), ready) is ready


def test_filter_dialog_when_cancelled_then_complete_layer_state_restored():
    """Review R-merge P1, through the wired path: FilterWithDialog -> loader ->
    FontLabPluginHost -> ModelPluginAdapter -> model. Preview and Cancel must
    leave node selection, anchors (none added), width and shape order as they
    were; the path keeps its identity."""
    from fontlab_glyport.glyphsapp.fontlab_session import ModelPluginAdapter
    from fontlab_glyport.model import GSAnchor, GSNode, GSPath, Model
    from fontlab_glyport.model.fake_backend import FakeBackend
    from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
    from fontlab_glyport.plugins.loader import load_plugin

    backend = FakeBackend()
    model = Model(backend)
    font = model.font
    layer = font.glyphs["A"].layers[0]
    layer.anchors.append(GSAnchor("top", (10, 20)))
    # a second path after the component: shape order path, component, path
    layer.paths.append(
        GSPath([GSNode((5, 5)), GSNode((9, 5)), GSNode((9, 9))], closed=True)
    )
    layer.paths[1].nodes[1].selected = True
    backend.current_layer_data["font"] = (("A", "Regular"),)

    def state():
        return {
            "width": layer.width,
            "shapes": [type(s).__name__ for s in layer.shapes],
            "path_ids": [p.id for p in layer.paths],
            "nodes": [
                [(n.x, n.y, n.type, n.selected) for n in p.nodes] for p in layer.paths
            ],
            "anchors": sorted((a.name, a.x, a.y) for a in layer.anchors),
        }

    before = state()
    host, _, errors = _qt_host(model=ModelPluginAdapter(model))
    env = PluginEnv(host, {}, lambda e, s: errors.append(e), log=errors.append)
    plugins = make_plugins_module(env)

    class Grow(plugins.FilterWithDialog):
        def settings(self):
            self.menuName = "Grow"
            self.dialog = QWidget()

        def filter(self, layer, inEditView, customParameters):
            layer.width = layer.width + 100
            path = layer.paths[1]
            path.nodes[0].position = (6, 6)
            layer.paths.append(GSPath([GSNode((1, 1)), GSNode((2, 2))]))
            if layer.anchors["bottom"] is None:
                layer.anchors.append(GSAnchor("bottom", (0, 0)))
            layer.anchors["top"].position = (11, 21)

    handle = load_plugin(Grow, env)
    assert handle.status == "loaded", handle.error
    host._menu("FILTER_MENU").actions()[-1].trigger()  # opens the dialog, previews
    assert state()["width"] == before["width"] + 100, ("the preview ran", errors)
    window = handle.plugin.dialog.parent
    next(b for b in window.children if getattr(b, "text", None) == "Cancel").click()
    after = state()
    assert after == before, (before, after)
    assert errors == []


def _wired_filter_cancel(mutate, *, extra_path=False, backend_patch=None):
    """Run a FilterWithDialog whose filter() calls ``mutate(layer)`` through the
    wired path, Cancel it, and return (state before, state after, errors)."""
    from fontlab_glyport.glyphsapp.fontlab_session import ModelPluginAdapter
    from fontlab_glyport.model import GSNode, GSPath, Model
    from fontlab_glyport.model.fake_backend import FakeBackend
    from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
    from fontlab_glyport.plugins.loader import load_plugin

    backend = FakeBackend()
    model = Model(backend)
    layer = model.font.glyphs["A"].layers[0]
    for start in (5, 50) if extra_path else (5,):
        layer.paths.append(
            GSPath([GSNode((start, 5)), GSNode((9, 5)), GSNode((9, 9))], closed=True)
        )
    layer.paths[0].nodes[0].selected = True
    layer.paths[1].nodes[1].selected = True
    backend.current_layer_data["font"] = (("A", "Regular"),)
    if backend_patch:
        backend_patch(backend)

    def state():
        return {
            "width": layer.width,
            "shapes": [type(s).__name__ for s in layer.shapes],
            "nodes": [
                [(n.x, n.y, n.type, n.selected) for n in p.nodes] for p in layer.paths
            ],
        }

    before = state()
    host, _, errors = _qt_host(model=ModelPluginAdapter(model))
    env = PluginEnv(host, {}, lambda e, s: errors.append(e), log=errors.append)
    plugins = make_plugins_module(env)

    class Edit(plugins.FilterWithDialog):
        def settings(self):
            self.menuName = "Edit"
            self.dialog = QWidget()

        def filter(self, layer, inEditView, customParameters):
            mutate(layer)

    handle = load_plugin(Edit, env)
    assert handle.status == "loaded", handle.error
    host._menu("FILTER_MENU").actions()[-1].trigger()
    window = handle.plugin.dialog.parent
    next(b for b in window.children if getattr(b, "text", None) == "Cancel").click()
    return before, state(), errors


def _remove_path(index):
    def mutate(layer):
        layer.paths.remove(layer.paths[index])

    return mutate


def _insert_then_delete(layer):
    from fontlab_glyport.model import GSNode, GSPath

    layer.paths.append(GSPath([GSNode((1, 1)), GSNode((2, 2))]))
    layer.paths.remove(layer.paths[0])


@pytest.mark.parametrize(
    "mutate, extra_path",
    [
        (_remove_path(0), False),  # RR-merge P1: [path, component, path]
        (_remove_path(-1), False),
        (_remove_path(1), True),  # middle of [path, component, path, path]
        (_insert_then_delete, False),
    ],
    ids=["delete-first", "delete-last", "delete-middle", "insert-then-delete"],
)
def test_filter_cancel_when_preview_deleted_paths_then_order_and_selection_restored(
    mutate, extra_path
):
    """Review RR-merge P1: a preview that deletes paths is undone by Cancel
    with every path back at its shape index (components included) and its
    node selection restored."""
    before, after, errors = _wired_filter_cancel(mutate, extra_path=extra_path)
    assert after == before, (before, after)
    assert errors == []


def test_filter_cancel_when_exact_restore_impossible_then_error_reported():
    """If the restored layer cannot equal the snapshot, Cancel reports it."""

    def lossy(backend):
        insert = backend.insert_path

        def without_selection(layer_id, index, path):
            from dataclasses import replace

            nodes = tuple(replace(n, selected=False) for n in path.nodes)
            return insert(layer_id, index, replace(path, nodes=nodes))

        backend.insert_path = without_selection

    _, _, errors = _wired_filter_cancel(_remove_path(0), backend_patch=lossy)
    assert any("restore" in str(e) for e in errors), errors


def test_has_callbacks_when_app_property_overridden_then_public_property_used():
    class Host(FontLabPluginHost):
        @property
        def has_items(self):
            return True
    host = Host(object(), object(), error_sink=lambda e, s: None)
    assert host.has_callbacks, "callback state must use App's public property"


def test_remove_when_public_dispatching_true_then_cleanup_waits():
    class Host(FontLabPluginHost):
        @property
        def dispatching(self):
            return True
    host = Host(object(), object(), error_sink=lambda e, s: None)
    called = []
    host._cleanups[99] = lambda: called.append(99)
    host.remove(99)
    assert called == [] and 99 in host._cleanups
