# this_file: tests/test_plugins.py
"""The seven SDK plugin protocols over an in-memory host (R025-R027)."""

from pathlib import Path

import pytest
from plugin_doubles import FakeHost, Layer
from test_ui_nib_image import PixLabel, Pixmap
from ui_doubles import make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.loader import load_plugin
from fontlab_glyport.plugins.menus import AppMenu
from fontlab_glyport.ui.cocoa import NSSize
from fontlab_glyport.ui.cocoa_menu import NSMenuItem, NSOffState, NSOnState
from fontlab_glyport.ui.cocoa_views import make_appkit_classes

NIB_FIXTURES = Path(__file__).parent / "fixtures" / "nib"


@pytest.fixture
def setup():
    host = FakeHost([Layer("A", ["p1"]), Layer("B", ["p2"])])
    errors = []
    appkit = make_appkit_classes(make_qt(), error_sink=print)
    env = PluginEnv(host, appkit, lambda e, s: errors.append(e), log=errors.append)
    return host, env, make_plugins_module(env), errors


def test_module_when_made_then_exports_seven_classes_and_helpers(setup):
    _, _, plugins, _ = setup
    assert set(plugins.__all__) == {
        "GeneralPlugin",
        "FilterWithoutDialog",
        "FilterWithDialog",
        "PalettePlugin",
        "ReporterPlugin",
        "SelectTool",
        "FileFormatPlugin",
        "setUpMenuHelper",
        "pathForResource",
    }


def test_general_plugin_when_loaded_then_settings_start_and_menu_unload(setup):
    host, env, plugins, _ = setup
    menu = AppMenu(host)
    order = []

    class Tools(plugins.GeneralPlugin):
        def settings(self):
            order.append("settings")
            self.name = "Tools"

        def start(self):
            order.append("start")
            menu["EDIT_MENU"].append(NSMenuItem("Do It", self.doIt_))

        def doIt_(self, sender):
            order.append(("do", sender.title()))

    handle = load_plugin(Tools, env)
    assert (handle.status, handle.kind, order) == (
        "loaded",
        "GeneralPlugin",
        ["settings", "start"],
    )
    (entry,) = host.entries("menu")
    assert entry[1] == "EDIT_MENU" and entry[2].title() == "Do It"
    entry[2].fire()
    assert order[-1] == ("do", "Do It")
    menu.close()
    menu.close()
    assert host.entries("menu") == [] and len(host.removed) == 1


def test_app_menu_when_unknown_or_index_then_errors(setup):
    host = setup[0]
    menu = AppMenu(host)
    with pytest.raises(KeyError):
        menu["NOPE_MENU"]
    with pytest.raises(UnsupportedCapability):
        menu[3]


def test_filter_without_dialog_when_run_then_selected_layers_in_one_undo(setup):
    host, env, plugins, _ = setup

    class Reverse(plugins.FilterWithoutDialog):
        def settings(self):
            self.menuName = "Reverse"
            self.keyboardShortcut = "r"

        def filter(self, layer, inEditView, customParameters):
            layer.paths.append(("rev", inEditView))

    handle = load_plugin(Reverse, env)
    (entry,) = host.entries("menu")
    assert entry[1] == "FILTER_MENU" and entry[2].keyEquivalent() == "r"
    entry[2].fire()
    assert [layer.paths for layer in host.layers] == [
        ["p1", ("rev", True)],
        ["p2", ("rev", True)],
    ]
    assert host.log[:2] == [("undo-begin", "Reverse"), ("undo-end", "Reverse")]
    plugin = handle.plugin
    plugin.processLayer_withArguments_(host.layers[0], ["Reverse", "width:12", "x"])
    assert plugin.title() == "Reverse"


def test_filter_without_dialog_when_custom_parameters_then_parsed(setup):
    host, env, plugins, _ = setup
    seen = []

    class Offset(plugins.FilterWithoutDialog):
        def filter(self, layer, inEditView, customParameters):
            seen.append((inEditView, customParameters))

    handle = load_plugin(Offset, env)
    handle.plugin.processLayer_withArguments_(
        host.layers[0], ["Offset", "width:12", "abc", "3"]
    )
    assert seen == [(False, {"width": 12.0, 0: "abc", 1: 3.0})]


