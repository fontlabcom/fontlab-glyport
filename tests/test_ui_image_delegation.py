# this_file: tests/test_ui_image_delegation.py
"""Cocoa image policy stays here while generic algorithms come from App."""

from pathlib import Path
from types import SimpleNamespace

import fontlabapp.qt.images.resources as shared
import pytest

from fontlab_glyport.ui import images
from fontlab_glyport.ui.cocoa import NSSize


def test_resource_adapters_when_called_then_legacy_policy_forwarded(monkeypatch):
    assert images._image_resources is shared, "use the real public App implementation"
    seen = []

    def lookup(*args, **kwargs):
        seen.append((args, kwargs))
        return Path("found")

    monkeypatch.setattr(shared, "find_image", lookup)
    assert images.find_image("name", "root") == Path("found")
    assert seen == [
        (
            ("name", "root"),
            {"extensions": images.IMAGE_TYPES, "folders": images._FOLDERS},
        )
    ]
    monkeypatch.setattr(shared, "retina_variant", lookup)
    images.retina_variant("icon.png")
    assert seen[-1] == (("icon.png",), {"raster_types": images._RASTER})


def test_pdf_adapters_when_called_then_cocoa_size_and_original_process_defaults(
    monkeypatch,
):
    seen = []
    runner = object()

    def dimensions(*args, **kwargs):
        seen.append((args, kwargs))
        return (15.0, 18.0)

    monkeypatch.setattr(shared, "pdf_dimensions", dimensions)
    size = images.pdf_size("file.pdf", run=runner)
    assert isinstance(size, NSSize) and tuple(size) == (15.0, 18.0)
    assert seen[-1] == (
        ("file.pdf",),
        {"run": runner, "executable": images.SIPS, "timeout": images.SIPS_TIMEOUT},
    )
    monkeypatch.setattr(shared, "render_pdf", dimensions)
    images.render_pdf("file.pdf", 30, 36, run=runner)
    assert seen[-1] == (
        ("file.pdf", 30, 36),
        {
            "run": runner,
            "executable": images.SIPS,
            "timeout": images.SIPS_TIMEOUT,
            "scratch_prefix": "glyport-pdf-",
        },
    )
    monkeypatch.setattr(shared, "run_sips", dimensions)
    images._sips(["-g"], runner)
    assert seen[-1] == (
        (["-g"], runner),
        {"executable": images.SIPS, "timeout": images.SIPS_TIMEOUT},
    )


class Image:
    def __init__(self):
        self.scale = None

    def loadFromData(self, data, kind):
        return data == b"valid" and kind == "PNG"

    def setDevicePixelRatio(self, scale):
        self.scale = scale


def source(kind, *, qt=None):
    image = images.image_class(
        qt
        or SimpleNamespace(
            QtGui=SimpleNamespace(QImage=Image), QtCore=SimpleNamespace()
        )
    ).alloc()
    image._path = Path("icon." + kind)
    image._size = NSSize(16, 12)
    return image


@pytest.mark.parametrize("payload", [None, b"bad", b"valid"])
def test_nsimage_when_pdf_rendered_then_original_pixels_or_error(monkeypatch, payload):
    seen = []

    def render(path, width, height):
        seen.append((path, width, height))
        return payload

    monkeypatch.setattr(images, "render_pdf", render)
    image = source("pdf")
    if payload == b"valid":
        assert image.image(2).scale == 2
    else:
        with pytest.raises(OSError, match="cannot rasterise PDF icon.pdf"):
            image.image(2)
    assert seen == [(Path("icon.pdf"), 32, 24)]


@pytest.mark.parametrize("scale,retina", [(1, None), (2, Path("icon@2x.png"))])
def test_nsimage_when_raster_rendered_then_shared_reader_and_retina_policy(
    monkeypatch, scale, retina
):
    image, seen = source("png"), []
    monkeypatch.setattr(images, "retina_variant", lambda path: retina)

    def raster(qt, path, width, height):
        seen.append((qt, path, width, height))
        return Image()

    monkeypatch.setattr(shared, "raster_image", raster)
    assert image.image(scale).scale == scale
    assert seen == [(image._qt, retina or image._path, 16 * scale, 12 * scale)]


def test_nsimage_when_svg_rendered_then_shared_painter_and_deferred_renderer(
    monkeypatch,
):
    image = source("svg")
    seen = []

    def svg(qt, renderer, width, height):
        seen.append((qt, renderer.__self__, width, height))
        return Image()

    monkeypatch.setattr(shared, "svg_image", svg)
    assert image.image().scale == 1
    assert seen == [(image._qt, image, 16, 12)]


@pytest.mark.parametrize("valid", [False, True])
@pytest.mark.parametrize("module", ["QtSvg", "QtGui"])
def test_nsimage_when_svg_inspected_then_existing_renderer_and_validity(valid, module):
    renderer = SimpleNamespace(
        isValid=lambda: valid,
        defaultSize=lambda: SimpleNamespace(width=lambda: 5, height=lambda: 6),
    )
    qt = SimpleNamespace(
        **{module: SimpleNamespace(QSvgRenderer=lambda path: renderer)}
    )
    image = source("svg", qt=qt)
    assert image._svg() is renderer
    size = image._natural_size()
    assert (tuple(size) if size else None) == ((5.0, 6.0) if valid else None)


def test_nsimage_when_pdf_size_or_icon_requested_then_cocoa_policy_and_composition(
    monkeypatch,
):
    seen = []
    icon = SimpleNamespace(addPixmap=seen.append)
    qt = SimpleNamespace(
        QtGui=SimpleNamespace(
            QIcon=lambda: icon,
            QPixmap=SimpleNamespace(fromImage=lambda image: ("pixmap", image.scale)),
        )
    )
    image = source("pdf", qt=qt)
    monkeypatch.setattr(images, "pdf_size", lambda path: NSSize(5, 6))
    assert tuple(image._natural_size()) == (5, 6)
    image.setSize_((7, 8))
    assert tuple(image.size()) == (7, 8) and image.path() == "icon.pdf"
    image.image = lambda scale: SimpleNamespace(scale=scale)
    assert image.icon() is icon
    assert seen == [("pixmap", 1.0), ("pixmap", 2.0)]
    cursor = images.cursor_class(SimpleNamespace()).arrowCursor()
    assert cursor.set() is None and cursor.push() is None and cursor.pop() is None
