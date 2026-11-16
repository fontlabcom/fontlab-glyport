# this_file: tests/test_model_r020_review.py
"""R020 review fixes (reports/R-r020.md) at the model level: record identity
and lifetime, feature and class text, axis uniqueness. No native host."""

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.proxies import (
    BOTTOMGHOST,
    TOPGHOST,
    GSAxis,
    GSClass,
    GSFeature,
    GSHint,
    GSInstance,
)


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def _instances(font, *names):
    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    for name in names:
        instance = GSInstance()
        instance.name, instance.axes = name, [400]
        font.instances.append(instance)


# P1 instance identity -------------------------------------------------------------


def test_instance_when_equal_twin_removed_then_held_proxy_stale_and_survivor_kept(font):
    _instances(font, "Same", "Same")
    first, second = font.instances[0], font.instances[1]
    font.instances.remove(first)
    with pytest.raises(StaleNativeObject):
        first.name = "Edited"
    second.name = "Survivor"
    assert [i.name for i in font.instances] == ["Survivor"]
    assert font.instances[0] is second


def test_instance_when_edited_through_alias_then_other_alias_reads_live(font):
    _instances(font, "Bold")
    a, b = font.instances[0], font.instances["Bold"]
    assert a is b
    a.exports = False
    a.name = "Black"
    assert (b.name, b.exports) == ("Black", False)


def test_instance_when_list_changed_outside_glyport_then_held_proxies_stale(font):
    _instances(font, "Bold")
    held = font.instances[0]
    backend = font._model._backend
    backend.instance_data["font"] = ()
    with pytest.raises(StaleNativeObject):
        _ = held.name


# P1 features ---------------------------------------------------------------------


def test_feature_when_comment_precedes_block_then_verbatim_and_round_trip(font):
    backend = font._model._backend
    text = "# Ligatures\nfeature liga {\n  sub f i by f_i;\n} liga;\n"
    backend.feature_data["font"] = ("", (("liga", text),))
    liga = font.features["liga"]
    assert liga.code == text
    liga.code = liga.code
    assert backend.feature_data["font"][1] == (("liga", text),)
    with pytest.raises(UnsupportedCapability):
        liga.code = "sub a by b;"
    assert backend.feature_data["font"][1] == (("liga", text),)


def test_feature_when_clean_block_then_body_replaced_in_place_byte_exact(font):
    backend = font._model._backend
    backend.feature_data["font"] = (
        "",
        (("kern", "feature kern{pos A B -40;}kern;\n"),),
    )
    kern = font.features["kern"]
    assert kern.code == "pos A B -40;"
    kern.code = kern.code
    assert backend.feature_data["font"][1] == (
        ("kern", "feature kern{pos A B -40;}kern;\n"),
    )
    kern.code = "pos A B -60;"
    assert backend.feature_data["font"][1] == (
        ("kern", "feature kern{pos A B -60;}kern;\n"),
    )


def test_feature_when_removed_or_replaced_then_held_proxy_stale(font):
    font.features.append(GSFeature("liga", "x;"))
    held = font.features["liga"]
    assert held is font.features["liga"]
    font.features.remove(held)
    with pytest.raises(StaleNativeObject):
        held.code = "y;"
    font.features.append(GSFeature("liga", "z;"))
    with pytest.raises(StaleNativeObject):
        held.code = "y;"
    assert font.features["liga"].code == "z;"


# P1 classes ----------------------------------------------------------------------


@pytest.mark.parametrize("code", ["A # comment\nB", "@uc a", "[A B]", "A;", "A \\B"])
def test_class_when_code_has_unrepresentable_syntax_then_refused_before_write(
    font, code
):
    backend = font._model._backend
    with pytest.raises(UnsupportedCapability):
        font.classes.append(GSClass("uc", code))
    assert backend.class_data.get("font", ()) == ()
    font.classes.append(GSClass("lc", "a b"))
    with pytest.raises(UnsupportedCapability):
        font.classes["lc"].code = code
    assert font.classes["lc"].code == "a b"


