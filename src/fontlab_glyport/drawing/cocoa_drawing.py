# this_file: src/fontlab_glyport/drawing/cocoa_drawing.py
"""AppKit drawing classes painted with QPainter (R032).

Corpus counts (literal grep of the Glyphs corpus ``.py`` files) decided the
surface: ``NSColor`` (colorWithCalibratedRed 181, white/black/text/gray/red/
blue and system colours), ``NSAffineTransform`` (transform 135),
``NSBezierPath`` (bezierPath 112, fillRect_ 46, ovals 46, rounded rects 35,
rects 24, strokeLineFromPoint 12), ``NSFont`` (systemFontOfSize_ 79,
fontWithName_size_ 34), ``NSAttributedString`` (92) and
``NSGraphicsContext`` save/restore. Paths keep their elements in Python and
become a ``QPainterPath`` only when painted; colours become ``QColor``.
Everything paints through ``context.current()``, so drawing outside a paint
callback raises ``RuntimeError``.
"""

import colorsys
import math
from typing import Any

from ..affine import NSAffineTransformStruct
from ..ui.cocoa import NSMakeRect, NSObject, NSRect, NSSize, as_rect
from . import context as gc

NSFontAttributeName = "NSFont"
NSForegroundColorAttributeName = "NSColor"
NSBackgroundColorAttributeName = "NSBackgroundColor"
NSParagraphStyleAttributeName = "NSParagraphStyle"
NSButtLineCapStyle, NSRoundLineCapStyle, NSSquareLineCapStyle = 0, 1, 2
NSMiterLineJoinStyle, NSRoundLineJoinStyle, NSBevelLineJoinStyle = 0, 1, 2
NSNonZeroWindingRule, NSEvenOddWindingRule = 0, 1
_KAPPA = 0.5522847498  # cubic approximation of a quarter circle

# Named colours: AppKit's sRGB values for the light appearance.
_NAMED = {
    "blackColor": (0, 0, 0, 1),
    "whiteColor": (1, 1, 1, 1),
    "grayColor": (0.5, 0.5, 0.5, 1),
    "lightGrayColor": (2 / 3, 2 / 3, 2 / 3, 1),
    "darkGrayColor": (1 / 3, 1 / 3, 1 / 3, 1),
    "redColor": (1, 0, 0, 1),
    "greenColor": (0, 1, 0, 1),
    "blueColor": (0, 0, 1, 1),
    "yellowColor": (1, 1, 0, 1),
    "orangeColor": (1, 0.5, 0, 1),
    "brownColor": (0.6, 0.4, 0.2, 1),
    "purpleColor": (0.5, 0, 0.5, 1),
    "cyanColor": (0, 1, 1, 1),
    "magentaColor": (1, 0, 1, 1),
    "clearColor": (0, 0, 0, 0),
    "textColor": (0, 0, 0, 0.85),
    "labelColor": (0, 0, 0, 0.85),
    "controlTextColor": (0, 0, 0, 0.85),
    "secondaryLabelColor": (0, 0, 0, 0.5),
    "tertiaryLabelColor": (0, 0, 0, 0.26),
    "disabledControlTextColor": (0, 0, 0, 0.25),
    "separatorColor": (0, 0, 0, 0.1),
    "textBackgroundColor": (1, 1, 1, 1),
    "windowBackgroundColor": (0.925, 0.925, 0.925, 1),
    "controlAccentColor": (0, 0.478, 1, 1),
    "keyboardFocusIndicatorColor": (0, 0.404, 0.957, 0.5),
    "systemPinkColor": (1, 0.176, 0.333, 1),
    "systemRedColor": (1, 0.231, 0.188, 1),
    "systemOrangeColor": (1, 0.584, 0, 1),
    "systemBlueColor": (0, 0.478, 1, 1),
    "systemGrayColor": (0.557, 0.557, 0.576, 1),
    "systemGreenColor": (0.204, 0.78, 0.349, 1),
    # Portable light-appearance fallbacks, like the existing semantic colours.
    "systemYellowColor": (1, 0.8, 0, 1),
    "systemMintColor": (0, 0.78, 0.745, 1),
    "systemTealColor": (0.188, 0.69, 0.78, 1),
    "systemCyanColor": (0.196, 0.678, 0.902, 1),
    "systemIndigoColor": (0.345, 0.337, 0.839, 1),
    "systemPurpleColor": (0.686, 0.322, 0.871, 1),
    "systemBrownColor": (0.635, 0.518, 0.369, 1),
    "quaternaryLabelColor": (0, 0, 0, 0.1),
    "placeholderTextColor": (0, 0, 0, 0.25),
    "controlBackgroundColor": (1, 1, 1, 1),
    "controlColor": (1, 1, 1, 1),
    "selectedControlColor": (0.702, 0.843, 1, 1),
    "selectedControlTextColor": (0, 0, 0, 1),
    "alternateSelectedControlTextColor": (1, 1, 1, 1),
    "selectedTextBackgroundColor": (0.702, 0.843, 1, 1),
    "gridColor": (0, 0, 0, 0.1),
}


