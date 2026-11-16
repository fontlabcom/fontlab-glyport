# this_file: tests/test_issue106_round7_adapters.py
"""Handwritten Cocoa, vanilla and Python 2 acceptance cases for round seven."""

from types import SimpleNamespace

import pytest
from ui_doubles_session import make_session

from fontlab_glyport import AdaptationError, adapt_source
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.plugins.fontlab_host import FontLabPluginHost


def test_f25_modifier_flags_class_reads_keyboard_instance_keeps_event(
    tmp_path, monkeypatch
):
    ctx, session = make_session(tmp_path)
    from drawing_doubles import QMouseEvent, add_drawing

    qt = add_drawing(session.qt)
    qt.QtCore.Qt.MetaModifier = 1 << 28
    qt.QtCore.Qt.ControlModifier = 1 << 26
    qt.QtCore.Qt.AltModifier = 1 << 27
    modifiers = [qt.QtCore.Qt.ShiftModifier | qt.QtCore.Qt.ControlModifier]
    monkeypatch.setattr(
        qt.QtGui.QApplication,
        "keyboardModifiers",
        staticmethod(lambda: modifiers[0]),
        raising=False,
    )
    with ctx:
        kit = ctx.import_module("AppKit")
        event_type = kit.NSEvent
        instance = event_type.alloc().init()
        instance._flags = kit.NSEventModifierFlagOption
        assert (
            event_type.modifierFlags()
            == kit.NSEventModifierFlagShift | kit.NSEventModifierFlagCommand
        )
        modifiers[0] = qt.QtCore.Qt.MetaModifier
        assert event_type.modifierFlags() == kit.NSEventModifierFlagControl
        assert instance.modifierFlags() == kit.NSEventModifierFlagOption
        assert ctx.import_module("Cocoa").NSEvent is event_type
        modifiers[0] = 0
        assert event_type.modifierFlags() == 0
        events = []

        class View(kit.NSView):
            def mouseDown_(self, event):
                events.append(event)

        view = View.alloc().initWithFrame_(((0, 0), (80, 50)))
        view._qt.mousePressEvent(QMouseEvent(10, 15, qt.QtCore.Qt.AltModifier))
        assert len(events) == 1 and isinstance(events[0], event_type)
        assert events[0].modifierFlags() == kit.NSEventModifierFlagOption
    ctx.close()


def test_f26_text_fields_become_first_responder(tmp_path, monkeypatch):
    ctx, _ = make_session(tmp_path)
    focused = []
    from ui_doubles import QLineEdit

    monkeypatch.setattr(
        QLineEdit, "setFocus", lambda self: focused.append(self), raising=False
    )
    with ctx:
        kit = ctx.import_module("AppKit")
        for cls in (kit.NSTextField, kit.GSSteppingTextField):
            field = cls.alloc().initWithFrame_(((0, 0), (80, 20)))
            assert field.becomeFirstResponder() is True
            assert focused[-1] is field._qt
    ctx.close()


def test_f27_no_dialog_view_is_a_located_capability_error_before_qt_allocation():
    host = FontLabPluginHost.__new__(FontLabPluginHost)
    host.qt = SimpleNamespace(QtGui=object())
    with pytest.raises(UnsupportedCapability) as error:
        host.run_dialog(None, "Empty filter", "Apply", lambda applied: None)
    assert error.value.capability == "FilterWithDialog.view"
    assert error.value.location is not None


