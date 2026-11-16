# this_file: tests/test_issue106_round34.py
"""Unicode no-ops and the restored metadata-only fontgate write protocol."""

from weakref import WeakSet

import pytest
from test_issue106_round9 import native as native_fixture


@pytest.fixture
def native(monkeypatch):
    n = native_fixture.__wrapped__(monkeypatch)
    isolate_unicode_backend(n, monkeypatch)
    return n


def isolate_unicode_backend(n, monkeypatch):
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._LIVE_BACKENDS", WeakSet([n.backend])
    )
    n.glyph.layers = [n.layer]

    def no_tools(*args, **kwargs):
        pytest.fail("Unicode metadata must not use MCP whole-glyph replacement")

    monkeypatch.setattr(n.backend, "_resolve_tool", no_tools)
    return n


def test_unchanged_unicode_is_noop_even_on_auto_layer(native):
    native.layer.autoLayer = True
    native.backend.set_glyph_unicodes(native.gid, ("0041",))
    assert native.calls == []


@pytest.mark.parametrize("codes", [(), ("0042",), ("0041", "1F600")])
def test_changed_unicode_uses_font_owned_record_and_glyph_only_undo(native, codes):
    class Record:
        codes = (65,)
        writes = 0

        @property
        def unicodes(self):
            return self.codes

        @unicodes.setter
        def unicodes(self, value):
            assert len(native.calls) == 1, "Baseline must precede mutation"
            self.codes = value
            self.writes += 1

    record = Record()
    native.package.fgPackage["A"] = record
    original_shapes = tuple(native.layer.shapes)
    with native.font.undo_group("Encoding"):
        native.backend.set_glyph_unicodes(native.gid, codes)
        assert native.backend._undo_name == "Encoding"
        assert len(native.calls) == 1
    assert record.codes == [int(code, 16) for code in codes]
    assert record.writes == 1
    assert tuple(native.layer.shapes) == original_shapes
    assert [call[0] for call in native.calls] == ["Encoding", "Encoding"]
    assert all(call[1] == [native.glyph] for call in native.calls)


@pytest.mark.parametrize("reason", ["auto", "pending"])
def test_unsafe_or_unavailable_unicode_route_refuses_before_mutation(
    native, monkeypatch, reason
):
    from fontlab_glyport.errors import UnsupportedCapability

    if reason == "auto":
        native.layer.autoLayer = True
    elif reason == "pending":
        native.backend._changed["layer", native.layer.id] = native.layer
    with pytest.raises(UnsupportedCapability):
        native.backend.set_glyph_unicodes(native.gid, ("0042",))
    assert native.glyph.fgGlyph.unicodes == [65]
    assert native.calls == []


def test_update_glyph_info_already_correct_is_noop(native, owned_edit_info):
    native.font.parent._local_glyph_info = owned_edit_info
    pytest.importorskip("fontTools")
    # Metadata reads font-level parameters even for non-Arabic glyphs (ROS).
    native.package.packageLib = {}
    native.glyph.fgGlyph.unicodes = [0x0041, 0x0061]
    native.font.glyphs[0].updateGlyphInfo()
    assert native.calls == []
    assert native.package.packageLib == {}, "Parameter lookup must remain read-only"