class _ColorMeta(type):
    """``NSColor.redColor()`` and friends come from the ``_NAMED`` table."""

    def __getattr__(cls, name: str):
        if name in _NAMED:
            return lambda: cls(*_NAMED[name])
        raise AttributeError(name)


class NSColor(metaclass=_ColorMeta):
    """An sRGB colour; ``set``/``setFill``/``setStroke`` change the current context."""

    def __init__(self, red: float, green: float, blue: float, alpha: float = 1.0):
        self.rgba = tuple(
            min(max(float(v), 0.0), 1.0) for v in (red, green, blue, alpha)
        )

    def __eq__(self, other) -> bool:
        return isinstance(other, NSColor) and self.rgba == other.rgba

    def blendedColorWithFraction_ofColor_(self, fraction, color):
        fraction = min(1.0, max(0.0, float(fraction)))
        return NSColor(
            *(
                a + fraction * (b - a)
                for a, b in zip(self.rgba, color.rgba, strict=True)
            )
        )

    def __hash__(self) -> int:
        return hash(self.rgba)

    def __repr__(self) -> str:
        r, g, b, a = self.rgba
        return f"NSColor({r:.3f}, {g:.3f}, {b:.3f}, {a:.3f})"

    @classmethod
    def colorWithRed_green_blue_alpha_(cls, r, g, b, a):
        return cls(r, g, b, a)

    colorWithCalibratedRed_green_blue_alpha_ = colorWithRed_green_blue_alpha_
    colorWithDeviceRed_green_blue_alpha_ = colorWithRed_green_blue_alpha_
    colorWithSRGBRed_green_blue_alpha_ = colorWithRed_green_blue_alpha_

    @classmethod
    def colorWithWhite_alpha_(cls, white, alpha):
        return cls(white, white, white, alpha)

    colorWithCalibratedWhite_alpha_ = colorWithWhite_alpha_
    colorWithDeviceWhite_alpha_ = colorWithWhite_alpha_

    @classmethod
    def colorWithHue_saturation_brightness_alpha_(cls, h, s, b, a):
        return cls(*colorsys.hsv_to_rgb(float(h), float(s), float(b)), a)

    colorWithCalibratedHue_saturation_brightness_alpha_ = (
        colorWithHue_saturation_brightness_alpha_
    )
    colorWithDeviceHue_saturation_brightness_alpha_ = (
        colorWithHue_saturation_brightness_alpha_
    )

    def colorWithAlphaComponent_(self, alpha):
        return NSColor(*self.rgba[:3], alpha)

    def alphaComponent(self) -> float:
        return self.rgba[3]

    def redComponent(self) -> float:
        return self.rgba[0]

    def greenComponent(self) -> float:
        return self.rgba[1]

    def blueComponent(self) -> float:
        return self.rgba[2]

    def set(self) -> None:
        state = gc.current().state
        state.fill = state.stroke = self

    def setFill(self) -> None:
        gc.current().state.fill = self

    def setStroke(self) -> None:
        gc.current().state.stroke = self

    def qcolor(self, qt: Any) -> Any:
        return qt.QtGui.QColor.fromRgbF(*self.rgba)


_DEFAULT_LINE_WIDTH = [1.0]


