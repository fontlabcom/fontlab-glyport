# this_file: tests/test_fly_consumers.py
"""Current authored scripts/payloads use Fly; foreign compatibility source stays foreign."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECT = {"fontlab_glyport", "fontlabapp", "fontlab", "fontgate", "fontpr", "PythonQt"}


@pytest.mark.parametrize("path", sorted((ROOT / "native-drivers").rglob("*.py")) + sorted((ROOT / "Scripts").rglob("*.py")), ids=lambda p: str(p.relative_to(ROOT)))
def test_authored_consumer_when_importing_provider_then_uses_fly(path):
    tree = ast.parse(path.read_text())
    trees = [tree]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                trees.append(ast.parse(node.value))
            except SyntaxError:
                pass  # documentation or an incomplete composed snippet
    for payload in trees:
        for node in ast.walk(payload):
            if isinstance(node, ast.Import):
                names = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.split(".")[0] in DIRECT for name in names), ast.unparse(node)


@pytest.mark.parametrize("cached", ["canonical", "canonical_child", "attribute", "root", "child"])
def test_native_driver_when_alias_already_loaded_then_refuses_before_purge(monkeypatch, cached):
    import sys
    from types import ModuleType

    tree = ast.parse((ROOT / "native-drivers/driver_common.py").read_text())
    enter = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "__enter__")
    source = next(node.value for node in ast.walk(enter) if isinstance(node, ast.Constant) and isinstance(node.value, str) and "driver_key" in node.value)
    import fly

    original_modules = dict(sys.modules)
    original_fly = dict(vars(fly))
    try:
        for name in list(sys.modules):
            if name in ("fontlab_glyport", "fly.gp") or name.startswith(("fontlab_glyport.", "fly.gp.")):
                del sys.modules[name]
        vars(fly).pop("gp", None)
        existing = ModuleType("cached_provider")
        names = {"canonical": "fontlab_glyport", "canonical_child": "fontlab_glyport.child", "root": "fly.gp", "child": "fly.gp.child"}
        if cached == "attribute":
            vars(fly)["gp"] = existing
        else:
            sys.modules[names[cached]] = existing
        unrelated = ModuleType("fontlabapp")
        monkeypatch.setitem(sys.modules, "fontlabapp", unrelated)
        before = dict(sys.modules)
        paths = list(sys.path)
        with pytest.raises(RuntimeError, match="Release existing"):
            exec(source, {"repo": str(ROOT), "driver_key": "owned-test"})  # noqa: S102 - actual driver preflight, before native access
        assert sys.path == paths and "owned-test" not in sys.modules
        assert all(sys.modules.get(name) is module for name, module in before.items())
        assert sys.modules["fontlabapp"] is unrelated
        if cached == "attribute":
            assert vars(fly)["gp"] is existing
    finally:
        for name in list(sys.modules):
            if name not in original_modules:
                del sys.modules[name]
        sys.modules.update(original_modules)
        vars(fly).clear()
        vars(fly).update(original_fly)



@pytest.mark.parametrize("failed", [False, True])
def test_realuse_teardown_when_close_fails_then_retains_provider_and_aliases(monkeypatch, failed):
    import sys
    from types import ModuleType, SimpleNamespace

    import fly

    tree = ast.parse((ROOT / "native-drivers/realuse/realuse_common.py").read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "TEARDOWN" for target in node.targets))
    source = assignment.value.right.value  # actual teardown, without native COMMON imports
    original_modules = dict(sys.modules)
    original_fly = dict(vars(fly))
    try:
        provider = ModuleType("fontlab_glyport")
        child = ModuleType("fontlab_glyport.model")
        owned = {"fontlab_glyport": provider, "fly.gp": provider, "fontlab_glyport.model": child, "fly.gp.model": child, "fontlab_glyport.model.child": child, "fly.gp.model.child": child, "GlyphsApp": provider, "GlyphsApp.plugins": child, "vanilla": provider, "vanilla.dialogs": child}
        unrelated = {name: ModuleType(name) for name in ("fontlabapp", "fontlabapp.child", "fly.ap", "fly.ap.child", "fontlab_fontport", "fly.fp", "fly.fp.child", "fontlab_glyportish", "fly.gpish", "fly.gpish.child")}
        for name, module in {**owned, **unrelated}.items():
            monkeypatch.setitem(sys.modules, name, module)
        monkeypatch.setitem(vars(fly), "gp", provider)
        monkeypatch.setitem(vars(fly), "ap", unrelated["fontlabapp"])
        monkeypatch.setitem(vars(fly), "fp", unrelated["fontlab_fontport"])
        monkeypatch.setitem(sys.modules, "_glyport_launcher", SimpleNamespace(close_all=lambda: ["still open"] if failed else []))
        monkeypatch.delitem(sys.modules, "_realuse_guard", raising=False)
        owned = {name: module for name, module in sys.modules.items() if name.split(".")[0] in ("fontlab_glyport", "GlyphsApp", "vanilla") or name == "fly.gp" or name.startswith("fly.gp.")}
        scope = {"sys": sys, "st": None}
        exec(source, scope)  # noqa: S102 - actual host-free teardown branch, no native calls
        assert scope["result"]["failures"] == (["still open"] if failed else [])
        for name, module in owned.items():
            if failed:
                assert sys.modules.get(name) is module, name
            else:
                assert name not in sys.modules, name
        assert all(sys.modules.get(name) is module for name, module in unrelated.items())
        assert vars(fly)["ap"] is unrelated["fontlabapp"]
        assert vars(fly)["fp"] is unrelated["fontlab_fontport"]
        assert (vars(fly).get("gp") is provider) == failed
    finally:
        sys.modules.update(original_modules)
        vars(fly).clear()
        vars(fly).update(original_fly)


@pytest.mark.parametrize("failed", [False, True])
def test_driver_enter_when_bootstrap_fails_then_closes_only_owned_transport(monkeypatch, failed):
    import importlib.util
    import sys
    from types import ModuleType

    calls = []
    error = RuntimeError("unique bootstrap refusal")
    class Client:
        def __enter__(self):
            calls.append("enter")
            return self
        def run(self, *args, **kwargs):
            calls.append("run")
            if failed:
                raise error
        def close(self):
            calls.append("close")
    transport = ModuleType("fontlab_remopy")
    transport.FontLab = Client
    monkeypatch.setitem(sys.modules, "fontlab_remopy", transport)
    monkeypatch.setattr(sys, "argv", ["driver", "--repo", str(ROOT)])
    spec = importlib.util.spec_from_file_location("owned_driver_review", ROOT / "native-drivers/driver_common.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    driver = module.Driver("owned transport test")
    if failed:
        with pytest.raises(RuntimeError) as caught:
            driver.__enter__()
        assert caught.value is error
        assert calls == ["enter", "run", "close"]
    else:
        assert driver.__enter__() is driver
        assert calls == ["enter", "run"], "successful bootstrap keeps its owned transport"