def test_class_when_removed_then_write_stale_not_recreated(font):
    font.classes.append(GSClass("uc", "A"))
    held = font.classes["uc"]
    font.classes.remove(held)
    with pytest.raises(StaleNativeObject):
        held.code = "A B"
    assert list(font.classes) == []


def test_class_when_renamed_then_same_proxy_follows(font):
    font.classes.append(GSClass("uc", "A"))
    held = font.classes["uc"]
    held.name = "caps"
    assert font.classes["caps"] is held
    held.code = "A B"
    assert font.classes["caps"].code == "A B"


# P1 axes -------------------------------------------------------------------------


def test_axis_when_attached_tag_or_name_collides_then_refused(font):
    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    font.axes.append(GSAxis(name="Width", axisTag="wdth"))
    width = font.axes[1]
    with pytest.raises(UnsupportedCapability):
        width.axisTag = "wght"
    with pytest.raises(UnsupportedCapability):
        width.name = "Weight"
    assert [(a.name, a.axisTag) for a in font.axes] == [
        ("Weight", "wght"),
        ("Width", "wdth"),
    ]


def test_axis_when_tag_changed_then_same_proxy_and_identity(font):
    font.axes.append(GSAxis(name="Width", axisTag="wdth"))
    axis = font.axes[0]
    ident = axis.id
    axis.axisTag = "WDTH"
    assert font.axes[0] is axis and axis.id == ident and axis.axisTag == "WDTH"
    font.axes.remove(axis)
    with pytest.raises(StaleNativeObject):
        axis.hidden = True


# P2 hints ------------------------------------------------------------------------


def _hint(position, width=50):
    hint = GSHint()
    hint.position, hint.width = position, width
    return hint


def test_hint_when_name_only_edit_then_only_name_patched(font):
    layer = font.glyphs["A"].layers[0]
    layer.hints.append(_hint(100))
    backend = font._model._backend
    calls = []
    original = backend.set_hint
    backend.set_hint = lambda layer_id, index, changes: (
        calls.append(dict(changes)),
        original(layer_id, index, changes),
    )
    layer.hints[0].name = "bar"
    assert calls == [{"name": "bar"}]


def test_hint_when_stem_reoriented_then_allowed_ghost_refused(font):
    layer = font.glyphs["A"].layers[0]
    layer.hints.append(_hint(100))
    ghost = GSHint()
    ghost.type, ghost.position = BOTTOMGHOST, 0
    layer.hints.append(ghost)
    layer.hints[0].horizontal = False
    assert layer.hints[0].horizontal is False
    with pytest.raises(UnsupportedCapability):
        layer.hints[1].horizontal = False
    assert layer.hints[1].type == BOTTOMGHOST and TOPGHOST != BOTTOMGHOST


def test_hint_when_earlier_hint_removed_then_survivor_remapped_removed_stale(font):
    layer = font.glyphs["A"].layers[0]
    layer.hints.append(_hint(100))
    layer.hints.append(_hint(100))
    first, second = layer.hints[0], layer.hints[1]
    layer.hints.remove(first)
    with pytest.raises(StaleNativeObject):
        first.name = "x"
    second.name = "kept"
    assert [h.name for h in layer.hints] == ["kept"] and layer.hints[0] is second


# Re-review RR-r020 -------------------------------------------------------------


def test_instance_when_replaced_outside_glyport_same_length_then_held_proxy_stale(font):
    from dataclasses import replace

    _instances(font, "Bold")
    held = font.instances[0]
    backend = font._model._backend
    (old,) = backend.instance_data["font"]
    backend.instance_data["font"] = (replace(old, name="Other"),)
    with pytest.raises(StaleNativeObject):
        held.name = "WRONG TARGET"
    assert font.instances[0].name == "Other" and font.instances[0] is not held