class NSBezierPath(NSObject):
    """Moves, lines, cubic curves and closes in user space."""

    def init(self):
        self._elements: list[tuple] = []
        self._width, self._cap, self._join = _DEFAULT_LINE_WIDTH[0], 0, 0
        self._rule, self._dash = NSNonZeroWindingRule, None
        return self

    @classmethod
    def bezierPath(cls):
        return cls.alloc().init()

    @classmethod
    def bezierPathWithRect_(cls, rect):
        path = cls.bezierPath()
        path.appendBezierPathWithRect_(rect)
        return path

    @classmethod
    def bezierPathWithOvalInRect_(cls, rect):
        path = cls.bezierPath()
        path.appendBezierPathWithOvalInRect_(rect)
        return path

    @classmethod
    def bezierPathWithRoundedRect_xRadius_yRadius_(cls, rect, rx, ry):
        path = cls.bezierPath()
        path.appendBezierPathWithRoundedRect_xRadius_yRadius_(rect, rx, ry)
        return path

    @classmethod
    def bezierPathWithRoundedRect_cornerRadius_(cls, rect, radius):
        return cls.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)

    @classmethod
    def fillRect_(cls, rect) -> None:
        cls.bezierPathWithRect_(rect).fill()

    @classmethod
    def strokeRect_(cls, rect) -> None:
        cls.bezierPathWithRect_(rect).stroke()

    @classmethod
    def strokeLineFromPoint_toPoint_(cls, a, b) -> None:
        path = cls.bezierPath()
        path.moveToPoint_(a)
        path.lineToPoint_(b)
        path.stroke()

    @classmethod
    def setDefaultLineWidth_(cls, width) -> None:
        _DEFAULT_LINE_WIDTH[0] = float(width)

    @classmethod
    def defaultLineWidth(cls) -> float:
        return _DEFAULT_LINE_WIDTH[0]

    # construction
    def moveToPoint_(self, point) -> None:
        self._elements.append(("move", _pt(point)))

    def lineToPoint_(self, point) -> None:
        self._elements.append(("line", _pt(point)))

    def curveToPoint_controlPoint1_controlPoint2_(self, point, c1, c2) -> None:
        self._elements.append(("curve", _pt(c1), _pt(c2), _pt(point)))

    def closePath(self) -> None:
        self._elements.append(("close",))

    def removeAllPoints(self) -> None:
        self._elements.clear()

    def appendBezierPath_(self, other) -> None:
        self._elements.extend(other._elements)

    def appendBezierPathWithRect_(self, rect) -> None:
        (x, y), (w, h) = as_rect(rect)
        self.moveToPoint_((x, y))
        for point in ((x + w, y), (x + w, y + h), (x, y + h)):
            self.lineToPoint_(point)
        self.closePath()

    def appendBezierPathWithOvalInRect_(self, rect) -> None:
        self.appendBezierPathWithRoundedRect_xRadius_yRadius_(
            rect, as_rect(rect).size.width / 2, as_rect(rect).size.height / 2
        )

    def appendBezierPathWithRoundedRect_xRadius_yRadius_(self, rect, rx, ry):
        (x, y), (w, h) = as_rect(rect)
        rx, ry = min(float(rx), w / 2), min(float(ry), h / 2)
        kx, ky = rx * _KAPPA, ry * _KAPPA
        self.moveToPoint_((x + rx, y))
        self.lineToPoint_((x + w - rx, y))
        self._corner((x + w - rx + kx, y), (x + w, y + ry - ky), (x + w, y + ry))
        self.lineToPoint_((x + w, y + h - ry))
        self._corner(
            (x + w, y + h - ry + ky), (x + w - rx + kx, y + h), (x + w - rx, y + h)
        )
        self.lineToPoint_((x + rx, y + h))
        self._corner((x + rx - kx, y + h), (x, y + h - ry + ky), (x, y + h - ry))
        self.lineToPoint_((x, y + ry))
        self._corner((x, y + ry - ky), (x + rx - kx, y), (x + rx, y))
        self.closePath()

    def _corner(self, c1, c2, end) -> None:
        if c1 != end:
            self.curveToPoint_controlPoint1_controlPoint2_(end, c1, c2)

    # attributes
    def lineWidth(self) -> float:
        return self._width

    def setLineWidth_(self, width) -> None:
        self._width = float(width)

    def setLineCapStyle_(self, style) -> None:
        self._cap = int(style)

    def setLineJoinStyle_(self, style) -> None:
        self._join = int(style)

    def setWindingRule_(self, rule) -> None:
        self._rule = int(rule)

    def setLineDash_count_phase_(self, pattern, count, phase) -> None:
        self._dash = (list(pattern)[: int(count)], float(phase)) if count else None

    def elementCount(self) -> int:
        return len(self._elements)

    def isEmpty(self) -> bool:
        return not self._elements

    def copy(self):
        clone = type(self).bezierPath()
        clone._elements = list(self._elements)
        clone._width, clone._cap, clone._join = self._width, self._cap, self._join
        clone._rule, clone._dash = self._rule, self._dash
        return clone

    def transformUsingAffineTransform_(self, transform) -> None:
        t = transform._m
        self._elements = [
            (kind, *[gc.apply(t, *p) for p in points])
            for kind, *points in self._elements
        ]

    def bounds(self) -> NSRect:
        points = [p for _, *ps in self._elements for p in ps]
        if not points:
            return NSMakeRect(0, 0, 0, 0)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return NSMakeRect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    controlPointBounds = bounds

    def containsPoint_(self, point) -> bool:
        """Cocoa fill containment, including cubic curves and winding rules."""
        from ..fonttools import fonttools_module

        module = fonttools_module("pens.pointInsidePen", "NSBezierPath.containsPoint_")
        pen = module.PointInsidePen(None, _pt(point), evenOdd=bool(self._rule))
        for kind, *points in self._elements:
            if kind == "move":
                pen.moveTo(points[0])
            elif kind == "line":
                pen.lineTo(points[0])
            elif kind == "curve":
                pen.curveTo(*points)
            else:
                pen.closePath()
        return pen.getResult()

    # painting
    def qpath(self, qt: Any) -> Any:
        gui, core = qt.QtGui, qt.QtCore
        path = gui.QPainterPath()
        for kind, *points in self._elements:
            if kind == "move":
                path.moveTo(core.QPointF(*points[0]))
            elif kind == "line":
                path.lineTo(core.QPointF(*points[0]))
            elif kind == "curve":
                path.cubicTo(*(core.QPointF(*p) for p in points))
            else:
                path.closeSubpath()
        path.setFillRule(core.Qt.OddEvenFill if self._rule else core.Qt.WindingFill)
        return path

    def fill(self) -> None:
        ctx = gc.optional_current()
        if ctx is None:
            return
        color = ctx.state.fill or NSColor(0, 0, 0, 1)
        painter = ctx.painter
        painter.setTransform(ctx.qtransform())
        painter.fillPath(self.qpath(ctx.qt), ctx.qt.QtGui.QBrush(color.qcolor(ctx.qt)))

    def stroke(self) -> None:
        ctx = gc.optional_current()
        if ctx is None:
            return
        qt, painter = ctx.qt, ctx.painter
        color = ctx.state.stroke or NSColor(0, 0, 0, 1)
        pen = qt.QtGui.QPen(color.qcolor(qt))
        pen.setWidthF(self._width)
        core = qt.QtCore.Qt
        pen.setCapStyle((core.FlatCap, core.RoundCap, core.SquareCap)[self._cap])
        pen.setJoinStyle((core.MiterJoin, core.RoundJoin, core.BevelJoin)[self._join])
        if self._dash and self._width > 0:
            pen.setDashPattern([max(v / self._width, 0.01) for v in self._dash[0]])
            pen.setDashOffset(self._dash[1] / self._width)
        painter.setTransform(ctx.qtransform())
        painter.strokePath(self.qpath(qt), pen)


