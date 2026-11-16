# this_file: src/fontlab_glyport/ui/images.py
"""Bundle image resources for Qt: the ``NSImage`` subset plugins use, and ``NSCursor``.

``NSImage.alloc().initWithContentsOfFile_(path)``, ``NSImage.imageNamed_(name)``
over the plugin bundle's resources, and ``find_image(name, resources)`` (the
SDK's automatic lookup of ``self.icon = "ExportIcon"`` or a tool's ``toolbar``)
give an image whose ``pixmap(scale)`` renders at ``size() * scale`` device
pixels with alpha:

- formats Qt reads (PNG, TIFF, ...): from 2x up the ``name@2x`` sibling when
  the bundle has one, else the frame nearest the requested size (multi-image
  TIFFs carry 1x/2x variants), scaled smoothly;
- SVG: ``QSvgRenderer`` into a transparent image, so every scale is vector;
- PDF: Qt 5 has no PDF reader, so macOS ``sips`` rasterises the page at the
  requested pixel size into a scratch PNG that is deleted after reading.

Unreadable files give ``None``, as in AppKit. Size is in points: a raster's
first frame, an SVG's default size, a PDF page's size at 72 dpi.
"""

import subprocess
from pathlib import Path
from typing import Any

import fontlabapp.qt.images.resources as _image_resources

from .cocoa import NSObject, NSSize

IMAGE_TYPES = ("pdf", "tiff", "tif", "png", "svg", "icns", "jpg", "jpeg", "gif")
SIPS = "/usr/bin/sips"
SIPS_TIMEOUT = 5.0
_FOLDERS = ("", "Base.lproj", "en.lproj", "English.lproj")


def find_image(name: str | None, resources: str | Path | None) -> Path | None:
    """``name`` (with or without extension) under ``resources`` or its lprojs."""
    return _image_resources.find_image(
        name, resources, extensions=IMAGE_TYPES, folders=_FOLDERS
    )


_RASTER = ("tiff", "tif", "png", "jpg", "jpeg", "gif")


def retina_variant(path: str | Path) -> Path | None:
    """A raster's ``name@2x`` sibling (AppKit's high-DPI representation)."""
    return _image_resources.retina_variant(path, raster_types=_RASTER)


def _sips(argv: list[str], run) -> Any:
    return _image_resources.run_sips(argv, run, executable=SIPS, timeout=SIPS_TIMEOUT)


def pdf_size(path: str | Path, *, run=subprocess.run) -> NSSize | None:
    """The first page's size in points, or None when sips cannot read it."""
    size = _image_resources.pdf_dimensions(
        path, run=run, executable=SIPS, timeout=SIPS_TIMEOUT
    )
    return NSSize(*size) if size is not None else None


def render_pdf(
    path: str | Path, width: int, height: int, *, run=subprocess.run
) -> bytes | None:
    """PNG bytes of the page rasterised at ``width`` x ``height`` pixels."""
    return _image_resources.render_pdf(
        path,
        width,
        height,
        run=run,
        executable=SIPS,
        timeout=SIPS_TIMEOUT,
        scratch_prefix="glyport-pdf-",
    )


