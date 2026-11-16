# this_file: tests/test_issue106_round11_runtime.py
"""Version guards and per-script working directories without a host."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from ui_doubles import make_qt

from fontlab_glyport import run_script
from fontlab_glyport.entrypoints import ExecutionHost
from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp.fontlab_session import FontLabSession
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.profile_versions import PROFILE_VERSIONS
from fontlab_glyport.profiles import select_profile
from fontlab_glyport.receipt import ReceiptEnvironment


def script_host():
    def adapters(context, font):
        session = FontLabSession(
            context,
            version=PROFILE_VERSIONS[context.profile],
            packages=[],
            qt=make_qt(),
            fontlab=SimpleNamespace(MainWindow=lambda: None),
            defaults={},
        )
        session.backend = FakeBackend()
        session.model = Model(session.backend)
        return session.adapters()

    return ExecutionHost(
        lambda operation: operation(),
        ReceiptEnvironment("fixture", "1", "3.11", "5.15", "test", "test"),
        adapter_factory=adapters,
    )


@pytest.mark.parametrize(
    "source",
    [
        "minimumVersion = 4\nif Glyphs.versionNumber < minimumVersion: raise SystemExit(1)\n",
        "if Glyphs.versionNumber < 4: raise SystemExit(1)\n",
        "if 4 > Glyphs.versionNumber: raise SystemExit(1)\n",
    ],
)
def test_f48_version_guards_select_glyphs4_and_default_launcher_finishes(
    tmp_path, source
):
    assert select_profile(sources={"main.py": source.encode()}).profile == "glyphs4"
    path = tmp_path / "main.py"
    path.write_text(source + "finished = True\n")
    handle = run_script(path, host=script_host())
    try:
        assert handle.context.globals["finished"] is True
        assert handle.receipt.adapter.profile == "glyphs4"
    finally:
        handle.close()


@pytest.mark.parametrize(
    "profile,expected",
    [
        ("auto", (4.1, "4.1.1", 4108)),
        ("glyphs2", (2.0, "2.0", 2000)),
        ("glyphs3", (3.0, "3.0", 3000)),
        ("glyphs4", (4.1, "4.1.1", 4108)),
    ],
)
def test_f48_runtime_profile_is_consistent_across_version_attributes(
    tmp_path, profile, expected
):
    path = tmp_path / "main.py"
    path.write_text(
        "seen = (Glyphs.versionNumber, Glyphs.versionString, Glyphs.buildNumber)\n"
    )
    handle = run_script(path, profile=profile, host=script_host())
    try:
        assert handle.context.globals["seen"] == expected
        assert handle.receipt.adapter.profile == f"glyphs{int(expected[0])}"
    finally:
        handle.close()


@pytest.mark.parametrize("major,number", [(2, 2.0), (3, 3.0), (4, 4.1)])
def test_f48_rejection_guard_selects_its_supported_major(major, number):
    source = f"required = {number}\nif Glyphs.versionNumber != required: raise SystemExit(1)\n"
    assert (
        select_profile(sources={"main.py": source.encode()}).profile == f"glyphs{major}"
    )


def test_f48_impossible_and_conflicting_guards_need_explicit_override(tmp_path):
    path = tmp_path / "future.py"
    path.write_text("if Glyphs.versionNumber < 5: raise SystemExit(1)\n")
    with pytest.raises(UnsupportedCapability) as caught:
        run_script(path, host=script_host())
    assert caught.value.capability == "execution:profile"
    result = select_profile(
        metadata={"GlyphsVersion": "3"},
        sources={"main.py": b"if Glyphs.versionNumber < 4: raise SystemExit(1)\n"},
    )
    assert result.profile == "auto"


@pytest.mark.parametrize(
    "ending", ["", "raise ValueError('script failure')\n", "raise SystemExit(7)\n"]
)
def test_f49_script_directory_is_active_and_caller_directory_restored(
    tmp_path, monkeypatch, ending
):
    caller, scripts = tmp_path / "caller", tmp_path / "scripts' folder"
    caller.mkdir()
    scripts.mkdir()
    (scripts / "data.txt").write_text("local resource")
    path = scripts / "main.py"
    path.write_text(
        "from pathlib import Path\nseen = (Path.cwd(), Path('./data.txt').read_text())\n"
        + ending
    )
    monkeypatch.chdir(caller)
    context = ExecutionContext(tmp_path, "glyphs4")
    try:
        if "ValueError" in ending:
            with pytest.raises(ValueError, match="script failure"):
                context.run(path)
        else:
            context.run(path)
        assert context.globals["seen"] == (scripts, "local resource")
        assert Path.cwd() == caller
    finally:
        context.close()


def test_f49_launcher_imports_resources_from_script_folder_and_restores_after_script_chdir(
    tmp_path, monkeypatch
):
    caller, scripts = tmp_path / "caller", tmp_path / "scripts"
    caller.mkdir()
    scripts.mkdir()
    (scripts / "data.txt").write_text("resource")
    (scripts / "helper.py").write_text("value = open('./data.txt').read()\n")
    script = scripts / "main.py"
    script.write_text("import os, helper\nseen = helper.value\nos.chdir('..')\n")
    monkeypatch.chdir(caller)
    handle = run_script(script, host=script_host())
    try:
        assert handle.context.globals["seen"] == "resource"
        assert Path.cwd() == caller
    finally:
        handle.close()