def test_filter_with_dialog_when_preview_and_cancel_then_layers_restored(setup):
    host, env, plugins, _ = setup

    class Grow(plugins.FilterWithDialog):
        def settings(self):
            self.menuName = "Grow"
            self.amount = 1
            self.dialog = "the-view"

        def filter(self, layer, inEditView, customParameters):
            layer.paths.append(("grow", self.amount))

        def setAmount_(self, sender):
            self.amount = sender
            self.update()

    handle = load_plugin(Grow, env)
    (entry,) = host.entries("menu")
    assert entry[2].title() == "Grow…"
    entry[2].fire()
    dialog = host.dialogs[0]
    assert (dialog["view"], dialog["title"], dialog["apply"]) == (
        "the-view",
        "Grow",
        "Apply",
    )
    assert host.layers[0].paths == ["p1", ("grow", 1)], "setup() previews once"
    handle.plugin.setAmount_(5)
    assert host.layers[0].paths == ["p1", ("grow", 5)], (
        "each preview starts from the snapshot"
    )
    dialog["close"](False)
    assert [layer.paths for layer in host.layers] == [["p1"], ["p2"]]
    assert ("undo-end", "Grow") in host.log and handle.plugin.layers == ()


def test_filter_with_dialog_when_applied_then_result_kept(setup):
    host, env, plugins, _ = setup

    class Mark(plugins.FilterWithDialog):
        def settings(self):
            self.dialog = "owned-view"

        def filter(self, layer, inEditView, customParameters):
            layer.paths.append("m")

    load_plugin(Mark, env)
    host.entries("menu")[0][2].fire()
    host.dialogs[0]["close"](True)
    assert host.layers[0].paths == ["p1", "m"]


def test_filter_with_dialog_when_load_nib_then_owner_outlets_and_view(setup, tmp_path):
    _, env, plugins, _ = setup
    resources = tmp_path / "Demo.glyphsFilter" / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "IBdialog.xib").write_bytes(
        (NIB_FIXTURES / "DemoDialog.xib").read_bytes()
    )
    plugin_file = str(resources / "plugin.py")

    class DemoFilter(plugins.FilterWithDialog):
        def settings(self):
            self.menuName = "Demo"
            self.loadNib("IBdialog", plugin_file)

    handle = load_plugin(DemoFilter, env)
    plugin = handle.plugin
    assert handle.status == "loaded", handle.error
    assert type(plugin.dialog).__name__ == "GSPaletteView"
    assert plugin.widthField.stringValue() == "12"
    assert plugin.topLevelObjects[0] is plugin.dialog


def test_load_nib_when_missing_then_logged_not_raised(setup, tmp_path):
    _, env, plugins, errors = setup

    class Broken(plugins.GeneralPlugin):
        def settings(self):
            self.loadNib("Nope", str(tmp_path / "Contents" / "Resources" / "plugin.py"))

    assert load_plugin(Broken, env).status == "loaded"
    assert any("Error loading nib Nope" in str(e) for e in errors)


def test_palette_when_loaded_then_panel_with_view_and_heights(setup):
    host, env, plugins, _ = setup
    view = env.appkit["GSPaletteView"].alloc().initWithFrame_(((0, 0), (160, 80)))

    class Pal(plugins.PalettePlugin):
        def settings(self):
            self.name = "Pal"
            self.dialog = view

    handle = load_plugin(Pal, env)
    (panel,) = host.entries("panel")
    assert panel[1:] == (view, "Pal", 80, 80)
    handle.plugin.setCurrentHeight_(80)
    assert handle.plugin.currentHeight() == 80
    handle.unload()
    handle.unload()
    assert host.entries("panel") == [] and handle.status == "unloaded"


def test_reporter_when_toggled_then_painters_follow_hooks(setup):
    host, env, plugins, _ = setup
    drawn = []

    class Rep(plugins.ReporterPlugin):
        def settings(self):
            self.menuName = "Marks"

        def foreground(self, layer):
            drawn.append(("fg", layer.name, self.getScale()))

        def inactiveLayerBackground(self, layer):
            drawn.append(("inactive-bg", layer.name))

    handle = load_plugin(Rep, env)
    (toggle,) = host.entries("menu")
    assert toggle[1] == "VIEW_MENU" and toggle[2].title() == "Show Marks"
    toggle[2].fire()
    assert toggle[2].state() == NSOnState
    phases = sorted((e[1], e[3]) for e in host.entries("painter"))
    assert phases == [
        ("after_native_layer", "active"),
        ("before_native_layer", "inactive"),
    ]
    host.paint("after_native_layer", host.layers[0], scale=3.0)
    host.paint("before_native_layer", host.layers[1], layer_filter="inactive")
    assert drawn == [("fg", "A", 3.0), ("inactive-bg", "B")]
    toggle[2].fire()
    assert host.entries("painter") == []
    handle.unload()
    assert host.registered == {}


