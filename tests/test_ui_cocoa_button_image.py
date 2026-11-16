# this_file: tests/test_ui_cocoa_button_image.py
"""NSButton images and borders, NSTextField.cell() line breaks (L2m plain-model
target: mekkablue's helper package styles vanilla buttons and text boxes)."""

from ui_doubles import QLabel, QPushButton, make_qt

from fontlab_glyport.ui import cocoa_views
from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject
from fontlab_glyport.ui.cocoa_views import make_appkit_classes


class IconButton(QPushButton):
    __slots__ = ("flat", "icon")

    def __init__(self):
        super().__init__()
        self.icon, self.flat = None, False

    def setIcon(self, icon):
        self.icon = icon

    def setFlat(self, flat):
        self.flat = flat


class WrapLabel(QLabel):
    __slots__ = ("wrap",)

    def __init__(self):
        super().__init__()
        self.wrap = False

    def setWordWrap(self, flag):
        self.wrap = flag


class Image(NSObject):
    def icon(self):
        return "icon"


def _kit():
    qt = make_qt()
    qt.QtGui.QPushButton = IconButton
    qt.QtGui.QLabel = WrapLabel
    qt.QtGui.QIcon = lambda: "no icon"
    return make_appkit_classes(qt, error_sink=print)


def test_button_when_image_position_and_border_set_then_qt_follows():
    kit = _kit()
    button = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    button.setTitle_("Update")
    image = Image.alloc().init()
    button.setImage_(image)
    assert button.image() is image and button._qt.icon == "icon"
    button.setImagePosition_(cocoa_views.NSImageLeading)
    assert button.imagePosition() == 7 and button._qt.text == "Update"
    button.setImagePosition_(cocoa_views.NSImageOnly)
    assert button._qt.text == "" and button.title() == "Update"
    button.setImagePosition_(cocoa_views.NSImageLeft)
    assert button._qt.text == "Update"
    button.setBordered_(False)
    assert button._qt.flat and not button.isBordered()
    button.setImage_(None)  # NSImage.imageNamed_ of an unknown name gives None
    assert button.image() is None and button._qt.icon == "no icon"
    kit["close"]()


def test_button_when_checkbox_not_bordered_then_ignored():
    kit = _kit()
    box = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    box.setButtonType_(cocoa_views.NSSwitchButton)
    box.setBordered_(False)
    assert not box.isBordered()
    kit["close"]()


def test_text_field_cell_when_line_break_mode_set_then_label_wraps_or_clips():
    kit = _kit()
    label = kit["NSTextField"]._adopt(WrapLabel())
    cell = label.cell()
    cell.setLineBreakMode_(cocoa_views.NSLineBreakByWordWrapping)
    assert label._qt.wrap and cell.lineBreakMode() == 0
    cell.setLineBreakMode_(cocoa_views.NSLineBreakByClipping)
    assert not label._qt.wrap and label.cell().lineBreakMode() == 2
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    field.cell().setLineBreakMode_(cocoa_views.NSLineBreakByTruncatingTail)
    assert field.cell().lineBreakMode() == 4, "a line edit is one line: recorded"
    kit["close"]()
