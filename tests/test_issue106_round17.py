# this_file: tests/test_issue106_round17.py
"""Round-five corpus failures expressed as small, host-free API calls."""

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSGuide, GSHint, GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


def test_master_guides_append_and_detach():
    font = Model(FakeBackend()).font
    guide = GSGuide()
    guide.position, guide.angle, guide.name = (30, 40), 25, "diagonal"
    font.selectedFontMaster.guides.append(guide)
    saved = font.selectedFontMaster.guides[0]
    assert (saved.position, saved.angle, saved.name) == ((30, 40), 25, "diagonal")


def test_reporter_layer_indexes_and_bracket_queries():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    path = layer.paths[0]
    assert layer.indexOfObjectInShapes_(path) == 0
    assert layer.indexOfPath_(path) == 0
    assert layer.isBracketLayer is False
    assert layer.isBraceLayer is False
    assert layer.italicAngle == layer.master.italicAngle


def test_layer_selector_transform_slants_nodes_and_anchors():
    from fontlab_glyport.model import GSAnchor

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.components = []
    layer.paths = [GSPath([GSNode((10, 20))], closed=False)]
    layer.anchors = [GSAnchor("top", (30, 40))]
    layer.transform_checkForSelection_doComponents_((1, 0, 0.5, 1, -5, 0), False, True)
    assert layer.paths[0].nodes[0].position == (15, 20)
    assert layer.anchors[0].position == (45, 40)


def test_detached_associated_master_is_editable_independently():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    copied = layer.copy()
    copied.associatedMasterId = "other-master"
    assert copied.associatedMasterId == "other-master"
    assert layer.associatedMasterId != "other-master"


def test_hints_copy_can_be_added_to_another_layer():
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    hint = GSHint()
    hint.horizontal, hint.position, hint.width = False, 17, 23
    layer.hints.append(hint)
    copied = layer.hints[0].copy()
    assert (copied.horizontal, copied.position, copied.width) == (False, 17, 23)
    layer.hints.append(copied)
    assert len(layer.hints) == 2


def test_font_filepath_has_nsstring_path_methods(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(backend, "font_path", lambda fid: "/tmp/Sample Font.vfj")
    path = Model(backend).font.filepath
    assert path.lastPathComponent() == "Sample Font.vfj"
    assert path.stringByDeletingLastPathComponent() == "/tmp"


def test_unicode_script_for_rekha_gurmukhi(owned_edit_info):
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = owned_edit_info
    glyph = font.glyphs[0]
    glyph.unicode = "0A15"
    assert glyph.script == "latin", (
        "Unicode changes must not replace named script metadata"
    )
    glyph.name = "ka-gurmukhi"
    assert glyph.script == "gurmukhi", "Rekha filters the named glyph script"


def test_update_metrics_uses_backend_without_changing_other_layers(monkeypatch):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    calls = []
    monkeypatch.setattr(backend, "update_layer_metrics", calls.append, raising=False)
    layer.updateMetrics()
    assert calls == [layer.id]


def test_copy_loaded_hint_uses_native_record_not_empty_constructor_defaults():
    from fontlab_glyport.model.backend import HintInfo

    backend = FakeBackend()
    backend.hint_data["layer"] = (HintInfo(False, 13, 27, "stem"),)
    hint = Model(backend).font.glyphs[0].layers[0].hints[0].copy()
    assert (hint.position, hint.width, hint.horizontal, hint.name) == (
        13,
        27,
        False,
        "stem",
    )


def test_image_interpolation_none_is_exported(tmp_path):
    from ui_doubles_session import make_session

    ctx, _ = make_session(tmp_path)
    with ctx:
        assert ctx.import_module("AppKit").NSImageInterpolationNone == 1
    ctx.close()


def test_callback_handler_exports_forward_and_remove_callable_callbacks():
    from test_glyphsapp import _make

    module, _bridge, _ = _make()
    calls = []
    callback = calls.append
    handler = module.GSCallbackHandler
    handler.addCallback_forOperation_(callback, module.UPDATEINTERFACE)
    assert len(module.Glyphs._tokens) == 1
    handler.removeCallback_forOperation_(callback, module.UPDATEINTERFACE)
    assert module.Glyphs._tokens == {}


def test_graphic_view_redraw_is_available_outside_paint(monkeypatch):
    from fontlab_glyport.model.backend import EditViewInfo

    backend = FakeBackend()
    backend.edit_views["font"] = EditViewInfo((("A",),), "A", "Regular", "tab")
    calls = []
    monkeypatch.setattr(backend, "redraw_edit_view", calls.append, raising=False)
    Model(backend).font.currentTab.graphicView().setNeedsDisplay_(True)
    assert calls == ["font"]


def test_update_glyph_info_assigns_unicode_for_known_agl_combining_mark(
    owned_edit_info,
):
    from fontlab_glyport.model import GSGlyph

    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = owned_edit_info
    mark = font.glyphs.append(GSGlyph("gravecomb"))
    mark.updateGlyphInfo()
    assert mark.unicode == "0300"


def test_layer_transform_selector_accepts_cocoa_affine_object():
    from fontlab_glyport.drawing.cocoa_drawing import NSAffineTransform

    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    transform = NSAffineTransform.transform()
    transform.translateXBy_yBy_(12, 13)
    layer.transform_checkForSelection_doComponents_(transform, False, True)
    assert backend.transforms[-1][1] == (1, 0, 0, 1, 12, 13)


def test_update_glyph_info_when_database_missing_then_refuses_full_refresh(
    monkeypatch,
):
    import sys

    from fontlab_glyport.model import GSGlyph

    monkeypatch.setitem(sys.modules, "glyphsLib", None)
    font = Model(FakeBackend()).font
    for base, code in (
        ("acutecomb", "0301"),
        ("gravecomb", "0300"),
        ("circumflexcomb", "0302"),
        ("tildecomb", "0303"),
        ("cedillacomb", "0327"),
    ):
        for suffix in ("", ".case"):
            mark = font.glyphs.append(GSGlyph(base + suffix))
            before = (mark.name, mark.unicodes, mark._case_state())
            with pytest.raises(UnsupportedCapability, match="glyphsLib"):
                mark.updateGlyphInfo()
            assert (mark.name, mark.unicodes, mark._case_state()) == before, (
                "Full metadata refresh must fail before partial Unicode-only mutation"
            )
            assert mark.unicode == (None if suffix else code), (
                "Creation keeps its documented optional AGL fallback"
            )
