# this_file: tests/test_bootstrap.py
"""Ordinary interpreter import and activation lifecycle contracts (fake host)."""

import builtins
import sys
from types import ModuleType, SimpleNamespace

import pytest

import fontlab_glyport as glyport
from fontlab_glyport.entrypoints import ExecutionHost
from fontlab_glyport.receipt import ReceiptEnvironment


@pytest.fixture
def host(monkeypatch):
    from fontlab_glyport import entrypoints

    modules = {}
    for name in (
        "GlyphsApp",
        "GlyphsApp.plugins",
        "AppKit",
        "Foundation",
        "vanilla",
        "vanilla.dialogs",
    ):
        module = modules[name] = ModuleType(name)
        module.__all__ = ["marker"]
        module.marker = object()
        module.__path__ = []
    modules["GlyphsApp"].__all__.append("Glyphs")
    modules["GlyphsApp"].Glyphs = object()
    closed = []

    def adapters(context, font):
        context.on_close(lambda: closed.append(True))
        return {name: lambda m=m: m for name, m in modules.items()}

    gateway = ExecutionHost(
        lambda fn: fn(),
        ReceiptEnvironment("test", None, "3", None, "test", "test"),
        adapter_factory=adapters,
    )
    monkeypatch.setattr(entrypoints, "_native_host", lambda: gateway)
    yield modules, closed
    glyport.deactivate()


def test_ordinary_imports_identity_lifetime_and_idempotence(host):
    modules, closed = host
    original = builtins.__import__
    handle = glyport.activate()
    namespace = {}
    exec(  # noqa: S102 - original script import contract
        "from GlyphsApp import *\nimport AppKit, Foundation, vanilla\nfrom vanilla import dialogs",
        namespace,
    )
    assert namespace["marker"] is modules["GlyphsApp"].marker
    assert namespace["dialogs"] is modules["vanilla.dialogs"]
    assert namespace["AppKit"] is modules["AppKit"]
    assert glyport.activate() is handle
    assert builtins.__import__ is original
    assert not handle.context._active
    assert not closed
    glyport.deactivate()
    glyport.deactivate()
    assert closed == [True]
    assert "GlyphsApp" not in sys.modules


def test_activation_supplies_legacy_font_for_each_caller_and_restores_owned_names(host):
    modules, _closed = host
    first, second = object(), object()
    modules["GlyphsApp"].Glyphs = SimpleNamespace(font=first)
    namespace, another = {}, {}
    handle = glyport.activate(namespace=namespace)
    assert namespace["Font"] is first, "Old scripts expect the current font as Font"
    modules["GlyphsApp"].Glyphs.font = second
    assert glyport.activate(namespace=another) is handle
    assert another["Font"] is second, "A new caller gets its own current-font snapshot"
    namespace["Font"] = "script-owned replacement"
    handle.close()
    assert namespace == {"Font": "script-owned replacement"}
    assert another == {}, "Close removes only globals still owned by activation"


def test_activation_supplies_none_font_without_open_document(host):
    modules, _closed = host
    modules["GlyphsApp"].Glyphs = SimpleNamespace(font=None)
    namespace = {}
    handle = glyport.activate(namespace=namespace)
    assert namespace["Font"] is None, "No document must not invent a font"
    handle.close()
    assert namespace == {}


def test_activation_refuses_foreign_legacy_font_before_publishing_exports(host):
    modules, closed = host
    modules["GlyphsApp"].Glyphs = SimpleNamespace(font=object())
    owner = object()
    namespace = {"Font": owner}
    with pytest.raises(ValueError, match="Font"):
        glyport.activate(namespace=namespace)
    assert namespace == {"Font": owner}, "A collision leaves caller globals untouched"
    assert "GlyphsApp" not in sys.modules
    assert closed == [True], "Failed activation must close its newly owned context"


def test_collision_refuses_and_preserves_unrelated(host, monkeypatch):
    foreign = ModuleType("AppKit")
    monkeypatch.setitem(sys.modules, "AppKit", foreign)
    with pytest.raises(ImportError, match="AppKit"):
        glyport.activate()
    assert sys.modules["AppKit"] is foreign
    assert "GlyphsApp" not in sys.modules


