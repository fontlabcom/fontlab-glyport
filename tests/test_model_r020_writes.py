# this_file: tests/test_model_r020_writes.py
"""R020 writes through the Glyphs model (no native host): features, prefix,
classes, axes, instances and hints. Native proof lives in the evidence drivers
(verification/issue-101-ecosystem/evidence/glyport-r020/)."""

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.proxies import GSFeature, GSFeaturePrefix


@pytest.fixture
def font():
    return Model(FakeBackend()).font


# Features and prefix ------------------------------------------------------------


def test_feature_append_when_glyphs_body_then_stored_wrapped_in_fontlab_block(font):
    backend = font._model._backend
    font.features.append(GSFeature("liga", "sub f i by f_i;"))
    assert backend.feature_data["font"][1] == (
        ("liga", "feature liga {\nsub f i by f_i;\n} liga;\n"),
    )
    (liga,) = font.features
    assert (liga.name, liga.code) == ("liga", "sub f i by f_i;")


def test_feature_code_when_set_on_attached_feature_then_written(font):
    font.features.append(GSFeature(name="kern", code="pos A V -40;"))
    font.features["kern"].code = "pos A V -60;"
    assert font.features["kern"].code == "pos A V -60;"


def test_feature_remove_when_attached_then_gone(font):
    font.features.append(GSFeature("liga", "sub f i by f_i;"))
    font.features.append(GSFeature("kern", "pos A V -40;"))
    font.features.remove(font.features["liga"])
    assert [f.name for f in font.features] == ["kern"]


def test_feature_append_when_name_exists_or_invalid_then_refused(font):
    font.features.append(GSFeature("liga", "x;"))
    with pytest.raises(UnsupportedCapability):
        font.features.append(GSFeature("liga", "y;"))
    with pytest.raises(TypeError):
        font.features.append("liga")
    with pytest.raises(ValueError):
        font.features.append(GSFeature("", "x;"))
    with pytest.raises(TypeError):
        font.features.append(GSFeature("ss01", None))


def test_feature_detached_when_edited_then_values_kept_until_append(font):
    feature = GSFeature()
    feature.name, feature.code = "ss01", "sub a by a.ss01;"
    font.features.append(feature)
    assert font.features["ss01"].code == "sub a by a.ss01;"


def test_feature_name_when_attached_then_rename_unsupported(font):
    font.features.append(GSFeature("liga", "x;"))
    with pytest.raises(UnsupportedCapability):
        font.features["liga"].name = "dlig"


def test_feature_code_when_native_text_is_not_one_block_then_read_verbatim(font):
    backend = font._model._backend
    backend.feature_data["font"] = ("", (("kern", "# comment\nlookup x {} x;"),))
    assert font.features["kern"].code == "# comment\nlookup x {} x;"


def test_feature_edits_when_undo_group_then_inside_one_group(font):
    backend = font._model._backend
    with font.undo_group("features"):
        font.features.append(GSFeature("liga", "x;"))
        font.features["liga"].code = "y;"
    assert backend.undo_events == [("begin", "features"), ("end", None)]


def test_prefix_when_appended_set_and_removed_then_one_native_prefix(font):
    backend = font._model._backend
    font.featurePrefixes.append(GSFeaturePrefix("Prefix", "languagesystem DFLT dflt;"))
    (prefix,) = font.featurePrefixes
    assert prefix.code == "languagesystem DFLT dflt;"
    prefix.code = "languagesystem latn dflt;"
    assert backend.feature_data["font"][0] == "languagesystem latn dflt;"
    with pytest.raises(UnsupportedCapability):
        font.featurePrefixes.append(GSFeaturePrefix("Other", "x"))
    font.featurePrefixes.remove(font.featurePrefixes[0])
    assert list(font.featurePrefixes) == []


# OpenType classes ---------------------------------------------------------------


def test_class_append_when_names_then_native_glyph_list(font):
    from fontlab_glyport.model.backend import ClassInfo
    from fontlab_glyport.model.proxies import GSClass

    backend = font._model._backend
    font.classes.append(GSClass("uc", "A  B\nC"))
    assert backend.class_data["font"] == (ClassInfo("uc", ("A", "B", "C")),)
    assert font.classes["uc"].code == "A B C"


def test_class_code_name_and_remove_when_attached_then_written(font):
    from fontlab_glyport.model.proxies import GSClass

    font.classes.append(GSClass("uc", "A"))
    font.classes["uc"].code = "A B"
    assert font.classes["uc"].code == "A B"
    font.classes["uc"].name = "caps"
    assert [c.name for c in font.classes] == ["caps"]
    font.classes.remove(font.classes["caps"])
    assert list(font.classes) == []


