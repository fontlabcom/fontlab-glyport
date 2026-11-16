# this_file: tests/test_archive_inventory.py
"""Versioned bytecode archives: inventory by magic, choose by magic (R049 versioned-archive)."""

import zipfile

import pytest

from fontlab_glyport.adaptation_entries import (
    PY311_MAGIC,
    archive_inventory,
    choose_archive,
    pyc_version,
)
from fontlab_glyport.errors import DependencyUnavailable

MAGIC = {"3.10": b"\x6f\x0d\x0d\x0a", "3.11": PY311_MAGIC, "3.13": b"\xf3\x0d\x0d\x0a"}


def _zip(path, version, extra=()):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pkg/", "")
        archive.writestr("pkg/__init__.pyc", MAGIC[version] + bytes(12) + b"code")
        archive.writestr("pkg/data.txt", "x")
        for name, data in extra:
            archive.writestr(name, data)
    return path


def test_pyc_version_when_known_magic_then_release_else_none():
    assert pyc_version(PY311_MAGIC + bytes(12)) == "3.11"
    assert pyc_version(b"\x03\xf3\x0d\x0a" + bytes(12)) == "2.7"
    assert pyc_version(b"\x2b\x0e\x0d\x0a") == "3.14"
    assert pyc_version(b"\x00\x00\x0d\x0a") is None and pyc_version(b"") is None


def test_archive_inventory_when_foreign_bytecode_then_every_member_listed(tmp_path):
    archive = _zip(tmp_path / "corretto311.zip", "3.13")  # misleading name
    members = archive_inventory(archive)
    assert [(m.name, m.kind, m.python) for m in members] == [
        ("pkg/", "directory", None),
        ("pkg/__init__.pyc", "bytecode", "3.13"),
        ("pkg/data.txt", "data", None),
    ]
    assert members[1].sha256 and members[1].size == 20


def test_archive_inventory_when_unsafe_member_then_unavailable(tmp_path):
    archive = _zip(tmp_path / "bad.zip", "3.11", [("../escape.py", "x")])
    with pytest.raises(DependencyUnavailable):
        archive_inventory(archive)


def test_choose_archive_when_versions_differ_then_magic_decides_not_name(tmp_path):
    named_311 = _zip(tmp_path / "corretto311.zip", "3.13")
    real_311 = _zip(tmp_path / "corretto310.zip", "3.11")
    _zip(tmp_path / "other.zip", "3.10")
    candidates = sorted(tmp_path.glob("*.zip"))
    assert choose_archive(candidates, "3.11") == real_311
    assert choose_archive([named_311], "3.11") is None
    assert choose_archive(candidates, "3.12") is None
