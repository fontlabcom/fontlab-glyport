# this_file: tests/test_issue106_api1.py
"""API-surface contracts on backend-neutral model objects."""

import pytest
from glyphsapp_doubles import FakeGlyphsBridge

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import GSComponent, GSNode, GSPath, Model
from fontlab_glyport.model.copies import DetachedLayer
from fontlab_glyport.model.fake_backend import FakeBackend


def test_add_node_selector_preserves_identity_and_parent():
    path, node = GSPath(), GSNode((12, 34))
    assert path.addNode_(node) is None, "Objective-C void selector"
    assert list(path.nodes) == [node] and node.parent is path
    with pytest.raises(TypeError):
        path.addNode_(object())


@pytest.mark.parametrize("reverse, expected", [(False, -1), (True, 1)])
def test_direction_uses_glyphs_clockwise_sign(reverse, expected):
    points = [(0, 0), (100, 0), (100, 100), (0, 100)]
    path = GSPath([GSNode(p) for p in (points[::-1] if reverse else points)])
    assert path.direction == expected, "Glyphs clockwise is +1"
    assert path.copy().direction == expected


def test_direction_integrates_beziers_instead_of_control_polygon():
    path = GSPath(
        [
            GSNode((0, 0)),
            GSNode((100, 0), "offcurve"),
            GSNode((100, 100), "offcurve"),
            GSNode((0, 100), "curve"),
        ]
    )
    assert path.direction == -1, "cubic encloses positive mathematical area"


def test_smooth_selector_preserves_handle_length_and_other_nodes():
    moving, center, opposite = GSNode((3, 4)), GSNode((0, 0)), GSNode((0, 7))
    path = GSPath([moving, center, opposite])
    path.setSmooth_withCenterNode_oppositeNode_(moving, center, opposite)
    assert moving.position == pytest.approx((0, -5))
    assert center.position == (0, 0) and opposite.position == (0, 7)


def test_change_groups_nest_and_reject_unbalanced_end():
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    layer.beginChanges()
    layer.beginChanges()
    layer.width = 123
    layer.endChanges()
    layer.endChanges()
    assert backend.undo_events == [("begin", "Change layer"), ("end", None)]
    assert layer.width == 123
    with pytest.raises(RuntimeError, match="beginChanges"):
        layer.endChanges()


def test_detached_layer_attributes_are_mutable_and_deep_copied():
    layer = DetachedLayer()
    assert layer.parent is None
    layer.attributes["coordinates"] = [12]
    copied = layer.copy()
    copied.attributes["coordinates"].append(34)
    assert layer.attributes == {"coordinates": [12]}
    layer.beginChanges()
    layer.endChanges()


def test_menu_and_export_constants():
    module = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    )
    assert (module.ONSTATE, module.OFFSTATE, module.MIXEDSTATE) == (1, 0, -1)
    assert (module.WOFF, module.WOFF2) == ("WOFF", "WOFF2")


@pytest.mark.parametrize("name", ["tool"])
def test_font_ui_refusal_names_host_boundary(name):
    with pytest.raises(UnsupportedCapability, match="FontLab.*tool"):
        getattr(Model(FakeBackend()).font, name)


def test_alignment_refuses_instead_of_faking_component_layout():
    component = GSComponent("A")
    with pytest.raises(UnsupportedCapability, match="automatic alignment"):
        component.alignment = -1


def test_detached_parent_assignment_preserves_glyph_reference():
    layer = DetachedLayer()
    glyph = Model(FakeBackend()).font.glyphs[0]
    layer.parent = glyph
    assert layer.parent is glyph
    layer.parent = None
    assert layer.parent is None
    with pytest.raises(TypeError):
        layer.parent = object()


def test_compare_string_uses_node_types_and_closed_state():
    layer = DetachedLayer()
    layer.shapes = [GSPath([GSNode((0, 0)), GSNode((1, 2))], closed=False)]
    assert layer.compareString() == "ll|_"
    copy = layer.copy()
    copy.paths[0].nodes[0].position = (99, 99)
    assert copy.compareString() == layer.compareString()
    copy.paths[0].closed = True
    assert copy.compareString() != layer.compareString()