def test_class_append_when_duplicate_or_bad_then_refused(font):
    from fontlab_glyport.model.proxies import GSClass

    font.classes.append(GSClass("uc", "A"))
    with pytest.raises(UnsupportedCapability):
        font.classes.append(GSClass("uc", "B"))
    with pytest.raises(TypeError):
        font.classes.append(GSFeature("lc", "a"))
    with pytest.raises(ValueError):
        font.classes.append(GSClass("", "a"))


def test_class_rename_when_target_exists_then_refused(font):
    from fontlab_glyport.model.proxies import GSClass

    font.classes.append(GSClass("uc", "A"))
    font.classes.append(GSClass("lc", "a"))
    with pytest.raises(UnsupportedCapability):
        font.classes["uc"].name = "lc"


def test_class_automatic_when_set_true_then_unsupported(font):
    from fontlab_glyport.model.proxies import GSClass

    cls = GSClass("uc", "A")
    assert cls.automatic is False
    with pytest.raises(UnsupportedCapability):
        cls.automatic = True


# Hints --------------------------------------------------------------------------


def _layer(font):
    return font.glyphs["A"].layers[0]


def test_hint_append_when_position_and_width_then_fontlab_stem(font):
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.proxies import GSHint

    layer = _layer(font)
    hint = GSHint()
    hint.horizontal, hint.position, hint.width, hint.name = True, 100, 80, "h1"
    layer.hints.append(hint)
    assert font._model._backend.hint_data[layer.id] == (HintInfo(True, 100, 80, "h1"),)
    (stored,) = layer.hints
    assert (stored.position, stored.width, stored.name) == (100, 80, "h1")


def test_hint_append_when_origin_and_target_nodes_then_position_and_width(font):
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.proxies import GSHint, GSNode

    layer = _layer(font)
    hint = GSHint()
    hint.originNode, hint.targetNode = GSNode((10, 700)), GSNode((90, 620))
    layer.hints.append(hint)  # horizontal by default: y edges, sorted
    vertical = GSHint()
    vertical.horizontal = False
    vertical.originNode, vertical.targetNode = GSNode((90, 0)), GSNode((10, 0))
    layer.hints.append(vertical)
    assert font._model._backend.hint_data[layer.id] == (
        HintInfo(True, 620, 80, ""),
        HintInfo(False, 10, 80, ""),
    )


def test_hint_append_when_ghosts_then_native_ghost_widths(font):
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.proxies import BOTTOMGHOST, TOPGHOST, GSHint, GSNode

    layer = _layer(font)
    top = GSHint()
    top.type, top.originNode = TOPGHOST, GSNode((0, 700))
    bottom = GSHint()
    bottom.type, bottom.position = BOTTOMGHOST, 0
    layer.hints.append(top)
    layer.hints.append(bottom)
    assert font._model._backend.hint_data[layer.id] == (
        HintInfo(True, 700, -20, "", True),
        HintInfo(True, 0, 21, "", True),
    )
    assert [h.type for h in layer.hints] == [TOPGHOST, BOTTOMGHOST]


def test_hint_append_when_incomplete_or_unsupported_then_refused(font):
    from fontlab_glyport.model.proxies import TOPGHOST, GSHint

    layer = _layer(font)
    with pytest.raises(ValueError):
        layer.hints.append(GSHint())  # no position
    ghost = GSHint()
    ghost.type, ghost.horizontal, ghost.position = TOPGHOST, False, 10
    with pytest.raises(UnsupportedCapability):
        layer.hints.append(ghost)
    with pytest.raises(UnsupportedCapability):
        GSHint().type = 2  # TrueType and other Glyphs hint types
    with pytest.raises(TypeError):
        layer.hints.append("hint")
    zero = GSHint()
    zero.position, zero.width = 10, 0
    with pytest.raises(ValueError):
        layer.hints.append(zero)


def test_hint_remove_and_edit_when_attached_then_by_native_index(font):
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.proxies import GSHint

    layer = _layer(font)
    for position in (100, 300):
        hint = GSHint()
        hint.position, hint.width = position, 50
        layer.hints.append(hint)
    layer.hints[1].name = "upper"
    layer.hints[1].position = 320
    layer.hints.remove(layer.hints[0])
    assert font._model._backend.hint_data[layer.id] == (
        HintInfo(True, 320, 50, "upper"),
    )


def test_hint_when_native_list_changed_since_read_then_stale(font):
    from fontlab_glyport.errors import StaleNativeObject
    from fontlab_glyport.model.proxies import GSHint

    layer = _layer(font)
    hint = GSHint()
    hint.position, hint.width = 100, 50
    layer.hints.append(hint)
    held = layer.hints[0]
    backend = font._model._backend
    backend.hint_data[layer.id] = ()
    with pytest.raises(StaleNativeObject):
        held.name = "x"
    with pytest.raises(ValueError):
        layer.hints.remove(held)


