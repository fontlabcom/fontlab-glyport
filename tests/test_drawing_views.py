# this_file: tests/test_drawing_views.py
"""NSView subclasses with drawRect_ and mouse methods on Qt widgets (R032)."""

from drawing_doubles import PAINTERS, QMouseEvent, add_drawing
from ui_doubles import LOG, make_qt

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.drawing.cocoa_drawing import NSColor, NSRectFill
from fontlab_glyport.drawing.events import (
    NSEventModifierFlagCommand,
    NSEventModifierFlagShift,
)
from fontlab_glyport.ui.cocoa import NSMakeRect
from fontlab_glyport.ui.cocoa_views import make_appkit_classes


def _kit():
    errors = []
    kit = make_appkit_classes(
        add_drawing(make_qt()), error_sink=lambda e, s: errors.append(e)
    )
    return kit, errors


def test_custom_view_when_painted_then_draw_rect_in_y_up_bounds():
    kit, errors = _kit()
    seen = []

    class Swatch(kit["NSView"]):
        def drawRect_(self, rect):
            seen.append(rect)
            NSColor.redColor().set()
            NSRectFill(((0, 0), (10, 10)))

    view = Swatch.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 50))
    view._qt.paintEvent(None)
    assert seen == [NSMakeRect(0, 0, 100, 50)] and errors == []
    painter = PAINTERS[-1]
    assert painter.device is view._qt and painter.ended
    fill = next(c for c in painter.calls if c[0] == "fill")
    assert gc.apply(fill[3], 0, 0) == (0, 50), "Cocoa's origin is the bottom-left"


def test_plain_view_when_painted_then_native_paint_only():
    kit, _ = _kit()
    view = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    before = len(PAINTERS)
    view._qt.paintEvent(None)
    assert len(PAINTERS) == before
    assert ("native.paintEvent", view._qt) in LOG, "the native handler runs instead"


def test_custom_view_when_draw_raises_then_sink_and_painter_ended():
    kit, errors = _kit()

    class Bad(kit["NSView"]):
        def drawRect_(self, rect):
            raise ValueError("paint failed")

    view = Bad.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    view._qt.paintEvent(None)
    assert [str(e) for e in errors] == ["paint failed"] and PAINTERS[-1].ended


def test_custom_view_when_mouse_then_ns_event_in_view_coordinates():
    kit, _ = _kit()
    events = []

    class Pad(kit["NSView"]):
        def mouseDown_(self, event):
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            events.append((tuple(point), event.modifierFlags(), event.clickCount()))

    view = Pad.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 50))
    press = QMouseEvent(10, 15, 0x02000000 | 0x04000000)
    view._qt.mousePressEvent(press)
    assert press.accepted
    assert events == [
        ((10.0, 35.0), NSEventModifierFlagShift | NSEventModifierFlagCommand, 1)
    ]