class NSImage(NSObject):
    """A file-backed image; ``image_class(qt, resources)`` binds Qt and lookup."""

    _qt: Any = None
    _resources: tuple = ()

    @classmethod
    def imageNamed_(cls, name):
        for root in cls._resources:
            path = find_image(str(name), root)
            if path is not None:
                return cls.alloc().initWithContentsOfFile_(str(path))
        return None

    def initWithContentsOfFile_(self, path):
        self._path, self._template = Path(str(path)), False
        size = self._natural_size() if self._path.is_file() else None
        if size is None:
            return None
        self._size = size
        return self

    def _kind(self) -> str:
        return self._path.suffix.lower().lstrip(".")

    def _natural_size(self) -> NSSize | None:
        if self._kind() == "pdf":
            return pdf_size(self._path)
        if self._kind() in ("svg", "svgz"):
            renderer = self._svg()
            if not renderer.isValid():
                return None
            size = renderer.defaultSize()
        else:
            reader = self._qt.QtGui.QImageReader(str(self._path))
            if not reader.canRead():
                return None
            size = reader.size()
        return NSSize(float(size.width()), float(size.height()))

    def _svg(self) -> Any:
        module = getattr(self._qt, "QtSvg", None) or self._qt.QtGui
        return module.QSvgRenderer(
            str(self._path)
        )  # never read its properties generically

    def path(self) -> str:
        return str(self._path)

    def size(self) -> NSSize:
        return self._size

    def setSize_(self, size) -> None:
        self._size = NSSize(float(size[0]), float(size[1]))

    def isTemplate(self) -> bool:
        return self._template

    def setTemplate_(self, flag) -> None:
        self._template = bool(flag)

    def image(self, scale: float = 1.0) -> Any:
        """A ``QImage`` of ``size() * scale`` pixels, devicePixelRatio ``scale``."""
        gui = self._qt.QtGui
        width = max(1, round(self._size.width * scale))
        height = max(1, round(self._size.height * scale))
        kind = self._kind()
        if kind == "pdf":
            data = render_pdf(self._path, width, height)
            image = gui.QImage()
            if data is None or not image.loadFromData(data, "PNG"):
                raise OSError(f"cannot rasterise PDF {self._path.name}")
        elif kind in ("svg", "svgz"):
            image = _image_resources.svg_image(self._qt, self._svg, width, height)
        else:
            retina = retina_variant(self._path) if scale >= 2 else None
            image = self._raster(retina or self._path, width, height)
        image.setDevicePixelRatio(scale)
        return image

    def _raster(self, path: Path, width: int, height: int) -> Any:
        return _image_resources.raster_image(self._qt, path, width, height)

    def pixmap(self, scale: float = 1.0) -> Any:
        return self._qt.QtGui.QPixmap.fromImage(self.image(scale))

    def icon(self) -> Any:
        """A ``QIcon`` with 1x and 2x pixmaps."""
        icon = self._qt.QtGui.QIcon()
        for scale in (1.0, 2.0):
            icon.addPixmap(self.pixmap(scale))
        return icon


def image_class(qt: Any, resources=()) -> type:
    """``NSImage`` bound to ``qt`` (PythonQt or a namespace with QtGui/QtCore[/QtSvg])
    and to the resource folders ``imageNamed_`` searches."""
    return type("NSImage", (NSImage,), {"_qt": qt, "_resources": tuple(resources)})


# AppKit cursor factory -> Qt::CursorShape name.
_CURSORS = {
    "arrowCursor": "ArrowCursor",
    "pointingHandCursor": "PointingHandCursor",
    "crosshairCursor": "CrossCursor",
    "IBeamCursor": "IBeamCursor",
    "openHandCursor": "OpenHandCursor",
    "closedHandCursor": "ClosedHandCursor",
    "resizeLeftRightCursor": "SizeHorCursor",
    "resizeUpDownCursor": "SizeVerCursor",
    "operationNotAllowedCursor": "ForbiddenCursor",
}


class NSCursor(NSObject):
    """A standard cursor (Qt cursor shape) or an image with a hot spot.

    Glyphs tools return one from ``standardCursor``; ``qcursor()`` gives the
    ``QCursor`` a host would set. FontLab 9 has no Python tool API (R054), so
    nothing installs a tool cursor yet.
    """

    _qt: Any = None
    _shared: dict

    def initWithImage_hotSpot_(self, image, point):
        self._shape, self._image = None, image
        self._hot_spot = (float(point[0]), float(point[1]))
        return self

    def hotSpot(self) -> tuple:
        return self._hot_spot

    def image(self):
        return self._image

    def qcursor(self) -> Any:
        gui = self._qt.QtGui
        if self._shape is not None:
            return gui.QCursor(getattr(self._qt.QtCore.Qt, self._shape))
        x, y = self._hot_spot
        return gui.QCursor(self._image.pixmap(), round(x), round(y))

    def set(self) -> None:
        """No current-cursor stack in the FontLab host: a no-op, as for push/pop."""

    push = pop = set


def _standard(name: str, shape: str):
    def factory(cls):
        if name not in cls._shared:
            cursor = cls.alloc()
            cursor._shape, cursor._image, cursor._hot_spot = shape, None, (0.0, 0.0)
            cls._shared[name] = cursor
        return cls._shared[name]

    factory.__name__ = name
    return classmethod(factory)


for _name, _shape in _CURSORS.items():
    setattr(NSCursor, _name, _standard(_name, _shape))


def cursor_class(qt: Any) -> type:
    """``NSCursor`` bound to ``qt``; standard cursors are shared per binding."""
    return type("NSCursor", (NSCursor,), {"_qt": qt, "_shared": {}})