def test_hint_when_replaced_outside_glyport_same_length_then_held_proxy_stale(font):
    from fontlab_glyport.model.backend import HintInfo

    layer = font.glyphs["A"].layers[0]
    layer.hints.append(_hint(100))
    held = layer.hints[0]
    font._model._backend.hint_data[layer.id] = (HintInfo(True, 300, 60, "other"),)
    with pytest.raises(StaleNativeObject):
        held.name = "WRONG TARGET"
    assert layer.hints[0].name == "other"


def test_named_records_when_recreated_outside_glyport_then_held_proxy_stale(font):
    from fontlab_glyport.model.backend import ClassInfo

    font.features.append(GSFeature("liga", "x;"))
    font.classes.append(GSClass("uc", "A"))
    feature, cls = font.features["liga"], font.classes["uc"]
    backend = font._model._backend
    backend.feature_data["font"] = (
        "",
        (("liga", "feature liga {\nother;\n} liga;\n"),),
    )
    backend.class_data["font"] = (ClassInfo("uc", ("B",)),)
    with pytest.raises(StaleNativeObject):
        feature.code = "y;"
    with pytest.raises(StaleNativeObject):
        cls.code = "C"
    assert font.features["liga"].code == "other;" and font.classes["uc"].code == "B"


def test_glyport_edits_and_axis_changes_keep_held_proxies(font):
    _instances(font, "Bold")
    held = font.instances[0]
    font.axes.append(GSAxis(name="Grade", axisTag="GRAD"))
    held.name = "Black"
    font.axes.remove(font.axes["Grade"])
    held.exports = False
    assert (font.instances[0] is held, held.name, held.exports) == (
        True,
        "Black",
        False,
    )


def test_wrappers_when_records_removed_then_retired(font):
    import gc

    font.axes.append(GSAxis(name="Weight", axisTag="wght"))
    for _ in range(50):
        instance = GSInstance()
        font.instances.append(instance)
        font.instances.remove(instance)
        font.features.append(GSFeature("liga", "x;"))
        font.features.remove(font.features["liga"])
    del instance
    gc.collect()
    assert len(font._records) <= 2


def test_prefix_when_appended_empty_then_bound_and_code_settable(font):
    from fontlab_glyport.model.proxies import GSFeaturePrefix

    prefix = GSFeaturePrefix("Prefix", "")
    font.featurePrefixes.append(prefix)
    assert list(font.featurePrefixes) == [prefix] and prefix.code == ""
    prefix.code = "languagesystem DFLT dflt;"
    assert font._model._backend.feature_data["font"][0] == "languagesystem DFLT dflt;"
    assert font.featurePrefixes[0] is prefix


def test_feature_when_several_blocks_of_one_tag_then_verbatim_round_trip(font):
    backend = font._model._backend
    text = "feature liga {sub a by b;} liga;\nfeature liga {sub c by d;} liga;\n"
    backend.feature_data["font"] = ("", (("liga", text),))
    liga = font.features["liga"]
    assert liga.code == text
    liga.code = liga.code
    assert backend.feature_data["font"][1] == (("liga", text),)
    with pytest.raises(UnsupportedCapability):
        liga.code = "sub e by f;"


def test_named_records_when_code_edited_then_native_order_kept(font):
    font.classes.append(GSClass("uc", "A"))
    font.classes.append(GSClass("lc", "a"))
    font.classes["uc"].code = "A B"
    assert [c.name for c in font.classes] == ["uc", "lc"]


# Round-2 re-review RR2-r020 ------------------------------------------------------


def test_named_records_when_edited_by_index_then_each_record_once_in_order(font):
    font.features.append(GSFeature("liga", "a;"))
    font.features.append(GSFeature("kern", "b;"))
    font.classes.append(GSClass("uc", "A"))
    font.classes.append(GSClass("lc", "a"))
    for i in range(2):
        font.features[i].code = font.features[i].code + " # edited"
        font.classes[i].code = font.classes[i].code + " X"
    assert [(f.name, f.code) for f in font.features] == [
        ("liga", "a; # edited"),
        ("kern", "b; # edited"),
    ]
    assert [(c.name, c.code) for c in font.classes] == [("uc", "A X"), ("lc", "a X")]
    font.classes["uc"].name = "caps"
    assert [c.name for c in font.classes] == ["caps", "lc"]
    assert list(font._names["class"]) == ["caps", "lc"]


