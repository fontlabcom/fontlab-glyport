# this_file: tests/test_issue106_round8_indexes.py
"""Lookup work is independent of font size after a revision's single listing."""

from dataclasses import replace

import pytest

from fontlab_glyport.model import GSGlyph, GSNode, GSPath, Model
from fontlab_glyport.model.backend import GlyphInfo
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize("size", [100, 2000])
def test_glyph_indexes_list_once_then_resolve_names_unicode_chars_ids_and_ordinals(
    size,
):
    class Backend(FakeBackend):
        listings = 0

        def glyphs(self, font_id):
            self.listings += 1
            return super().glyphs(font_id)

    backend = Backend()
    backend.glyph_lists["font"] = tuple(
        GlyphInfo(f"g{i}", f"item{i}", (f"{0x400 + i:04X}",)) for i in range(size)
    )
    font = Model(backend).font
    seq = font.glyphs
    last = seq[f"item{size - 1}"]
    for _ in range(20):
        assert seq[f"item{size - 1}"] is seq[size - 1] is last
        assert seq[last.unicode] is seq[chr(int(last.unicode, 16))] is last
        assert seq[last.id] is last and last in seq and last.glyphId() == size - 1
        assert font.glyphForUnicode_(last.unicode) is last
        assert seq["absent"] is None
    assert backend.listings == 1


def test_glyph_index_invalidates_on_script_and_host_add_rename_remove():
    backend = FakeBackend()
    backend.glyph_lists["font"] = (
        replace(backend.glyph_lists["font"][0], name="Before"),
    )
    font = Model(backend).font
    old = font.glyphs["Before"]
    old.name = "Renamed"
    assert font.glyphs["Before"] is None and font.glyphs["Renamed"] is old
    new = font.glyphs.append(GSGlyph("Added"))
    assert new in font.glyphs and font.glyphs["Added"] is new
    font.glyphs.remove(new)
    assert new not in font.glyphs and font.glyphs["Added"] is None
    backend.glyph_lists["font"] = (
        replace(backend.glyph_lists["font"][0], name="Host"),
    )
    assert font.glyphs["Host"] is old and font.glyphs["Renamed"] is None


def test_layer_child_id_indexes_avoid_native_listing_per_node_read():
    class Backend(FakeBackend):
        reads = 0

        def layer(self, glyph, master):
            self.reads += 1
            return super().layer(glyph, master)

    backend = Backend()
    font = Model(backend).font
    layer = font.glyphs[0].layers[0]
    layer.paths = [GSPath([GSNode((i, i)) for i in range(200)])]
    backend.reads = 0
    path = layer.paths[0]
    for node in path.nodes:
        assert node.x == node.y
    assert backend.reads <= 1
    path.nodes[0].x = 40
    assert path.nodes[0].x == 40


def test_unicode_lookup_uses_unicode_index_even_when_name_collides():
    backend = FakeBackend()
    backend.glyph_lists["font"] = (
        GlyphInfo("name", "0041", ()),
        GlyphInfo("encoded", "EncodedA", ("0041",)),
    )
    font = Model(backend).font
    assert font.glyphs["0041"].id == "name"
    assert font.glyphForUnicode_("0041").id == "encoded"


@pytest.mark.parametrize("size", [100, 2000])
def test_append_paths_and_child_lookup_do_not_rescan_layer(size):
    class Backend(FakeBackend):
        reads = 0

        def layer(self, glyph, master):
            self.reads += 1
            return super().layer(glyph, master)

    backend = Backend()
    font = Model(backend).font
    layer = font.glyphs[0].layers[0]
    layer.paths = [GSPath([GSNode((i, i)) for i in range(size)])]
    backend.reads = 0
    last = layer.paths[0].nodes[-1]
    for _ in range(20):
        assert layer.paths[0].nodes[last.id] is last
        assert last.x == size - 1
    assert backend.reads <= 1
    backend.reads = 0
    for _ in range(5):
        layer.paths.append(GSPath([GSNode((1, 1))]))
    assert backend.reads == 0, "append returns its id-bound proxy directly"


def test_axis_lookup_reads_font_once_per_revision_for_repeated_access():
    from fontlab_glyport.model.backend import AxisInfo

    class Backend(FakeBackend):
        reads = 0

        def font_info(self, fid):
            self.reads += 1
            return super().font_info(fid)

    backend = Backend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        axes=tuple(AxisInfo(str(i), f"Axis {i}", f"{i:04}") for i in range(100)),
    )
    font = Model(backend).font
    last = font.axes["Axis 99"]
    backend.reads = 0
    for _ in range(30):
        assert font.axes[last.id] is last and last.name == "Axis 99"
    assert backend.reads <= 1


@pytest.mark.parametrize("size", [100, 2000])
def test_tab_text_uses_metadata_index_without_materializing_unrelated_glyphs(size):
    backend = FakeBackend()
    backend.glyph_lists["font"] = tuple(
        GlyphInfo(f"g{i}", f"item{i}", ()) for i in range(size)
    )
    font = Model(backend).font
    tab = font.newTab("/item0")
    assert not any(cls is GSGlyph for cls, token in font._cache), (
        "parsing text needs metadata only"
    )
    assert backend.edit_texts[-1] == ("font", (("item0",),))
    backend.edit_views["font"] = replace(backend.edit_views["font"], lines=(("item0",),))
    assert tab.text == "/item0"
    assert sum(cls is GSGlyph for cls, token in font._cache) == 1