def test_failure_rolls_back_and_closes(host, monkeypatch):
    _modules, closed = host

    def fail():
        raise RuntimeError("provider failed")

    from fontlab_glyport import entrypoints

    gateway = entrypoints._native_host()
    original = gateway.adapter_factory

    def adapters(ctx, font):
        result = original(ctx, font)
        result["Foundation"] = fail
        return result

    gateway.adapter_factory = adapters
    with pytest.raises(RuntimeError, match="provider failed"):
        glyport.activate()
    assert closed == [True]
    assert "GlyphsApp" not in sys.modules
    assert not any(name.startswith("_glyport_") for name in sys.modules)


def test_scoped_execution_coexists_and_unrelated_import_survives(host, tmp_path):
    handle = glyport.activate()
    path = tmp_path / "script.py"
    path.write_text("from GlyphsApp import marker\n")
    from fontlab_glyport import entrypoints

    scoped = glyport.run_script(
        path, profile="glyphs4", host=entrypoints._native_host()
    )
    scoped.close()
    assert sys.modules["GlyphsApp"] is host[0]["GlyphsApp"]
    unrelated = sys.modules["bootstrap_unrelated"] = ModuleType("bootstrap_unrelated")
    try:
        handle.close()
        assert sys.modules["bootstrap_unrelated"] is unrelated
    finally:
        sys.modules.pop("bootstrap_unrelated", None)


def test_outside_fontlab_fails_clearly(monkeypatch):
    monkeypatch.setitem(sys.modules, "fontlab", None)
    with pytest.raises(glyport.HostUnavailable):
        glyport.activate()


def test_callback_retains_context_until_deactivation(host):
    handle = glyport.activate()
    calls = []
    callback = handle.context.wrap(
        lambda: calls.append(handle.context.import_module("GlyphsApp"))
    )
    callback()
    assert calls == [host[0]["GlyphsApp"]]
    glyport.deactivate()
    with pytest.raises(RuntimeError, match="closed"):
        callback()


def test_close_failure_still_removes_aliases_and_allows_reactivation(host):
    handle = glyport.activate()

    def fail():
        raise RuntimeError("close failure")

    handle.context.on_close(fail)
    with pytest.raises(glyport.PartialFailure, match="close failure"):
        glyport.deactivate()
    assert "GlyphsApp" not in sys.modules
    assert host[1] == [True]
    assert glyport.activate() is not handle


def test_foreign_child_collision_refused(host, monkeypatch):
    foreign = ModuleType("GlyphsApp.foreign")
    monkeypatch.setitem(sys.modules, "GlyphsApp.foreign", foreign)
    with pytest.raises(ImportError, match="GlyphsApp.foreign"):
        glyport.activate()
    assert sys.modules["GlyphsApp.foreign"] is foreign


def test_profile_change_and_caller_replacement(host, monkeypatch):
    glyport.activate()
    with pytest.raises(ValueError, match="Deactivate"):
        glyport.activate(profile="glyphs3")
    foreign = ModuleType("AppKit")
    sys.modules["AppKit"] = foreign
    glyport.deactivate()
    assert sys.modules.pop("AppKit") is foreign


def test_invalid_profile_does_not_create_session(host):
    with pytest.raises(ValueError, match="Unknown"):
        glyport.activate(profile="auto")
    assert not host[1]


def test_deactivation_during_scope_refuses_without_snapshot_resurrection(
    host, tmp_path
):
    from fontlab_glyport.execution import ExecutionContext

    handle = glyport.activate()
    with (
        ExecutionContext(tmp_path, "glyphs4"),
        pytest.raises(RuntimeError, match="outside an active"),
    ):
        glyport.deactivate()
    assert not handle.closed
    glyport.deactivate()
    assert "GlyphsApp" not in sys.modules


def test_caller_globals_bind_restore_and_preserve_script_changes(host):
    namespace = {"__builtins__": builtins.__dict__}
    exec(  # noqa: S102 - ordinary script namespace
        "import fontlab_glyport; fontlab_glyport.activate()\nimport GlyphsApp\nresult = Glyphs",
        namespace,
    )
    assert namespace["result"] is host[0]["GlyphsApp"].Glyphs
    replacement = namespace["marker"] = object()
    glyport.deactivate()
    assert namespace["marker"] is replacement


