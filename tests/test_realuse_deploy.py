# this_file: tests/test_realuse_deploy.py
"""tools/deploy: the FontLab Scripts-folder launcher (issue 106, lane G1).

The launcher runs against a stand-in glyport package written to tmp_path, so
these tests exercise its sys.path, purge and handle bookkeeping without FontLab.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "deploy_launcher", REPO / "tools/deploy/deploy_launcher.py"
)
deploy_launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy_launcher)
DeployError = deploy_launcher.DeployError

FAKE_INIT = """
CALLS = []
class Handle:
    def __init__(self, path):
        self.path, self.state = path, "active"
    def close(self):
        CALLS.append(("close", self.path)); self.state = "closed"
class PluginHandle(Handle):
    def unload(self):
        CALLS.append(("unload", self.path)); self.state = "closed"
def run_script(path, profile="auto", **options):
    CALLS.append(("run", path, profile, options.get("options"))); return Handle(path)
def install_plugin(path, profile="auto", **options):
    CALLS.append(("install", path, profile)); return PluginHandle(path)
"""
FAKE_ENTRY = "from dataclasses import dataclass\n@dataclass\nclass ExecutionOptions:\n    dependency_paths: tuple = ()\n"


@pytest.fixture
def isolated():
    """Restore sys.modules/sys.path: the launcher purges fontlab_glyport."""
    modules, path = dict(sys.modules), list(sys.path)
    import fly

    fly_state = dict(vars(fly))
    yield
    for name in [m for m in sys.modules if m not in modules]:
        del sys.modules[name]
    sys.modules.update(modules)
    sys.path[:] = path
    vars(fly).clear()
    vars(fly).update(fly_state)


def fake_src(root: Path) -> Path:
    package = root / "src/fontlab_glyport"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(FAKE_INIT)
    (package / "entrypoints.py").write_text(FAKE_ENTRY)
    return root / "src"


def launch(path: Path) -> object:
    code = compile(path.read_text(), str(REPO / "tools/deploy/launcher_template.py"), "exec")
    exec(code, {"__name__": "launcher", "GLYPORT_LAUNCHER_NO_UI": True})  # noqa: S102 - the generated launcher
    return sys.modules["_glyport_launcher"]


def test_deploy_when_folder_empty_then_launcher_embeds_paths_and_compiles(tmp_path):
    scripts, site = tmp_path / "Scripts", tmp_path / "site"
    scripts.mkdir()
    site.mkdir()
    target = deploy_launcher.deploy(scripts, site=site)
    text = target.read_text()
    assert target.name == "Glyport Launcher.py"
    assert text.splitlines()[0] == deploy_launcher.MARKER, (
        "marker line identifies tool-written launchers"
    )
    assert (
        repr(str((REPO / "src").resolve())) in text
        and repr(str(site.resolve())) in text
    )
    assert "@GLYPORT" not in text and "this_file" not in text, (
        "placeholders and source header replaced"
    )
    compile(text, str(target), "exec")


def test_deploy_when_foreign_file_has_the_name_then_refused_unless_forced(tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "Glyport Launcher.py").write_text("print('mine')\n")
    with pytest.raises(DeployError, match="collides"):
        deploy_launcher.deploy(scripts)
    assert (scripts / "Glyport Launcher.py").read_text() == "print('mine')\n", (
        "foreign file untouched"
    )
    deploy_launcher.deploy(scripts, force=True)
    assert (
        (scripts / "Glyport Launcher.py").read_text().startswith(deploy_launcher.MARKER)
    )


def test_deploy_when_own_launcher_exists_then_replaced(tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    first = deploy_launcher.deploy(scripts)
    first.write_text(first.read_text() + "# stale\n")
    assert "# stale" not in deploy_launcher.deploy(scripts).read_text()


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda s: None, "does not exist"),
        (
            lambda s: (s.mkdir(), (s / "Glyport Launcher.py").symlink_to(s)),
            "link or directory",
        ),
    ],
)
def test_deploy_when_target_unsafe_then_refused(tmp_path, setup, message):
    scripts = tmp_path / "Scripts"
    setup(scripts)
    with pytest.raises(DeployError, match=message):
        deploy_launcher.deploy(scripts)


def test_deploy_when_path_goes_through_user_folder_link_then_refused(tmp_path):
    scripts = tmp_path / "fontlab-user-folder/Scripts"
    scripts.mkdir(parents=True)
    with pytest.raises(DeployError, match="fontlab-user-folder"):
        deploy_launcher.deploy(scripts)


@pytest.mark.parametrize("name", ["x.txt", "a/b.py", ".hidden.py"])
def test_deploy_when_name_not_plain_py_then_refused(tmp_path, name):
    (tmp_path / "Scripts").mkdir()
    with pytest.raises(DeployError, match="plain .py"):
        deploy_launcher.deploy(tmp_path / "Scripts", name=name)


def test_render_when_src_or_site_missing_then_refused(tmp_path):
    with pytest.raises(DeployError, match="not a glyport src"):
        deploy_launcher.render(tmp_path, None)
    with pytest.raises(DeployError, match="site directory"):
        deploy_launcher.render(REPO / "src", tmp_path / "missing")


def test_main_when_refused_then_exit_1(tmp_path, capsys):
    assert deploy_launcher.main(["--scripts", str(tmp_path / "none")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_launcher_when_run_then_src_first_stale_modules_purged_and_handles_kept(
    tmp_path, isolated
):
    src = fake_src(tmp_path)
    site = tmp_path / "site"
    site.mkdir()
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    for stale in (
        "fontlab_glyport",
        "fontlab_glyport.model",
        "GlyphsApp",
        "vanilla.vanillaBase",
    ):
        sys.modules[stale] = type(sys)(stale)
    sys.modules["vanillaish"] = keep = type(sys)("vanillaish")
    target = deploy_launcher.deploy(scripts, src=src, site=site)
    launcher = launch(target)
    (tmp_path / "Script.py").write_text("x = 1\n")
    handle = launcher.run_script(
        tmp_path / "Script.py", dependency_paths=[tmp_path / "deps"]
    )
    assert sys.path[:2] == [str(src.resolve()), str(site.resolve())]
    glyport = sys.modules["fontlab_glyport"]
    assert glyport.__file__.startswith(str(src.resolve())), (
        "stale fontlab_glyport replaced by the launcher's src"
    )
    assert "GlyphsApp" not in sys.modules and "vanilla.vanillaBase" not in sys.modules
    assert sys.modules["vanillaish"] is keep, "only exact package roots are purged"
    kind, path, profile, options = glyport.CALLS[0]
    assert (kind, path, profile) == ("run", str(tmp_path / "Script.py"), "auto")
    assert options.dependency_paths == (str(tmp_path / "deps"),)
    plugin = launcher.install_plugin(tmp_path / "P.glyphsReporter")
    assert launcher.handles == [handle, plugin]
    assert launch(target).handles == [handle, plugin], (
        "re-running the launcher keeps live handles"
    )
    assert sys.modules["fontlab_glyport"] is glyport, (
        "no purge while live handles use the loaded package"
    )
    assert launcher.close_all() == []
    assert glyport.CALLS[-2:] == [
        ("unload", str(tmp_path / "P.glyphsReporter")),
        ("close", str(tmp_path / "Script.py")),
    ]
    assert launcher.handles == []
    assert launcher.activate() is glyport, "plain activation keeps the current package"
    assert launcher.activate(reload=True) is not glyport, (
        "reload purges this checkout's modules once no handle uses them"
    )


def test_launcher_profile_when_source_is_python2_then_glyphs2_else_auto(
    tmp_path, isolated
):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    launcher = launch(deploy_launcher.deploy(scripts, src=fake_src(tmp_path)))
    modern, legacy = tmp_path / "modern.py", tmp_path / "legacy.py"
    modern.write_text("print('x')\n")
    legacy.write_text("print 'x'\n")
    bundle = tmp_path / "P.glyphsFilter/Contents/Resources"
    bundle.mkdir(parents=True)
    (bundle / "plugin.py").write_text("x = 1\n")
    assert launcher.detect_profile(str(modern)) == "auto"  # glyport decides (F48)
    assert launcher.detect_profile(str(legacy)) == "glyphs2"
    assert launcher.detect_profile(str(tmp_path / "P.glyphsFilter")) == "auto"
    (bundle / "helper.py").write_text(
        "except_ = 1\ntry:\n  pass\nexcept A, e:\n  pass\n"
    )
    assert launcher.detect_profile(str(tmp_path / "P.glyphsFilter")) == "glyphs2"
    launcher.run_script(legacy)
    assert sys.modules["fontlab_glyport"].CALLS[-1][2] == "glyphs2"


@pytest.mark.parametrize(
    ("clause", "expected"),
    [
        ("(A, B)", "auto"),
        ("A as e", "auto"),
        ("(A, B), e", "glyphs2"),
        ("A, e", "glyphs2"),
        ("A, B", "glyphs2"),  # valid on 3.14 (PEP 758) but ambiguous with Python 2
    ],
)
def test_launcher_profile_when_except_clause_then_profile(
    tmp_path, isolated, clause, expected
):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    launcher = launch(deploy_launcher.deploy(scripts, src=fake_src(tmp_path)))
    script = tmp_path / "script.py"
    script.write_text(f"try:\n  pass\nexcept {clause}:\n  pass\n")
    assert launcher.detect_profile(str(script)) == expected


def test_launcher_when_package_resolves_elsewhere_then_import_error(tmp_path, isolated):
    src = fake_src(tmp_path / "a")
    other = fake_src(tmp_path / "b")
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    launcher = launch(deploy_launcher.deploy(scripts, src=src))
    sys.modules.pop("fontlab_glyport", None)
    real_import = (
        __builtins__["__import__"]
        if isinstance(__builtins__, dict)
        else __builtins__.__import__
    )

    def shadowed(name, *args, **kwargs):  # a stale path entry wins the import
        if name == "fly" and "fontlab_glyport" not in sys.modules:
            sys.path.insert(0, str(other))
            try:
                return real_import(name, *args, **kwargs)
            finally:
                sys.path.remove(str(other))
        return real_import(name, *args, **kwargs)

    import builtins

    builtins.__import__ = shadowed
    try:
        with pytest.raises(ImportError, match="not "):
            launcher.activate()
    finally:
        builtins.__import__ = real_import


def test_launcher_when_deployed_installed_then_uses_importable_package_unchanged(
    tmp_path, isolated
):
    installed = fake_src(tmp_path / "site-packages-like")
    sys.path.insert(0, str(installed))
    for name in [m for m in sys.modules if m.split(".")[0] == "fontlab_glyport"]:
        del sys.modules[name]  # as in a fresh FontLab: nothing imported yet
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    target = deploy_launcher.deploy(scripts, src=None)
    assert (
        "GLYPORT_SRC = ''" in target.read_text()
        and "GLYPORT_SITE = ''" in target.read_text()
    )
    paths = list(sys.path)
    launcher = launch(target)
    (tmp_path / "s.py").write_text("x = 1\n")
    launcher.run_script(tmp_path / "s.py")
    assert sys.modules["fontlab_glyport"].__file__.startswith(str(installed)), (
        "the installed copy is used"
    )
    assert sys.path == paths, "no import path is added or moved"


def test_main_when_installed_flag_then_src_and_site_ignored(tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    assert (
        deploy_launcher.main(
            ["--scripts", str(scripts), "--installed", "--site", str(tmp_path / "nope")]
        )
        == 0
    )
    assert "GLYPORT_SRC = ''" in (scripts / "Glyport Launcher.py").read_text()


def test_launcher_when_real_fly_cached_then_switch_refuses_live_and_refreshes_closed(tmp_path):
    """Exercise root/child Fly caches in isolation without native objects."""
    fly_source = Path(os.environ.get("FONTLAB_FLY_SOURCE", REPO.parent / "fontlab-fly/src")).resolve()
    assert (fly_source / "fly/__init__.py").is_file(), "supply the reviewed Fly source"
    first = fake_src(tmp_path / "first")
    second = fake_src(tmp_path / "second")
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    a = deploy_launcher.deploy(scripts, src=first, name="first.py")
    b = deploy_launcher.deploy(scripts, src=second, name="second.py")
    code = f"""
