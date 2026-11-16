# this_file: tests/test_issue106_next_gaps.py
"""Next ranked gaps against fake backends and existing menu/control doubles."""

from types import SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from ui_doubles import QPushButton, make_qt
from ui_doubles_session import make_session

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend


def test_font_filepath_when_unsaved_saved_and_closed_then_live_values_or_stale():
    backend = FakeBackend()
    font = Model(backend).font
    assert font.filepath is None
    backend.font_paths["font"] = "/tmp/example.vfj"
    assert font.filepath == "/tmp/example.vfj"
    backend.font_paths["font"] = "/tmp/renamed.vfj"
    assert font.filepath == "/tmp/renamed.vfj"
    backend.close_font("font")
    with pytest.raises(StaleNativeObject):
        _ = font.filepath


def test_font_filepath_when_native_adapter_reads_then_uses_only_package_filename(
    monkeypatch,
):
    backend = FontLabBackend(packages=[])
    package = SimpleNamespace(fileName="/tmp/owned.vfj")
    monkeypatch.setattr(backend, "_object", lambda token: package)
    assert backend.font_path("font") == "/tmp/owned.vfj"
    package.fileName = ""
    assert backend.font_path("font") is None


def test_register_defaults_when_existing_values_then_preserved_and_new_values_added():
    store = {"org.example.existing": False}
    module = make_glyphsapp_module(
        Model(FakeBackend()),
        FakeGlyphsBridge(),
        defaults=store,
        error_sink=lambda *args: None,
    )
    module.Glyphs.registerDefaults({"org.example.existing": True, "org.example.new": 3})
    assert store == {"org.example.existing": False, "org.example.new": 3}
    with pytest.raises(TypeError):
        module.Glyphs.registerDefaults([("org.example.invalid", 1)])


def test_legacy_menu_item_when_imported_then_target_action_and_alias_share_existing_menu_behavior(
    tmp_path,
):
    ctx, _ = make_session(tmp_path)
    with ctx:
        ui = ctx.import_module("GlyphsApp.UI")
        glyphs = ctx.import_module("GlyphsApp")
        cocoa = ctx.import_module("AppKit")
        assert glyphs.NSMenuItem is cocoa.NSMenuItem
        calls = []
        target = SimpleNamespace(run_=calls.append)
        item = ui.MenuItem("Example", action="run:", target=target)
        item.fire()
        assert item.title() == "Example" and calls == [item]
    ctx.close()


@pytest.mark.parametrize(
    ("key", "modifiers", "expected"),
    [
        ("k", ["command"], "Ctrl+k"),
        ("uparrow", ["option", "shift"], "Alt+Shift+Up"),
        ("\r", [], "Return"),
        ("\x1b", [], "Escape"),
        ("x", ["control"], "Meta+x"),
        ("x", None, "x"),
    ],
)
def test_button_bind_when_keys_and_modifiers_then_qt_shortcut_set(
    key, modifiers, expected
):
    from fontlab_glyport.ui.vanilla import make_vanilla_module

    class ButtonWidget(QPushButton):
        def setShortcut(self, value):
            self.shortcut = value

    qt = make_qt()
    qt.QtGui.QPushButton = ButtonWidget
    qt.QtGui.QKeySequence = str
    vanilla = make_vanilla_module(qt, error_sink=lambda *args: None)
    button = vanilla.Button((0, 0, 80, 20), "Run")
    button.bind(key, modifiers)
    assert button.getNSView().shortcut == expected
    with pytest.raises(UnsupportedCapability):
        button.bind("x", ["capslock"])
    button._retire()


def test_modifier_constants_when_imported_then_existing_event_bits_are_exported(
    tmp_path,
):
    ctx, _ = make_session(tmp_path)
    with ctx:
        kit = ctx.import_module("AppKit")
        assert kit.NSEventModifierFlagOption == 1 << 19
        assert kit.NSEventModifierFlagCommand == 1 << 20
        assert kit.NSEventModifierFlagShift == 1 << 17
        assert kit.NSEventModifierFlagControl == 1 << 18
    ctx.close()
