# this_file: tests/test_public_api_gaps.py
"""SDK contract and behavioural regressions for the public API review."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import (
    GSAnchor,
    GSComponent,
    GSFont,
    GSFontMaster,
    GSGlyph,
    GSGuide,
    GSNode,
    GSPath,
    Model,
)
from fontlab_glyport.model.fake_backend import FakeBackend


def sdk_path():
    """Return the Glyphs SDK wrapper named by GLYPHS_SDK_PATH, or None when unset."""
    location = os.environ.get("GLYPHS_SDK_PATH")
    if not location:
        return None
    path = Path(location)
    return (
        path if path.suffix == ".py" else path / "ObjectWrapper/GlyphsApp/__init__.py"
    )


@pytest.mark.parametrize("wrapper_file", [False, True])
def test_sdk_path_uses_explicit_environment_location(
    monkeypatch, tmp_path, wrapper_file
):
    root = tmp_path / "SDK"
    wrapper = root / "ObjectWrapper/GlyphsApp/__init__.py"
    monkeypatch.setenv("GLYPHS_SDK_PATH", str(wrapper if wrapper_file else root))
    assert sdk_path() == wrapper


def test_sdk_path_when_environment_unset_then_none(monkeypatch):
    monkeypatch.delenv("GLYPHS_SDK_PATH", raising=False)
    assert sdk_path() is None, "no machine-specific default SDK location"


def test_all_overlapping_sdk_constants_match():
    sdk = sdk_path()
    if sdk is None or not sdk.is_file():
        pytest.skip("set GLYPHS_SDK_PATH to the Glyphs SDK checkout")
    constants = {}
    for statement in ast.parse(sdk.read_text()).body:
        if not isinstance(statement, ast.Assign):
            continue
        try:
            value = ast.literal_eval(statement.value)
        except (ValueError, TypeError):
            expression = statement.value
            if isinstance(expression, ast.BinOp) and isinstance(
                expression.op, ast.LShift
            ):
                value = ast.literal_eval(expression.left) << ast.literal_eval(
                    expression.right
                )
            else:
                continue
        for target in statement.targets:
            if isinstance(target, ast.Name) and isinstance(value, (str, int, float)):
                constants[target.id] = value
    module = make_glyphsapp_module(
        Model(FakeBackend()), None, error_sink=lambda *a: None
    )
    overlapping = set(constants) & set(module.__all__)
    assert len(overlapping) > 150
    assert {name: getattr(module, name) for name in overlapping} == {
        name: constants[name] for name in overlapping
    }
    assert module.GSRTL == module.RTL == 2
    assert module.GSBIDI == module.BIDI == 1
    assert module.GSGuideLine is module.GSGuide
    assert module.MOVE == module.GSMOVE == "move"
    assert (module.ONSTATE, module.OFFSTATE, module.MIXEDSTATE) == (1, 0, -1)


def test_plugin_bases_import_without_backend_or_host():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from fontlab_glyport.GlyphsApp.plugins import (
    GeneralPlugin, FileFormatPlugin, FilterWithDialog, FilterWithoutDialog,
    PalettePlugin, ReporterPlugin, SelectTool,
)
from fontlab_glyport.GlyphsApp import _binding
assert _binding._default is _binding._context is None
assert not {'fontlab', 'fontgate', 'PythonQt'} & sys.modules.keys()
assert GeneralPlugin.__name__ == 'GeneralPlugin'
""",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_public_imports_expose_detached_constructors_and_sdk_aliases():
    import fontlab_glyport.GlyphsApp as public

    public.unbind()
    public.use_backend(FakeBackend())
    try:
        from fontlab_glyport.GlyphsApp import (
            BIDI,
            MOVE,
            RTL,
            GSFont,
            GSFontMaster,
            GSGuide,
            GSGuideLine,
        )

        font, master = GSFont(), GSFontMaster()
        master.name = "Display"
        font.masters.append(master)
        assert font.masters[0] is master and master.font is font
        assert (BIDI, RTL, MOVE) == (1, 2, "move")
        assert GSGuideLine is GSGuide
    finally:
        public.unbind()


def test_project_and_host_installer_require_app_release_floor():
    import tomllib

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    dependencies = project["project"]["dependencies"]
    assert "fontlab-fontlabapp>=1.2.10" in dependencies
    assert project["tool"]["fontlab-install"]["dependencies"] == dependencies


