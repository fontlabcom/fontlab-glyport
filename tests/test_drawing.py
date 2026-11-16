# this_file: tests/test_drawing.py
"""Cocoa drawing translated to QPainter calls (R032), over recording doubles."""

import pytest
from drawing_doubles import QPainter, QTransform, make_drawing_qt

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.drawing.cocoa_drawing import (
    NSAffineTransform,
    NSAttributedString,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSGraphicsContext,
    NSRectFill,
    NSString,
)
from fontlab_glyport.plugins.host import PaintContext

QT = make_drawing_qt()
GLYPH_TO_VIEW = (0.5, 0.0, 0.0, -0.5, 100.0, 400.0)  # zoom 0.5, y up, origin (100, 400)


def _first(painter, kind):
    return next(c for c in painter.calls if c[0] in kind)


def _scope(painter=None, base=GLYPH_TO_VIEW):
    painter = painter or QPainter()
    return painter, gc.scope(QT, painter, base)


def test_concat_and_invert_when_composed_then_row_vector_order():
    translate = (1, 0, 0, 1, 10, 0)
    scale = (2, 0, 0, 2, 0, 0)
    assert gc.apply(gc.concat(translate, scale), 1, 1) == (22, 2), (
        "translate, then scale"
    )
    t = gc.concat(gc.rotation(30), (1, 0, 0, 1, 5, -3))
    x, y = gc.apply(gc.concat(t, gc.invert(t)), 7, 9)
    assert (round(x, 9), round(y, 9)) == (7, 9)


def test_context_state_requires_scope_but_path_painting_without_destination_is_noop():
    with pytest.raises(RuntimeError):
        NSColor.redColor().set()
    path = NSBezierPath.bezierPathWithRect_(((0, 0), (1, 1)))
    path.fill()
    path.stroke()


def test_fill_when_rect_and_color_then_qpath_brush_and_device_transform():
    painter, scope = _scope()
    with scope:
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 0, 0, 0.5).set()
        NSBezierPath.fillRect_(((10, 20), (30, 40)))
    kind, ops, rgba, transform = _first(painter, ("fill", "stroke"))
    assert kind == "fill" and rgba == (1.0, 0.0, 0.0, 0.5)
    assert ops == [("M", 10, 20), ("L", 40, 20), ("L", 40, 60), ("L", 10, 60), ("Z",)]
    assert transform == GLYPH_TO_VIEW
    assert painter.kinds()[0] == "save" and painter.kinds()[-1] == "restore"


def test_stroke_when_width_cap_dash_then_pen_in_user_space():
    painter, scope = _scope()
    with scope:
        NSColor.blueColor().setStroke()
        path = NSBezierPath.bezierPath()
        path.moveToPoint_((0, 0))
        path.curveToPoint_controlPoint1_controlPoint2_((30, 0), (10, 10), (20, 10))
        path.setLineWidth_(2)
        path.setLineCapStyle_(1)
        path.setLineDash_count_phase_([4, 2], 2, 1)
        path.stroke()
    _, ops, pen, _ = _first(painter, ("fill", "stroke"))
    assert ops == [("M", 0, 0), ("C", 10, 10, 20, 10, 30, 0)]
    assert (pen.width, pen.cap, pen.dash, pen.offset) == (2.0, "Round", [2.0, 1.0], 0.5)
    assert pen.color.rgba == (0, 0, 1, 1)


def test_affine_transform_when_concat_then_ctm_applies_before_base():
    painter, scope = _scope()
    with scope:
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(100, 0)
        t.scaleBy_(2)
        t.concat()
        NSRectFill(((0, 0), (1, 1)))
    transform = _first(painter, ("fill", "stroke"))[3]
    assert gc.apply(transform, 1, 0) == (gc.apply(GLYPH_TO_VIEW, 102, 0))
    assert NSAffineTransform.transform().transformPoint_((3, 4)) == (3, 4)
    t2 = NSAffineTransform.transform()
    t2.rotateByDegrees_(90)
    x, y = t2.transformPoint_((1, 0))
    assert (round(x, 9), round(y, 9)) == (0, 1)