def _pt(point) -> tuple[float, float]:
    x, y = point
    return float(x), float(y)


class NSAffineTransform(NSObject):
    """A 2D affine matrix; ``concat``/``set`` act on the current context CTM."""

    def init(self):
        self._m = gc.IDENTITY
        return self

    @classmethod
    def transform(cls):
        return cls.alloc().init()

    def initWithTransform_(self, other):
        self._m = other._m
        return self

    def _prepend(self, t: gc.Affine) -> None:
        self._m = gc.concat(t, self._m)

    def translateXBy_yBy_(self, x, y) -> None:
        self._prepend((1.0, 0.0, 0.0, 1.0, float(x), float(y)))

    def scaleBy_(self, factor) -> None:
        self.scaleXBy_yBy_(factor, factor)

    def scaleXBy_yBy_(self, sx, sy) -> None:
        self._prepend((float(sx), 0.0, 0.0, float(sy), 0.0, 0.0))

    def shearXBy_(self, factor) -> None:
        """Glyphs' category method: x' = x + factor * y (prepended)."""
        self._prepend((1.0, 0.0, float(factor), 1.0, 0.0, 0.0))

    def rotateByDegrees_(self, degrees) -> None:
        self._prepend(gc.rotation(float(degrees)))

    def rotateByRadians_(self, radians) -> None:
        self.rotateByDegrees_(math.degrees(float(radians)))

    def appendTransform_(self, other) -> None:
        self._m = gc.concat(self._m, other._m)

    def prependTransform_(self, other) -> None:
        self._prepend(other._m)

    def invert(self) -> None:
        self._m = gc.invert(self._m)

    def transformStruct(self) -> NSAffineTransformStruct:
        return NSAffineTransformStruct(*self._m)

    def setTransformStruct_(self, values) -> None:
        matrix = tuple(float(v) for v in values)
        if len(matrix) != 6:
            raise ValueError("NSAffineTransformStruct needs six values")
        self._m = matrix

    def transformPoint_(self, point):
        return gc.apply(self._m, *_pt(point))

    def transformSize_(self, size):
        a, b, c, d, _, _ = self._m
        w, h = size
        return w * a + h * c, w * b + h * d

    def transformBezierPath_(self, path):
        clone = path.copy()
        clone.transformUsingAffineTransform_(self)
        return clone

    def concat(self) -> None:
        state = gc.current().state
        state.ctm = gc.concat(self._m, state.ctm)

    def set(self) -> None:
        gc.current().state.ctm = self._m


