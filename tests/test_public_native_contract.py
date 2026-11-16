# this_file: tests/test_public_native_contract.py
"""Qualified native save and deliberate close contracts, using call doubles."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import NativeOperationError, UnsupportedCapability
from fontlab_glyport.model import Model
from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def native(monkeypatch, tmp_path):
    calls = []
    package = SimpleNamespace(
        id=1,
        fgId=101,
        fileName=str(tmp_path / "Example.vfj"),
        getProperty=lambda key: False,
        close=lambda save: calls.append(("close", save)),
    )
    workspace = SimpleNamespace(currentPackage=SimpleNamespace(id=99))

    def call(name, **arguments):
        calls.append((name, arguments))
        destination = Path(arguments["path"])
        destination.write_text("native document")
        package.fileName = str(destination)

    backend = FontLabBackend()
    monkeypatch.setattr(backend, "_font_write", lambda *args: package)
    monkeypatch.setattr(backend, "_object", lambda *args: package)
    monkeypatch.setattr(
        backend, "_fontpr", lambda: SimpleNamespace(call=call, Error=RuntimeError)
    )
    monkeypatch.setattr(
        backend,
        "_native",
        lambda: SimpleNamespace(
            flWorkspace=SimpleNamespace(instance=lambda: workspace)
        ),
    )
    monkeypatch.setattr(
        backend, "_invalidate", lambda token: calls.append(("invalidate", token))
    )
    return backend, workspace, package, calls


def test_native_save_when_font_is_not_current_then_qualified_tool_targets_its_id(
    native, monkeypatch, tmp_path
):
    backend, _, package, calls = native
    assert backend.save_font("font") is None
    monkeypatch.chdir(tmp_path)
    assert backend.save_font("font", "Other.vfc") is None
    assert calls == [
        (
            "save_font",
            {"font_id": 101, "path": str(tmp_path / "Example.vfj"), "overwrite": True},
        ),
        (
            "save_font",
            {"font_id": 101, "path": str(tmp_path / "Other.vfc"), "overwrite": True},
        ),
    ]
    assert package.fileName == str(tmp_path / "Other.vfc")


@pytest.mark.parametrize("suffix", [".ufo", ".vfb", ".glyphs", ".txt"])
def test_native_save_when_format_is_not_native_then_refuses_before_call(
    native, tmp_path, suffix
):
    backend, _, _, calls = native
    with pytest.raises(UnsupportedCapability, match="export"):
        backend.save_font("font", str(tmp_path / ("Other" + suffix)))
    assert calls == []


def test_native_save_when_no_path_or_no_file_created_then_raises(
    native, monkeypatch, tmp_path
):
    backend, _, package, calls = native
    package.fileName = ""
    with pytest.raises(ValueError, match="path"):
        backend.save_font("font")
    monkeypatch.setattr(
        backend,
        "_fontpr",
        lambda: SimpleNamespace(Error=RuntimeError, call=lambda *args, **kwargs: None),
    )
    with pytest.raises(NativeOperationError, match="create"):
        backend.save_font("font", str(tmp_path / "Missing.vfj"))
    assert calls == []


def test_native_save_when_make_copy_then_preserves_original_recorded_path(
    native, tmp_path
):
    backend, _, package, _ = native
    original = package.fileName
    backend.save_font("font", str(tmp_path / "Copy.vfj"), make_copy=True)
    assert package.fileName == original
    assert (tmp_path / "Copy.vfj").is_file()


def test_font_save_when_keywords_supplied_then_copy_is_forwarded_and_format_refused(
    native, monkeypatch, tmp_path
):
    backend, _, _, calls = native
    monkeypatch.setattr(backend, "is_valid", lambda token: True)
    from fontlab_glyport.model.proxies import GSFont

    font = GSFont(Model(backend), "font")
    font.save(str(tmp_path / "Copy.vfj"), formatVersion=None, makeCopy=True)
    with pytest.raises(UnsupportedCapability, match="formatVersion"):
        font.save(str(tmp_path / "Other.vfj"), formatVersion=3)
    assert len(calls) == 1


@pytest.mark.parametrize("dirty", [True, None])
def test_native_close_when_dirty_or_unknown_then_requires_explicit_permission(
    native, dirty
):
    backend, _, package, calls = native
    package.getProperty = lambda key: dirty
    with pytest.raises(UnsupportedCapability, match="ignoreChanges=True"):
        backend.close_font("font")
    with pytest.raises(UnsupportedCapability, match="ignoreChanges=True"):
        backend.close_font("font", ignore_changes=False)
    assert calls == []
    backend.close_font("font", ignore_changes=True)
    assert calls == [("close", False), ("invalidate", "font")]


def test_font_close_when_omitted_then_requires_permission_for_unsaved_edits():
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    font = Model(backend).font
    font.glyphs[0].layers[0].width = 600
    with pytest.raises(UnsupportedCapability, match="ignoreChanges=True"):
        font.close()
    with pytest.raises(UnsupportedCapability, match="ignoreChanges=True"):
        font.close(ignoreChanges=False)
    assert backend.is_valid(font.id)
    font.close(ignoreChanges=True)
    assert not backend.list_fonts()


def test_native_clean_close_and_pending_failures_preserve_contract(native):
    backend, _, package, calls = native
    backend._undo_name = "Unfinished"
    for operation in (backend.save_font, backend.close_font):
        with pytest.raises(UnsupportedCapability, match="pending"):
            operation("font")
    backend._undo_name = None
    package.close = lambda save: False
    with pytest.raises(NativeOperationError, match="close"):
        backend.close_font("font", ignore_changes=False)
    assert calls == []


def test_native_close_when_clean_then_checks_the_native_dirty_flag(native):
    backend, _, package, calls = native
    keys = []
    package.getProperty = lambda key: keys.append(key) or False
    backend.close_font("font")
    assert keys == ["__has_history_changes"]
    assert calls == [("close", False), ("invalidate", "font")]


def test_native_copy_when_file_is_not_created_then_still_restores_original_path(
    native, monkeypatch, tmp_path
):
    backend, _, package, _ = native
    original = package.fileName

    def save_without_file(name, **arguments):
        package.fileName = arguments["path"]

    monkeypatch.setattr(
        backend,
        "_fontpr",
        lambda: SimpleNamespace(Error=RuntimeError, call=save_without_file),
    )
    with pytest.raises(NativeOperationError, match="create"):
        backend.save_font("font", str(tmp_path / "Missing.vfj"), make_copy=True)
    assert package.fileName == original
