# this_file: tests/test_ui_images.py
"""Bundle image resources (NSImage subset). Pixel rendering is native-only:
verification/issue-101-ecosystem/evidence/glyport-matrix (svg, raster, pdf)."""

import subprocess
from types import SimpleNamespace
from typing import ClassVar

from fontlab_glyport.ui import images
from fontlab_glyport.ui.cocoa_menu import NSMenuItem
from fontlab_glyport.ui.images import find_image, image_class, pdf_size, render_pdf


def _resources(tmp_path):
    root = tmp_path / "Plugin.glyphsFileFormat/Contents/Resources"
    (root / "Base.lproj").mkdir(parents=True)
    (root / "ExportIcon.tiff").write_bytes(b"II*\x00")
    (root / "Base.lproj/toolbar.pdf").write_bytes(b"%PDF-1.6")
    (root / "icons").mkdir()
    (root / "icons/add.svg").write_text("<svg/>")
    return root


def test_find_image_when_bare_name_then_first_known_type_in_bundle(tmp_path):
    root = _resources(tmp_path)
    assert find_image("ExportIcon", root) == root / "ExportIcon.tiff"
    assert find_image("toolbar", root) == root / "Base.lproj/toolbar.pdf"
    assert find_image("icons/add.svg", root) == root / "icons/add.svg"
    assert find_image("Missing", root) is None
    assert find_image("", root) is None and find_image("ExportIcon", None) is None


def test_pdf_size_when_sips_reports_points_then_size_else_none():
    out = "x.pdf\n  pixelWidth: 15.000\n  pixelHeight: 18.000\n"

    def run(argv, **kw):
        assert argv[:2] == [images.SIPS, "-g"] and kw["timeout"] == images.SIPS_TIMEOUT
        return SimpleNamespace(returncode=0, stdout=out)

    assert tuple(pdf_size("x.pdf", run=run)) == (15.0, 18.0)
    failed = lambda argv, **kw: SimpleNamespace(returncode=1, stdout="")
    assert pdf_size("x.pdf", run=failed) is None

    def timeout(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    assert pdf_size("x.pdf", run=timeout) is None


def test_render_pdf_when_rasterised_then_png_bytes_and_scratch_removed():
    seen = []

    def run(argv, **kw):
        seen.append(argv)
        out = argv[argv.index("--out") + 1]
        with open(out, "wb") as stream:
            stream.write(b"\x89PNG")
        return SimpleNamespace(returncode=0, stdout="")

    assert render_pdf("x.pdf", 30, 36, run=run) == b"\x89PNG"
    argv = seen[0]
    assert argv[argv.index("-z") + 1 : argv.index("-z") + 3] == ["36", "30"]
    import os

    assert not os.path.exists(argv[argv.index("--out") + 1])


class _Reader:
    sizes: ClassVar = {".png": (16, 12)}

    def __init__(self, path):
        import os

        self.dims = self.sizes.get(os.path.splitext(path)[1])

    def canRead(self):
        return self.dims is not None

    def size(self):
        w, h = self.dims
        return SimpleNamespace(width=lambda: w, height=lambda: h)


def test_init_with_contents_when_missing_or_unreadable_then_none(tmp_path):
    qt = SimpleNamespace(QtGui=SimpleNamespace(QImageReader=_Reader))
    NSImage = image_class(qt)
    png = tmp_path / "a.png"
    png.write_bytes(b"x")
    image = NSImage.alloc().initWithContentsOfFile_(str(png))
    assert tuple(image.size()) == (16, 12) and not image.isTemplate()
    image.setTemplate_(True)
    assert image.isTemplate()
    assert NSImage.alloc().initWithContentsOfFile_(str(tmp_path / "none.png")) is None
    bad = tmp_path / "a.bmpx"
    bad.write_bytes(b"x")
    assert NSImage.alloc().initWithContentsOfFile_(str(bad)) is None


def test_image_named_when_bound_to_bundle_resources_then_resolved(tmp_path):
    root = tmp_path / "R"
    root.mkdir()
    (root / "Icon.png").write_bytes(b"x")
    qt = SimpleNamespace(QtGui=SimpleNamespace(QImageReader=_Reader))
    NSImage = image_class(qt, [root])
    assert tuple(NSImage.imageNamed_("Icon").size()) == (16, 12)
    assert NSImage.imageNamed_("Nope") is None


def test_menu_item_image_when_set_then_observers_told():
    item, seen = NSMenuItem("Export", lambda s: None), []
    item._observers.append(seen.append)
    image = object()
    item.setImage_(image)
    assert item.image() is image and seen == [item]


def test_cursor_when_standard_or_image_then_qt_shape_or_pixmap():
    shapes = SimpleNamespace(PointingHandCursor=13, ArrowCursor=0, CrossCursor=2)
    made = []

    class QCursor:
        def __init__(self, *args):
            made.append(args)

    qt = SimpleNamespace(
        QtCore=SimpleNamespace(Qt=shapes), QtGui=SimpleNamespace(QCursor=QCursor)
    )
    NSCursor = images.cursor_class(qt)
    hand = NSCursor.pointingHandCursor()
    assert hand is NSCursor.pointingHandCursor(), "standard cursors are shared"
    hand.qcursor()
    assert made[-1] == (13,)
    image = SimpleNamespace(pixmap=lambda scale=1.0: "pixmap")
    custom = NSCursor.alloc().initWithImage_hotSpot_(image, (3, 4))
    custom.qcursor()
    assert made[-1] == ("pixmap", 3, 4) and custom.hotSpot() == (3, 4)
    assert NSCursor.crosshairCursor().qcursor() is not None and made[-1] == (2,)


def test_retina_variant_when_at2x_sibling_then_found_for_raster_only(tmp_path):
    from fontlab_glyport.ui.images import retina_variant

    (tmp_path / "ExportIcon.tiff").write_bytes(b"x")
    (tmp_path / "ExportIcon@2x.tif").write_bytes(b"x")
    (tmp_path / "plain.png").write_bytes(b"x")
    (tmp_path / "toolbar.pdf").write_bytes(b"x")
    (tmp_path / "toolbar@2x.pdf").write_bytes(b"x")
    assert (
        retina_variant(tmp_path / "ExportIcon.tiff") == tmp_path / "ExportIcon@2x.tif"
    )
    assert retina_variant(tmp_path / "plain.png") is None
    assert retina_variant(tmp_path / "toolbar.pdf") is None, (
        "vector sources scale themselves"
    )