class NSGraphicsContext(NSObject):
    """``currentContext().saveGraphicsState()`` and the class-level pair."""

    @classmethod
    def currentContext(cls):
        context = cls.alloc().init()
        context._context = gc.current()
        return context

    @classmethod
    def saveGraphicsState(cls) -> None:
        gc.current().save()

    @classmethod
    def restoreGraphicsState(cls) -> None:
        gc.current().restore()

    def setShouldAntialias_(self, flag) -> None:
        self._context.state.antialias = bool(flag)
        hint = self._context.qt.QtGui.QPainter.Antialiasing
        self._context.painter.setRenderHint(hint, bool(flag))

    def isFlipped(self) -> bool:
        return self._context.flipped


def NSRectFill(rect) -> None:
    NSBezierPath.fillRect_(rect)


def NSFrameRect(rect) -> None:
    NSBezierPath.strokeRect_(rect)


class NSFont(NSObject):
    """A font name and point size; ``qfont`` builds the QFont at paint time."""

    SYSTEM = ".AppleSystemUIFont"

    @classmethod
    def _make(cls, name: str, size: float, weight: float = 0.0):
        font = cls.alloc().init()
        font._name, font._size, font._weight = name, float(size), float(weight)
        return font

    @classmethod
    def systemFontOfSize_(cls, size):
        return cls._make(cls.SYSTEM, size)

    @classmethod
    def menuFontOfSize_(cls, size):
        return cls._make(cls.SYSTEM, size or cls.systemFontSize())

    def fontWithSize_(self, size):
        return self._make(self._name, size, self._weight)

    labelFontOfSize_ = systemFontOfSize_
    userFontOfSize_ = systemFontOfSize_

    @classmethod
    def boldSystemFontOfSize_(cls, size):
        return cls._make(cls.SYSTEM, size, 0.4)

    @classmethod
    def systemFontOfSize_weight_(cls, size, weight):
        return cls._make(cls.SYSTEM, size, weight)

    @classmethod
    def monospacedDigitSystemFontOfSize_weight_(cls, size, weight):
        return cls._make(cls.SYSTEM, size, weight)

    @classmethod
    def monospacedSystemFontOfSize_weight_(cls, size, weight):
        return cls._make("Menlo", size, weight)

    @classmethod
    def userFixedPitchFontOfSize_(cls, size):
        return cls._make("Menlo", size or 11)

    @classmethod
    def fontWithName_size_(cls, name, size):
        return cls._make(str(name), size)

    @classmethod
    def systemFontSize(cls) -> float:
        return 13.0

    @classmethod
    def smallSystemFontSize(cls) -> float:
        return 11.0

    def pointSize(self) -> float:
        return self._size

    def fontName(self) -> str:
        return self._name

    def qfont(self, qt: Any, pixel_size: float) -> Any:
        font = qt.QtGui.QFont()
        if self._name != self.SYSTEM:
            font.setFamily(self._name)
        font.setPixelSize(max(1, round(pixel_size)))
        if self._weight > 0.2:
            font.setBold(True)
        return font


