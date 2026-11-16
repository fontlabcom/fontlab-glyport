# this_file: tests/test_issue106_compat.py
"""Hand-written compatibility examples; no corpus code or FontLab imports."""

import pytest
from glyphsapp_doubles import FakeGlyphsBridge

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import glyphsapp_provider, make_glyphsapp_module
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.mark.parametrize(
    ("short", "long", "value"),
    [
        ("OFFCURVE", "GSOFFCURVE", "offcurve"),
        ("CURVE", "GSCURVE", "curve"),
        ("LINE", "GSLINE", "line"),
        ("QCURVE", "GSQCURVE", "qcurve"),
    ],
)
def test_node_alias_when_exported_then_accepted_by_draft_and_live_nodes(
    short, long, value
):
    backend = FakeBackend()
    module = make_glyphsapp_module(
        Model(backend), FakeGlyphsBridge(), error_sink=lambda *args: None
    )
    assert short in module.__all__
    assert getattr(module, short) == getattr(module, long) == value
    node = GSNode((12, 34), type=getattr(module, short))
    assert node.type == value
    layer = module.Glyphs.font.glyphs[0].layers[0]
    layer.paths.append(GSPath([node]))
    assert layer.paths[-1].nodes[0].type == value


def test_node_alias_when_star_imported_then_available_in_owned_execution(tmp_path):
    script = tmp_path / "curves.py"
    script.write_text(
        "from GlyphsApp import *\n"
        "result = [GSNode((i, 0), type=t).type "
        "for i, t in enumerate((LINE, CURVE, OFFCURVE, QCURVE))]\n"
    )
    with ExecutionContext(tmp_path, "glyphs3") as ctx:
        ctx.adapters["GlyphsApp"] = glyphsapp_provider(
            Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
        )
    ctx.run(script)
    assert ctx.globals["result"] == ["line", "curve", "offcurve", "qcurve"]
    ctx.close()


def test_associated_master_when_master_layer_then_returns_live_master_id():
    backend = FakeBackend()
    font = Model(backend).font
    layer = font.glyphs[0].layers[0]
    assert layer.associatedMasterId == layer.master.id == font.masters[0].id
    with pytest.raises(UnsupportedCapability) as error:
        layer.associatedMasterId = "another-master"
    assert error.value.capability == "GSLayer.associatedMasterId"
    assert layer.associatedMasterId == font.masters[0].id
    backend.close_font("font")
    with pytest.raises(StaleNativeObject):
        _ = layer.associatedMasterId


def test_affine_struct_when_mutated_then_preserves_field_order_and_transform():
    from fontlab_glyport.drawing.cocoa_drawing import NSAffineTransform
    from fontlab_glyport.foundation import NSAffineTransformStruct

    values = NSAffineTransformStruct(m11=2, m22=3, tX=5, tY=-4)
    values.m21 = 0.5
    values[1] = 1
    assert tuple(values) == (2, 1, 0.5, 3, 5, -4)
    assert len(values) == 6 and values[-1] == -4
    assert values[2:4] == (0.5, 3)
    transform = NSAffineTransform.transform()
    transform.setTransformStruct_(values)
    assert transform.transformPoint_((4, 2)) == (14, 6)
    result = transform.transformStruct()
    assert isinstance(result, NSAffineTransformStruct)
    assert result.m11 == 2 and result.tX == 5
    result.tX = 99
    assert transform.transformPoint_((0, 0)) == (5, -4), "returned structs are copies"


def test_affine_struct_when_default_then_zero_fields_and_invalid_index_rejected():
    from fontlab_glyport.foundation import NSAffineTransformStruct

    assert tuple(NSAffineTransformStruct()) == (0, 0, 0, 0, 0, 0)
    with pytest.raises(IndexError):
        NSAffineTransformStruct()[6] = 1


def test_affine_struct_when_helpers_used_then_copies_and_fixed_length_slices():
    from fontlab_glyport.affine import NSAffineTransformStruct

    value = NSAffineTransformStruct(1, 2, 3, 4, 5, 6)
    value[::2] = (10, 30, 50)
    assert tuple(value) == (10, 2, 30, 4, 50, 6)
    before = tuple(value)
    with pytest.raises(ValueError):
        value[1:3] = (1,)
    assert tuple(value) == before
    assert value._asdict()["tX"] == 50
    clone = value._replace(tY=-5)
    assert clone.tY == -5 and value.tY == 6
    assert value.copy() == value and value.copy() is not value
    with pytest.raises(TypeError):
        value._replace(unknown=3)


def test_cocoa_lookup_when_struct_name_then_not_an_objective_c_class(tmp_path):
    from ui_doubles_session import make_session

    ctx, _ = make_session(tmp_path)
    with ctx:
        cocoa = ctx.import_module("Foundation")
        objc = ctx.import_module("objc")
        assert cocoa.NSClassFromString("NSAffineTransformStruct") is None
        with pytest.raises(objc.nosuchclass_error):
            objc.lookUpClass("NSAffineTransformStruct")
        assert cocoa.NSClassFromString("NSView") is cocoa.NSView
    ctx.close()


@pytest.mark.parametrize("module", ["AppKit", "Foundation", "Cocoa"])
def test_affine_struct_when_host_free_adapter_used_then_all_cocoa_aliases_export(
    module,
):
    from fontlab_glyport.adaptation_imports import cocoa_adapters

    values = cocoa_adapters()[module]().NSAffineTransformStruct(1, 0, 0, 1, -3, 4)
    assert tuple(values) == (1, 0, 0, 1, -3, 4)


@pytest.mark.parametrize("values", [(), (1, 2), (1, 2, 3, 4, 5, 6, 7)])
def test_affine_set_struct_when_wrong_arity_then_rejects_without_changing_matrix(
    values,
):
    from fontlab_glyport.drawing.cocoa_drawing import NSAffineTransform

    transform = NSAffineTransform.transform()
    with pytest.raises(ValueError):
        transform.setTransformStruct_(values)
    assert transform.transformPoint_((3, 4)) == (3, 4)
