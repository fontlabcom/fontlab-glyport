# this_file: tests/test_issue106_round8_ui.py
"""Cocoa and vanilla round-eight APIs over Qt-shaped doubles."""

from types import SimpleNamespace as NS

import pytest
from plugin_doubles import FakeHost
from ui_doubles import QWidget, make_qt
from ui_doubles_session import make_session

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
from fontlab_glyport.plugins.loader import load_plugin
from fontlab_glyport.ui.cocoa_alert import alert_class
from fontlab_glyport.ui.cocoa_views import make_appkit_classes


def test_f38_imports_boxed_points_and_helpers(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        kit, foundation, ga = (
            ctx.import_module(name) for name in ("AppKit", "Foundation", "GlyphsApp")
        )
        assert (
            kit.NSMiniControlSize,
            kit.NSEventMaskFlagsChanged,
            kit.NSDeviceWhiteColorSpace,
        ) == (2, 1 << 12, "NSDeviceWhiteColorSpace")
        value = foundation.NSValue.valueWithPoint_((3, 7))
        assert value.pointValue().x == 3 and value.pointValue().y == 7
        assert foundation.NSValue.valueWithRect_(((1, 2), (3, 4))).rectValue() == (
            (1, 2),
            (3, 4),
        )
        with pytest.raises(UnsupportedCapability):
            value.rectValue()
        assert ga.TTF == "TTF"
        assert ga.subtractPoints((4, 9), (1, 3)) == (3, 6)
        assert ga.addPoints((4, 9), (1, 3)) == (5, 12)
        assert ga.scalePoint((4, 9), 0.5) == (2, 4.5)
        assert ga.GSAlignmentZone(700, 10).position == 700
    ctx.close()


def test_f39_vanilla_base_subclass_and_f16_f19_precise_refusals(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        v = ctx.import_module("vanilla")
        base = ctx.import_module("vanilla.vanillaBase")
        assert base.VanillaBaseObject is v.VanillaBaseObject

        class Custom(base.VanillaBaseControl):
            def __init__(self):
                self._setupView(ctx.import_module("AppKit").NSView, (0, 0, 40, 20))

        assert isinstance(Custom().getNSView(), QWidget)
        with pytest.raises(UnsupportedCapability) as error:
            v.Drawer((200, 100))
        assert error.value.capability == "vanilla.Drawer"
        test = ctx.import_module("vanilla.test.testAll").Test
        with pytest.raises(UnsupportedCapability) as error:
            test()
        assert error.value.capability == "vanilla.test.Test"
    ctx.close()


@pytest.mark.parametrize("raw_view", [False, True])
def test_f39_popover_is_anchored_reusable_and_disposed_with_owner(
    tmp_path, monkeypatch, raw_view
):
    ctx, session = make_session(tmp_path)
    session.qt.QtCore.QPoint = lambda x, y: NS(x=lambda: x, y=lambda: y)
    monkeypatch.setattr(QWidget, "mapToGlobal", lambda self, p: p, raising=False)
    monkeypatch.setattr(QWidget, "rect", lambda self: self.geometry, raising=False)
    monkeypatch.setattr(
        QWidget,
        "move",
        lambda self, x, y: self.setGeometry(
            x, y, self.geometry.width(), self.geometry.height()
        ),
        raising=False,
    )
    with ctx:
        v = ctx.import_module("vanilla")
        window = v.Window((300, 200))
        window.button = v.Button((10, 20, 80, 20), "Open")
        window.open()
        pop = v.Popover((100, 50))
        pop.label = v.TextBox((0, 0, 80, 20), "Content")
        anchor = window.button.getNSView() if raw_view else window.button
        pop.open(anchor, preferredEdge="bottom", relativeRect=((0, 0), (80, 20)))
        assert pop._view.geometry.y() == 20 and pop._view.isVisible()
        pop.close()
        assert not pop._view.isVisible() and not pop._closed
        pop.open(anchor, preferredEdge="right", relativeRect=((0, 0), (80, 20)))
        assert pop._view.geometry.x() == 80
        window.close()
        assert pop._closed and pop._view._deleted
    ctx.close()


def test_f39_never_opened_popover_is_disposed_at_context_close(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        pop = ctx.import_module("vanilla").Popover((100, 50))
    ctx.close()
    assert pop._closed and pop._view._deleted


def test_f41_reporter_private_draw_name_does_not_shadow_dispatch_and_f24_controller():
    font = Model(FakeBackend()).font
    tab = font.newTab("/A")
    layer = font.glyphs[0].layers[0]
    host = FakeHost([layer])
    host.current_font = lambda: font
    seen, errors = [], []
    env = PluginEnv(
        host,
        make_appkit_classes(make_qt(), error_sink=print),
        lambda e, sender: errors.append(e),
    )
    plugins = make_plugins_module(env)

    class Reporter(plugins.ReporterPlugin):
        def _draw(self, layer):
            seen.append(layer.parent)

        def foreground(self, layer):
            assert self.controller._tab_id == tab._tab_id
            assert self.controller().className() == "GSEditViewController"
            self._draw(layer)

        background = foreground
        inactiveLayerForeground = foreground
        inactiveLayerBackground = foreground

    handle = load_plugin(Reporter, env)
    assert handle.status == "loaded"
    host.entries("menu")[0][2].fire()
    for kind, phase in [
        ("active", "after_native_layer"),
        ("active", "before_native_layer"),
        ("inactive", "after_native_layer"),
        ("inactive", "before_native_layer"),
    ]:
        host.paint(phase, layer, layer_filter=kind)
    assert not errors
    assert seen == [layer.parent] * 4
    handle.unload()


def test_f42_edittext_nil_raises_without_changing_text(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        field = ctx.import_module("vanilla").EditText((0, 0, 80, 20), "80")
        with pytest.raises(TypeError):
            field.set(None)
        assert field.get() == "80"
    ctx.close()


def test_f43_alert_injected_answer_accessory_and_no_implicit_modal(tmp_path):
    ctx, session = make_session(tmp_path)
    session.bridge.answers = {}
    with ctx:
        kit = ctx.import_module("AppKit")
        alert = kit.NSAlert.alloc().init()
        alert.setMessageText_("Choose master")
        alert.setInformativeText_("Choose source")
        alert.setAlertStyle_(kit.NSAlertStyleWarning)
        button = alert.addButtonWithTitle_("Use")
        alert.addButtonWithTitle_("Cancel")
        popup = kit.NSPopUpButton.alloc().initWithFrame_(((0, 0), (100, 20)))
        popup.addItemsWithTitles_(["One", "Two"])
        alert.setAccessoryView_(popup)

        def answer(current):
            current.accessoryView().selectItemAtIndex_(1)
            return 0

        session.bridge.answers["alert"] = answer
        assert alert.runModal() == 1000 and popup.indexOfSelectedItem() == 1
        assert alert.buttons().count() == 2 and alert.buttons()[0] is button
        assert (
            alert.messageText() == "Choose master"
            and alert.informativeText() == "Choose source"
        )
        session.bridge.answers["alert"] = 1001
        assert alert.runModal() == kit.NSAlertSecondButtonReturn == 1001
        assert kit.NSAlertThirdButtonReturn == 1002
        session.bridge.answers["alert"] = 9
        with pytest.raises(ValueError):
            alert.runModal()
        session.bridge.answers.clear()
        with pytest.raises(UnsupportedCapability) as error:
            alert.runModal()
        assert error.value.capability == "NSAlert.runModal"
    ctx.close()


def test_f43_modal_double_retains_accessory_and_button_widgets_after_dialog_delete():
    qt = make_qt()

    class Box(QWidget):
        Warning, Information, Critical, AcceptRole = 0, 1, 2, 0

        def __init__(self):
            super().__init__()
            self.buttons = []
            self.added_accessory = None

        def setText(self, value):
            pass

        setInformativeText = setIcon = setText

        def addButton(self, button, role):
            button.setParent(self)
            self.buttons.append(button)

        def layout(self):
            return self

        def rowCount(self):
            return 1

        def columnCount(self):
            return 3

        def addWidget(self, widget, *args):
            widget.setParent(self)
            self.added_accessory = widget

        def exec(self):
            pass

        def clickedButton(self):
            return self.buttons[1]

        def deleteLater(self):
            assert self.added_accessory.parentWidget() is None
            assert all(button.parentWidget() is None for button in self.buttons)
            super().deleteLater()

    qt.QtGui.QMessageBox = Box
    appkit = make_appkit_classes(qt, error_sink=print)
    Alert = alert_class(qt, appkit["NSButton"], answers={}, interactive=True)
    alert = Alert.alloc().init()
    alert.addButtonWithTitle_("Yes")
    alert.addButtonWithTitle_("No")
    accessory = QWidget()
    alert.setAccessoryView_(accessory)
    assert alert.runModal() == 1001
    assert not accessory._deleted
    assert all(not button._qt._deleted for button in alert.buttons())


def test_lows_alloc_event_flags_cosmetic_styles_and_f44_textbox_font_color(
    tmp_path, monkeypatch
):
    from drawing_doubles import QColor, QFont

    class Font(QFont):
        def setPointSizeF(self, size):
            self.points = size

    class Palette:
        Base, Window = "Base", "Window"

        def __init__(self):
            self.colors = {}

        def setColor(self, role, color):
            self.colors[role] = color.rgba

    ctx, session = make_session(tmp_path)
    qt = session.qt
    qt.QtGui.QFont, qt.QtGui.QPalette, qt.QtGui.QColor = Font, Palette, QColor
    fonts, palettes, fills = {}, {}, {}
    monkeypatch.setattr(
        QWidget,
        "setFont",
        lambda self, font: fonts.__setitem__(self, font),
        raising=False,
    )
    monkeypatch.setattr(
        QWidget,
        "palette",
        lambda self: palettes.setdefault(self, Palette()),
        raising=False,
    )
    monkeypatch.setattr(
        QWidget,
        "setPalette",
        lambda self, p: palettes.__setitem__(self, p),
        raising=False,
    )
    monkeypatch.setattr(
        QWidget,
        "setAutoFillBackground",
        lambda self, value: fills.__setitem__(self, value),
        raising=False,
    )
    monkeypatch.setattr(QWidget, "setFlat", lambda *args: None, raising=False)
    (
        qt.QtCore.Qt.MetaModifier,
        qt.QtCore.Qt.ControlModifier,
        qt.QtCore.Qt.AltModifier,
    ) = 1 << 28, 1 << 26, 1 << 27
    monkeypatch.setattr(
        qt.QtGui.QApplication,
        "keyboardModifiers",
        staticmethod(lambda: 0),
        raising=False,
    )
    monkeypatch.setattr(
        qt.QtGui.QApplication,
        "queryKeyboardModifiers",
        staticmethod(lambda: qt.QtCore.Qt.ShiftModifier),
        raising=False,
    )
    with ctx:
        kit, v = ctx.import_module("AppKit"), ctx.import_module("vanilla")
        assert kit.NSEvent.alloc().init().modifierFlags() == 0
        assert kit.NSEvent.modifierFlags() == kit.NSEventModifierFlagShift
        text = v.TextBox((0, 0, 100, 20), "Title").getNSTextField()
        text.setFont_(kit.NSFont.systemFontOfSize_(11))
        assert fonts[text._qt].points == 11
        text.setBackgroundColor_(kit.NSColor.separatorColor())
        assert palettes[text._qt].colors["Window"] == (0, 0, 0, 0.1) and fills[text._qt]
        text.setBackgroundColor_(None)
        assert not fills[text._qt]
        button = kit.NSButton.alloc().init()
        for style in (1, 4, 13, 15):
            button.setBezelStyle_(style)
            assert button.bezelStyle() == style
    ctx.close()