class NSMutableParagraphStyle(NSObject):
    """Paragraph attributes a script sets. Text drawn at a point is one
    unbounded line in Cocoa, so alignment and line breaking do not move it;
    they are kept for reads."""

    def init(self):
        self._alignment, self._line_break = 0, 0
        return self

    def setAlignment_(self, value) -> None:
        self._alignment = int(value)

    def alignment(self) -> int:
        return self._alignment

    def setLineBreakMode_(self, value) -> None:
        self._line_break = int(value)

    def lineBreakMode(self) -> int:
        return self._line_break


class NSAttributedString(NSObject):
    """A string with NSFont/NSColor attributes; draws upright in any CTM."""

    def initWithString_attributes_(self, text, attributes):
        self._text, self._attrs = str(text), dict(attributes or {})
        return self

    def initWithString_(self, text):
        return self.initWithString_attributes_(text, {})

    def string(self) -> str:
        return self._text

    def length(self) -> int:
        return len(self._text)

    def _font(self):
        return self._attrs.get(NSFontAttributeName) or NSFont.systemFontOfSize_(12)

    def size(self):
        font = self._font()
        return NSSize(len(self._text) * font.pointSize() * 0.6, font.pointSize() * 1.2)

    def drawAtPoint_(self, point) -> None:
        self.drawAtPoint_alignment_(point, 0)

    def drawAtPoint_alignment_(self, point, alignment) -> None:
        """Glyphs' alignment codes: 0-2 bottom, 3-5 middle, 6-8 top; left/centre/right."""
        ctx = gc.current()
        qt, painter = ctx.qt, ctx.painter
        device = ctx.device()
        x, y = gc.apply(device, *_pt(point))
        scale = math.hypot(device[0], device[1])
        font = self._font().qfont(qt, self._font().pointSize() * scale)
        metrics = qt.QtGui.QFontMetricsF(font)
        width, ascent, descent = (
            metrics.width(self._text),
            metrics.ascent(),
            metrics.descent(),
        )
        column, row = int(alignment) % 3, int(alignment) // 3
        x -= (0.0, width / 2, width)[column]
        y_up = device[3] < 0  # drawing space y grows upward on screen
        height = ascent + descent
        baseline = y - descent if y_up else y + ascent
        shift = (0.0, height / 2, height)[row]
        baseline += shift if y_up else -shift
        color = self._attrs.get(NSForegroundColorAttributeName) or NSColor(0, 0, 0, 1)
        painter.setTransform(qt.QtGui.QTransform())
        painter.setFont(font)
        painter.setPen(color.qcolor(qt))
        painter.drawText(qt.QtCore.QPointF(x, baseline), self._text)


class NSString(str):
    """A Python string with the NSString drawing calls the corpus uses."""

    @classmethod
    def stringWithString_(cls, text):
        return cls(text)

    @classmethod
    def string(cls):
        return cls("")

    def drawAtPoint_withAttributes_(self, point, attributes) -> None:
        NSAttributedString.alloc().initWithString_attributes_(
            self, attributes
        ).drawAtPoint_(point)

    def sizeWithAttributes_(self, attributes):
        return (
            NSAttributedString.alloc()
            .initWithString_attributes_(self, attributes)
            .size()
        )


DRAWING_NAMES = {
    "NSColor": NSColor,
    "NSBezierPath": NSBezierPath,
    "NSAffineTransform": NSAffineTransform,
    "NSGraphicsContext": NSGraphicsContext,
    "NSFont": NSFont,
    "NSAttributedString": NSAttributedString,
    "NSString": NSString,
    "NSRectFill": NSRectFill,
    "NSFrameRect": NSFrameRect,
    "NSFontAttributeName": NSFontAttributeName,
    "NSForegroundColorAttributeName": NSForegroundColorAttributeName,
    "NSBackgroundColorAttributeName": NSBackgroundColorAttributeName,
    "NSParagraphStyleAttributeName": NSParagraphStyleAttributeName,
    "NSMutableParagraphStyle": NSMutableParagraphStyle,
    "NSButtLineCapStyle": NSButtLineCapStyle,
    "NSRoundLineCapStyle": NSRoundLineCapStyle,
    "NSSquareLineCapStyle": NSSquareLineCapStyle,
    "NSMiterLineJoinStyle": NSMiterLineJoinStyle,
    "NSRoundLineJoinStyle": NSRoundLineJoinStyle,
    "NSBevelLineJoinStyle": NSBevelLineJoinStyle,
    "NSNonZeroWindingRule": NSNonZeroWindingRule,
    "NSEvenOddWindingRule": NSEvenOddWindingRule,
}
