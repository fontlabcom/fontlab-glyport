# this_file: tests/test_custom_info_filesystem.py
"""Owned macOS filesystem discovery; no Foundation or application requests."""

import ctypes
import errno
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import custom_info_filesystem as fs


def listed(path):
    with fs.directory_entries(str(path)) as entries:
        return None if entries is None else list(entries)


def set_owned_flags(path, flags):
    """SDK sys/xattr.h setxattr writes only task-owned scratch fixtures."""
    data = bytearray(32)
    data[8:10] = flags.to_bytes(2, "big")
    setxattr = ctypes.CDLL(None, use_errno=True).setxattr
    setxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    setxattr.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(bytes(data))
    result = setxattr(fs.os.fsencode(path), b"com.apple.FinderInfo", buffer, 32, 0, 0)
    assert result == 0, f"Owned FinderInfo write failed: errno{ctypes.get_errno()}"


def test_absent_file_and_empty_directory_keep_distinct_enumerator_results(tmp_path):
    assert listed(tmp_path / "missing") is None
    assert listed(tmp_path) == []
    file = tmp_path / "ordinary.xml"
    file.touch()
    assert listed(file) == [], "The SDK documents an empty enumerator for a file"
    assert listed(file / "Info") is None


def test_shallow_enumeration_skips_dot_files_and_finder_invisible_not_directories(
    tmp_path,
):
    (tmp_path / "Visible").mkdir()
    (tmp_path / "Visible" / "inside").touch()
    (tmp_path / ".hidden").touch()
    invisible = tmp_path / "Invisible"
    invisible.touch()
    set_owned_flags(invisible, 0x4000)
    assert fs._finder_flags(str(invisible)) == 0x4000
    assert listed(tmp_path) == [str(tmp_path / "Visible")]


def test_scandir_provider_order_is_preserved_and_closed_on_resolution_error(
    monkeypatch,
):
    class Entry:
        def __init__(self, name):
            self.name, self.path = name, "/owned/" + name

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return SimpleNamespace(st_flags=0)

    class Scan:
        closed = False

        def __enter__(self):
            return iter([Entry("z"), Entry("a")])

        def __exit__(self, *args):
            self.closed = True

    scan = Scan()
    monkeypatch.setattr(fs.os, "scandir", lambda path: scan)
    monkeypatch.setattr(fs, "_finder_flags", lambda *args, **kwargs: 0)
    with pytest.raises(RuntimeError, match="owned resolve"), fs.directory_entries("/owned") as entries:
        assert list(entries) == ["/owned/z", "/owned/a"]
        raise RuntimeError("owned resolve")
    assert scan.closed is True


def test_symbolic_link_file_resolves_to_target_and_directory_link_is_unqualified(
    tmp_path,
):
    target = tmp_path / "target.txt"
    target.touch()
    link = tmp_path / "GlyphData.xml"
    link.symlink_to(target)
    assert fs.resolve_symlinks(str(link)) == str(target)
    directory_link = tmp_path / "folder-link"
    directory_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(UnsupportedCapability) as caught:
        listed(directory_link)
    assert caught.value.capability == "GSGlyphsInfo.discovery.directorySymlink"


def test_finder_alias_flag_refuses_without_reading_file_bytes(tmp_path, monkeypatch):
    alias = tmp_path / "GlyphData_alias.xml"
    alias.write_bytes(b"owned alias-shaped fixture, not a qualified native alias")
    set_owned_flags(alias, 0x8000)
    monkeypatch.setattr(
        Path, "read_bytes", lambda self: pytest.fail("Alias bytes must not be parsed")
    )
    with pytest.raises(UnsupportedCapability) as caught:
        fs.resolve_symlinks(str(alias))
    assert caught.value.capability == "GSGlyphsInfo.discovery.alias"