def test_empty_font_and_master_can_be_filled_and_saved(tmp_path):
    font, master = GSFont(), GSFontMaster()
    assert len(font.glyphs) == len(font.masters) == 0
    assert master.font is None
    font.familyName, font.upm = "Detached", 2048
    master.name, master.ascender, master.descender = "Book", 1550, -450
    font.masters.append(master)
    font.glyphs.append(GSGlyph("X"))
    assert master.font is font and font.masters[0] is master
    assert (font.familyName, font.unitsPerEm) == ("Detached", 2048)
    assert (master.name, master.ascender, master.descender) == ("Book", 1550, -450)
    font.save(str(tmp_path / "Detached.ufo"))
    from fontTools.ufoLib import UFOReader

    with UFOReader(tmp_path / "Detached.ufo") as reader:
        assert reader.getGlyphSet().keys() == ["X"]


@pytest.fixture
def font():
    return Model(FakeBackend()).font


@pytest.mark.parametrize("detached", [False, True])
def test_selection_replaces_and_clears_all_four_kinds_without_undo(font, detached):
    layer = font.glyphs[0].layers[0]
    layer.anchors.append(GSAnchor("top", (10, 100)))
    layer.guides.append(GSGuide((20, 30)))
    if detached:
        layer = layer.copy()
    items = [
        layer.paths[0].nodes[0],
        layer.anchors[0],
        layer.components[0],
        layer.guides[0],
    ]
    layer.selection = items
    assert list(layer.selection) == items
    assert all(item.selected for item in items)
    layer.selection = [items[2]]
    assert list(layer.selection) == [items[2]]
    assert not items[0].selected and not items[1].selected and not items[3].selected
    layer.selection = items
    layer.clearSelection()
    assert list(layer.selection) == [] and not any(item.selected for item in items)
    layer.selection = []
    assert font._model._backend.undo_events == []


def test_selection_preflights_foreign_and_unsupported_kinds(font):
    layer = font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    layer.selection = [node]
    for invalid in [GSNode(), GSAnchor(), object()]:
        with pytest.raises((ValueError, UnsupportedCapability)):
            layer.selection = [node, invalid]
        assert list(layer.selection) == [node]
    anchor = layer.anchors.append(GSAnchor("top"))
    font._model._backend.supports_anchor_selection = False
    with pytest.raises(UnsupportedCapability, match="anchorSelection"):
        layer.selection = [anchor]
    assert node.selected and not anchor.selected
    layer.selection = []
    assert not node.selected and not layer.selection
    layer.selection = [node]
    layer.clearSelection()
    assert not node.selected and not layer.selection


@pytest.mark.parametrize("kind", ["anchor", "guide"])
def test_selection_clear_skips_unobservable_kinds_without_changing_them(font, kind):
    layer = font.glyphs[0].layers[0]
    sequence, element = (
        (layer.anchors, GSAnchor("top"))
        if kind == "anchor"
        else (layer.guides, GSGuide((10, 20)))
    )
    unsupported = sequence.append(element)
    unsupported.selected = True
    backend = font._model._backend
    setattr(backend, f"supports_{kind}_selection", False)
    node, component = layer.paths[0].nodes[0], layer.components[0]
    layer.selection = [node]
    with pytest.raises(UnsupportedCapability, match=kind + "Selection"):
        layer.selection = [component, unsupported]
    assert list(layer.selection) == [node]
    layer.selection = [component]
    assert component.selected and not node.selected
    layer.clearSelection()
    assert list(layer.selection) == []
    layer.selection = [node]
    layer.selection = []
    assert not node.selected and unsupported._data().selected
    assert backend.undo_events == []


@pytest.mark.parametrize("scale", [(-1, 1), (1, -1)])
@pytest.mark.parametrize("live", [False, True])
def test_component_mirror_keeps_axis_sign_and_zero_rotation(font, scale, live):
    component = GSComponent("A", offset=(10, 20), scale=scale)
    if live:
        component = font.glyphs[0].layers[0].components.append(component)
    assert component.scale == scale
    assert component.rotation == 0
    assert component.transform == (scale[0], 0, 0, scale[1], 10, 20)
    component.scale = tuple(value * 2 for value in scale)
    assert component.scale == (scale[0] * 2, scale[1] * 2)
    assert component.rotation == 0 and component.position == (10, 20)


@pytest.mark.parametrize("scale,angle", [((2, 3), 135), ((-2, 3), 30), ((2, -3), -30)])
def test_component_rotated_scaled_matrix_round_trip(scale, angle):
    from math import cos, radians, sin

    component = GSComponent("A", offset=(10, 20), scale=scale)
    component.rotation = angle
    a = radians(angle)
    expected = (
        scale[0] * cos(a),
        scale[0] * sin(a),
        -scale[1] * sin(a),
        scale[1] * cos(a),
        10,
        20,
    )
    assert component.transform == pytest.approx(expected)
    restored = GSComponent("A", transform=component.transform)
    assert restored.scale == pytest.approx(scale)
    assert restored.rotation == pytest.approx(angle)
    restored.rotation = 0
    assert restored.transform == pytest.approx((scale[0], 0, 0, scale[1], 10, 20))


