# this_file: tests/test_issue106_round4_ui.py
"""F7/F16/F18 UI regressions through Qt doubles and real layout arithmetic."""

from types import SimpleNamespace

import pytest
from test_ui_nib_image import FakeImage, PixLabel
from ui_doubles import QLabel, QLineEdit, make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.vanilla import make_vanilla_module


def geometry(control):
    rect = control.getNSView().geometry
    return rect.x(), rect.y(), rect.width(), rect.height()


@pytest.fixture
def vanilla():
    module = make_vanilla_module(make_qt(), error_sink=print)
    yield module
    module.Window._env.close_windows()


def test_f7_window_resize_when_requested_then_origin_and_child_resizing_preserved(
    vanilla,
):
    window = vanilla.FloatingWindow((12, 18, 120, 90))
    window.label = vanilla.TextBox((5, 5, -5, -5), "Resize")
    window.open()
    window.resize(200, 150, animate=False)
    assert window.getPosSize() == (12, 18, 200, 150)
    assert geometry(window.label) == (5, 5, 190, 140)


def test_f16_placeholder_when_set_through_native_field_then_read_live():
    class Edit(QLineEdit):
        @property
        def placeholderText(self):
            return self._placeholder

    qt = make_qt()
    qt.QtGui.QLineEdit = Edit
    vanilla = make_vanilla_module(qt, error_sink=print)
    edit = vanilla.EditText((0, 0, 80, 20), placeholder="Hint")
    assert edit.getPlaceholder() == "Hint"
    edit.getNSTextField().setPlaceholderString_("Native hint")
    assert edit.getPlaceholder() == "Native hint"
    edit._retire()


def test_f16_auto_layout_when_vfl_equalities_then_anchors_metrics_and_resize_apply(
    vanilla,
):
    window = vanilla.Window((240, 120))
    window.alpha = vanilla.TextBox("auto", "Alpha")
    window.beta = vanilla.Button("auto", "Beta")
    window.addAutoPosSizeRules(
        [
            "H:|-pad-[alpha]-pad-|",
            "H:|-pad-[beta]-pad-|",
            "V:|-pad-[alpha(==24)]-6-[beta]-pad-|",
        ],
        {"pad": 12},
    )
    assert geometry(window.alpha) == (12, 12, 216, 24)
    assert geometry(window.beta) == (12, 42, 216, 66)
    window.resize(300, 180)
    assert geometry(window.beta) == (12, 42, 276, 126)
    window.open()


def test_f16_auto_layout_when_dictionary_equalities_then_relative_size_and_center(
    vanilla,
):
    window = vanilla.Window((200, 100))
    window.box = vanilla.Group("auto")
    window.addAutoPosSizeRules(
        [
            {
                "view1": window.box,
                "attribute1": "width",
                "view2": window,
                "attribute2": "width",
                "multiplier": 0.5,
            },
            {"view1": window.box, "attribute1": "height", "constant": 20},
            {
                "view1": window.box,
                "attribute1": "centerX",
                "view2": window,
                "attribute2": "centerX",
            },
            {"view1": window.box, "attribute1": "top", "constant": 8},
        ]
    )
    assert geometry(window.box) == (50, 8, 100, 20)
    window.open()


def test_f16_auto_layout_when_unsupported_or_contradictory_then_precise_no_partial_registration(
    vanilla,
):
    window = vanilla.Window((200, 100))
    window.item = vanilla.TextBox("auto", "Item")
    with pytest.raises(UnsupportedCapability, match="addAutoPosSizeRules"):
        window.addAutoPosSizeRules(["H:|[item(>=20)]|"])
    with pytest.raises(UnsupportedCapability, match="unsatisfiable"):
        window.addAutoPosSizeRules(["H:|[item(300)]|"])
    assert not window.__dict__.get("_auto_rules")
    window.open()