def test_graphics_state_when_saved_and_restored_then_ctm_and_colors_return():
    painter, scope = _scope()
    with scope:
        NSColor.redColor().set()
        NSGraphicsContext.saveGraphicsState()
        t = NSAffineTransform.transform()
        t.translateXBy_yBy_(5, 5)
        t.concat()
        NSColor.greenColor().set()
        NSGraphicsContext.restoreGraphicsState()
        NSRectFill(((0, 0), (1, 1)))
        NSGraphicsContext.currentContext().setShouldAntialias_(False)
    _, _, rgba, transform = _first(painter, ("fill", "stroke"))
    assert rgba == (1, 0, 0, 1) and transform == GLYPH_TO_VIEW
    assert ("hint", 1, False) in painter.calls


def test_oval_and_rounded_rect_when_built_then_cubic_quadrants():
    oval = NSBezierPath.bezierPathWithOvalInRect_(((0, 0), (20, 10)))
    kinds = [e[0] for e in oval._elements]
    assert kinds.count("curve") == 4 and kinds[-1] == "close"
    assert oval.bounds() == ((0, 0), (20, 10))
    rounded = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        ((0, 0), (20, 10)), 3, 3
    )
    assert [e[0] for e in rounded._elements].count("line") == 4
    square = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        ((0, 0), (20, 10)), 0, 0
    )
    assert [e[0] for e in square._elements].count("curve") == 0


def test_transform_bezier_path_when_applied_then_points_moved_copy_kept():
    path = NSBezierPath.bezierPathWithRect_(((0, 0), (1, 1)))
    t = NSAffineTransform.transform()
    t.translateXBy_yBy_(5, 0)
    moved = t.transformBezierPath_(path)
    assert moved.bounds().origin == (5, 0) and path.bounds().origin == (0, 0)


def test_text_when_drawn_in_y_up_glyph_space_then_upright_at_device_point():
    painter, scope = _scope()
    with scope:
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(20),
            NSForegroundColorAttributeName: NSColor.redColor(),
        }
        text = NSAttributedString.alloc().initWithString_attributes_("ab", attrs)
        text.drawAtPoint_alignment_((0, 0), 1)  # bottom centre
    font_px = next(c for c in painter.calls if c[0] == "font")[1]
    assert font_px == 10, "20 pt at zoom 0.5"
    (_, x, y, string) = next(c for c in painter.calls if c[0] == "text")
    assert (x, y, string) == (100 - 10 * 0.5, 400 - 2, "ab")
    assert ("setTransform", (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)) in painter.calls


def test_ns_string_when_drawn_then_same_as_attributed():
    painter, scope = _scope(base=gc.IDENTITY)
    with scope:
        NSString.stringWithString_("x").drawAtPoint_withAttributes_(
            (5, 5), {NSFontAttributeName: NSFont.boldSystemFontOfSize_(10)}
        )
    assert [c for c in painter.calls if c[0] == "text"] == [("text", 5.0, 13.0, "x")]


def test_named_and_hsb_colors():
    assert NSColor.whiteColor().rgba == (1, 1, 1, 1)
    assert NSColor.colorWithCalibratedWhite_alpha_(0.5, 0.2).rgba == (
        0.5,
        0.5,
        0.5,
        0.2,
    )
    red = NSColor.colorWithHue_saturation_brightness_alpha_(0, 1, 1, 1)
    assert red.rgba == (1, 0, 0, 1)
    assert NSColor.redColor().colorWithAlphaComponent_(0.3).alphaComponent() == 0.3
    with pytest.raises(AttributeError):
        NSColor.notAColor()