# Axes and master coordinates ------------------------------------------------------


def test_axis_append_when_new_then_font_axis_and_master_coordinate(font):
    from fontlab_glyport.model.proxies import GSAxis

    axis = GSAxis()
    axis.name, axis.axisTag = "Weight", "wght"
    font.axes.append(axis)
    (stored,) = font.axes
    assert (stored.name, stored.axisTag, stored.hidden) == ("Weight", "wght", False)
    assert stored == axis and axis.id == stored.id
    assert font.masters[0].axes == [0.0]


def test_axis_append_when_duplicate_or_incomplete_then_refused(font):
    from fontlab_glyport.model.proxies import GSAxis

    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    with pytest.raises(UnsupportedCapability):
        font.axes.append(GSAxis(name="Weight", axisTag="wgt2"))
    with pytest.raises(UnsupportedCapability):
        font.axes.append(GSAxis(name="Heavy", axisTag="wght"))
    with pytest.raises(ValueError):
        font.axes.append(GSAxis(name="", axisTag="wdth"))
    with pytest.raises(ValueError):
        font.axes.append(GSAxis(name="Width", axisTag="toolong"))
    with pytest.raises(TypeError):
        font.axes.append("Width")


def test_axis_remove_when_attached_then_axis_and_master_coordinate_gone(font):
    from fontlab_glyport.model.proxies import GSAxis

    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    font.axes.append(GSAxis(name="Width", axisTag="wdth"))
    font.masters[0].axes = [700, 100]
    font.axes.remove(font.axes["Weight"])
    assert [a.name for a in font.axes] == ["Width"]
    assert font.masters[0].axes == [100.0]


def test_axis_attributes_when_attached_then_written(font):
    from fontlab_glyport.model.proxies import GSAxis

    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    axis = font.axes[0]
    axis.hidden = True
    axis.name = "Boldness"
    assert (font.axes[0].name, font.axes[0].hidden) == ("Boldness", True)


def test_master_axes_when_set_then_coordinates_in_axis_order(font):
    from fontlab_glyport.model.proxies import GSAxis

    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    master = font.masters[0]
    master.axes = [400]
    assert master.axes == [400.0] and master.internalAxesValues == [400.0]
    with pytest.raises(ValueError):
        master.axes = [400, 100]
    with pytest.raises(TypeError):
        master.axes = ["bold"]


# Instances ---------------------------------------------------------------------


def _axis_font():
    from fontlab_glyport.model.proxies import GSAxis

    font = Model(FakeBackend()).font
    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    font.masters[0].axes = [400]
    return font


def test_instance_append_when_new_then_name_exports_and_coordinates():
    from fontlab_glyport.model.proxies import GSInstance

    font = _axis_font()
    bold = GSInstance()
    bold.name, bold.axes = "Bold", [700]
    font.instances.append(bold)
    light = GSInstance()
    light.name, light.exports = "Light", False
    font.instances.append(light)  # no coordinates: the first master's
    assert [(i.name, i.exports, i.axes) for i in font.instances] == [
        ("Bold", True, [700.0]),
        ("Light", False, [400.0]),
    ]
    assert bold == font.instances[0]


def test_instance_attributes_and_remove_when_attached_then_written():
    from fontlab_glyport.model.proxies import GSInstance

    font = _axis_font()
    for name, weight in (("Light", 300), ("Bold", 700)):
        instance = GSInstance()
        instance.name, instance.internalAxesValues = name, [weight]
        font.instances.append(instance)
    bold = font.instances["Bold"]
    bold.name, bold.exports, bold.axes = "Black", False, [900]
    assert [(i.name, i.exports, i.axes) for i in font.instances] == [
        ("Light", True, [300.0]),
        ("Black", False, [900.0]),
    ]
    font.instances.remove(font.instances["Light"])
    assert [i.name for i in font.instances] == ["Black"]


def test_instance_when_bad_values_or_stale_then_refused():
    from fontlab_glyport.errors import StaleNativeObject
    from fontlab_glyport.model.proxies import GSInstance

    font = _axis_font()
    wrong = GSInstance()
    wrong.axes = [1, 2]
    with pytest.raises(ValueError):
        font.instances.append(wrong)
    unnamed = GSInstance()
    unnamed.name = ""
    with pytest.raises(ValueError):
        font.instances.append(unnamed)
    with pytest.raises(TypeError):
        font.instances.append("Bold")
    with pytest.raises(UnsupportedCapability):
        GSInstance().weightClass = 700
    font.instances.append(GSInstance())
    held = font.instances[0]
    font._model._backend.instance_data["font"] = ()
    with pytest.raises(StaleNativeObject):
        held.name = "x"