def test_popup_set_item_selects_title_without_callback():
    from ui_doubles import make_qt

    from fontlab_glyport.ui.vanilla import make_vanilla_module

    called = []
    module = make_vanilla_module(make_qt(), error_sink=lambda *args: None)
    popup = module.PopUpButton((0, 0, 100, 20), ["A", "B"], callback=called.append)
    popup.setItem("B")
    assert popup.get() == 1 and popup.getItem() == "B"
    popup.setItem("unknown")
    assert popup.getItem() == "B", "AppKit leaves selection on an unknown title"
    assert not called


def test_attributed_string_size_has_named_dimensions_and_tuple_access():
    from fontlab_glyport.drawing.cocoa_drawing import NSAttributedString

    size = NSAttributedString.alloc().initWithString_("abc").size()
    assert size.width == size[0] and size.height == size[1]


def test_objc_signature_is_a_bound_selector_with_signature_metadata():
    from fontlab_glyport.ui.objc_bridge import make_objc_module

    objc = make_objc_module({})

    class Receiver:
        @objc.signature(b"v@:@")
        def receive_(self, value):
            return value

    assert Receiver.receive_.signature == b"v@:@"
    assert Receiver().receive_(12) == 12


def test_format_version_refuses_foreign_serialization_mode():
    font = Model(FakeBackend()).font
    for operation in (
        lambda: font.formatVersion,
        lambda: setattr(font, "formatVersion", 3),
    ):
        with pytest.raises(UnsupportedCapability, match="Glyphs file format"):
            operation()


def test_background_image_refuses_raster_attachment_with_reason():
    from fontlab_glyport.model.background import GSBackgroundImage

    with pytest.raises(UnsupportedCapability, match="raster.*attachment"):
        GSBackgroundImage("/not-read.png")


def test_delegate_refuses_private_cocoa_controller_access():
    module = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    )
    with pytest.raises(UnsupportedCapability, match="Cocoa.*controller"):
        module.Glyphs.delegate()


def test_attributed_menu_title_refuses_losing_text_styles():
    from fontlab_glyport.ui.cocoa_menu import NSMenuItem

    item = NSMenuItem()
    with pytest.raises(UnsupportedCapability, match="QAction.*attributed"):
        item.setAttributedTitle_(object())
    assert item.title() == "", "refusal must leave the item unchanged"


def test_edit_view_layers_assignment_stages_names_before_publication():
    backend = FakeBackend()
    font = Model(backend).font
    tab = font.newTab()
    layer = font.glyphs[0].layers[0]
    tab.layers = [layer, layer]
    assert backend.edit_texts[-1] == (font.id, (("A", "A"),))
    before = list(backend.edit_texts)
    with pytest.raises(TypeError):
        tab.layers = [layer, object()]
    assert backend.edit_texts == before, "invalid input must not partly change the tab"


def test_live_direction_and_compare_string_read_current_geometry():
    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    layer.shapes = [GSPath([GSNode(p) for p in [(0, 0), (1, 0), (0, 1)]])]
    path = layer.paths[0]
    assert path.direction == -1
    assert "lll_" in layer.compareString()
    path.nodes[1].position = (-1, 0)
    assert path.direction == 1


def test_empty_direction_and_smooth_degenerate_rejection():
    assert GSPath().direction == 1
    a, b, c = (GSNode((0, 0)) for _ in range(3))
    path = GSPath([a, b, c])
    with pytest.raises(ValueError):
        path.setSmooth_withCenterNode_oppositeNode_(a, b, c)
    assert a.position == (0, 0)


def test_floating_window_level_export():
    from fontlab_glyport.ui.cocoa_views import NSFloatingWindowLevel

    assert NSFloatingWindowLevel == 3


def test_editor_view_when_beyond_window_controller_then_refused():
    """Issue 201: only the reporters' tool check exists on the view chain."""
    font = Model(FakeBackend()).font
    tab = font.newTab()
    controller = tab.view().window().windowController()
    tool = controller.toolDrawDelegate()
    assert tool.className() == "GlyphsToolSelect" and not tool.dragging()
    assert not tool.isKindOfClass_(None), "NSClassFromString('GlyphsToolText') is nil"
    assert tool.isKindOfClass_("GlyphsToolSelect")
    assert controller.toolEventHandler().className() == "GlyphsToolSelect"
    assert tab.windowController().document() is font.parent
    with pytest.raises(UnsupportedCapability, match="_EditorView.frame"):
        tab.view().frame()


