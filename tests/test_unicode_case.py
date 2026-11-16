# this_file: tests/test_unicode_case.py
"""Public Unicode17 scalar data, checked against independent NSString results."""

import json
import subprocess
import sys

import pytest

from fontlab_glyport.errors import UnsupportedCapability

# Independent macOS27.2 NSString calibration; values are public Unicode facts.
NEWER_CASES = [
    ("1C89", ("1C8A",)),
    ("A7CB", ("0264",)),
    ("A7CC", ("A7CD",)),
    ("A7CE", ("A7CF",)),
    ("A7D2", ("A7D3",)),
    ("A7D4", ("A7D5",)),
    ("A7DA", ("A7DB",)),
    ("A7DC", ("019B",)),
    ("10D50", ("10D70",)),
    ("10D51", ("10D71",)),
    ("10D52", ("10D72",)),
    ("10D53", ("10D73",)),
    ("10D54", ("10D74",)),
    ("10D55", ("10D75",)),
    ("10D56", ("10D76",)),
    ("10D57", ("10D77",)),
    ("10D58", ("10D78",)),
    ("10D59", ("10D79",)),
    ("10D5A", ("10D7A",)),
    ("10D5B", ("10D7B",)),
    ("10D5C", ("10D7C",)),
    ("10D5D", ("10D7D",)),
    ("10D5E", ("10D7E",)),
    ("10D5F", ("10D7F",)),
    ("10D60", ("10D80",)),
    ("10D61", ("10D81",)),
    ("10D62", ("10D82",)),
    ("10D63", ("10D83",)),
    ("10D64", ("10D84",)),
    ("10D65", ("10D85",)),
    ("16EA0", ("16EBB",)),
    ("16EA1", ("16EBC",)),
    ("16EA2", ("16EBD",)),
    ("16EA3", ("16EBE",)),
    ("16EA4", ("16EBF",)),
    ("16EA5", ("16EC0",)),
    ("16EA6", ("16EC1",)),
    ("16EA7", ("16EC2",)),
    ("16EA8", ("16EC3",)),
    ("16EA9", ("16EC4",)),
    ("16EAA", ("16EC5",)),
    ("16EAB", ("16EC6",)),
    ("16EAC", ("16EC7",)),
    ("16EAD", ("16EC8",)),
    ("16EAE", ("16EC9",)),
    ("16EAF", ("16ECA",)),
    ("16EB0", ("16ECB",)),
    ("16EB1", ("16ECC",)),
    ("16EB2", ("16ECD",)),
    ("16EB3", ("16ECE",)),
    ("16EB4", ("16ECF",)),
    ("16EB5", ("16ED0",)),
    ("16EB6", ("16ED1",)),
    ("16EB7", ("16ED2",)),
    ("16EB8", ("16ED3",)),
]


@pytest.mark.parametrize("code, expected", NEWER_CASES)
def test_lowercase_scalar_when_newer_than_python14_then_matches_calibrated_data(
    code, expected
):
    from fontlab_glyport.model.unicode_case import lowercase_scalar

    assert lowercase_scalar(int(code, 16)) == tuple(
        int(value, 16) for value in expected
    ), "Bundled data must preserve all55 independently observed newer-case differences"


@pytest.mark.parametrize(
    "code, expected",
    [
        (0, (0,)),
        (0x0041, (0x0061,)),
        (0x0061, (0x0061,)),
        (0x0130, (0x0069, 0x0307)),
        (0x0391, (0x03B1,)),
        (0x1F600, (0x1F600,)),
        (0x10FFFF, (0x10FFFF,)),
    ],
)
def test_lowercase_scalar_when_control_or_identity_then_full_scalar_sequence(
    code, expected
):
    from fontlab_glyport.model.unicode_case import lowercase_scalar

    assert lowercase_scalar(code) == expected, (
        "Scalar mapping must retain identity defaults and full expansions"
    )


@pytest.mark.parametrize(
    "value, error",
    [
        (-1, ValueError),
        (0x110000, ValueError),
        (True, TypeError),
        ("0041", TypeError),
        (1.5, TypeError),
        (None, TypeError),
    ],
)
def test_lowercase_scalar_when_outside_contract_then_refuses(value, error):
    from fontlab_glyport.model.unicode_case import lowercase_scalar

    with pytest.raises(error):
        lowercase_scalar(value)


@pytest.mark.parametrize(
    "mode",
    [
        "missing",
        "invalid_json",
        "wrong_version",
        "no_mapping",
        "empty_mapping",
        "bad_key",
        "bad_value",
        "empty_value",
        "out_of_range",
    ],
)
def test_lowercase_resource_when_missing_or_malformed_then_explicit_refusal(
    tmp_path, monkeypatch, mode
):
    from fontlab_glyport.model import unicode_case

    original = unicode_case.resources.files
    table = json.loads(
        original("fontlab_glyport")
        .joinpath("data", "unicode17_lowercase.json")
        .read_text("utf-8")
    )
    destination = tmp_path / "data" / "unicode17_lowercase.json"
    destination.parent.mkdir()
    if mode == "wrong_version":
        table["unicode_version"] = "99.0.0"
    elif mode == "no_mapping":
        del table["lowercase"]
    elif mode == "empty_mapping":
        table["lowercase"] = {}
    elif mode == "bad_key":
        table["lowercase"]["notHex"] = ["0061"]
    elif mode == "bad_value":
        table["lowercase"]["0041"] = "0061"
    elif mode == "empty_value":
        table["lowercase"]["0041"] = []
    elif mode == "out_of_range":
        table["lowercase"]["0041"] = ["110000"]
    if mode != "missing":
        destination.write_text("{" if mode == "invalid_json" else json.dumps(table))
    monkeypatch.setattr(unicode_case.resources, "files", lambda package: tmp_path)
    unicode_case._mapping.cache_clear()
    try:
        with pytest.raises(UnsupportedCapability) as caught:
            unicode_case.lowercase_scalar(0x0041)
        assert caught.value.capability == "GSGlyph.metadata.lowercaseData", (
            "Missing/malformed package resources must identify the exact read boundary"
        )
    finally:
        unicode_case._mapping.cache_clear()


def test_lowercase_resource_when_module_imported_then_no_read_before_use():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            (
                "from importlib import resources; "
                "resources.files=lambda *a,**k: (_ for _ in ()).throw(AssertionError('eager read')); "
                "import fontlab_glyport.model.unicode_case"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, "Import must remain lazy: " + result.stderr


def test_lowercase_resource_when_repeated_calls_then_one_packaged_read(monkeypatch):
    from fontlab_glyport.model import unicode_case

    original = unicode_case.resources.files
    reads = []

    def files(package):
        reads.append(package)
        return original(package)

    unicode_case._mapping.cache_clear()
    monkeypatch.setattr(unicode_case.resources, "files", files)
    try:
        assert unicode_case.lowercase_scalar(0x0041) == (0x0061,)
        assert unicode_case.lowercase_scalar(0) == (0,)
        assert reads == ["fontlab_glyport"], (
            "The packaged map should be read lazily once"
        )
    finally:
        unicode_case._mapping.cache_clear()
