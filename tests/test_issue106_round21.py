# this_file: tests/test_issue106_round21.py
"""Round-21 value boundaries, spacing and corpus-shaped API regressions."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


class Handle:
    def __deepcopy__(self, memo):
        return self


@pytest.mark.parametrize("value", [Handle(), {"nested": [Handle()]}, {1: "bad key"}])
def test_lib_values_reject_handles_and_non_string_keys(value):
    from fontlab_glyport.model.fontlab_backend import _plain

    with pytest.raises(UnsupportedCapability):
        _plain(value)


def test_attachment_rejects_nested_source_handle_before_any_target_write(monkeypatch):
    source = Model(FakeBackend()).font.glyphs[0]
    source.userData["bad"] = {"value": Handle()}
    copied = source.copy()
    backend = FakeBackend()
    writes = []
    monkeypatch.setattr(backend, "append_glyph", lambda *args: writes.append(args))
    with pytest.raises(UnsupportedCapability):
        Model(backend).font.glyphs.append(copied)
    assert writes == []


def test_cross_font_colliding_master_token_matches_name_not_token():
    from fontlab_glyport.model.attachment import target_master

    font = Model(FakeBackend()).font
    token = font.masters[0].id
    source = NS(associatedMasterId=token, name="Regular", __dict__={})
    masters = [NS(id=token, name="Bold"), NS(id="regular", name="Regular")]
    destination = NS(masters=masters)
    assert target_master(destination, source) == "regular"


def test_italic_sidebearings_include_half_xheight_center():
    from math import radians, tan

    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    layer.components = []
    layer.paths = [
        GSPath(
            [GSNode((10, 0)), GSNode((110, 0)), GSNode((110, 200)), GSNode((10, 200))]
        )
    ]
    layer.width = 120
    layer.master.italicAngle = 9
    center = layer.master.xHeight / 2
    shear = tan(radians(9))
    assert layer.LSB == pytest.approx(10 - shear * (200 - center))
    assert layer.RSB == pytest.approx(10 - shear * center)


def test_cocoa_rect_and_nested_point_fields_are_writable():
    from fontlab_glyport.ui.cocoa import NSPoint, NSRect, NSSize

    rect = NSRect()
    rect.origin = NSPoint(20, 700)
    rect.size = NSSize(500, 100)
    rect.origin.x = -20
    assert tuple(rect.origin) == (-20, 700)
    assert rect == ((-20, 700), (500, 100))


def test_glyph_metrics_keys_are_writable_and_inherited_by_layers():
    glyph = Model(FakeBackend()).font.glyphs[0]
    assert glyph.widthMetricsKey is None
    glyph.widthMetricsKey = "=B"
    assert glyph.widthMetricsKey == "=B"
    assert glyph.layers[0].widthMetricsKey is None


@pytest.mark.parametrize("failure", ["assignment", "verification", "recovery"])
def test_master_lib_restores_on_assignment_or_verification_failure(
    native, monkeypatch, failure
):
    from fontlab_glyport.errors import PartialFailure

    class Package:
        id = 1

        def __init__(self):
            self.value = {"keep": 7}
            self.writes = 0

        @property
        def masterLib(self):
            if failure == "verification" and self.writes == 1:
                raise RuntimeError("verification failed")
            return self.value

        @masterLib.setter
        def masterLib(self, value):
            self.writes += 1
            self.value = value
            if (
                self.writes == 1 or failure == "recovery"
            ) and failure != "verification":
                raise RuntimeError("assignment failed")

    package = Package()
    monkeypatch.setattr(native.backend, "_master_read", lambda mid, read: read(package))
    monkeypatch.setattr(native.backend, "_prepare", lambda *args: None)
    error = PartialFailure if failure == "recovery" else RuntimeError
    with pytest.raises(error):
        native.backend.set_lib(native.mid, {"new": 8})
    assert package.writes == 2
    assert package.value == {"keep": 7}


def test_update_metrics_evaluates_both_sides_independently(monkeypatch):
    from fontlab_glyport.model import GSGlyph

    font = Model(FakeBackend()).font
    target = font.glyphs[0].layers[0]
    target.components = []
    target.paths = [
        GSPath(
            [GSNode((10, 0)), GSNode((110, 0)), GSNode((110, 100)), GSNode((10, 100))]
        )
    ]
    reference = font.glyphs.append(GSGlyph("reference")).layers[0]
    reference.paths = [
        GSPath(
            [GSNode((23, 0)), GSNode((123, 0)), GSNode((123, 100)), GSNode((23, 100))]
        )
    ]
    reference.width = 170
    target.leftMetricsKey = "=reference"
    target.rightMetricsKey = "=reference"

    def bounds(layer_id):
        info = font._model._backend.layers[font._model._backend._layer_key(layer_id)]
        nodes = [node for path in info.paths for node in path.nodes]
        xs, ys = [node.x for node in nodes], [node.y for node in nodes]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    monkeypatch.setattr(font._model._backend, "layer_bounds", bounds)
    target.updateMetrics()
    assert target.LSB == pytest.approx(23)
    assert target.RSB == pytest.approx(47)


def test_layer_hint_bulk_assignment_copies_values_and_can_clear():
    from fontlab_glyport.model import GSHint

    font = Model(FakeBackend()).font
    layer = font.glyphs[0].layers[0]
    hint = GSHint()
    hint.position, hint.width = 50, 20
    layer.hints = [hint]
    copied = layer.copy()
    assert [(item.position, item.width) for item in copied.hints] == [(50, 20)]
    layer.hints = []
    layer.hints = [item.copy() for item in copied.hints]
    assert [(item.position, item.width) for item in layer.hints] == [(50, 20)]


def test_unlocker_startup_spinner_and_callback_lifecycle():
    import ui_doubles_controls  # noqa: F401 - register PythonQt control doubles
    from ui_doubles import make_qt

    from fontlab_glyport.ui.vanilla import make_vanilla_module

    vanilla = make_vanilla_module(make_qt(), error_sink=lambda *args: None)
    window = vanilla.FloatingWindow((300, 200), "Pairs")
    window.spinner = vanilla.ProgressSpinner((10, 10, 16, 16), sizeStyle="regular")
    window.spinner.start()
    view = window.spinner.getNSView()
    assert (view.minimum, view.maximum) == (0, 0)
    window.spinner.stop()
    assert view.maximum > view.minimum
    window.close()


def test_reinterpolation_workflow_refuses_rename_before_any_edit():
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    before = layer.copy()
    with pytest.raises(UnsupportedCapability) as error:
        layer.name = "scratch"
    assert error.value.capability == "GSLayer.name"
    assert layer.name == before.name
    assert layer.width == before.width


def test_generic_guide_constructor_value_error_is_a_precise_refusal(native):
    guide = type("flObject", (), {})()

    def refuse(*args):
        raise ValueError("Error creating object of type flGuideLine")

    native.module.flGuideLine = refuse
    with pytest.raises(UnsupportedCapability) as error:
        native.backend._guide_line(guide)
    assert error.value.capability == "GSGuide.nativeWrapper"


def test_master_parameter_reads_do_not_write_libs(native, monkeypatch):
    native.package.master = "Regular"
    native.package.masterLib = {}
    writes = []
    monkeypatch.setattr(native.backend, "_prepare", lambda *args: writes.append(args))
    master = native.font.masters[0]
    assert master.customParameters["paramArea"] is None
    assert "paramArea" not in master.customParameters
    assert native.package.masterLib == {}
    assert not writes


def test_cross_font_shapes_and_anchors_are_detached_values_at_append(monkeypatch):
    from fontlab_glyport.model import GSAnchor, GSComponent
    from fontlab_glyport.model.backend import ComponentInfo, PathInfo

    source = Model(FakeBackend()).font.glyphs[0].layers[0]
    source.anchors = [GSAnchor("top", (20, 40))]
    source.components = [GSComponent("A")]
    source.paths = [GSPath([GSNode((10, 0)), GSNode((110, 0)), GSNode((110, 100))])]
    backend = FakeBackend()
    destination = Model(backend).font.glyphs[0].layers[0]
    original_path, original_component = backend.append_path, backend.append_component
    calls = []

    def path(layer_id, info, *args, **kwargs):
        assert isinstance(info, PathInfo) and info.id == ""
        assert all(node.id == "" for node in info.nodes)
        calls.append("path")
        return original_path(layer_id, info, *args, **kwargs)

    def component(layer_id, info, *args, **kwargs):
        assert isinstance(info, ComponentInfo) and info.id == ""
        assert info.componentName == "A"
        assert all(isinstance(value, (float, int)) for value in info.transform)
        calls.append("component")
        return original_component(layer_id, info, *args, **kwargs)

    monkeypatch.setattr(backend, "append_path", path)
    monkeypatch.setattr(backend, "append_component", component)
    destination.shapes = []
    for shape in source.shapes:
        copied = shape.copy()
        assert "_font" not in copied.__dict__
        destination.shapes.append(copied)
    destination.anchors = [anchor.copy() for anchor in source.anchors]
    assert sorted(calls) == ["component", "path"]
    assert destination.anchors["top"].position == (20, 40)
    destination.anchors["top"].position = (30, 50)
    assert source.anchors["top"].position == (20, 40)


@pytest.mark.parametrize("value", [80, 10001])
def test_explicit_slant_metric_and_unset_sentinel_match_recovered_core(monkeypatch, value):
    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    monkeypatch.setattr(type(layer), "metricForType_", lambda self, kind: value)
    expected = 80 if value == 80 else layer.master.xHeight / 2
    assert layer.master.slantHeightForLayer_(layer) == expected


def test_layer_userdata_handle_is_rejected_before_insertion(monkeypatch):
    source = Model(FakeBackend()).font.glyphs[0]
    source.layers[0].userData["bad"] = Handle()
    detached = source.copy()
    backend = FakeBackend()
    writes = []
    monkeypatch.setattr(backend, "append_glyph", lambda *args: writes.append(args))
    with pytest.raises(UnsupportedCapability):
        Model(backend).font.glyphs.append(detached)
    assert not writes


def test_supported_lib_graph_is_materialized_and_cycles_refuse():
    from fontlab_glyport.model.fontlab_backend import _plain

    class Text(str):
        pass

    result = _plain({"data": (Text("value"), b"bytes", 3, True, None)})
    assert type(result["data"]) is list
    assert type(result["data"][0]) is str
    cycle = []
    cycle.append(cycle)
    with pytest.raises(UnsupportedCapability, match="Cyclic"):
        _plain(cycle)


def test_actual_cross_font_copy_fills_regular_not_colliding_bold():
    from dataclasses import replace

    from fontlab_glyport.model.backend import MasterInfo

    source = Model(FakeBackend()).font.glyphs[0]
    source.layers[0].width = 500
    copied = source.copy()
    copied.name = "Copied"
    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Bold"), MasterInfo("regular", "Regular")),
    )
    result = Model(backend).font.glyphs.append(copied)
    assert result.layers["regular"].width == 500
    assert result.layers["master"].width == 0
