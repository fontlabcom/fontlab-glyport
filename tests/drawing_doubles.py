# this_file: tests/drawing_doubles.py
"""Recording QPainter-family doubles for the Cocoa drawing translation."""

from types import SimpleNamespace


class QPointF:
    def __init__(self, x, y):
        self._x, self._y = float(x), float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def __eq__(self, other):
        return (self._x, self._y) == (other._x, other._y)

    def __repr__(self):
        return f"P({self._x:g},{self._y:g})"


class QTransform:
    def __init__(self, *m):
        self.m = tuple(float(v) for v in m) if m else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def m11(self):
        return self.m[0]

    def m12(self):
        return self.m[1]

    def m21(self):
        return self.m[2]

    def m22(self):
        return self.m[3]

    def dx(self):
        return self.m[4]

    def dy(self):
        return self.m[5]


class QPainterPath:
    def __init__(self):
        self.ops, self.rule = [], None

    def moveTo(self, p):
        self.ops.append(("M", p.x(), p.y()))

    def lineTo(self, p):
        self.ops.append(("L", p.x(), p.y()))

    def cubicTo(self, a, b, c):
        self.ops.append(("C", a.x(), a.y(), b.x(), b.y(), c.x(), c.y()))

    def closeSubpath(self):
        self.ops.append(("Z",))

    def setFillRule(self, rule):
        self.rule = rule


class QColor:
    def __init__(self, rgba):
        self.rgba = rgba

    @staticmethod
    def fromRgbF(r, g, b, a):
        return QColor((r, g, b, a))


class QBrush:
    def __init__(self, color):
        self.color = color


class QPen:
    def __init__(self, color):
        self.color, self.width, self.cap, self.join = color, 1.0, None, None
        self.dash, self.offset = None, None

    def setWidthF(self, w):
        self.width = w

    def setCapStyle(self, c):
        self.cap = c

    def setJoinStyle(self, j):
        self.join = j

    def setDashPattern(self, d):
        self.dash = d

    def setDashOffset(self, o):
        self.offset = o


class QFont:
    def __init__(self):
        self.family, self.pixel, self.bold = None, None, False

    def setFamily(self, f):
        self.family = f

    def setPixelSize(self, s):
        self.pixel = s

    def setBold(self, b):
        self.bold = b


class QFontMetricsF:
    def __init__(self, font):
        self.font = font

    def width(self, text):
        return len(text) * self.font.pixel * 0.5

    def ascent(self):
        return self.font.pixel * 0.8

    def descent(self):
        return self.font.pixel * 0.2


class QPainter:
    Antialiasing = 1

    def __init__(self):
        self.calls = []
        self.transform = None

    def save(self):
        self.calls.append(("save",))

    def restore(self):
        self.calls.append(("restore",))

    def setTransform(self, t, combine=False):
        self.transform = t.m
        self.calls.append(("setTransform", t.m))

    def fillPath(self, path, brush):
        self.calls.append(("fill", path.ops, brush.color.rgba, self.transform))

    def strokePath(self, path, pen):
        self.calls.append(("stroke", path.ops, pen, self.transform))

    def setFont(self, font):
        self.calls.append(("font", font.pixel))

    def setPen(self, color):
        self.calls.append(("pen", color.rgba))

    def drawText(self, point, text):
        self.calls.append(("text", round(point.x(), 3), round(point.y(), 3), text))

    def setRenderHint(self, hint, on):
        self.calls.append(("hint", hint, on))

    def kinds(self):
        return [c[0] for c in self.calls]


def make_drawing_qt():
    gui = SimpleNamespace(
        QPainterPath=QPainterPath,
        QTransform=QTransform,
        QColor=QColor,
        QBrush=QBrush,
        QPen=QPen,
        QFont=QFont,
        QFontMetricsF=QFontMetricsF,
        QPainter=QPainter,
    )
    qt_enums = SimpleNamespace(
        OddEvenFill="OddEven",
        WindingFill="Winding",
        FlatCap="Flat",
        RoundCap="Round",
        SquareCap="Square",
        MiterJoin="Miter",
        RoundJoin="RoundJ",
        BevelJoin="Bevel",
    )
    return SimpleNamespace(
        QtGui=gui, QtCore=SimpleNamespace(QPointF=QPointF, Qt=qt_enums)
    )


class WidgetPainter(QPainter):
    """``QPainter(widget)`` as a custom view's paintEvent builds it."""

    def __init__(self, device=None):
        super().__init__()
        self.device, self.ended = device, False
        PAINTERS.append(self)

    def end(self):
        self.ended = True


PAINTERS: list = []


class QMouseEvent:
    MouseButtonPress, MouseButtonDblClick = 2, 4

    def __init__(self, x, y, modifiers=0, kind=2):
        self._pos, self._mods, self._kind, self.accepted = (
            QPointF(x, y),
            modifiers,
            kind,
            False,
        )

    def localPos(self):
        return self._pos

    def modifiers(self):
        return self._mods

    def type(self):
        return self._kind

    def accept(self):
        self.accepted = True


def add_drawing(qt):
    """Extend a ui_doubles ``make_qt()`` namespace with the painting doubles."""
    drawing = make_drawing_qt()
    for name, value in vars(drawing.QtGui).items():
        setattr(qt.QtGui, name, value)
    qt.QtGui.QPainter = WidgetPainter
    qt.QtCore.QPointF = QPointF
    for name, value in vars(drawing.QtCore.Qt).items():
        setattr(qt.QtCore.Qt, name, value)
    for name, bit in (
        ("ShiftModifier", 0x02000000),
        ("ControlModifier", 0x04000000),
        ("AltModifier", 0x08000000),
        ("MetaModifier", 0x10000000),
    ):
        setattr(qt.QtCore.Qt, name, bit)
    qt.QtCore.QEvent = QMouseEvent
    PAINTERS.clear()
    return qt
