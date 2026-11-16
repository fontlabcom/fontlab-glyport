# this_file: tests/test_compare_string_anchors.py
"""GlyphsCore comparison strings for ordinary named anchors and path topology."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSAnchor, GSComponent, GSNode, GSPath, Model
from fontlab_glyport.model.copies import DetachedLayer
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.proxies import CAP, CORNER


@pytest.fixture(params=["detached", "attached"])
def layer(request):
    result = (
        DetachedLayer()
        if request.param == "detached"
        else Model(FakeBackend()).font.glyphs[0].layers[0]
    )
    result.shapes = [GSPath([GSNode((0, 0)), GSNode((100, 100))])]
    return result


@pytest.mark.parametrize(
    "names, expected",
    [
        ([], "ll_"),
        (["top"], "ll_top"),
        (["top", "bottom"], "ll_bottom**top"),
        (
            ["top", "ogonek", "bottom", "_top", "top_1"],
            "ll__top**bottom**ogonek**top**top_1",
        ),
    ],
)
def test_compare_string_when_named_anchors_then_exact_reference_suffix(
    layer, names, expected
):
    for name in names:
        layer.anchors.append(GSAnchor(name, (10, 20)))
    assert layer.compareString() == expected, "sorted names use the reference ** join"


def test_compare_string_when_coordinates_change_then_signature_is_unchanged(layer):
    layer.anchors.append(GSAnchor("top", (10, 20)))
    before = layer.compareString()
    layer.anchors["top"].position = (-500, 1000)
    layer.paths[0].nodes[0].position = (999, -999)
    assert layer.compareString() == before == "ll_top", "geometry is excluded"


def test_compare_string_when_anchor_order_changes_then_signature_is_unchanged(layer):
    for name in ("top", "bottom"):
        layer.anchors.append(GSAnchor(name))
    before = layer.compareString()
    top = layer.anchors["top"].copy()
    layer.anchors.remove(layer.anchors["top"])
    layer.anchors.append(top)
    assert [a.name for a in layer.anchors] == ["bottom", "top"], "order changed"
    assert layer.compareString() == before == "ll_bottom**top", "sort by name"


def test_compare_string_when_anchor_added_removed_or_renamed_then_suffix_changes(layer):
    layer.anchors.append(GSAnchor("top"))
    assert layer.compareString() == "ll_top", "single anchor has no delimiter"
    layer.anchors.append(GSAnchor("bottom"))
    assert layer.compareString() == "ll_bottom**top", "new names participate"
    layer.anchors.remove(layer.anchors["top"])
    assert layer.compareString() == "ll_bottom", "removed name leaves no separator"
    layer.anchors.remove(layer.anchors["bottom"])
    layer.anchors.append(GSAnchor("center"))
    assert layer.compareString() == "ll_center", "renamed anchor changes the signature"
    layer.anchors.remove(layer.anchors["center"])
    assert layer.compareString() == "ll_", "no anchor leaves only path topology"


def test_compare_string_when_anchor_only_layer_then_names_have_no_outline_prefix(layer):
    layer.shapes = []
    layer.anchors.append(GSAnchor("top"))
    layer.anchors.append(GSAnchor("bottom"))
    assert layer.compareString() == "bottom**top", "no synthetic prefix or suffix"


def test_compare_string_when_node_topology_or_closed_state_changes_then_string_changes(
    layer,
):
    layer.anchors.append(GSAnchor("top"))
    path = layer.paths[0].copy()
    path.nodes.append(GSNode((20, 30), "offcurve"))
    layer.shapes = [path]
    assert layer.compareString() == "llo_top", "node count and type participate"
    path = layer.paths[0].copy()
    path.nodes[-1].type = "curve"
    layer.shapes = [path]
    assert layer.compareString() == "llc_top", "same node count can be incompatible"
    path = layer.paths[0].copy()
    path.closed = False
    layer.shapes = [path]
    assert layer.compareString() == "llc|_top", "open-path marker precedes names"
    path = layer.paths[0].copy()
    path.nodes[-1].type = "qcurve"
    layer.shapes = [path]
    assert layer.compareString() == "llq|_top", "quadratic node code is preserved"


def test_compare_string_when_paths_reordered_then_outline_order_is_preserved(layer):
    layer.anchors.append(GSAnchor("top"))
    first, second = GSPath([GSNode()]), GSPath([GSNode(), GSNode()], closed=False)
    layer.shapes = [first, second]
    assert layer.compareString() == "l_ll|_top", "each contour retains its terminator"
    layer.shapes = [second, first]
    assert layer.compareString() == "ll|_l_top", "path order is significant"


@pytest.mark.parametrize(
    "names",
    [
        ["z", "\u00e9"],
        ["z", "e\u0301"],
        ["\U00010000", "\ue000"],
        ["\ue000", "\U00010000"],
    ],
)
def test_compare_string_when_non_ascii_anchor_names_then_refuses_unverified_collation(
    layer, names
):
    for name in names:
        layer.anchors.append(GSAnchor(name))
    with pytest.raises(
        UnsupportedCapability,
        match=r"GSLayer\.compareString\.nonASCIIAnchorNames.*unverified NSString collation",
    ):
        layer.compareString()


@pytest.mark.parametrize("anchor_name", ["top", "\u00e9"])
def test_compare_string_when_component_and_anchor_present_then_component_refuses(
    layer, anchor_name
):
    layer.anchors.append(GSAnchor(anchor_name))
    layer.shapes.append(GSComponent("A"))
    with pytest.raises(UnsupportedCapability, match="anchorOrComponentEncoding"):
        layer.compareString()


@pytest.mark.parametrize("hint_type", [CAP, CORNER])
@pytest.mark.parametrize("anchor_name", ["top", "\u00e9"])
def test_compare_string_when_path_component_hint_then_refuses_before_anchor_encoding(
    hint_type, anchor_name
):
    layer = DetachedLayer()
    layer.anchors.append(GSAnchor(anchor_name))
    # Public GSHint construction already refuses these unsupported native kinds.
    layer._hints = [SimpleNamespace(type=hint_type)]
    with pytest.raises(UnsupportedCapability, match="pathComponents"):
        layer.compareString()
