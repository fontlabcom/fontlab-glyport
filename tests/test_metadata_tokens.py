# this_file: tests/test_metadata_tokens.py
"""Independent retained byte-decoder oracles; no bridge/runtime claim."""

import pytest

from fontlab_glyport.model.metadata_tokens import (
    case_from_string,
    direction_from_string,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        (None, 0),
        ("", 0),
        ("B", 0),
        ("RT", 0),
        ("LTR", 0),
        ("BIDI", 1),
        ("RTL", 2),
        ("VTR", 12),
        ("VTL", 4),
        ("Rxx", 2),
        ("rtl", 0),
        ("V?Rextra", 12),
        ("V\U00010000R", 4),
        ("V\ud800R", 12),
        ("B\U00010000", 1),
        ("\U00010000R", 0),
    ],
)
def test_direction_decoder_uses_first_and_third_utf16_units(text, expected):
    assert direction_from_string(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        (None, 0),
        ("", 0),
        ("upper", 1),
        ("lower", 2),
        ("smallCaps", 3),
        ("minor", 4),
        ("other", 5),
        ("noCase", 0),
        ("Upper", 0),
        ("u", 1),
        ("l", 2),
        ("m", 4),
        ("o", 5),
        ("s", 3),
        ("p", 0),
        ("r", 0),
        ("t", 0),
        ("\U00010000", 0),
    ],
)
def test_case_decoder_uses_retained_first_character_table(text, expected):
    assert case_from_string(text) == expected