def test_namespace_collision_rolls_back_without_overwriting(host):
    original = object()
    namespace = {"marker": original}
    with pytest.raises(ValueError, match="namespace collision"):
        glyport.activate(namespace=namespace)
    assert namespace == {"marker": original}
    assert "GlyphsApp" not in sys.modules


def test_repeat_activation_binds_multiple_namespaces_and_restores_only_added(host):
    first = {}
    second = {"marker": host[0]["GlyphsApp"].marker}
    handle = glyport.activate(namespace=first)
    assert glyport.activate(namespace=second) is handle
    third = {}
    assert glyport.activate(namespace=third) is handle
    glyport.deactivate()
    assert first == third == {}
    assert second["marker"] is host[0]["GlyphsApp"].marker


@pytest.mark.parametrize("scope_kind", ["independent", "callback"])
def test_repeat_activation_in_active_scope_refuses_atomically(
    host, tmp_path, scope_kind
):
    from fontlab_glyport.execution import ExecutionContext

    handle = glyport.activate(namespace={})
    namespace = {"untouched": object()}
    snapshot = namespace.copy()

    def repeat():
        with pytest.raises(RuntimeError, match="outside an active"):
            glyport.activate(namespace=namespace)

    if scope_kind == "callback":
        handle.context.wrap(repeat)()
    else:
        with ExecutionContext(tmp_path, "glyphs3"):
            repeat()
    assert namespace == snapshot
    assert not handle.closed


def test_repeat_activation_uses_dispatcher_thread_gate(host):
    import threading

    handle = glyport.activate(namespace={})
    main_thread = threading.get_ident()
    dispatched = []

    def dispatch(operation):
        dispatched.append(threading.get_ident())
        if threading.get_ident() != main_thread:
            raise glyport.HostUnavailable("GUI thread required")
        return operation()

    handle.host.dispatch = dispatch
    namespace = {}
    failures = []

    def worker():
        try:
            glyport.activate(namespace=namespace)
        except glyport.HostUnavailable as error:
            failures.append(str(error))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert failures == ["GUI thread required"]
    assert len(dispatched) == 1
    assert namespace == {}


def test_force_qt_restores_preloaded_native_modules(host, monkeypatch, cocoa_modules):
    native = cocoa_modules()["AppKit"]
    before = dict(vars(native))
    monkeypatch.setitem(sys.modules, "AppKit", native)
    handle = glyport.activate(cocoa_backend="qt", namespace={})
    assert sys.modules["AppKit"] is host[0]["AppKit"]
    assert handle.cocoa_backend == "qt"
    with pytest.raises(ValueError, match="cocoa_backend"):
        glyport.activate(cocoa_backend="native", namespace={})
    handle.close()
    assert sys.modules["AppKit"] is native
    assert vars(native) == before


def test_native_activation_keeps_module_identity(host, monkeypatch, cocoa_modules):
    from fontlab_glyport import cocoa_backend

    monkeypatch.setattr(cocoa_backend.sys, "platform", "darwin")
    modules = cocoa_modules()
    before = {name: dict(vars(module)) for name, module in modules.items()}
    handle = glyport.activate(cocoa_backend="native", namespace={})
    assert handle.cocoa_backend == "native"
    assert all(sys.modules[name] is module for name, module in modules.items())
    handle.close()
    assert all(sys.modules[name] is module for name, module in modules.items())
    assert all(vars(module) == before[name] for name, module in modules.items())


def test_scoped_selection_inherits_activation_instead_of_importing_aliases(
    host, tmp_path, monkeypatch
):
    from fontlab_glyport import cocoa_backend
    from fontlab_glyport.entrypoints import ExecutionOptions, run_script

    handle = glyport.activate(cocoa_backend="qt", namespace={})

    def fail(request):
        pytest.fail("selection must reuse active route")

    monkeypatch.setattr(cocoa_backend, "select_backend", fail)
    path = tmp_path / "pilot.py"
    path.write_text("import AppKit\n")
    run = run_script(
        path, profile="glyphs4", options=ExecutionOptions(cocoa_backend="qt")
    )
    assert run.cocoa_backend == "qt"
    run.close()
    handle.close()


