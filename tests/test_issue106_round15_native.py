# this_file: tests/test_issue106_round15_native.py
"""Metadata index invalidation and Undo through native-shaped doubles."""

import pytest
from test_issue106_round9 import native as native_fixture
from test_issue106_round10 import peer_font

from fontlab_glyport.model.backend import GlyphInfo


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_unicode_changes_invalidate_peer_indexes_inside_an_open_group(
    native, monkeypatch
):
    from test_issue106_round34 import isolate_unicode_backend

    isolate_unicode_backend(native, monkeypatch)
    peer = peer_font(native, monkeypatch)
    native.glyph.fgGlyph.unicodes = [0x42]
    for font in (native.font, peer):
        backend = font._model._backend
        monkeypatch.setattr(
            backend,
            "glyphs",
            lambda fid, font=font: (
                GlyphInfo(
                    font._model._backend._keys[(font._id, "glyph", 200)],
                    "A",
                    tuple(f"{u:04X}" for u in native.glyph.fgGlyph.unicodes),
                ),
            ),
        )
    assert peer.glyphs[0].unicode == "0042"
    assert peer.glyphForUnicode_("0042") is peer.glyphs[0]
    with native.font.undo_group("Change encoding"):
        native.font.glyphs[0].unicode = "0043"
        assert peer.glyphs[0].unicode == "0043"
        assert peer.glyphForUnicode_("0043") is peer.glyphs[0]
        assert peer.glyphForUnicode_("0042") is None


def test_deleted_glyph_drops_its_pending_native_children_before_group_publish(native):
    backend = native.backend
    native.package.deleteGlyph = lambda glyph: True
    with native.font.undo_group("Failed attachment"):
        layer = native.font.glyphs[0].layers[0]
        layer.paths[0].nodes[0].position = (7, 8)
        backend.remove_glyph(native.fid, native.gid)
    assert native.calls[-1][1] == [native.package], (
        "do not publish deleted glyph/layer wrappers"
    )


def test_native_node_name_writes_clone_and_copy_preserves_the_name(native):
    layer = native.font.glyphs[0].layers[0]
    original_shape = native.layer.shapes[0]
    original_shape.contours[0].nodes()[0].name = "original"
    node = layer.paths[0].nodes[0]
    assert node.name == "original"
    node.name = "renamed"
    assert node.name == "renamed" and node.copy().name == "renamed"
    assert original_shape.contours[0].nodes()[0].name == "original"


def test_graphic_view_dark_flag_uses_current_native_preferences(native):
    from test_drawing import _scope

    from fontlab_glyport.model.proxies import _GraphicView

    preferences = type("Preferences", (), {"isDark": False})()
    native.module.flPreferences = lambda: preferences
    painter, scope = _scope()
    from types import SimpleNamespace as NS

    painter.device = lambda: NS(width=lambda: 200, height=lambda: 100)
    with scope as context:
        view = _GraphicView(context, native.backend.dark_mode)
        assert view.drawDark() is False
        preferences.isDark = True
        assert view.drawDark() is True


@pytest.mark.parametrize("earlier_node_edit", [False, True])
def test_f55_bulk_remove_append_keeps_real_outer_batch_and_original_history(
    native, monkeypatch, earlier_node_edit
):
    from copy import deepcopy
    from types import SimpleNamespace as NS

    from fontlab_glyport.model import GSNode, GSPath

    shape_type = type(native.layer.shapes[0])
    contour_type = type(native.layer.shapes[0].contours[0])
    node_type = type(native.layer.shapes[0].contours[0].nodes()[0])

    def make_node(point, *, nodeType):
        node = node_type(point.x())
        node.y = point.y()
        node.nodeState = (node.nodeState & ~7) | {"on": 1, "off": 2, "curve": 4}[
            nodeType
        ]
        return node

    def make_contour(nodes, *, closed):
        contour = contour_type(0)
        contour._nodes, contour.closed = list(nodes), closed
        return contour

    def make_shape():
        shape = shape_type()
        shape.contours = []
        shape.addContour = lambda contour, clone: shape.contours.append(contour)
        return shape

    def add_shape(shape):
        native.layer.shapes.append(shape)
        return shape

    make_node.NodeKind = node_type.NodeKind
    native.module.flNode, native.module.flContour, native.module.flShape = (
        make_node,
        make_contour,
        make_shape,
    )
    native.layer.addShape = add_shape
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._qpoint",
        lambda x, y: NS(x=lambda: x, y=lambda: y),
    )
    batches = []

    def notify(name, objects, recursive=False):
        assert objects == [native.layer, native.glyph]
        assert objects[0] is native.layer and objects[1] is native.glyph
        assert recursive is True
        batches.append(
            (name, tuple(native.layer.shapes), deepcopy(native.layer.shapes))
        )

    native.module.flItems = lambda: NS(notifyChangesApplied=notify)
    layer = native.font.glyphs[0].layers[0]
    original = native.layer.shapes[0]
    with native.font.undo_group("Filter Apply"):
        if earlier_node_edit:
            layer.paths[0].nodes[0].position = (33, 44)
        for x in (100, 200):
            layer.paths = [GSPath([GSNode((x, 9)), GSNode((x + 10, 19))], closed=False)]
    assert [batch[0] for batch in batches] == ["Filter Apply", "Filter Apply"]
    assert [(c.nodes()[0].x, c.nodes()[0].y) for c in original.contours] == [
        (10, 2),
        (20, 2),
    ]
    assert all(shape is not original for shape in native.layer.shapes)
    assert batches[0][1] == (original,), (
        "history records the original geometry, before any working clone"
    )
    native.layer.shapes[:] = batches[0][2]
    native.backend._revision += 1
    assert [path.nodes[0].position for path in layer.paths] == [(10, 2), (20, 2)]
