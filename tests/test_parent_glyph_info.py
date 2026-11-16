# this_file: tests/test_parent_glyph_info.py
"""Owned original-selector dispatch, ownership and model-resolver boundaries."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphsInfo
from fontlab_glyport.glyphsapp.glyph_info import GSGlyphInfo
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


class OwnedManager:
    def __init__(self, result):
        self.result, self.calls = result, []

    def __bool__(self):
        return False

    def glyphInfoForGlyph_(self, glyph):
        self.calls.append(glyph)
        return self.result


class OwnedDocument:
    def __init__(self, value):
        self.value, self.keys = value, []

    def valueForKey_(self, key):
        self.keys.append(key)
        assert key == "glyphsInfo", "Use the retained document manager key"
        return self.value


def owned_font():
    backend = FakeBackend()
    return Model(backend).font, backend


def test_font_manager_when_document_supplies_falsey_instance_then_keeps_identity():
    font, _ = owned_font()
    manager = OwnedManager(object())
    document = font._document = OwnedDocument(manager)
    assert font.glyphsInfo() is manager, "Only nil selects the shared manager"
    assert document.keys == ["glyphsInfo"]


def test_font_manager_when_document_value_nil_then_selects_shared(monkeypatch):
    font, _ = owned_font()
    document = font._document = OwnedDocument(None)
    sentinel = object()
    monkeypatch.setattr(
        GSGlyphsInfo, "sharedManager", classmethod(lambda cls: sentinel), raising=False
    )
    assert font.glyphsInfo() is sentinel
    assert document.keys == ["glyphsInfo"]


def test_manager_when_shared_requested_twice_then_same_actual_instance():
    first = GSGlyphsInfo.sharedManager()
    assert isinstance(first, GSGlyphsInfo) and first is GSGlyphsInfo.sharedManager()


@pytest.mark.parametrize(
    "result", [None, "owned-result", SimpleNamespace(name="Owned")]
)
def test_glyph_info_when_document_manager_supplied_then_delegates_exact_glyph(result):
    font, _ = owned_font()
    glyph = font.glyphs["A"]
    manager = OwnedManager(result)
    font._document = OwnedDocument(manager)
    assert glyph.glyphInfo is result, "Do not substitute a raw model snapshot"
    assert manager.calls == [glyph], "Dispatch the actual owned glyph once"


def test_font_manager_when_provider_raises_then_error_is_not_a_global_miss():
    font, _ = owned_font()
    failure = RuntimeError("owned document failure")

    class BrokenDocument:
        def valueForKey_(self, key):
            raise failure

    font._document = BrokenDocument()
    with pytest.raises(RuntimeError) as caught:
        font.glyphsInfo()
    assert caught.value is failure, "Do not hide document-manager errors"


def test_font_manager_when_font_stale_then_refuses_before_document_access():
    font, backend = owned_font()
    document = font._document = OwnedDocument(OwnedManager(None))
    backend.fonts.clear()
    with pytest.raises(StaleNativeObject):
        font.glyphsInfo()
    assert document.keys == [], "A stale owner must not consume cached manager data"


def test_glyph_info_when_glyph_stale_then_refuses_before_custom_manager_call():
    font, backend = owned_font()
    glyph = font.glyphs["A"]
    manager = OwnedManager(object())
    font._document = OwnedDocument(manager)
    backend.remove_glyph(font._id, glyph._id)
    with pytest.raises(StaleNativeObject):
        _ = glyph.glyphInfo
    assert manager.calls == [], "Do not give a custom manager a stale glyph"


@pytest.mark.parametrize("stored,expected", [(False, 1), (True, 5)])
def test_glyph_info_when_case_storage_differs_then_preserves_resolved_vs_raw(
    stored, expected
):
    font, _ = owned_font()
    glyph = font.glyphs["A"]
    glyph.storeCase = stored
    glyph.case = 5
    raw = GSGlyphInfo(glyph)
    assert raw.case == 5, "The existing raw constructor remains independent"
    assert glyph.glyphInfo.case == expected, "Use the actual resolved manager record"
    assert glyph.case == 5, "A metadata read must not refresh the model"


def test_glyph_info_when_draft_has_no_parent_then_refuses_without_creating_owner():
    glyph = GSGlyph("A")
    assert glyph.parent is None
    with pytest.raises(UnsupportedCapability):
        _ = glyph.glyphInfo
    assert glyph.parent is None, "Do not create a synthetic font for a detached draft"