def test_f16_vertical_stack_when_resized_then_children_fill_equally_and_teardown_disconnects(
    vanilla,
):
    window = vanilla.Window((200, 140))
    first, second = vanilla.Button("auto", "One"), vanilla.Button("auto", "Two")
    stack = vanilla.VerticalStackView(
        (0, 0, 0, 0), [first, {"view": second}], spacing=4, edgeInsets=(10, 8, 10, 8)
    )
    window.stack = stack
    assert geometry(first) == (60, 8, 80, 60)
    assert geometry(second) == (60, 72, 80, 60)
    window.resize(240, 160)
    assert geometry(first) == (80, 8, 80, 70)
    stack.removeView(first)
    assert geometry(second) == (80, 8, 80, 144)
    window.open()


def test_f16_image_view_when_set_and_resized_then_image_renders_and_clears():
    qt = make_qt()
    qt.QtGui.QLabel = PixLabel
    qt.QtCore.Qt.AlignCenter = 0x84
    vanilla = make_vanilla_module(qt, error_sink=print)
    window = vanilla.Window((8, 8))
    window.image = vanilla.ImageView((0, 0, 0, 0))
    image = FakeImage.alloc().initWithContentsOfFile_("owned.png")
    window.image.setImage(imageObject=image)
    assert window.image.getNSImageView().image() is image
    assert window.image.getNSView().pixmap.scale == 0.5
    window.resize(160, 160)
    assert window.image.getNSView().pixmap.scale == 1
    window.image.setImage()
    assert window.image.getNSView().pixmap is None
    window.close()


def test_f16_auto_layout_when_other_fixed_controls_exist_then_their_geometry_is_preserved(
    vanilla,
):
    window = vanilla.Window((200, 120))
    window.fixed = vanilla.TextBox((30, 45, 60, 18), "Fixed")
    window.auto = vanilla.Button("auto", "Auto")
    window.addAutoPosSizeRules(["H:|[auto]|", "V:|[auto(20)]"])
    assert geometry(window.fixed) == (30, 45, 60, 18)
    window.open()


def test_f16_nested_auto_group_when_parent_size_is_pending_then_child_constraints_defer(
    vanilla,
):
    window = vanilla.Window((240, 200))
    group = vanilla.Group("auto")
    group.text = vanilla.TextBox("auto", "Nested")
    group.addAutoPosSizeRules(["H:|-16-[text]-16-|", "V:|-16-[text(40)]-16-|"])
    window.group = group
    window.addAutoPosSizeRules(["H:|[group]|", "V:|[group(72)]"])
    assert geometry(group.text) == (16, 16, 208, 40)
    window.open()


def test_f16_drawer_when_requested_then_named_refusal(vanilla):
    with pytest.raises(UnsupportedCapability) as error:
        vanilla.Drawer((100, 100))
    assert error.value.capability == "vanilla.Drawer"


def test_f18_text_color_when_label_or_edit_then_correct_palette_role_preserved():
    class Palette:
        WindowText, Text = "window-text", "text"

        def __init__(self, values=None):
            self.values = dict(values or {"background": "original"})

        def setColor(self, role, color):
            self.values[role] = color

    class Colored:
        def palette(self):
            return Palette(getattr(self, "colors", None))

        def setPalette(self, palette):
            self.colors = palette.values

    class Label(Colored, QLabel):
        pass

    class Edit(Colored, QLineEdit):
        pass

    qt = make_qt()
    qt.QtGui.QLabel, qt.QtGui.QLineEdit, qt.QtGui.QPalette = Label, Edit, Palette
    qt.QtGui.QColor = SimpleNamespace(fromRgbF=lambda *rgba: rgba)
    vanilla = make_vanilla_module(qt, error_sink=print)
    from fontlab_glyport.drawing.cocoa_drawing import NSColor

    for cls, role in ((vanilla.TextBox, "window-text"), (vanilla.EditText, "text")):
        control = cls((0, 0, 80, 20), "Text")
        field = control.getNSTextField()
        field.setTextColor_(NSColor.redColor())
        assert control.getNSView().colors == {
            "background": "original",
            role: (1, 0, 0, 1),
        }
        control._retire()