@pytest.mark.parametrize("kind", ["script", "plugin"])
@pytest.mark.parametrize("first,later", [("native", "qt"), ("qt", "native")])
def test_retained_backend_refuses_later_activation_and_close_allows_change(
    host, tmp_path, monkeypatch, cocoa_modules, kind, first, later
):
    import plistlib

    from fontlab_glyport import entrypoints

    monkeypatch.setattr(sys, "platform", "darwin")
    native = cocoa_modules()
    options = entrypoints.ExecutionOptions(cocoa_backend=first)
    source = "def callback():\n import AppKit\n return AppKit\n"
    unloaded = []
    if kind == "script":
        path = tmp_path / "pilot.py"
        path.write_text(source)
        retained = glyport.run_script(path, profile="glyphs4", options=options)
    else:
        path = tmp_path / "Pilot.glyphsPlugin"
        resources = path / "Contents/Resources"
        resources.mkdir(parents=True)
        (resources / "plugin.py").write_text(source + "class Pilot: pass\n")
        (path / "Contents/Info.plist").write_bytes(
            plistlib.dumps(
                {"NSPrincipalClass": "Pilot", "PyMainFileNames": ["plugin.py"]}
            )
        )
        gateway = entrypoints._native_host()
        gateway.plugin_installer = lambda context, assessment: (
            entrypoints.PluginRegistration(
                lambda: unloaded.append(context.import_module("AppKit")),
                evidence=("fixture",),
            )
        )
        retained = glyport.install_plugin(path, profile="glyphs4", options=options)
    callback = retained.wrap(retained.context.globals["callback"])
    expected = native["AppKit"] if first == "native" else host[0]["AppKit"]
    assert callback() is expected
    before = {name: sys.modules[name] for name in native}
    namespace = {}
    with pytest.raises(ValueError, match="backend"):
        glyport.activate(cocoa_backend=later, namespace=namespace)
    assert namespace == {}
    assert all(sys.modules[name] is value for name, value in before.items())
    assert callback() is expected
    retained.close()
    if kind == "plugin":
        assert unloaded == [expected]
    activation = glyport.activate(cocoa_backend=later, namespace={})
    assert activation.cocoa_backend == later
    activation.close()


def test_closed_context_releases_backend_even_when_cleanup_fails(
    host, tmp_path, monkeypatch, cocoa_modules
):
    monkeypatch.setattr(sys, "platform", "darwin")
    cocoa_modules()
    from fontlab_glyport.entrypoints import ExecutionOptions

    path = tmp_path / "pilot.py"
    path.write_text("value = 1\n")
    retained = glyport.run_script(
        path, profile="glyphs4", options=ExecutionOptions(cocoa_backend="native")
    )

    def fail():
        raise ValueError("fixture cleanup failure")

    retained.context.on_close(fail)
    with pytest.raises(glyport.PartialFailure):
        retained.close()
    assert retained.context._closed
    activation = glyport.activate(cocoa_backend="qt", namespace={})
    activation.close()


def test_same_backend_handles_share_lifetime_and_block_change_until_all_closed(
    host, tmp_path, monkeypatch, cocoa_modules
):
    from fontlab_glyport.entrypoints import ExecutionOptions

    monkeypatch.setattr(sys, "platform", "darwin")
    cocoa_modules()
    path = tmp_path / "pilot.py"
    path.write_text("value = 1\n")
    options = ExecutionOptions(cocoa_backend="native")
    first = glyport.run_script(path, profile="glyphs4", options=options)
    second = glyport.run_script(path, profile="glyphs4", options=options)
    first.close()
    with pytest.raises(ValueError, match="backend"):
        glyport.run_script(
            path, profile="glyphs4", options=ExecutionOptions(cocoa_backend="qt")
        )
    assert second.context.globals["value"] == 1
    second.close()
    activation = glyport.activate(cocoa_backend="qt", namespace={})
    activation.close()


def test_failed_execution_releases_registered_backend(
    host, tmp_path, monkeypatch, cocoa_modules
):
    from fontlab_glyport.entrypoints import ExecutionOptions

    monkeypatch.setattr(sys, "platform", "darwin")
    cocoa_modules()
    path = tmp_path / "pilot.py"
    path.write_text("raise ValueError('fixture execution failure')\n")
    with pytest.raises(ValueError, match="fixture execution failure") as failure:
        glyport.run_script(
            path, profile="glyphs4", options=ExecutionOptions(cocoa_backend="native")
        )
    assert failure.value.handle.context._closed
    activation = glyport.activate(cocoa_backend="qt", namespace={})
    activation.close()
