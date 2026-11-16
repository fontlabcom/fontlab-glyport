# this_file: tests/test_image_view_delegation.py
"""Cocoa/Vanilla policy remains local; every image presentation delegates to App."""

from types import SimpleNamespace as NS

import fontlabapp.qt.images.view as shared
import pytest
from test_ui_nib_image import FakeImage, _kit

from fontlab_glyport.ui.cocoa import NSMakeRect


@pytest.mark.parametrize(
    "scaling,mode", [(0, "down"), (1, "stretch"), (2, "none"), (3, "fit"), (99, "none")]
)
def test_cocoa_view_delegates_native_enums_frame_and_same_renderer(
    monkeypatch, scaling, mode
):
    kit = _kit()
    view = kit["NSImageView"].alloc().initWithFrame_(NSMakeRect(0, 0, 13, 7))
    image = FakeImage.alloc().initWithContentsOfFile_("owned.png")
    calls = []
    monkeypatch.setattr(shared, "present", lambda *args, **kw: calls.append((args, kw)))
    view.setImageScaling_(scaling)
    view.setImage_(image)
    args, kw = calls[-1]
    assert args[:2] == (view._env.qt, view._qt)
    assert args[2].__self__ is image and args[2].__func__ is image.pixmap.__func__
    assert kw == {
        "size": (13, 7),
        "natural": (0.0, 0.0) if mode == "stretch" else (16, 8),
        "mode": mode,
    }
    view.setImage_(None)
    assert calls[-1] == ((view._env.qt, view._qt), {})
    kit["close"]()


def test_stretch_does_not_require_natural_dimensions_beyond_original_size_call(
    monkeypatch,
):
    kit = _kit()
    view = kit["NSImageView"].alloc().initWithFrame_(NSMakeRect(0, 0, 13, 7))
    view.setImageScaling_(1)
    seen = []
    image = NS(size=lambda: seen.append("size") or object(), pixmap=lambda scale: None)
    monkeypatch.setattr(shared, "present", lambda *a, **kw: seen.append(kw["mode"]))
    view.setImage_(image)
    assert seen == ["size", "stretch"]
    kit["close"]()