def test_reporter_when_host_lacks_background_then_diagnostic_and_foreground_kept(setup):
    host, env, plugins, _ = setup

    class Both(plugins.ReporterPlugin):
        def foreground(self, layer):
            pass

        def background(self, layer):
            raise RuntimeError("boom")

    original = host.register_painter

    def register(phase, callback, **kw):
        if phase == "before_native_layer":
            raise UnsupportedCapability(
                "no hook", capability="host.before_native_layer"
            )
        return original(phase, callback, **kw)

    host.register_painter = register
    handle = load_plugin(Both, env)
    host.entries("menu")[0][2].fire()
    assert [e[1] for e in host.entries("painter")] == [
        "after_native_layer",
        "after_native_layer",
    ]
    assert "REPORTER_BACKGROUND_AS_OVERLAY" in handle.diagnostics[0]
    assert "background drawn as overlay" in handle.diagnostics[0]


def test_reporter_when_hook_raises_then_sink_not_host(setup):
    host, env, plugins, errors = setup

    class Bad(plugins.ReporterPlugin):
        def foreground(self, layer):
            raise RuntimeError("bad paint")

    load_plugin(Bad, env)
    host.entries("menu")[0][2].fire()
    host.paint("after_native_layer", host.layers[0])
    assert [str(e) for e in errors] == ["bad paint"]


def test_select_tool_when_host_has_no_tools_then_diagnostic(setup):
    host, env, plugins, _ = setup
    host.unsupported.add("tool")

    class Tool(plugins.SelectTool):
        def settings(self):
            self.name = "Knife"

    handle = load_plugin(Tool, env)
    assert handle.status == "loaded" and handle.diagnostics == ["tool: no tool"]
    assert handle.plugin.title() == "Knife"


def test_file_format_when_exported_then_host_notified(setup):
    host, env, plugins, _ = setup

    class Fmt(plugins.FileFormatPlugin):
        def settings(self):
            self.name = "CSV"

        def export(self, font):
            return True, f"wrote {font}"

    handle = load_plugin(Fmt, env)
    (entry,) = host.entries("file_format")
    assert entry[1] is handle.plugin
    handle.plugin.exportFont_(host.current_font())
    assert host.log[-1] == ("notify", "CSV: Export done", "wrote font")


def test_load_when_start_raises_then_failed_and_registrations_removed(setup):
    host, env, plugins, _ = setup
    menu = AppMenu(host)

    class Half(plugins.FilterWithoutDialog):
        def start(self):
            raise ValueError("half way")

    handle = load_plugin(Half, env)
    assert handle.status == "failed" and str(handle.error) == "half way"
    assert host.registered == {}
    menu.close()


def test_load_when_not_a_plugin_then_type_error(setup):
    with pytest.raises(TypeError):
        load_plugin(int, setup[1])


def test_set_up_menu_helper_and_path_for_resource(setup, tmp_path):
    _, _, plugins, _ = setup
    from fontlab_glyport.ui.cocoa_menu import NSMenu

    menu = NSMenu.alloc().init()
    target = object()
    plugins.setUpMenuHelper(
        menu,
        [
            {"name": "One", "action": "one:"},
            {"name": "Zero", "action": "z:", "index": 0},
        ],
        target,
    )
    assert [i.title() for i in menu.itemArray()] == ["Zero", "One"]
    assert menu.itemArray()[0].target() is target
    resources = tmp_path / "X.glyphsPlugin" / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "icon.pdf").write_bytes(b"%PDF")
    path = str(resources / "plugin.py")
    assert plugins.pathForResource("icon", "pdf", path) == str(resources / "icon.pdf")
    assert plugins.pathForResource("none", "pdf", path) is None


def test_guard_when_wrap_given_then_menu_and_paint_callbacks_wrapped(setup):
    host, env, plugins, _ = setup
    wrapped = []

    def wrap(function):
        def run(*args):
            wrapped.append(getattr(function, "__name__", "?"))
            return function(*args)

        return run

    env.wrap = wrap

    class Rep(plugins.ReporterPlugin):
        def foreground(self, layer):
            pass

    load_plugin(Rep, env)
    host.entries("menu")[0][2].fire()
    host.paint("after_native_layer", host.layers[0])
    assert "toggle" in wrapped and "drawForegroundForLayer_options_" in wrapped


