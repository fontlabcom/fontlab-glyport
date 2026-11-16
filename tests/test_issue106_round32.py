# this_file: tests/test_issue106_round32.py
"""Keep the Glyphs Python wrapper's None distinct from native kerning sentinels."""

import math

import pytest

from fontlab_glyport.model import Model
from fontlab_glyport.model.backend import KerningClassInfo
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def test_missing_explicit_pair_is_none_even_when_group_pair_exists(font):
    master = font.masters[0].id
    glyph = font.glyphs["A"]
    font._model._backend.kerning_class_data[font._id] = (
        KerningClassInfo("A", ("A",), left=True, right=True),
    )
    font.setKerningForPair(master, "@MMK_L_A", "@MMK_R_A", -70)
    assert font.kerningForPair(master, "A", "A") is None
    layer = glyph.layers[0]
    assert layer.nextKerningForLayer_direction_(layer, 0) == -70
    font.setKerningForPair(master, "A", "A", 0)
    assert font.kerningForPair(master, "A", "A") == 0
    assert layer.nextKerningForLayer_direction_(layer, 0) == 0


@pytest.mark.parametrize("value", [1_000_001, float("inf")])
def test_python_wrapper_converts_large_native_values_to_none(font, value):
    master = font.masters[0].id
    font.setKerningForPair(master, "A", "A", value)
    assert font.kerningForPair(master, "A", "A") is None
    layer = font.glyphs["A"].layers[0]
    assert layer.nextKerningForLayer_direction_(layer, 0) == value


def test_missing_layer_pair_returns_native_double_two_to_63(font):
    layer = font.glyphs["A"].layers[0]
    value = layer.nextKerningForLayer_direction_(layer, 0)
    assert type(value) is float
    assert value == float(2**63)
    assert layer.rightKerningForLayer_(layer) == value


@pytest.mark.parametrize("value", [-75, 0, 1_000_000, float("-inf"), float("nan")])
def test_other_stored_values_survive_python_and_native_read(font, value):
    master = font.masters[0].id
    font.setKerningForPair(master, "A", "A", value)
    layer = font.glyphs["A"].layers[0]
    results = [
        font.kerningForPair(master, "A", "A"),
        layer.nextKerningForLayer_direction_(layer, 0),
    ]
    if math.isnan(value):
        assert all(math.isnan(item) for item in results)
    else:
        assert results == [value, value]
