# this_file: tests/test_issue106_round14_native.py
"""Declared FontLab API behavior through native-shaped doubles only."""

from types import SimpleNamespace as NS

import pytest
from history_scene import install_font_window
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_italic_angle_restores_active_master_and_notifies(monkeypatch):
    package = NS(
        id=10,
        isValid=True,
        master="Regular",
        masters=["Regular", "Italic"],
        italicAngle_value=0,
    )
    backend = FontLabBackend(packages=[package])
    module = NS(flWorkspace=None)
    install_font_window(monkeypatch, module, package)
    monkeypatch.setattr(backend, '_native', lambda: module)
    fid = backend._font_id(package)
    mid = backend._register((fid, "master", "Italic"), package, fid)
    backend._master_names[mid] = "Italic"
    calls = []
    package.setMaster = lambda name: (
        calls.append(name),
        setattr(package, "master", name),
    )
    monkeypatch.setattr(
        backend, "_notify", lambda name, changes, **kwargs: calls.append(list(changes))
    )
    backend.set_master_italic_angle(mid, -12)
    assert package.italicAngle_value == -12 and package.master == "Regular"
    assert calls == [[("font", 10)], "Italic", [("font", 10)], "Regular"]


def test_guide_flobject_cast_and_position_write(native, monkeypatch):
    class flObject:
        id = 600

    guide = NS(
        id=600,
        isValid=True,
        isHint=False,
        name="test",
        angle=45,
        centerPoint=NS(x=lambda: 1, y=lambda: 2),
    )
    native.module.flGuideLine = lambda raw: guide
    native.layer.guidelines = [flObject()]
    layer = native.font.glyphs[0].layers[0]
    assert layer.guides[0].position == (1, 2)
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=lambda *values: values),
    )
    guide.applyTransform = lambda values: setattr(
        guide, "centerPoint", NS(x=lambda: 1 + values[4], y=lambda: 2 + values[5])
    )
    layer.guides[0].position = (3, 4)
    layer.guides[0].angle = 90
    assert layer.guides[0].position == (3, 4) and guide.angle == 90


def test_unicode_write_updates_live_fontgate_glyph_and_notifies(native, monkeypatch):
    from test_issue106_round34 import isolate_unicode_backend

    isolate_unicode_backend(native, monkeypatch)
    glyph = native.font.glyphs[0]
    glyph.unicodes = ["0041", "1F600"]
    assert native.glyph.fgGlyph.unicodes == [65, 0x1F600]
    assert native.calls, "metadata mutations must notify the native document"


def test_f55_undo_notifications_keep_original_outline_unmodified(native):
    # FontLab history retains shape references; no deep snapshot is supplied by
    # this double. Both preview edits must leave that original state untouched.
    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]
    before = tuple(native.layer.shapes)
    with font.undo_group("Filter Apply"):
        layer.paths[0].nodes[0].position = (100, 110)
        layer.paths[1].nodes[0].position = (200, 210)
    assert [(c.nodes()[0].x, c.nodes()[0].y) for c in before[0].contours] == [
        (10, 2),
        (20, 2),
    ]
    assert [p.nodes[0].position for p in layer.paths] == [(100, 110), (200, 210)]
    assert backend._undo_name is None and backend._owned_shapes == set()
    native.layer.shapes[:] = before  # native Undo restores the stored references
    backend._revision += 1
    assert [p.nodes[0].position for p in layer.paths] == [(10, 2), (20, 2)]


def test_f55_filter_apply_requests_recursive_history_on_older_hosts(native):
    from copy import deepcopy

    snapshots = []

    def notify(name, items, recursive=False):
        # The older API's shallow default retains nested layer data. Recursive
        # publication saves it independently, as required for outline Undo.
        snapshots.append(
            (name, deepcopy(native.layer.shapes) if recursive else native.layer)
        )

    native.module.flItems = lambda: NS(notifyChangesApplied=notify)
    layer = native.font.glyphs[0].layers[0]
    with native.font.undo_group("Filter Apply"):
        layer.paths[0].nodes[0].position = (100, 110)
        layer.paths[1].nodes[0].position = (200, 210)
    saved = snapshots[-2][1]
    native.layer.shapes[:] = saved if isinstance(saved, list) else saved.shapes
    native.backend._revision += 1
    assert [p.nodes[0].position for p in layer.paths] == [(10, 2), (20, 2)]
    assert snapshots[-1][0] == "Filter Apply"