def test_reload_when_unloaded_then_no_duplicate_menus_or_painters(setup):
    host, env, plugins, _ = setup
    env.menu = AppMenu(host)

    class Gen(plugins.GeneralPlugin):
        def start(self):
            env.menu["WINDOW_MENU"].append(NSMenuItem("Open", lambda s: None))

    class Rep(plugins.ReporterPlugin):
        def foreground(self, layer):
            pass

    for _ in range(2):
        handles = [load_plugin(Gen, env), load_plugin(Rep, env)]
        toggle = next(
            m for m in host.entries("menu") if m[2].title() == "Show New ReporterPlugin"
        )
        toggle[2].fire()
        assert len(host.entries("menu")) == 2 and len(host.entries("painter")) == 1
        for handle in handles:
            handle.unload()
        assert host.registered == {}, "unload alone removes everything"
    assert host.registered == {}


# --- review fixes (R-L2-review) ------------------------------------------------


def test_unload_when_filter_dialog_open_then_cancelled_and_restored(setup):
    host, env, plugins, _ = setup

    class Grow(plugins.FilterWithDialog):
        def settings(self):
            self.dialog = "owned-view"

        def filter(self, layer, inEditView, customParameters):
            layer.paths.append("g")

    handle = load_plugin(Grow, env)
    menu_item = host.entries("menu")[0][2]
    menu_item.fire()
    menu_item.fire()
    assert len(host.dialogs) == 1, "one dialog session per plugin instance"
    assert host.layers[0].paths == ["p1", "g"]
    handle.unload()
    assert host.layers[0].paths == ["p1"], "unload cancels the open dialog"
    assert ("undo-end", "My Filter") in host.log and host.registered == {}


def test_general_plugin_menus_when_unloaded_then_removed_with_the_plugin(setup):
    host, env, plugins, _ = setup
    env.menu = AppMenu(host)

    class Gen(plugins.GeneralPlugin):
        def start(self):
            env.menu["EDIT_MENU"].append(NSMenuItem("One", lambda s: None))

    handle = load_plugin(Gen, env)
    assert len(host.entries("menu")) == 1
    handle.unload()
    assert host.registered == {}, "no separate AppMenu.close() needed"
    env.menu.close()


def test_failed_start_when_menu_already_added_then_rolled_back(setup):
    host, env, plugins, _ = setup
    env.menu = AppMenu(host)

    class Half(plugins.GeneralPlugin):
        def start(self):
            env.menu["EDIT_MENU"].append(NSMenuItem("Added", lambda s: None))
            raise ValueError("half way")

    handle = load_plugin(Half, env)
    assert handle.status == "failed" and host.registered == {}


def test_app_menu_when_wrap_given_then_item_callbacks_wrapped(setup):
    host, _, _, _ = setup
    seen = []

    def wrap(function):
        def run(*args):
            seen.append("wrapped")
            return function(*args)

        return run

    menu = AppMenu(host, wrap=wrap)
    menu["EDIT_MENU"].append(
        NSMenuItem("Go", lambda sender: seen.append(sender.title()))
    )
    host.entries("menu")[0][2].fire()
    assert seen == ["wrapped", "Go"]


def test_file_format_when_registered_then_guard_passed(setup):
    host, env, plugins, _ = setup

    class Fmt(plugins.FileFormatPlugin):
        pass

    load_plugin(Fmt, env)
    (entry,) = host.entries("file_format")
    assert entry[2] == env.guard


def test_unload_when_painter_removal_fails_then_rest_still_removed(setup):
    host, env, plugins, _ = setup

    class Rep(plugins.ReporterPlugin):
        def foreground(self, layer):
            pass

    handle = load_plugin(Rep, env)
    host.entries("menu")[0][2].fire()
    original = host.remove

    def remove(token):
        if host.registered.get(token, ("",))[0] == "painter":
            raise RuntimeError("painter stuck")
        original(token)

    host.remove = remove
    with pytest.raises(RuntimeError):
        handle.unload()
    assert host.entries("menu") == [] and handle.status == "unloaded"


def test_palette_when_unloaded_then_nib_views_disposed(setup, tmp_path):
    _, env, plugins, _ = setup
    resources = tmp_path / "P.glyphsPalette" / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "IBdialog.xib").write_bytes(
        (NIB_FIXTURES / "DemoDialog.xib").read_bytes()
    )
    path = str(resources / "plugin.py")

    class Pal(plugins.PalettePlugin):
        def settings(self):
            self.loadNib("IBdialog", path)

    handle = load_plugin(Pal, env)
    view, field = handle.plugin.dialog, handle.plugin.widthField
    handle.unload()
    assert view._qt._deleted and field._qt._deleted
    assert view not in env.appkit["NSView"]._env.views


