# this_file: tests/test_custom_parameter_objects.py
"""Parameter object contract from the retained Glyphs setter audit."""

import pytest

from fontlab_glyport.model import GSCustomParameter


def test_parameter_when_properties_change_then_retains_values_and_active_flag():
    parameter = GSCustomParameter("Filter", ["first"])
    parameter.active = False
    parameter.value = {"nested": [1, 2]}
    parameter.name = "Other Filter"
    assert (parameter.name, parameter.value, parameter.active) == (
        "Other Filter",
        {"nested": [1, 2]},
        False,
    ), "Mutating name/value must preserve the inactive state"
    parameter.active = True
    assert parameter.active is True


@pytest.mark.parametrize(
    "source, expected",
    [
        ("‘Filter’", "'Filter'"),
        ("“Filter”", '"Filter"'),
        (
            " Use Arabic Presentation Form Unicodes ",
            " Use Arabic Presentation Form Unicodes ",
        ),
        ("UseArabicPresentationFormUnicodes", "UseArabicPresentationFormUnicodes"),
    ],
)
def test_parameter_when_name_assigned_then_only_normalizes_four_curly_quotes(
    source, expected
):
    parameter = GSCustomParameter(source, 1)
    assert parameter.name == expected, (
        "Constructor must use the same native name normalization"
    )
    parameter.name = source
    assert parameter.name == expected, (
        "Name mutation must preserve spaces and exact case"
    )


def test_parameter_when_value_is_none_then_object_keeps_none():
    parameter = GSCustomParameter("Filter", "x")
    parameter.value = None
    assert parameter.value is None, "Object mutation is distinct from name-key deletion"
