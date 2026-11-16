# this_file: tests/test_issue106_round34c.py
"""New glyphs carry their default or explicit encoding into creation itself."""

import pytest

from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize(
    "name, code",
    [
        ("acutecomb", "0301"),
        ("gravecomb", "0300"),
        ("circumflexcomb", "0302"),
        ("tildecomb", "0303"),
        ("cedillacomb", "0327"),
    ],
)
def test_creation_includes_default_unicode_without_post_creation_write(
    monkeypatch, name, code
):
    pytest.importorskip("fontTools")
    backend = FakeBackend()
    font = Model(backend).font
    original = backend.append_glyph
    calls = []

    def create(fid, glyph_name, *, unicodes=()):
        calls.append((glyph_name, unicodes))
        return original(fid, glyph_name, unicodes=unicodes)

    monkeypatch.setattr(backend, "append_glyph", create)
    glyph = GSGlyph(name)
    assert glyph.unicodes == [code]
    font.glyphs.append(glyph)
    assert calls == [(name, (code,))]
    assert glyph.unicode == code
    assert glyph.category == "Mark"


@pytest.mark.parametrize("codes", [[], ["E000"], ["E001", "E002"]])
def test_explicit_encoding_wins_at_creation(monkeypatch, codes):
    backend = FakeBackend()
    font = Model(backend).font
    glyph = GSGlyph("acutecomb")
    glyph.unicodes = codes
    original = backend.append_glyph
    calls = []

    def create(fid, name, *, unicodes=()):
        calls.append(unicodes)
        return original(fid, name, unicodes=unicodes)

    monkeypatch.setattr(backend, "append_glyph", create)
    font.glyphs.append(glyph)
    assert calls == [tuple(codes)]
    assert glyph.unicodes == codes


def test_native_creation_payload_has_encoding_and_update_info_is_noop(monkeypatch):
    from types import SimpleNamespace as NS

    from test_issue106_round9 import native as native_fixture

    pytest.importorskip("fontTools")
    n = native_fixture.__wrapped__(monkeypatch)
    payloads = []
    names = {"A": n.glyph}
    n.package.findName = names.get

    def create(**kw):
        assert kw["create"] is True
        data = kw["glyph_data"]
        assert kw["glyph_name"] not in names
        payloads.append(data)
        record = NS(id=999, name=data["name"], unicodes=data.get("unicodes", []))
        n.package.fgPackage[data["name"]] = record
        names[data["name"]] = NS(
            id=888, name=data["name"], isValid=True, fgGlyphId=999, layers=[]
        )

    monkeypatch.setattr(n.backend, "_resolve_tool", lambda *args: create)
    token = n.backend.append_glyph(n.fid, "acutecomb", unicodes=("0301",))
    assert payloads[0]["unicodes"] == [0x301]
    before = list(n.calls)
    n.backend.set_glyph_unicodes(token, ("0301",))
    assert n.calls == before


@pytest.mark.parametrize("name", ["unknown.custom", "A.alt", ".notdef"])
def test_unknown_or_alternate_name_is_not_assigned_a_base_encoding(name):
    backend = FakeBackend()
    font = Model(backend).font
    glyph = GSGlyph(name)
    font.glyphs.append(glyph)
    assert glyph.unicodes == []


@pytest.mark.parametrize("mode", ["rename", "readback", "explicit_empty"])
def test_draft_encoding_is_current_before_append_and_preserved_in_payload(
    monkeypatch, mode, owned_edit_info
):
    with owned_edit_info._scope():
        pytest.importorskip("fontTools")
        backend = FakeBackend()
        font = Model(backend).font
        glyph = GSGlyph("acutecomb")
        assert glyph.unicodes == ["0301"]
        if mode == "rename":
            glyph.name = "gravecomb"
            expected = ["0300"]
        elif mode == "readback":
            glyph.unicodes = glyph.unicodes
            expected = ["0301"]
        else:
            glyph.unicodes = []
            expected = []
        assert glyph.unicodes == expected
        original = backend.append_glyph
        payloads = []

        def create(fid, name, *, unicodes=()):
            payloads.append(unicodes)
            return original(fid, name, unicodes=unicodes)

        monkeypatch.setattr(backend, "append_glyph", create)
        monkeypatch.setattr(
            "fontlab_glyport.glyphsapp.glyph_info.creation_unicodes",
            lambda name: pytest.fail("append must not infer encoding"),
        )
        font.glyphs.append(glyph)
        assert payloads == [tuple(expected)]
        assert glyph.unicodes == expected


def test_empty_draft_name_assignment_initializes_encoding_and_same_name_keeps_override(
    owned_edit_info,
):
    with owned_edit_info._scope():
        pytest.importorskip("fontTools")
        glyph = GSGlyph()
        assert glyph.unicodes == []
        glyph.name = "acutecomb"
        assert glyph.unicodes == ["0301"]
        glyph.unicodes = []
        glyph.name = "acutecomb"
        assert glyph.unicodes == []
        glyph.name = "A.sc"
        assert glyph.unicodes == []


def test_attached_rename_when_known_name_then_refreshes_encoding(owned_edit_info):
    backend = FakeBackend()
    glyph = Model(backend).font.glyphs["A"]
    glyph.parent.parent._local_glyph_info = owned_edit_info
    glyph.name = "gravecomb"
    assert glyph.unicodes == ["0300"], (
        "Glyphs name assignment refreshes encoding after the backend rename primitive"
    )