def test_palette_when_the_view_comes_from_the_view_method_then_disposed(setup):
    _, env, plugins, _ = setup
    view = env.appkit["GSPaletteView"].alloc().initWithFrame_(((0, 0), (100, 40)))
    button = env.appkit["NSButton"].alloc().initWithFrame_(((0, 0), (50, 20)))
    view.addSubview_(button)

    class Pal(plugins.PalettePlugin):
        def theView(self):
            return view

    handle = load_plugin(Pal, env)
    handle.unload()
    assert view._qt._deleted and button._slots == []
    assert view not in env.appkit["NSView"]._env.views


def test_general_plugin_menus_when_env_wrap_then_callbacks_wrapped(setup):
    host, env, plugins, _ = setup
    env.menu, seen = AppMenu(host), []

    def wrap(function):
        def run(*args):
            seen.append("wrapped")
            return function(*args)

        return run

    env.wrap = wrap

    class Gen(plugins.GeneralPlugin):
        def start(self):
            env.menu["EDIT_MENU"].append(NSMenuItem("Go", self.go_))

        def go_(self, sender):
            seen.append("go")

    load_plugin(Gen, env)
    host.entries("menu")[0][2].fire()
    assert seen == ["wrapped", "go"]


def test_file_format_when_host_follows_the_contract_then_loads(setup):
    import inspect

    from fontlab_glyport.plugins.host import PluginHost

    assert setup
    parameters = inspect.signature(PluginHost.register_file_format).parameters
    assert "guard" in parameters, "the contract declares the guard keyword"


def test_load_nib_when_image_view_then_bundle_image_found(setup, tmp_path):
    _, env, plugins, _ = setup
    resources = tmp_path / "Demo.glyphsPalette" / "Contents" / "Resources"
    resources.mkdir(parents=True)
    for name in ("Image.xib", "Dot.png"):
        (resources / name).write_bytes((NIB_FIXTURES / name).read_bytes())
    found = []

    class Image(env.appkit["NSObject"]):
        def initWithContentsOfFile_(self, path):
            found.append(Path(path).name)
            return self

        def size(self):
            return NSSize(16, 8)

        def pixmap(self, scale=1.0):
            return Pixmap(scale)

    env.appkit["NSImage"] = Image
    qt = env.appkit["NSView"]._env.qt  # image views draw with pixmaps
    qt.QtGui.QLabel, qt.QtCore.Qt.AlignCenter = PixLabel, 0x84
    qt.QtCore.Qt.IgnoreAspectRatio = qt.QtCore.Qt.SmoothTransformation = 0
    logs = []

    class Demo(plugins.GeneralPlugin):
        def settings(self):
            self.logToConsole = logs.append
            self.loadNib("Image", str(resources / "plugin.py"))

    handle = load_plugin(Demo, env)
    assert handle.status == "loaded", handle.error
    assert found == ["Dot.png", "Dot.png"], "both image views found the bundle image"
    assert any("image NoSuchImage not found" in m for m in logs)
    assert not any("image Dot not found" in m for m in logs)


def test_reporter_context_menus_when_loaded_then_view_menu_options_follow_state(setup):
    """R049 reporter (CJK Metrics): generalContextMenus become VIEW_MENU items
    after the toggle (FontLab has no Python hook into the editor's context
    menu): a header without action is disabled, actions run with their state
    re-read from the rebuilt list, and a 'view' entry toggles a panel."""
    host, env, plugins, errors = setup
    view = object()

    class Rep(plugins.ReporterPlugin):
        def settings(self):
            self.menuName = "Grid"
            self.axes = True
            self.generalContextMenus = self.menus()

        def menus(self):
            return [
                {"name": "Grid Options:", "action": None},
                {"name": "Show Axes", "action": self.toggle, "state": self.axes},
                {"view": view},
            ]

        def toggle(self):
            self.axes = not self.axes
            self.generalContextMenus = self.menus()

    handle = load_plugin(Rep, env)
    assert handle.status == "loaded", (handle.error, errors)
    items = [e[2] for e in host.entries("menu")]
    assert [i.title() for i in items] == [
        "Show Grid",
        "Grid Options:",
        "Show Axes",
        "Grid Settings…",
    ]
    assert not items[1].isEnabled() and items[2].state() == NSOnState
    items[2].fire()
    assert handle.plugin.axes is False and items[2].state() == NSOffState
    items[3].fire()
    (panel,) = host.entries("panel")
    assert panel[1] is view and panel[2] == "Grid Settings"
    items[3].fire()
    assert host.entries("panel") == []
    handle.unload()
    assert host.registered == {}