def test_f28_hint_component_constants_match_sdk(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        ga = ctx.import_module("GlyphsApp")
        assert (ga.CORNER, ga.CAP) == (16, 17)
    ctx.close()


def test_f32_checkbox_cells_are_editable_without_callback_and_store_booleans(tmp_path):
    ctx, session = make_session(tmp_path)
    with ctx:
        vanilla = ctx.import_module("vanilla")
        changes = []
        checkbox = vanilla.CheckBoxListCell()
        table = vanilla.List(
            (0, 0, 150, 80),
            [{"use": True}],
            columnDescriptions=[{"title": "", "key": "use", "cell": checkbox}],
        )
        item = table._view.item(0, 0)
        qt = session.qt.QtCore.Qt
        assert item.checkState() == qt.Checked and item.text() == ""
        assert item.flags() & qt.ItemIsUserCheckable
        assert not item.flags() & qt.ItemIsEditable
        item.setCheckState(qt.Unchecked)
        assert table.get()[0]["use"] is False
        table.set([{"use": True}])
        assert table._view.item(0, 0).checkState() == qt.Checked
        other = vanilla.List(
            (0, 0, 150, 80),
            [{"use": False}],
            columnDescriptions=[{"title": "", "key": "use", "cell": checkbox}],
            editCallback=lambda sender: changes.append(sender.get()[0]["use"]),
        )
        other._view.item(0, 0).setCheckState(qt.Checked)
        assert changes == [True]
    ctx.close()


@pytest.mark.parametrize(
    "source",
    [
        'print "Count %d" % 3\n',
        'print "Count %d" % \\\n    3\n',
        'from __future__ import print_function\nprint("Count %d" % 3)\n',
    ],
)
def test_f34_valid_legacy_print_syntax_adapts(tmp_path, source):
    path = tmp_path / "print.py"
    path.write_text(source)
    result = adapt_source(path, profile="glyphs2", cache_dir=tmp_path / "cache")
    result.compile()
    assert path.read_text() == source


def test_f34_future_print_conflict_refuses_at_original_parse_location(tmp_path):
    path = tmp_path / "conflict.py"
    path.write_text('from __future__ import print_function\n\nprint "legacy"\n')
    with pytest.raises(AdaptationError) as error:
        adapt_source(path, profile="glyphs2", cache_dir=tmp_path / "cache")
    assert error.value.capability == "source:python2.parse"
    assert (error.value.location.line, error.value.location.column) == (3, 7)
    assert "__future__" in str(error.value)


def test_f27_dialog_builder_font_background_and_rounded_button_styles(
    tmp_path, monkeypatch
):
    from drawing_doubles import QColor, QFont
    from ui_doubles import QWidget

    class Font(QFont):
        def setPointSizeF(self, size):
            self.points = size

    class Palette:
        Base = "Base"

        def __init__(self):
            self.colors = {}

        def setColor(self, role, color):
            self.colors[role] = color.rgba

    ctx, session = make_session(tmp_path)
    session.qt.QtGui.QFont = Font
    session.qt.QtGui.QColor = QColor
    session.qt.QtGui.QPalette = Palette
    fonts, palettes, flat = {}, {}, {}
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
        lambda self, palette: palettes.__setitem__(self, palette),
        raising=False,
    )
    monkeypatch.setattr(
        QWidget,
        "setFlat",
        lambda self, value: flat.__setitem__(self, value),
        raising=False,
    )
    with ctx:
        kit = ctx.import_module("AppKit")
        label = kit.NSTextField.alloc().initWithFrame_(((0, 0), (100, 20)))
        label.setFont_(kit.NSFont.systemFontOfSize_(10))
        assert label.font().pointSize() == fonts[label._qt].points == 10
        label.setBackgroundColor_(kit.NSColor.separatorColor())
        assert palettes[label._qt].colors["Base"] == (0, 0, 0, 0.1)
        label.setBackgroundColor_(None)
        assert not palettes[label._qt].colors
        button = kit.NSButton.alloc().initWithFrame_(((0, 0), (70, 20)))
        button.setBezelStyle_(1)
        button.setFont_(kit.NSFont.systemFontOfSize_(11))
        assert button.bezelStyle() == 1 and flat[button._qt] is False
        assert fonts[button._qt].points == 11
    ctx.close()


def test_f27_none_view_menu_action_rolls_back_preview_and_closes_undo():
    from plugin_doubles import FakeHost, Layer
    from ui_doubles import make_qt

    from fontlab_glyport.plugins.base import PluginEnv, make_plugins_module
    from fontlab_glyport.plugins.loader import load_plugin
    from fontlab_glyport.ui.cocoa_views import make_appkit_classes

    host = FakeHost([Layer("A", ["original"])])
    errors = []
    env = PluginEnv(
        host,
        make_appkit_classes(make_qt(), error_sink=print),
        lambda error, sender: errors.append(error),
    )
    plugins = make_plugins_module(env)

    class MissingView(plugins.FilterWithDialog):
        def filter(self, layer, inEditView, customParameters):
            layer.paths.append("preview")

    handle = load_plugin(MissingView, env)
    host.entries("menu")[0][2].fire()
    assert len(errors) == 1 and errors[0].capability == "FilterWithDialog.view"
    assert host.layers[0].paths == ["original"]
    assert not host.dialogs and handle.dialog is None
    assert [entry[0] for entry in host.log].count("undo-end") == 1
    assert any("FilterWithDialog.view" in note for note in handle.diagnostics)
    handle.unload()