@pytest.mark.parametrize(
    "text",
    [
        "feature liga {\n  # Example: feature liga { sub x by y; } liga;\n  sub f i by f_i;\n} liga;\n",
        'feature liga {\n  sub f i by f_i; # "feature kern {"\n} liga;\n',
    ],
)
def test_feature_when_comment_mentions_a_block_then_still_one_block(font, text):
    backend = font._model._backend
    backend.feature_data["font"] = ("", (("liga", text),))
    liga = font.features["liga"]
    body = liga.code
    assert not body.startswith("feature") and "sub f i by f_i;" in body
    liga.code = body
    assert backend.feature_data["font"][1] == (("liga", text),)
    liga.code = "sub f l by f_l;"
    assert (
        backend.feature_data["font"][1][0][1]
        == "feature liga {\nsub f l by f_l;\n} liga;\n"
    )


# Documented limitation (RR2-r020 ruling): FontLab hands out instance copies, hint
# rows and feature/class text with no native identity, so a record removed and
# re-added outside glyport with byte-identical content is the same record to
# glyport; a held proxy then writes into it (equivalent content).


def test_identical_content_external_replacement_is_indistinguishable(font):
    from dataclasses import replace

    _instances(font, "Bold")
    held = font.instances[0]
    backend = font._model._backend
    (old,) = backend.instance_data["font"]
    backend.instance_data["font"] = (replace(old),)  # same content, same backend id
    held.name = "Black"
    assert font.instances[0].name == "Black"
    font.features.append(GSFeature("liga", "x;"))
    feature = font.features["liga"]
    backend.feature_data["font"] = backend.feature_data[
        "font"
    ]  # delete + recreate, same text
    feature.code = "y;"
    assert font.features["liga"].code == "y;"


# Round-3 re-review RR3-r020 ------------------------------------------------------


def test_instance_when_backend_assigns_new_id_to_identical_content_then_stale(font):
    from dataclasses import replace

    _instances(font, "Bold")
    held = font.instances[0]
    backend = font._model._backend
    (old,) = backend.instance_data["font"]
    backend.instance_data["font"] = (replace(old, id="recreated"),)
    with pytest.raises(StaleNativeObject):
        held.name = "WRONG TARGET"
    assert font.instances[0].name == "Bold"


def test_instance_when_earlier_removed_by_glyport_then_survivor_kept_despite_id_shift(
    font,
):
    from dataclasses import replace

    _instances(font, "Light", "Bold")
    bold = font.instances[1]
    backend = font._model._backend
    original = backend.remove_instance

    def remove_positional(font_id, index):
        # FontLab's instance ids are positional: removal shifts the survivors'.
        original(font_id, index)
        backend.instance_data[font_id] = tuple(
            replace(i, id=f"{font_id}-instance-{n}")
            for n, i in enumerate(backend.instance_data[font_id])
        )

    backend.remove_instance = remove_positional
    font.instances.remove(font.instances[0])
    bold.name = "Black"
    assert [i.name for i in font.instances] == ["Black"]


@pytest.mark.parametrize("newline", ["\r", "\r\n", "\n"])
def test_feature_when_comment_ends_at_any_newline_then_blocks_counted(font, newline):
    backend = font._model._backend
    text = newline.join(
        [
            "feature liga {# first",
            "sub a by b;} liga;",
            "feature liga {sub c by d;} liga;",
            "",
        ]
    )
    backend.feature_data["font"] = ("", (("liga", text),))
    liga = font.features["liga"]
    assert liga.code == text
    with pytest.raises(UnsupportedCapability):
        liga.code = "sub e by f;"
    assert backend.feature_data["font"][1] == (("liga", text),)