@pytest.mark.parametrize("operation", ["master_copy", "layer_append", "tab_remove"])
def test_deferred_collection_operations_refuse_before_mutation(operation):
    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    operations = {
        "master_copy": lambda: font.masters[0].copy(),
        "layer_append": lambda: font.glyphs[0].layers.append(layer.copy()),
        "tab_remove": lambda: font.tabs.remove(font.currentTab),
    }
    width = layer.width
    with pytest.raises(UnsupportedCapability):
        operations[operation]()
    assert layer.width == width and len(font.glyphs[0].layers) == 1


def test_existing_path_styling_mapping_preserves_owned_values():
    path = GSPath()
    path.attributes["strokeWidth"] = 42
    path.attributes["strokeHeight"] = 13
    assert dict(path.copy().attributes) == {"strokeWidth": 42, "strokeHeight": 13}
    del path.attributes["strokeHeight"]
    assert dict(path.attributes) == {"strokeWidth": 42}


def test_detached_attributes_return_none_for_missing_glyphs_keys():
    assert DetachedLayer().attributes["axisRules"] is None


def test_detached_layer_attributes_cannot_be_silently_lost_on_attachment(
    owned_edit_info,
):
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = owned_edit_info
    glyph = font.glyphs[0].copy()
    with owned_edit_info._scope():
        glyph.name = "B"
    glyph.layers[0].attributes["coordinates"] = {"weight": 100}
    with pytest.raises(UnsupportedCapability, match="layer attributes"):
        font.glyphs.append(glyph)
    assert font.glyphs["B"] is None, "refuse before inserting a native glyph"


def test_compare_string_refuses_unverified_reference_component_encoding():
    layer = DetachedLayer()
    layer.shapes = [GSComponent("A")]
    with pytest.raises(UnsupportedCapability, match="anchorOrComponentEncoding"):
        layer.compareString()


@pytest.mark.parametrize("nested", [False, True])
def test_end_changes_retries_failed_publication(monkeypatch, nested):
    backend = FakeBackend()
    layer = Model(backend).font.glyphs[0].layers[0]
    original = backend.end_undo
    attempts = []

    def fail_once():
        attempts.append(True)
        if len(attempts) == 1:
            raise RuntimeError("publication failed")
        original()

    monkeypatch.setattr(backend, "end_undo", fail_once)
    layer.beginChanges()
    if nested:
        layer.beginChanges()
        layer.endChanges()
    layer.width = 123
    with pytest.raises(RuntimeError, match="publication failed"):
        layer.endChanges()
    assert backend.undo_events == [("begin", "Change layer")]
    layer.endChanges()
    assert backend.undo_events == [("begin", "Change layer"), ("end", None)]
    assert len(attempts) == 2 and layer.width == 123
    layer.beginChanges()
    layer.endChanges()
    assert len(attempts) == 3 and len(backend.undo_events) == 4
    with pytest.raises(RuntimeError, match="beginChanges"):
        layer.endChanges()


def test_tab_layers_refuses_background_before_publishing():
    backend = FakeBackend()
    font = Model(backend).font
    tab = font.newTab("A")
    before = list(backend.edit_texts)
    with pytest.raises(UnsupportedCapability, match="unsupportedLayerKind"):
        tab.layers = [font.glyphs[0].layers[0].background]
    assert backend.edit_texts == before, "background must not become foreground"


@pytest.mark.parametrize("route", ["live_background", "nested_background"])
def test_background_attachment_refuses_attributes_before_any_mutation(route):
    from copy import deepcopy

    backend = FakeBackend()
    font = Model(backend).font
    target = font.glyphs[0].layers[0]
    source = DetachedLayer()
    source.attributes["coordinates"] = {"weight": 100}
    source.shapes = [GSPath([GSNode((99, 99))])]
    if route == "nested_background":
        container = DetachedLayer()
        container.background = source
        source = container
    before = deepcopy(dict(backend.layers))
    with pytest.raises(UnsupportedCapability, match="layer attributes"):
        target.background = source
    assert dict(backend.layers) == before, "no foreground or mask geometry mutation"
    assert not backend.undo_events, "reject before opening a mutation scope"


@pytest.mark.parametrize("points", [[], [(0, 0)], [(0, 0), (1, 1), (2, 2)]])
@pytest.mark.parametrize("closed", [False, True])
def test_degenerate_path_direction_is_positive_one(points, closed):
    path = GSPath([GSNode(point) for point in points], closed=closed)
    assert path.direction == 1, "GlyphsCore returns +1 for zero area"
