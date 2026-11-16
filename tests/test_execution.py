# this_file: tests/test_execution.py
import os
import sys
from types import ModuleType, SimpleNamespace

import pytest

from fontlab_glyport.errors import PartialFailure, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext


def test_scope_and_callback(tmp_path):
    (tmp_path / "sibling.py").write_text("value = 42\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("from .child import value\n")
    (tmp_path / "pkg/child.py").write_text("from sibling import value\n")
    script = tmp_path / "main.py"
    script.write_text(
        'import sibling, pkg\nimport importlib\nassert pkg.value == sibling.value == 42\ndef callback():\n return importlib.import_module("sibling").value\n'
    )
    host = ModuleType("sibling")
    old = sys.modules.get("sibling")
    sys.modules["sibling"] = host
    try:
        ctx = ExecutionContext(tmp_path, "glyphs3")
        assert ctx.run(script).status == "passed"
        assert sys.modules["sibling"] is host
        assert ctx.wrap(ctx.globals["callback"])() == 42
        assert not any(k.startswith(ctx.namespace) for k in sys.modules)
        ctx.close()
        ctx.close()
        with pytest.raises(RuntimeError):
            ctx.wrap(lambda: None)()
    finally:
        if old is None:
            sys.modules.pop("sibling", None)
        else:
            sys.modules["sibling"] = old


def test_errors_and_routing(tmp_path):
    script = tmp_path / "main.py"
    ctx = ExecutionContext(tmp_path, "glyphs3")
    out, err, cwd = sys.stdout, sys.stderr, os.getcwd()
    script.write_text(
        'import sys\nprint("out")\nprint("err", file=sys.stderr)\nraise SystemExit(3)\n'
    )
    assert ctx.run(script).status == "failed"
    assert ctx.exit_status == 3
    assert "out" in "".join(ctx.output.strings)
    assert "err" in "".join(ctx.output.strings)
    assert (sys.stdout, sys.stderr, os.getcwd()) == (out, err, cwd)
    (tmp_path / "bad.py").write_text('import sibling\nraise ValueError("bad")\n')
    (tmp_path / "sibling.py").write_text("value = 42\n")
    script.write_text("import bad\n")
    with pytest.raises(ValueError):
        ctx.run(script)
    assert not any(k.startswith(ctx.namespace) for k in sys.modules)
    script.write_text("import sibling\nassert sibling.value == 42\n")
    assert ctx.run(script).status == "passed"
    script.write_text("raise KeyboardInterrupt\n")
    with pytest.raises(KeyboardInterrupt):
        ctx.run(script)
    assert sys.stdout is out


def test_rejection_and_placeholder(tmp_path):
    first = ExecutionContext(tmp_path, "glyphs2")
    second = ExecutionContext(tmp_path, "glyphs3")
    with first:
        snapshot = dict(sys.modules)
        with pytest.raises(RuntimeError):
            second.__enter__()
        assert sys.modules == snapshot
        # Same-thread re-entry is balanced, not rejected.
        assert first.__enter__() is first
        first.__exit__(None, None, None)
        assert first._active
    script = tmp_path / "main.py"
    script.write_text("import GlyphsApp\nGlyphsApp.Glyphs\n")
    with pytest.raises(UnsupportedCapability) as caught:
        first.run(script)
    assert caught.value.capability == "GlyphsApp.Glyphs"
    assert caught.value.location.path == str(script)
    assert caught.value.location.line == 2


def test_resources_relative_and_shared_globals(tmp_path):
    resources = tmp_path / "Contents/Resources"
    resources.mkdir(parents=True)
    (resources / "helper.py").write_text("value = 7\n")
    (resources / "data.txt").write_text("bundle")
    script = resources / "main.py"
    script.write_text(
        'from .helper import value\nfrom pathlib import Path\nassert Path(__file__).with_name("data.txt").read_text() == "bundle"\ncount = globals().get("count", 0) + value\n'
    )
    ctx = ExecutionContext(tmp_path, "glyphs2", shared_globals=True)
    ctx.run(script)
    ctx.run(script)
    assert ctx.globals["count"] == 14
    fresh = ExecutionContext(tmp_path, "glyphs3")
    fresh.run(script)
    fresh.run(script)
    assert fresh.globals["count"] == 7


def test_restore_preexisting_and_preserve_unrelated_module(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    original = sys.modules["os"]
    unrelated = ModuleType("unrelated_owned_test")
    try:
        with pytest.raises(ValueError), ctx:
            sys.modules["os"] = ModuleType("os")
            sys.modules["unrelated_owned_test"] = unrelated
            ctx.import_module("GlyphsApp.UI")
            raise ValueError("failure")
        assert sys.modules["os"] is original
        assert sys.modules["unrelated_owned_test"] is unrelated
        assert not any(k.startswith(ctx.namespace) for k in sys.modules)
        assert ctx._finder not in sys.meta_path
    finally:
        sys.modules.pop("unrelated_owned_test", None)


def test_dynamic_package_and_provider(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "pkg/child.py").write_text("value = 8")
    script = tmp_path / "main.py"
    script.write_text(
        'import pkg.child\nfrom importlib import import_module\nassert import_module(".child", pkg.__name__).value == 8\nimport optional\nassert optional.value == 9\n'
    )
    provider = ModuleType("optional")
    provider.value = 9
    ctx = ExecutionContext(tmp_path, "glyphs3", {"optional": lambda: provider})
    assert ctx.run(script).status == "passed"
    assert "optional" not in sys.modules


def test_adapted_script_and_callback_output(tmp_path):
    script = tmp_path / "main.py"
    script.write_text("print 1/2\nimport GlyphsApp\nGlyphsApp.Glyphs\n")
    ctx = ExecutionContext(tmp_path, "glyphs2", cache_dir=tmp_path / "cache")
    with pytest.raises(UnsupportedCapability) as caught:
        ctx.run(script)
    assert caught.value.location.line == 3
    assert "".join(ctx.output.strings) == "0\n"
    before = sys.stdout
    ctx.wrap(lambda: print("callback"))()
    assert sys.stdout is before
    assert "callback" in "".join(ctx.output.strings)


def test_execution_context_when_reentered_on_same_thread_then_runs_and_restores(
    tmp_path,
):
    """run() inside an active ``with`` scope reuses it instead of rejecting it."""
    import sys

    from fontlab_glyport.execution import ExecutionContext

    (tmp_path / "sibling_mod.py").write_text("VALUE = 3\n")
    (tmp_path / "main.py").write_text("import sibling_mod\nprint(sibling_mod.VALUE)\n")
    captured = []
    before = set(sys.modules)
    context = ExecutionContext(tmp_path, profile="glyphs3", sink=captured.append)
    with context:
        stage = context.run(tmp_path / "main.py")
        assert context._active, "outer scope must stay active after nested run"
    assert stage.status == "passed", stage
    assert "".join(captured).strip() == "3"
    context.close()
    assert set(sys.modules) <= before | {
        m for m in sys.modules if m.startswith("_glyport_")
    }
    assert not [m for m in sys.modules if m.startswith(context.namespace)]


# Close hooks (integration task 1) -------------------------------------------


def test_close_when_hooks_registered_then_run_once_in_reverse_order(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    calls = []
    ctx.on_close(lambda: calls.append("first"))
    ctx.on_close(lambda: calls.append("second"))
    ctx.close()
    ctx.close()
    assert calls == ["second", "first"]


def test_close_when_hook_fails_then_later_hooks_run_and_failure_reported(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    calls = []
    boom, bang = RuntimeError("boom"), ValueError("bang")

    def fail(error):
        def hook():
            calls.append(str(error))
            raise error

        return hook

    ctx.on_close(lambda: calls.append("oldest"))
    ctx.on_close(fail(boom))
    ctx.on_close(fail(bang))
    with pytest.raises(PartialFailure) as info:
        ctx.close()
    assert calls == ["bang", "boom", "oldest"]
    assert info.value.errors == (bang, boom)
    assert "ValueError: bang" in str(info.value)
    assert "RuntimeError: boom" in str(info.value)
    assert info.value.__cause__ is bang
    assert ctx._closed and not ctx._modules
    ctx.close()  # already closed: silent, nothing re-runs
    assert calls == ["bang", "boom", "oldest"]


def test_close_when_hook_uses_context_then_context_still_usable(tmp_path):
    (tmp_path / "helper.py").write_text("VALUE = 7\n")
    ctx = ExecutionContext(tmp_path, "glyphs3")
    seen = []
    ctx.on_close(ctx.wrap(lambda: seen.append(ctx.import_module("helper").VALUE)))
    ctx.close()
    assert seen == [7]
    assert not any(k.startswith(ctx.namespace) for k in sys.modules)


def test_on_close_when_not_callable_or_closed_then_rejected(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    with pytest.raises(TypeError):
        ctx.on_close("not callable")
    ctx.close()
    with pytest.raises(RuntimeError):
        ctx.on_close(lambda: None)


def test_close_when_hook_registers_or_closes_again_then_each_runs_once(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    calls = []

    def reentrant():
        calls.append("reentrant")
        ctx.on_close(lambda: calls.append("late"))
        ctx.close()

    ctx.on_close(lambda: calls.append("oldest"))
    ctx.on_close(reentrant)
    ctx.close()
    assert calls == ["reentrant", "late", "oldest"]


def test_close_when_hook_exits_process_then_later_hooks_run_and_exit_propagates(
    tmp_path,
):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    later = []
    ctx.on_close(lambda: later.append("still run"))

    def failing_hook():
        raise RuntimeError("ordinary failure")

    def exit_hook():
        raise SystemExit(3)

    ctx.on_close(failing_hook)
    ctx.on_close(exit_hook)
    with pytest.raises(SystemExit) as info:
        ctx.close()
    assert info.value.code == 3
    assert ctx._closed and later == ["still run"] and not ctx._modules
    with pytest.raises(RuntimeError):
        ctx.on_close(lambda: None)


def test_implicit_imports_when_script_uses_glyphs_unimported_then_star_names(tmp_path):
    """Glyphs runs menu scripts as if they began with ``from GlyphsApp import *``."""
    script = tmp_path / "menu.py"
    script.write_text("seen = Glyphs.font\n")
    module = ModuleType("GlyphsApp")
    module.Glyphs, module._private = SimpleNamespace(font="F"), 1
    context = ExecutionContext(
        tmp_path,
        "glyphs3",
        {"GlyphsApp": lambda: module},
        implicit_imports=("GlyphsApp",),
    )
    try:
        assert context.run(script).status == "passed"
        assert context.globals["seen"] == "F" and "_private" not in context.globals
    finally:
        context.close()
    plain = ExecutionContext(tmp_path, "glyphs3", {"GlyphsApp": lambda: module})
    try:
        with pytest.raises(NameError):
            plain.run(script)
    finally:
        plain.close()


def test_open_when_text_mode_without_encoding_then_utf8(tmp_path):
    """Glyphs' Python runs in UTF-8 mode; FontLab's embedded Python defaults to
    ASCII (R049 fileformat: a CJK glyph in ExportCSV's rows). Reproduced with a
    C locale and UTF-8 mode and locale coercion off."""
    import subprocess

    script = tmp_path / "write.py"
    target = tmp_path / "out.txt"
    script.write_text(
        f"with open({str(target)!r}, 'w') as f:\n    f.write('\\u4e00')\n"
        f"with open({str(target)!r}) as f:\n    back = f.read()\n"
    )
    driver = (
        "import locale, sys\n"
        "assert locale.getpreferredencoding(False).lower() in ('ascii', 'us-ascii', 'ansi_x3.4-1968')\n"
        "from fontlab_glyport.execution import ExecutionContext\n"
        f"c = ExecutionContext({str(tmp_path)!r}, 'glyphs3')\n"
        f"assert c.run({str(script)!r}).status == 'passed'\n"
        "assert c.globals['back'] == '\\u4e00'\n"
        "c.close()\n"
    )
    env = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONUTF8": "0",
        "PYTHONCOERCECLOCALE": "0",
    }
    done = subprocess.run(
        [sys.executable, "-c", driver],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-800:]
    assert target.read_bytes() == "\u4e00".encode()


def test_dependency_dir_when_package_symlinked_then_importable_but_source_links_are_not(
    tmp_path,
):
    """Glyphs users install helper repositories under the package name
    (mekkablue--Glyphs-Scripts as Scripts/mekkablue, R049 plain-model). A
    symlink placed directly in a configured dependency directory is an
    explicit grant; a symlink inside the script's own folder is not."""
    from fontlab_glyport.errors import DependencyUnavailable

    repo = tmp_path / "helper--Repo"
    repo.mkdir()
    (repo / "__init__.py").write_text("value = 7\n")
    deps = tmp_path / "deps"
    deps.mkdir()
    (deps / "helperpkg").symlink_to(repo, target_is_directory=True)
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.py").write_text("import helperpkg\nresult = helperpkg.value\n")
    ctx = ExecutionContext(source, "glyphs3", dependency_paths=(deps,))
    assert ctx.run(source / "main.py").status == "passed"
    assert ctx.globals["result"] == 7
    ctx.close()

    (source / "escape").symlink_to(repo, target_is_directory=True)
    (source / "other.py").write_text("import escape\n")
    ctx = ExecutionContext(source, "glyphs3")
    with pytest.raises(DependencyUnavailable, match="outside"):
        ctx.run(source / "other.py")
    ctx.close()
