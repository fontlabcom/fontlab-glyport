# this_file: tests/test_unicode_casing.py
"""Public scalar casing and independently measured Foundation whole-name context."""

import pytest

from fontlab_glyport.model import unicode_casing as casing


@pytest.mark.parametrize(
    "code,expected",
    [
        (0, (0,)),
        (0x61, (0x41,)),
        (0xDF, (0x53, 0x53)),
        (0xFB03, (0x46, 0x46, 0x49)),
        (0x10428, (0x10400,)),
        (0x1F600, (0x1F600,)),
        (0x0131, (0x49,)),
        (0x1C8A, (0x1C89,)),
        (0x10D70, (0x10D50,)),
    ],
)
def test_uppercase_when_full_scalar_mapping_then_preserves_sequence(code, expected):
    assert casing.uppercase_scalar(code) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", ""),
        ("A", "a"),
        ("ABC", "abc"),
        ("İ", "i\u0307"),
        ("\U00010400", "\U00010428"),
        ("\U00010d50", "\U00010d70"),
        ("A\0B", "a\0b"),
        ("A\ud800B", "a\ud800b"),
    ],
)
def test_lowercase_when_context_free_name_then_uses_full_scalar_mapping(text, expected):
    assert casing.lowercase_text(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Σ", "σ"),
        ("ΟΣ", "ος"),
        ("AΣA", "aσa"),
        ("AΣ.SUFFIX", "aς.suffix"),
        ("A.Σ", "a.σ"),
        ("AΣ_SUFFIX", "aς_suffix"),
        ("'Σ", "'ς"),
        ("\u0345Σ", "\u0345ς"),
        ("AΣ\u0301A", "aσ\u0301a"),
        ("ªΣ", "ªσ"),
        ("AΣª", "aςª"),
        ("ǅΣ", "ǆς"),
        ("ⅠΣ", "ⅰσ"),
        ("AʼΣ", "aʼς"),
        ("\ud801\udc00Σ", "\U00010428ς"),
        ("AΣ\ud801\udc00", "aσ\U00010428"),
        ("\ud800Σ", "\ud800σ"),
        ("AΣ\udfff", "aς\udfff"),
    ],
)
def test_lowercase_when_foundation_context_then_preserves_retained_scan(text, expected):
    assert casing.lowercase_text(text) == expected


@pytest.mark.parametrize(
    "value,error",
    [(True, TypeError), ("0061", TypeError), (-1, ValueError), (0x110000, ValueError)],
)
def test_uppercase_when_invalid_scalar_then_raises(value, error):
    with pytest.raises(error):
        casing.uppercase_scalar(value)


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_casing_when_resource_unavailable_then_explicit_failure(
    monkeypatch, tmp_path, failure
):
    from fontlab_glyport.errors import UnsupportedCapability

    (tmp_path / "data").mkdir()
    if failure == "corrupt":
        (tmp_path / "data/unicode17_casing.json.gz").write_bytes(b"{}")
    casing._data.cache_clear()
    monkeypatch.setattr(casing.resources, "files", lambda package: tmp_path)
    try:
        with pytest.raises(UnsupportedCapability, match="casing data"):
            casing.uppercase_scalar(0x61)
    finally:
        casing._data.cache_clear()