@pytest.mark.parametrize("value", [None, "bogus", "move", "hobbycurve", 1, [], {}])
def test_live_node_type_rejects_invalid_values_before_any_backend_access(
    font, monkeypatch, value
):
    backend = font._model._backend
    node = font.glyphs[0].layers[0].paths[0].nodes[0]
    before = node._data()

    def forbidden(*args):
        pytest.fail("invalid node type touched the backend")

    with monkeypatch.context() as guard:
        guard.setattr(backend, "is_valid", forbidden)
        guard.setattr(backend, "set_node_type", forbidden)
        with pytest.raises(ValueError, match="Invalid node type"):
            node.type = value
    assert node._data() == before and backend.undo_events == []


def test_component_constructor_transform_scale_rotation_and_live_writes(font):
    component = GSComponent("A", offset=(10, 20), scale=(2, 3))
    assert component.transform == (2, 0, 0, 3, 10, 20)
    component.rotation = 90
    assert component.transform == pytest.approx((0, 2, -3, 0, 10, 20))
    assert component.scale == pytest.approx((2, 3))
    component.scale = (4, -5)
    assert component.transform == pytest.approx((0, 4, 5, 0, 10, 20))
    explicit = GSComponent(
        "A", offset=(99, 99), scale=(9, 9), transform=(1, 0, 0, 2, 3, 4)
    )
    assert explicit.transform == (1, 0, 0, 2, 3, 4)
    assert GSComponent().componentName == ""
    live = font.glyphs[0].layers[0].components[0]
    live.transform = component.transform
    live.rotation = 0
    live.scale = (6, 7)
    assert live.transform == pytest.approx((6, 0, 0, 7, 10, 20))
    assert len(font._model._backend.undo_events) == 6
    for bad in [(1, 2), (1, 0, 0, 1, float("nan"), 0)]:
        with pytest.raises(ValueError):
            live.transform = bad
    assert len(font._model._backend.undo_events) == 6


@pytest.mark.parametrize(
    "field,value",
    [
        ("familyName", "New family"),
        ("unitsPerEm", 2048),
        ("upm", 2000),
    ],
)
def test_font_metadata_writes_have_one_undo_step(font, field, value):
    setattr(font, field, value)
    assert getattr(font, field) == value
    assert len(font._model._backend.undo_events) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "Book"),
        ("ascender", 820),
        ("capHeight", 720),
        ("xHeight", 510),
        ("descender", -220),
        ("italicAngle", -12),
    ],
)
def test_master_metadata_writes_have_one_undo_step(font, field, value):
    master = font.masters[0]
    setattr(master, field, value)
    assert getattr(master, field) == value
    assert font.masters[master.id] is master
    assert len(font._model._backend.undo_events) == 2


def test_node_type_and_anchor_name_write_preserve_geometry_and_one_undo(font):
    layer = font.glyphs[0].layers[0]
    node = layer.paths[0].nodes[0]
    node.type = "offcurve"
    assert node.type == "offcurve" and node.position == (0, 0)
    anchor = layer.anchors.append(GSAnchor("top", (40, 90)))
    font._model._backend.undo_events.clear()
    anchor.name = "upper"
    assert layer.anchors["upper"] is anchor and anchor.position == (40, 90)
    assert len(font._model._backend.undo_events) == 2
    with pytest.raises(ValueError):
        node.type = "bogus"
    assert node.type == "offcurve"


@pytest.mark.parametrize("closed", [True, False])
@pytest.mark.parametrize("live", [True, False])
def test_reverse_preserves_curve_geometry_flags_and_undo(font, closed, live):
    path = GSPath(
        [
            GSNode((0, 0)),
            GSNode((10, 30), "offcurve"),
            GSNode((30, 30), "offcurve"),
            GSNode((40, 0), "curve"),
            GSNode((60, 0)),
        ],
        closed=closed,
    )
    if live:
        path = font.glyphs[0].layers[0].paths.append(path)
    before = [tuple(tuple(point) for point in segment) for segment in path.segments]
    assert path.reverse() is None
    assert path.closed is closed
    after = [tuple(tuple(point) for point in segment) for segment in path.segments]
    assert sorted(after) == sorted(tuple(reversed(segment)) for segment in before)
    assert len(font._model._backend.undo_events) == (2 if live else 0)
    path.reverse()
    assert sorted(
        tuple(tuple(point) for point in segment) for segment in path.segments
    ) == sorted(before)