@pytest.mark.parametrize("payload", [b"", b"x", b"x" * 31, b"x" * 33])
def test_malformed_finder_info_is_not_a_false_visible_or_nonalias_fact(
    payload, monkeypatch
):
    monkeypatch.setattr(fs, "_read_finder_info", lambda *args, **kwargs: payload)
    with pytest.raises(UnsupportedCapability) as caught:
        fs._finder_flags("/owned")
    assert caught.value.capability == "GSGlyphsInfo.discovery.finderInfo"


@pytest.mark.parametrize(
    "code", sorted({errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)})
)
def test_absent_finder_info_is_known_zero_flags(code, monkeypatch):
    def absent(*args, **kwargs):
        raise OSError(code, "owned missing xattr")

    monkeypatch.setattr(fs, "_read_finder_info", absent)
    assert fs._finder_flags("/owned") == 0


def test_finder_attribute_errors_refuse_instead_of_guessing_flags(monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("owned denied xattr")

    monkeypatch.setattr(fs, "_read_finder_info", denied)
    with pytest.raises(UnsupportedCapability) as caught:
        fs._finder_flags("/owned")
    assert caught.value.capability == "GSGlyphsInfo.discovery.finderInfo"


def test_enumeration_permission_error_is_not_missing_success(tmp_path, monkeypatch):
    def denied(path):
        raise PermissionError("owned denied directory")

    monkeypatch.setattr(fs.os, "scandir", denied)
    with pytest.raises(UnsupportedCapability) as caught:
        listed(tmp_path)
    assert caught.value.capability == "GSGlyphsInfo.discovery.enumeration"


def test_broken_symlink_and_loop_are_explicit_unqualified_resolution(tmp_path):
    link = tmp_path / "GlyphData.xml"
    link.symlink_to(tmp_path / "missing")
    with pytest.raises(UnsupportedCapability) as caught:
        fs.resolve_symlinks(str(link))
    assert caught.value.capability == "GSGlyphsInfo.discovery.resolution"
    link.unlink()
    link.symlink_to(link)
    with pytest.raises(UnsupportedCapability) as caught:
        fs.resolve_symlinks(str(link))
    assert caught.value.capability == "GSGlyphsInfo.discovery.resolution"


def test_non_macos_provider_refuses_before_enumeration_or_attributes(monkeypatch):
    monkeypatch.setattr(fs.sys, "platform", "win32")
    monkeypatch.setattr(fs.os, "scandir", lambda path: pytest.fail("No enumeration"))
    with pytest.raises(UnsupportedCapability) as caught:
        listed(Path("/owned"))
    assert caught.value.capability == "GSGlyphsInfo.discovery.filesystem.platform"
    with pytest.raises(UnsupportedCapability):
        fs.resolve_symlinks("/owned")


def test_bsd_hidden_flag_is_filtered_without_a_finder_invisible_attribute(tmp_path):
    hidden = tmp_path / "GlyphData_hidden.xml"
    hidden.touch()
    fs.os.chflags(hidden, stat.UF_HIDDEN)
    assert hidden.stat().st_flags & stat.UF_HIDDEN
    assert fs._finder_flags(str(hidden)) == 0, "BSD and Finder flags are distinct"
    assert listed(tmp_path) == []


def test_failed_stat_is_not_a_visible_entry_and_closes_owned_scan(monkeypatch):
    class Entry:
        name, path = "GlyphData.xml", "/owned/GlyphData.xml"

        def stat(self, **kwargs):
            raise PermissionError("owned stat failure")

    class Scan:
        closed = False

        def __enter__(self):
            return iter([Entry()])

        def __exit__(self, *args):
            self.closed = True

    scan = Scan()
    monkeypatch.setattr(fs.os, "scandir", lambda path: scan)
    monkeypatch.setattr(fs, "_finder_flags", lambda *args, **kwargs: 0)
    with pytest.raises(UnsupportedCapability) as caught:
        listed(Path("/owned"))
    assert caught.value.capability == "GSGlyphsInfo.discovery.stat"
    assert scan.closed is True