def test_paint_scope_when_plugin_context_then_glyph_to_view_base():
    painter = QPainter()
    context = PaintContext(
        1,
        "L",
        1,
        True,
        "after_native_layer",
        QTransform(1, 0, 0, 1, 50, 0),
        QTransform(0.5, 0, 0, -0.5, 75, 400),
        2.0,
        None,
        painter,
        0.5,
    )
    with gc.paint_scope(QT)(context):
        NSRectFill(((0, 0), (2, 2)))
    transform = _first(painter, ("fill", "stroke"))[3]
    assert gc.apply(transform, 0, 0) == (100.0, 400.0)
    assert gc.apply(transform, 2, 2) == (101.0, 399.0)


def test_view_scope_when_not_flipped_then_y_up_from_bottom():
    painter = QPainter()
    with gc.view_scope(QT, painter, 100, flipped=False):
        NSRectFill(((0, 0), (10, 10)))
    assert gc.apply(_first(painter, ("fill", "stroke"))[3], 0, 0) == (0, 100)
    painter = QPainter()
    with gc.view_scope(QT, painter, 100, flipped=True):
        NSRectFill(((0, 0), (10, 10)))
    assert gc.apply(_first(painter, ("fill", "stroke"))[3], 0, 0) == (0, 0)


def test_scope_when_exited_then_context_inactive_even_if_retained():
    _, scope = _scope()
    with scope as ctx:
        kept = NSGraphicsContext.currentContext()
    assert not ctx.active
    with pytest.raises(RuntimeError):
        NSColor.redColor().set()
    assert kept._context is ctx


def test_graphic_view_when_painting_then_visible_glyph_area_from_view_values():
    """R049 reporter (CJK Metrics): (visibleRect.origin - activePosition) /
    scale and visibleRect.size / scale give the visible glyph-unit area."""
    from types import SimpleNamespace

    from fontlab_glyport.model import Model
    from fontlab_glyport.model.backend import EditViewInfo
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    backend.edit_views["font"] = EditViewInfo((("A",),), "A", "Regular", "tab")
    tab = Model(backend).font.currentTab
    painter = QPainter()
    painter.device = lambda: SimpleNamespace(width=lambda: 400, height=lambda: 300)
    with pytest.raises(Exception, match="graphicView.scale"):
        tab.graphicView().scale()
    with gc.scope(QT, painter, GLYPH_TO_VIEW):
        view = tab.graphicView()
        rect, origin, scale = view.visibleRect(), view.activePosition(), 0.5
    x0, y0 = (rect.origin.x - origin.x) / scale, (rect.origin.y - origin.y) / scale
    # widget (0..400, 0..300) in glyph units: x -200..600, y 200..800 (y up)
    assert (x0, y0, rect.size.width / scale, rect.size.height / scale) == (
        -200.0,
        200.0,
        800.0,
        600.0,
    )


def test_paragraph_style_when_in_attributes_then_kept_and_text_drawn():
    """R049 custom-nsview (Waterfall): a right-aligned paragraph style in the
    attributes of drawAtPoint_; at a point Cocoa lays out one unbounded line,
    so the alignment does not move the text."""
    from fontlab_glyport.drawing.cocoa_drawing import (
        NSMutableParagraphStyle,
        NSParagraphStyleAttributeName,
    )

    style = NSMutableParagraphStyle.alloc().init()
    style.setAlignment_(1)
    assert style.alignment() == 1
    painter, scope = _scope()
    with scope:
        NSAttributedString.alloc().initWithString_attributes_(
            "12", {NSParagraphStyleAttributeName: style}
        ).drawAtPoint_((10, 20))
    assert any(c[0] == "text" for c in painter.calls), painter.calls


def test_affine_shear_when_x_by_factor_then_x_plus_factor_y():
    """Glyphs' NSAffineTransform.shearXBy_ (mekkablue geometry.transform skew)."""
    t = NSAffineTransform.transform()
    t.translateXBy_yBy_(10, 0)
    t.shearXBy_(0.5)
    assert t.transformStruct() == (1.0, 0.0, 0.5, 1.0, 10.0, 0.0)
    assert gc.apply(t.transformStruct(), 0, 100) == (60.0, 100.0)