import importlib, sys
from pathlib import Path
sys.path.insert(0, {str(fly_source)!r})
import fly
assert Path(fly.__file__).resolve() == Path({str(fly_source / 'fly/__init__.py')!r})
def launch(path):
    exec(Path(path).read_text(), {{"GLYPORT_LAUNCHER_NO_UI": True}})
    return sys.modules["_glyport_launcher"]
a = launch({str(a)!r})
old = a.activate()
old_child = importlib.import_module("fly.gp.entrypoints")
assert fly.gp is old
handle = a.run_script("owned.py")
assert a.activate(reload=True) is old
b = launch({str(b)!r})
try:
    b.activate()
except RuntimeError as error:
    assert "live" in str(error)
else:
    raise AssertionError("live source switch was accepted")
assert sys.modules["fontlab_glyport"] is fly.gp is old
assert sys.modules["fly.gp.entrypoints"] is old_child
assert handle.state == "active" and b.handles == [handle]
def failed_close():
    raise RuntimeError("still open")
handle.close = failed_close
assert b.close_all() == ["RuntimeError: still open"]
assert b.handles == [handle]
try:
    b.activate()
except RuntimeError:
    pass
else:
    raise AssertionError("failed-close handle was unloaded")
handle.state = "closed"
assert b.close_all() == [] and b.handles == []
keep = object()
fly.__dict__["ap"] = keep
new = b.activate()
new_child = importlib.import_module("fly.gp.entrypoints")
assert new is fly.gp is sys.modules["fontlab_glyport"]
assert new is not old and new_child is not old_child
assert new_child is sys.modules["fontlab_glyport.entrypoints"]
assert Path(new.__file__).is_relative_to({str(second)!r})
assert fly.ap is keep, "unrelated Fly aliases survive"
assert b.activate(reload=True) is not new
assert fly.gp is sys.modules["fontlab_glyport"]
"""
    completed = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(("choice", "path", "expected"), [("", "", []), ("Unload all glyport plugins", "", ["close"]), ("Run a Glyphs script…", "", []), ("Run a Glyphs script…", "script.py", ["run"]), ("Install a Glyphs plugin bundle…", "", []), ("Install a Glyphs plugin bundle…", "plugin", ["install"])])
def test_launcher_menu_when_choice_or_path_cancelled_then_only_requested_action_runs(tmp_path, isolated, monkeypatch, choice, path, expected):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    launcher = launch(deploy_launcher.deploy(scripts, src=fake_src(tmp_path)))
    gui = SimpleNamespace(
        QInputDialog=SimpleNamespace(getItem=lambda *a: choice),
        QFileDialog=SimpleNamespace(getOpenFileName=lambda *a: path, getExistingDirectory=lambda *a: path),
    )
    qt = type(sys)("PythonQt")
    qt.QtGui = gui
    monkeypatch.setitem(sys.modules, "PythonQt", qt)
    monkeypatch.delitem(sys.modules, "fly.qt", raising=False)
    import fly
    monkeypatch.delitem(vars(fly), "qt", raising=False)
    calls = []
    scope = launcher.activate.__globals__
    monkeypatch.setitem(scope, "activate", lambda reload=False: None)
    for name, action in [("run_script", "run"), ("install_plugin", "install")]:
        monkeypatch.setitem(scope, name, lambda p, action=action: (calls.append(action), SimpleNamespace(state="active"))[1])
    monkeypatch.setitem(scope, "close_all", lambda: calls.append("close") or [])
    scope["_choose"]()
    assert calls == expected


def test_launcher_when_real_handle_close_fails_then_terminal_failure_stays_tracked(tmp_path, isolated):
    """RunHandle marks failed/released even when context resources remain live."""
    import importlib

    from fontlab_glyport.entrypoints import ExecutionHost, ExecutionOptions, RunHandle
    from fontlab_glyport.receipt import ReceiptEnvironment

    calls = []
    def failed_close():
        calls.append("close")
        raise RuntimeError("owned resource still live")
    handle = RunHandle(tmp_path / "owned.py", ExecutionHost(lambda operation: operation(), ReceiptEnvironment(None, None, None, None, None, None)), ExecutionOptions())
    handle.context = SimpleNamespace(close=failed_close)
    handle.state = "active"
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    first = fake_src(tmp_path / "first")
    launcher = launch(deploy_launcher.deploy(scripts, src=first, name="first.py"))
    provider = launcher.activate()
    child = importlib.import_module("fly.gp.entrypoints")
    launcher.handles.append(handle)
    paths = list(sys.path)
    assert launcher.close_all() == ["RuntimeError: owned resource still live"]
    assert handle.state == "failed" and handle._released
    assert launcher.handles == [handle], "failed is not proof of released resources"
    assert launcher.close_all(), "the subsequent no-op close must still report unresolved cleanup"
    assert calls == ["close"], "RunHandle's failed cleanup cannot be retried through close"
    assert launcher.activate(reload=True) is provider
    second = fake_src(tmp_path / "second")
    foreign = launch(deploy_launcher.deploy(scripts, src=second, name="second.py"))
    with pytest.raises(RuntimeError, match="live"):
        foreign.activate()
    assert foreign.handles == [handle] and sys.path == paths
    assert sys.modules["fontlab_glyport"] is sys.modules["fly.gp"] is provider
    assert sys.modules["fontlab_glyport.entrypoints"] is sys.modules["fly.gp.entrypoints"] is child
    import fly
    assert vars(fly)["gp"] is provider
