# this_file: tests/test_receipt_privacy.py
"""Public validation catches private paths without destroying relative provenance."""

import pytest

from fontlab_glyport import validate_receipt


@pytest.mark.parametrize(
    "private",
    [
        "/Users/person/private.py",
        "/home/person/private.py",
        "/tmp/private.py",
        "~/private.py",
        "~person/private.py",
        "C:\\Users\\person\\private.py",
        "C:/Users/person/private.py",
        "\\\\server\\share\\private.py",
        "file:///Users/person/private.py",
        "$HOME/private.py",
        "${HOME}/private.py",
        "%USERPROFILE%\\private.py",
        "Failed at /Users/person/private.py:12",
        "path:/tmp/private.py",
        "path=[/tmp/private.py]",
        "~",
        "~person",
        "//server/share/private.py",
    ],
)
def test_public_when_private_path_anywhere_then_rejects(receipt, private):
    for section, key in (
        ("source", "repository"),
        ("diagnostics", "message"),
        ("artifacts", "path"),
    ):
        data = receipt.to_dict()
        record = data[section][0] if isinstance(data[section], list) else data[section]
        record[key] = private
        assert any("public" in error for error in validate_receipt(data)), (
            section,
            key,
            private,
        )
        assert validate_receipt(data, public=False) == []


@pytest.mark.parametrize(
    "private",
    [
        "/root.py",
        "~/root.py",
        "../root.py",
        "a/../../root.py",
        "C:\\root.py",
        "C:root.py",
        "..\\root.py",
    ],
)
def test_relative_provenance_when_absolute_or_escaping_then_always_rejects(
    receipt, private
):
    for key in ("relative_path", "dirty_files"):
        data = receipt.to_dict()
        data["source"][key] = {private: "a" * 64} if key == "dirty_files" else private
        assert validate_receipt(data, public=False), (
            "source identity must remain relative"
        )


def test_public_when_repository_url_and_relative_paths_then_preserves_provenance(
    receipt,
):
    data = receipt.to_dict()
    data["source"]["repository"] = "https://example.org/project/repository"
    assert validate_receipt(data) == []
    assert data["source"]["relative_path"] == "src/café.py"


def test_public_when_dirty_file_key_private_then_rejects(receipt):
    data = receipt.to_dict()
    data["source"]["dirty_files"] = {"/home/person/private.py": "a" * 64}
    assert validate_receipt(data)


def test_public_when_message_contains_division_then_accepts_ordinary_prose(receipt):
    data = receipt.to_dict()
    data["diagnostics"][0]["message"] = "Check x / y and x // y; pass/fail evidence"
    assert validate_receipt(data) == [], (
        "operators must not be mistaken for private paths"
    )
