# this_file: tests/test_ui_nib_image.py
"""NSImageView from XIB/NIB (R031 corpus). Fixture: self-authored ``Image.xib``,
its ibtool NIB and ``Dot.png`` (a generated 16x8 rectangle). Images are looked
up by name in the resource folders passed to ``instantiate``."""

from pathlib import Path

import pytest
from test_ui_nib import _canonical
from ui_doubles import QLabel, make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect, NSObject, NSSize
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.nib_graph import graph_from_nib, graph_from_xib
from fontlab_glyport.ui.nib_loader import instantiate, load_graph
from fontlab_glyport.ui.objc_bridge import make_objc_module

FIXTURES = Path(__file__).parent / "fixtures" / "nib"
XIB, NIB = FIXTURES / "Image.xib", FIXTURES / "Image.nib"
OUTLETS = ("dialog", "fitted", "stretched", "missing")


class Pixmap:
    def __init__(self, scale, size=None):
        self.scale, self.size, self.dpr = scale, size, None

    def setDevicePixelRatio(self, ratio):
        self.dpr = ratio

    def scaled(self, width, height, aspect, transform):
        return Pixmap(self.scale, (width, height, aspect, transform))


class PixLabel(QLabel):
    __slots__ = ("pixmap",)

    def __init__(self):
        super().__init__()
        self.pixmap = None

    def setPixmap(self, pixmap):
        self.pixmap = pixmap

    def clear(self):
        self.pixmap = None

    def devicePixelRatioF(self):
        return 1.0


class FakeImage(NSObject):
    """A file-backed image of 16x8 points (the fixture's Dot.png)."""

    def initWithContentsOfFile_(self, path):
        self.path = path
        return self

    def size(self):
        return NSSize(16, 8)

    def pixmap(self, scale=1.0):
        return Pixmap(scale)


def _kit():
    qt = make_qt()
    qt.QtGui.QLabel = PixLabel
    qt.QtCore.Qt.IgnoreAspectRatio = "IgnoreAspectRatio"
    qt.QtCore.Qt.SmoothTransformation = "SmoothTransformation"
    qt.QtCore.Qt.AlignCenter = 0x84
    kit = make_appkit_classes(qt, error_sink=print)
    kit["NSImage"] = FakeImage
    return kit


def _load(source):
    objc = make_objc_module({})
    owner_class = type(
        "ImageOwner", (NSObject,), {name: objc.IBOutlet() for name in OUTLETS}
    )
    kit, owner = _kit(), owner_class.alloc().init()
    instance = instantiate(load_graph(source), owner, kit, resources=[FIXTURES])
    return kit, owner, instance


def test_image_when_xib_and_nib_then_equal_graphs():
    assert _canonical(graph_from_nib(NIB)) == _canonical(graph_from_xib(XIB))
    nodes = graph_from_xib(XIB).to_json()["nodes"]
    views = {n["source_id"]: n["properties"] for n in nodes}
    assert (views["fit"]["image"], views["fit"]["imageScaling"]) == ("Dot", 3)
    assert views["str"]["imageScaling"] == 1 and views["mis"]["imageScaling"] == 0


@pytest.mark.parametrize("source", [XIB, NIB], ids=["xib", "nib"])
def test_instantiate_when_image_views_then_named_images_scaled_to_frames(source):
    kit, owner, instance = _load(source)
    assert all(getattr(owner, name) is not None for name in OUTLETS)
    fitted, stretched = owner.fitted, owner.stretched
    assert isinstance(fitted, kit["NSImageView"])
    assert Path(fitted.image().path) == FIXTURES / "Dot.png"
    assert fitted.imageScaling() == 3
    assert fitted._qt.pixmap.scale == 4.0, "16x8 fitted into 64x40: x4"
    assert stretched._qt.pixmap.size == (
        40,
        40,
        "IgnoreAspectRatio",
        "SmoothTransformation",
    )
    assert owner.missing.image() is None and owner.missing._qt.pixmap is None
    assert instance.diagnostics == ["image NoSuchImage not found"]
    kit["close"]()


def test_image_view_when_image_and_frame_change_then_redrawn():
    kit = _kit()
    view = kit["NSImageView"].alloc().initWithFrame_(NSMakeRect(0, 0, 8, 8))
    image = FakeImage.alloc().initWithContentsOfFile_("x.png")
    view.setImage_(image)
    assert view._qt.pixmap.scale == 0.5, "proportionally down by default"
    view.setFrame_(NSMakeRect(0, 0, 32, 32))
    assert view._qt.pixmap.scale == 1.0, "never scaled up by default"
    view.setImageScaling_(2)  # none
    view.setFrame_(NSMakeRect(0, 0, 4, 4))
    assert view._qt.pixmap.scale == 1.0
    view.setImage_(None)
    assert view._qt.pixmap is None and view.objectValue() is None
    kit["close"]()
