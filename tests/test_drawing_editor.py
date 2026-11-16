# this_file: tests/test_drawing_editor.py
"""EditorPainters over FontLab-shaped doubles (native proof: native_editor_painters)."""

from types import SimpleNamespace

import pytest
from drawing_doubles import QPainter, QPointF, QTransform

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.drawing.editor import EditorPainters
from fontlab_glyport.errors import UnsupportedCapability


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)


class Widget:
    def __init__(self, parent=None, name="QWidget"):
        self._name, self.parent, self.filters = name, parent, []
        self.attrs, self.visible, self.deleted, self.updates = {}, False, False, 0
        self.destroyed = Signal()
        self.rect = (0, 0, 800, 600)

    def className(self):
        return self._name

    def isVisible(self):
        return True

    def findChildren(self, cls):
        return [w for w in WIDGETS if w.parent is self]

    def installEventFilter(self, f):
        self.filters.append(f)

    def removeEventFilter(self, f):
        self.filters.remove(f)

    def setAttribute(self, a, on):
        self.attrs[a] = on

    def setGeometry(self, *args):
        self.geometry = args

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def raise_(self):
        pass

    def update(self):
        self.updates += 1

    def setParent(self, p):
        self.parent = p

    def deleteLater(self):
        self.deleted = True

    def devicePixelRatioF(self):
        return 2.0


WIDGETS: list = []


class Timer:
    def __init__(self):
        self.timeout, self.running, self.deleted = Signal(), False, False

    def setInterval(self, ms):
        self.ms = ms

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def deleteLater(self):
        self.deleted = True


class Info:
    def __init__(self, dx, active, kerning=0.0):
        self.transform = QTransform(0.1, 0, 0, -0.1, dx, 100)
        self.isActive, self.id, self._k = active, dx, kerning

    def kerningOffset(self, flag):
        return self._k


class Canvas:
    def __init__(self, infos):
        self.block = SimpleNamespace(
            transform=QTransform(),
            getAllGlyphs=lambda: infos,
            package=SimpleNamespace(id=7),
        )

    def textBlocks(self):
        return [self.block]

    def mapToViewportF(self, p):
        return QPointF(p.x() * 4 + 10, p.y() * 4 + 20)


def _setup(infos):
    WIDGETS.clear()
    window = Widget(name="GlyphWindow")
    viewport = Widget(window)
    WIDGETS.extend([window, viewport])
    canvas = Canvas(infos)
    workspace = SimpleNamespace(
        getCanvasForViewport=lambda w: canvas if w is viewport else None
    )

    class Base(Widget):
        def __init__(self, parent=None):
            super().__init__(parent)

    gui = SimpleNamespace(
        QWidget=Base,
        QApplication=SimpleNamespace(allWidgets=lambda: list(WIDGETS)),
        QPainter=lambda device: Recorder(),
        QTransform=QTransform,
    )
    core = SimpleNamespace(
        QTimer=Timer,
        QPointF=QPointF,
        QEvent=SimpleNamespace(Resize=14),
        Qt=SimpleNamespace(WA_TransparentForMouseEvents=1, WA_NoSystemBackground=2),
    )
    fl = SimpleNamespace(flWorkspace=SimpleNamespace(instance=lambda: workspace))
    errors = []
    painters = EditorPainters(
        SimpleNamespace(QtGui=gui, QtCore=core),
        fl,
        error_sink=lambda e, s: errors.append(e),
    )
    return painters, viewport, errors


class Recorder(QPainter):
    def end(self):
        self.calls.append(("end",))


def _overlay(painters):
    return next(iter(painters.overlays.values()))[0]


def test_register_when_before_phase_then_r054_unsupported():
    painters, _, _ = _setup([])
    with pytest.raises(UnsupportedCapability) as info:
        painters.register("before_native_layer", lambda c: None)
    assert info.value.capability == "FontLab.painter.before_native_layer"
    assert painters.overlays == {} and painters._timer is None


def test_register_when_glyph_window_then_overlay_and_glyph_contexts():
    painters, viewport, errors = _setup([Info(0, True), Info(60, False, kerning=5)])
    seen = []
    painters.register("after_native_layer", seen.append, layer_filter="all")
    overlay = _overlay(painters)
    assert overlay.parent is viewport and overlay in viewport.filters
    assert overlay.attrs == {1: True, 2: True} and overlay.visible
    overlay.paintEvent(SimpleNamespace(rect=lambda: "clip"))
    assert [c.is_active_layer for c in seen] == [True, False]
    first, second = seen
    full = gc.concat(
        gc.from_qtransform(first.glyph_to_canvas),
        gc.from_qtransform(first.canvas_to_view),
    )
    assert gc.apply(full, 0, 0) == (10.0, 420.0) and first.scale == pytest.approx(0.4)
    assert gc.from_qtransform(second.glyph_to_canvas)[4] == 60.0, (
        "kerning is already in the glyph transform"
    )
    assert (first.document_id, first.clip, first.device_pixel_ratio) == (7, "clip", 2.0)
    assert errors == []


def test_paint_when_filter_active_then_inactive_glyph_skipped_and_errors_to_sink():
    painters, _, errors = _setup([Info(0, True), Info(60, False)])
    calls = []

    def bad(context):
        calls.append(context.glyph_item_id)
        raise ValueError("plugin broke")

    painters.register("after_native_layer", bad)
    _overlay(painters).paintEvent(None)
    assert calls == [0] and [str(e) for e in errors] == ["plugin broke"]


def test_remove_when_last_painter_then_overlays_and_timer_torn_down():
    painters, viewport, _ = _setup([Info(0, True)])
    token = painters.register("after_native_layer", lambda c: None)
    overlay, timer = _overlay(painters), painters._timer
    painters.remove(token)
    painters.remove(token)
    assert painters.overlays == {} and painters._timer is None
    assert timer.timeout.slots == [] and not timer.running and timer.deleted
    assert (
        overlay.deleted and overlay not in viewport.filters and overlay._owner is None
    )
    assert viewport.destroyed.slots == []


def test_viewport_destroyed_when_window_closes_then_overlay_forgotten():
    painters, viewport, _ = _setup([Info(0, True)])
    painters.register("after_native_layer", lambda c: None)
    viewport.destroyed.slots[0]()
    assert painters.overlays == {}


def test_close_when_painters_registered_then_registrations_dropped():
    painters, _, _ = _setup([Info(0, True)])
    painters.register("after_native_layer", lambda c: None)
    painters.close()
    seen = []
    painters.register("after_native_layer", seen.append)
    _overlay(painters).paintEvent(None)
    assert len(seen) == 1 and len(painters.painters) == 1


def test_document_id_when_given_then_only_that_document_painted():
    painters, _, _ = _setup([Info(0, True)])
    mine, other = [], []
    painters.register("after_native_layer", mine.append, document_id=7)
    painters.register("after_native_layer", other.append, document_id=8)
    _overlay(painters).paintEvent(None)
    assert len(mine) == 1 and other == []
