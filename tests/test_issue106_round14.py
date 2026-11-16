# this_file: tests/test_issue106_round14.py
"""Host-free reproductions of round-four oracle blockers (issue 106)."""

import pytest

from fontlab_glyport.drawing.cocoa_drawing import NSBezierPath, NSColor, NSFont
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize("attached", [False, True])
def test_node_neighbors_wrap_even_on_open_paths(attached):
    path = GSPath([GSNode((1, 2)), GSNode((3, 4))], closed=False)
    if attached:
        layer = Model(FakeBackend()).font.glyphs[0].layers[0]
        layer.paths = [path]
        path = layer.paths[0]
    first, second = path.nodes
    assert first.parent is path and first.index == 0
    assert first.prevNode is second and first.nextNode is second
    assert second.nextNode is first and second.prevNode is first


def test_selection_bounds_excludes_unselected_nodes():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.paths = [GSPath([GSNode((1, 2)), GSNode((11, 22)), GSNode((999, 999))])]
    layer.paths[0].nodes[0].selected = True
    layer.paths[0].nodes[1].selected = True
    assert layer.selectionBounds == ((1, 2), (10, 20))
    layer.paths[0].selected = False
    assert layer.selectionBounds == ((0, 0), (0, 0))


def test_italic_angle_is_writable():
    backend = FakeBackend()
    master = Model(backend).font.masters[0]
    master.italicAngle = -12.5
    assert master.italicAngle == -12.5


def test_appended_copy_is_attached_and_preserves_outline_and_metadata(owned_edit_info):
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = owned_edit_info
    original = font.glyphs[0]
    original.userData["test"] = "value"
    variant = original.copy()
    with owned_edit_info._scope():
        variant.name = "A.ss01"
    variant.unicode = None
    expected = [n.position for n in original.layers[0].paths[0].nodes]
    font.glyphs.append(variant)
    assert variant is font.glyphs["A.ss01"] and variant.parent is font
    assert variant.id and variant.unicodes == []
    assert variant.userData["test"] == "value"
    assert [n.position for n in variant.layers[0].paths[0].nodes] == expected
    font.selection = [original, variant]
    assert font.selection == [original, variant]
    variant.layers[0].paths[0].nodes[0].position = (77, 88)
    assert original.layers[0].paths[0].nodes[0].position == expected[0]


def test_path_transform_and_collection_deletion():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.paths = [GSPath([GSNode((1, 2)), GSNode((3, 4))])]
    layer.paths[0].applyTransform((2, 0, 0, 3, 5, 6))
    assert [n.position for n in layer.paths[0].nodes] == [(7, 12), (11, 18)]
    del layer.paths[0]
    assert not layer.paths


def test_cocoa_drawing_without_context_is_harmless_and_geometry_survives():
    path = NSBezierPath.bezierPath()
    path.moveToPoint_((1, 2))
    path.lineToPoint_((11, 22))
    assert path.bounds() == ((1, 2), (10, 20))
    path.fill()
    path.stroke()
    assert path.bounds() == ((1, 2), (10, 20))


def test_cocoa_fonts_and_color_blending():
    font = NSFont.fontWithName_size_("Example", 12)
    resized = font.fontWithSize_(24)
    assert resized.fontName() == "Example" and resized.pointSize() == 24
    assert font.pointSize() == 12
    assert NSFont.menuFontOfSize_(0).pointSize() > 0
    mixed = NSColor.redColor().blendedColorWithFraction_ofColor_(
        0.25, NSColor.blueColor()
    )
    assert mixed.rgba == (0.75, 0, 0.25, 1)


def test_segments_expose_cocoa_points_type_length_and_interpolation():
    segment = GSPath([GSNode((0, 0)), GSNode((30, 40))], closed=False).segments[0]
    assert segment.type == "line"
    assert segment.countOfPoints == 2
    assert segment.pointAtIndex_(1) == (30, 40)
    assert segment.length() == 50
    assert segment.pointAtTime_(0.5) == (15, 20)


def test_component_resolves_its_glyph():
    from fontlab_glyport.model import GSComponent

    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    layer.components.append(GSComponent("A"))
    assert layer.components[0].component is font.glyphs["A"]


def test_guide_position_and_angle_are_writable():
    from fontlab_glyport.model import GSGuide

    guide = GSGuide((1, 2), 45)
    guide.position = (3, 4)
    guide.angle = 90
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.guides.append(guide)
    guide = layer.guides[0]
    guide.position = (5, 6)
    guide.angle = 30
    assert guide.position == (5, 6) and guide.angle == 30


def test_current_tab_accepts_its_active_tab_without_losing_text():
    font = Model(FakeBackend()).font
    tab = font.newTab("A")
    before = tab.text
    font.currentTab = tab
    assert font.currentTab._tab_id == tab._tab_id and font.currentTab.text == before


def test_draft_node_parent_is_set_on_insert_and_cleared_on_remove():
    node = GSNode((4, 5))
    path = GSPath([node])
    assert node.parent is path
    assert node.nextNode is node and node.prevNode is node
    path.nodes.remove(node)
    assert node.parent is None and node.nextNode is None
    path.nodes.append(node)
    assert node.parent is path


def test_kerning_keys_use_the_opposite_side_group_prefix_or_glyph_name():
    from fontlab_glyport.model.backend import KerningClassInfo

    backend = FakeBackend()
    glyph = Model(backend).font.glyphs[0]
    assert (glyph.leftKerningKey, glyph.rightKerningKey) == ("A", "A")
    backend.kerning_class_data["font"] = (
        KerningClassInfo("first", ("A",), left=True, right=False),
        KerningClassInfo("second", ("A",), left=False, right=True),
    )
    assert glyph.leftKerningKey == "@MMK_R_second"
    assert glyph.rightKerningKey == "@MMK_L_first"
