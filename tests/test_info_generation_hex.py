# this_file: tests/test_info_generation_hex.py
"""Retained helper's bytewise hex formatting, independently checked."""

import pytest

from fontlab_glyport.model.info_hex import hex_u32


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0000"),
        (1, "0001"),
        (15, "000F"),
        (255, "00FF"),
        (256, "0100"),
        (0xFFFE, "FFFE"),
        (0xFFFF, "FFFF"),
        (0x10000, "10000"),
        (0x10FFFF, "10FFFF"),
        (0xFFFFFFFE, "FFFFFFFE"),
        (0xFFFFFFFF, "FFFFFFFF"),
        (0x100000000, "FFFFFFFF"),
        (0xFFFFFFFFFFFFFFFF, "FFFFFFFF"),
    ],
)
def test_unsigned_formatter_retains_minimum_four_uppercase_digits_and_saturation(
    value, expected
):
    assert hex_u32(value) == expected


def test_all_bmp_values_and_wide_byte_vectors_match_independent_byte_oracle():
    samples = list(range(0x10000)) + [value * 0x01010101 for value in range(256)]
    samples += [value << shift for shift in range(0, 64, 8) for value in range(256)]
    for value in samples:
        bounded = min(value, 4294967295)
        expected = bounded.to_bytes(4, "big").hex().upper().lstrip("0").rjust(4, "0")
        assert hex_u32(value) == expected, f"unsigned source scalar {value}"


@pytest.mark.parametrize("value", [None, "0041", 1.0, True, object()])
def test_unqualified_python_input_is_not_coerced_into_native_bridge_success(value):
    with pytest.raises(TypeError):
        hex_u32(value)


@pytest.mark.parametrize("value", [-1, 1 << 64])
def test_unqualified_unsigned_word_bounds_are_explicit(value):
    with pytest.raises(ValueError):
        hex_u32(value)
