# this_file: tests/test_legacy_path_area.py
"""Legacy dialog routing and unsigned analytic area, without native execution."""

import importlib
import plistlib
import sys
from copy import deepcopy
from types import ModuleType, SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from test_bootstrap import host as bootstrap_host
from test_glyphsapp_session import _session

import fontlab_glyport as glyport
from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def host(monkeypatch):
    yield from bootstrap_host.__wrapped__(monkeypatch)


def rectangle():
    return GSPath([GSNode(p) for p in ((0, 0), (10, 0), (10, 10), (0, 10))])


@pytest.mark.parametrize("closed", [False, True])
def test_area_when_rectangle_open_or_reversed_then_unsigned_without_mutation(closed):
    path = rectangle()
    path.closed = closed
    before = [(tuple(n.position), n.type) for n in path.nodes]
    assert path.area() == 100, "Open paths must close for area"
    assert path.direction == -1, "Existing counterclockwise convention survives"
    assert [(tuple(n.position), n.type) for n in path.nodes] == before
    assert path.closed is closed, "Area must never close the source geometry"
    if closed:
        path = GSPath([GSNode(tuple(n.position), n.type) for n in reversed(path.nodes)])
        assert path.area() == 100, "Winding must not change unsigned area"
        assert path.direction == 1


@pytest.mark.parametrize("points", [(), ((3, 4),), ((0, 0), (10, 10), (20, 20))])
def test_area_when_degenerate_then_zero_and_positive_direction(points):
    path = GSPath([GSNode(point) for point in points])
    assert path.area() == 0, "Empty and collinear geometry has zero area"
    assert path.direction == 1, "Degenerate winding retains the +1 contract"


@pytest.mark.parametrize(
    ("controls", "end_type", "expected"),
    [(((0, 10), (10, 10)), "curve", 60), (((5, 10),), "qcurve", 100 / 3)],
)
def test_area_when_bezier_then_known_integral(controls, end_type, expected):
    path = GSPath(
        [GSNode((0, 0))]
        + [GSNode(p, "offcurve") for p in controls]
        + [GSNode((10, 0), end_type)],
        closed=False,
    )
    assert path.area() == pytest.approx(expected), "Use analytic Bezier area"
    reverse = GSPath(
        [GSNode((10, 0))]
        + [GSNode(p, "offcurve") for p in reversed(controls)]
        + [GSNode((0, 0), end_type)],
        closed=False,
    )
    assert reverse.area() == pytest.approx(expected), "Curved area is unsigned too"


def test_area_when_live_geometry_changes_then_current_and_stale_refused():
    backend = FakeBackend()
    font = Model(backend).font
    layer = font.glyphs["A"].layers[0]
    path = layer.paths.append(rectangle())
    before = deepcopy(dict(backend.layers))
    revision = backend.revision(font.id)
    events = list(backend.undo_events)
    assert path.area() == 100
    assert backend.layers == before and backend.revision(font.id) == revision
    assert backend.undo_events == events, "Area must not enter Undo or publish edits"
    path.nodes[1].position = (20, 0)
    assert path.area() == 150, "A retained proxy must read current geometry"
    detached = path.copy()
    layer.paths.remove(path)
    with pytest.raises(StaleNativeObject):
        path.area()
    assert detached.area() == 150, "A detached copy remains independently readable"
    retained = layer.paths[0]
    backend.close_font(font.id)
    with pytest.raises(StaleNativeObject):
        retained.area()


def test_area_when_dependency_fails_then_explicit_error(monkeypatch):
    from fontlab_glyport.model import segments

    def fail(*args):
        raise UnsupportedCapability("area dependency unavailable")

    monkeypatch.setattr(segments, "fonttools_module", fail)
    with pytest.raises(UnsupportedCapability, match="dependency unavailable"):
        rectangle().area()


def test_area_when_live_read_fails_then_same_error_without_guessing_zero(monkeypatch):
    backend = FakeBackend()
    font = Model(backend).font
    path = font.glyphs["A"].layers[0].paths.append(rectangle())
    error = RuntimeError("native read failed")

    def fail(*args):
        raise error

    monkeypatch.setattr(backend, "layer", fail)
    backend._bump()
    with pytest.raises(RuntimeError) as caught:
        path.area()
    assert caught.value is error, "Native read failures are never guessed zero area"


@pytest.fixture
def legacy(tmp_path):
    ctx, session = _session(tmp_path)
    bridge = FakeGlyphsBridge()
    session.bridge.ask_string = lambda *args: bridge.ask_string(*args)
    ctx.adapters.update(session.adapters())
    yield ctx, bridge
    ctx.close()


def test_legacy_when_scoped_nested_imports_then_real_defaults_answer_cancel(
    legacy, tmp_path
):
    ctx, bridge = legacy
    bridge.answers["ask_string"] = "12"
    (tmp_path / "helper.py").write_text(
        "import robofab.interface.all.dialogs\n"
        "from robofab.interface.all import dialogs\n"
        "from robofab.interface.all.dialogs import AskString\n"
        "import importlib\n"
        "assert importlib.import_module('robofab.interface.all.dialogs') is dialogs\n"
        "assert robofab.interface.all.dialogs is dialogs\n"
        "def ask():\n"
        "    from robofab.interface.all.dialogs import AskString\n"
        "    print('legacy callback')\n"
        "    return AskString('Limit')\n"
    )
    script = tmp_path / "main.py"
    script.write_text("from helper import ask\nresult = ask()\n")
    assert ctx.run(script).status == "passed"
    assert ctx.globals["result"] == "12"
    assert bridge.calls == [("ask_string", "Limit", "", "RoboFab", None, None)]
    callback = ctx.wrap(ctx.globals["ask"])
    bridge.answers["ask_string"] = None
    assert callback() is None, "Cancellation must reach the actual caller unchanged"
    assert "legacy callback" in "".join(ctx.output.strings)
    assert not any(n.startswith("robofab") for n in sys.modules)
    ctx.close()
    with pytest.raises(RuntimeError, match="closed"):
        callback()


def test_legacy_when_explicit_arguments_or_bridge_error_then_forward_unchanged(
    legacy, monkeypatch
):
    ctx, bridge = legacy
    bridge.answers["ask_string"] = "answer"
    with ctx:
        module = ctx.import_module("robofab.interface.all.dialogs")
        assert module.AskString("Prompt", "initial", "Owner") == "answer"
        assert bridge.calls[-1] == (
            "ask_string",
            "Prompt",
            "initial",
            "Owner",
            None,
            None,
        )
        error = RuntimeError("dialog failed")

        def fail(*args):
            raise error

        monkeypatch.setattr(bridge, "ask_string", fail)
        with pytest.raises(RuntimeError) as caught:
            module.AskString("Prompt")
        assert caught.value is error, "Never turn dialog errors into cancellation"
        with pytest.raises(UnsupportedCapability):
            _ = module.GetFile
        with pytest.raises(UnsupportedCapability):
            _ = ctx.import_module("robofab").RFont


def ordinary_providers(host, legacy):
    from fontlab_glyport import entrypoints

    ctx, _bridge = legacy
    gateway = entrypoints._native_host()
    previous = gateway.adapter_factory

    def adapters(context, font):
        result = previous(context, font)
        result.update(
            {n: p for n, p in ctx.adapters.items() if n.startswith("robofab")}
        )
        return result

    gateway.adapter_factory = adapters
    return gateway


def test_legacy_when_ordinary_activation_then_nested_imports_and_identity_cleanup(
    host, legacy
):
    ordinary_providers(host, legacy)
    bridge = legacy[1]
    bridge.answers["ask_string"] = "42"
    handle = glyport.activate(namespace={})
    namespace = {}
    exec(  # noqa: S102 - ordinary Python import contract, with owned literal source
        "import robofab.interface.all.dialogs\n"
        "from robofab.interface.all import dialogs\n"
        "from robofab.interface.all.dialogs import AskString\n"
        "result = AskString('Size')\n",
        namespace,
    )
    module = importlib.import_module("robofab.interface.all.dialogs")
    assert namespace["dialogs"] is module and namespace["result"] == "42"
    assert namespace["robofab"].interface.all.dialogs is module
    replacement = ModuleType("robofab.interface.all.dialogs")
    sys.modules[module.__name__] = replacement
    try:
        handle.close()
        assert sys.modules[module.__name__] is replacement, (
            "Preserve caller replacement"
        )
        assert "robofab" not in sys.modules, "Remove owned parents on close"
    finally:
        sys.modules.pop(module.__name__, None)


@pytest.mark.parametrize(
    "name", ["robofab", "robofab.interface.all.dialogs", "robofab.foreign"]
)
def test_legacy_when_foreign_module_then_refuse_ordinary_and_scoped_without_changes(
    host, legacy, monkeypatch, name
):
    ordinary_providers(host, legacy)
    foreign = ModuleType(name)
    monkeypatch.setitem(sys.modules, name, foreign)
    with pytest.raises(ImportError, match="robofab"):
        glyport.activate(namespace={})
    ctx, _ = legacy
    with pytest.raises(ImportError, match="robofab"), ctx:
        ctx.import_module("robofab.interface.all.dialogs")
    assert sys.modules[name] is foreign, "Foreign modules must survive failed imports"
    assert not any(n.startswith(ctx.namespace) for n in sys.modules)


def test_legacy_when_activation_binding_fails_then_rollback_and_retry(host, legacy):
    ordinary_providers(host, legacy)
    with pytest.raises(ValueError, match="namespace collision"):
        glyport.activate(namespace={"marker": object()})
    assert not any(n.startswith("robofab") for n in sys.modules)
    handle = glyport.activate(namespace={})
    assert "robofab.interface.all.dialogs" in sys.modules
    handle.close()
    assert not any(n.startswith("robofab") for n in sys.modules)


def test_legacy_when_provider_introduces_foreign_then_failed_activation_preserves_it(
    host, legacy, monkeypatch
):
    gateway = ordinary_providers(host, legacy)
    previous = gateway.adapter_factory
    foreign = ModuleType("robofab.owner")

    def adapters(context, font):
        providers = previous(context, font)
        vanilla = providers["vanilla"]

        def introduce():
            monkeypatch.setitem(sys.modules, "robofab.owner", foreign)
            return vanilla()

        providers["vanilla"] = introduce
        return providers

    gateway.adapter_factory = adapters
    namespace = {}
    with pytest.raises(ImportError, match="robofab.owner"):
        glyport.activate(namespace=namespace)
    assert namespace == {}, "Failed activation must not bind caller exports"
    assert sys.modules["robofab.owner"] is foreign
    assert {n for n in sys.modules if n.startswith("robofab")} == {"robofab.owner"}


@pytest.mark.parametrize("name", ["robofab", "robofab.interface.all.dialogs"])
def test_legacy_when_foreign_added_between_callbacks_then_cached_import_refused(
    legacy, tmp_path, monkeypatch, name
):
    ctx, bridge = legacy
    path = tmp_path / "cached.py"
    path.write_text(
        "def ask():\n"
        "    from robofab.interface.all.dialogs import AskString\n"
        "    return AskString('Cached')\n"
        "first = ask()\n"
    )
    ctx.run(path)
    callback = ctx.wrap(ctx.globals["ask"])
    foreign = ModuleType(name)
    monkeypatch.setitem(sys.modules, name, foreign)
    before = dict(sys.modules)
    namespace = dict(ctx.globals)
    calls = list(bridge.calls)
    with pytest.raises(ImportError, match="robofab"):
        callback()
    assert sys.modules.keys() == before.keys(), "Failed callback restores module keys"
    assert all(sys.modules[n] is m for n, m in before.items())
    assert ctx.globals == namespace, "Refused imports leave caller globals intact"
    assert bridge.calls == calls, "Refuse cached imports before showing any dialog"


@pytest.mark.parametrize("plugin", [False, True])
def test_legacy_when_public_script_or_plugin_then_nested_imports_and_cleanup(
    host, legacy, tmp_path, plugin
):
    from fontlab_glyport.entrypoints import PluginRegistration

    gateway = ordinary_providers(host, legacy)
    bridge = legacy[1]
    bridge.answers["ask_string"] = "native answer"
    root = tmp_path
    path = root / "main.py"
    if plugin:
        path = tmp_path / "Legacy.glyphsPlugin"
        root = path / "Contents/Resources"
        root.mkdir(parents=True)
        (path / "Contents/Info.plist").write_bytes(
            plistlib.dumps({"GlyphsVersion": "3", "PyMainFileNames": ["main.py"]})
        )
        gateway.plugin_installer = lambda context, assessment: PluginRegistration(
            lambda: None, evidence=("fixture:registered",)
        )
    (root / "nested.py").write_text(
        "from robofab.interface.all.dialogs import AskString\n"
        "import importlib\n"
        "assert importlib.import_module('robofab.interface.all.dialogs').AskString is AskString\n"
        "def callback():\n"
        "    from robofab.interface.all import dialogs\n"
        "    return dialogs.AskString('Public')\n"
    )
    (root / "main.py").write_text("from nested import callback\nresult = callback()\n")
    run = glyport.install_plugin if plugin else glyport.run_script
    handle = run(path, profile="glyphs3", host=gateway)
    try:
        assert handle.context.globals["result"] == "native answer"
        bridge.answers["ask_string"] = None
        assert handle.wrap(handle.context.globals["callback"])() is None
    finally:
        handle.close()
    assert not any(n.startswith("robofab") for n in sys.modules)


@pytest.fixture
def native_host_factory(monkeypatch):
    """Real native host/dispatcher; substitute only unavailable native boundaries."""
    from fontlab_glyport import entrypoints
    from fontlab_glyport.glyphsapp import fontlab_session

    calls = []
    pythonqt = ModuleType("PythonQt")
    pythonqt.QtGui = SimpleNamespace(
        QApplication=SimpleNamespace(instance=lambda: object())
    )
    monkeypatch.setitem(sys.modules, "PythonQt", pythonqt)
    monkeypatch.setitem(sys.modules, "fontlab", ModuleType("fontlab"))

    def session(context, **options):
        calls.append((context, options))
        glyphsapp = ModuleType("GlyphsApp")
        glyphsapp.__all__ = []
        return SimpleNamespace(adapters=lambda: {"GlyphsApp": lambda: glyphsapp})

    monkeypatch.setattr(fontlab_session, "FontLabSession", session)
    return entrypoints._native_host, calls


@pytest.mark.parametrize("explicit_font", [False, True])
def test_native_host_factory_when_gui_session_then_interactive_without_injected_answers(
    native_host_factory, tmp_path, explicit_font
):
    from fontlab_glyport.execution import ExecutionContext
    from fontlab_glyport.model.fontlab_backend import OwnedPackage
    from fontlab_glyport.profile_versions import PROFILE_VERSIONS

    factory, calls = native_host_factory
    gateway = factory()
    context = ExecutionContext(tmp_path, "glyphs3")
    font = OwnedPackage(object(), object()) if explicit_font else None
    try:
        providers = gateway.dispatch(lambda: gateway.adapter_factory(context, font))
        assert "GlyphsApp" in providers
        assert calls == [
            (
                context,
                {
                    "version": PROFILE_VERSIONS["glyphs3"],
                    "packages": [font] if font is not None else None,
                    "interactive": True,
                },
            )
        ], "Native GUI sessions must allow real dialogs without injected answers"
    finally:
        context.close()


@pytest.mark.parametrize("route", ["activate", "run_script", "install_plugin"])
def test_native_host_public_contexts_when_constructed_then_keep_gui_dialog_policy(
    native_host_factory, tmp_path, monkeypatch, route
):
    from fontlab_glyport import entrypoints
    from fontlab_glyport.entrypoints import ExecutionOptions, PluginRegistration
    from fontlab_glyport.profile_versions import PROFILE_VERSIONS

    _factory, calls = native_host_factory
    monkeypatch.setattr(
        entrypoints,
        "_native_registrar",
        lambda context, assessment: PluginRegistration(
            lambda: None, evidence=("fixture:registered",)
        ),
    )
    if route == "activate":
        handle = glyport.activate(profile="glyphs3", namespace={}, cocoa_backend="qt")
    else:
        path = tmp_path / "main.py"
        if route == "install_plugin":
            path = tmp_path / "GuiPolicy.glyphsPlugin"
            resources = path / "Contents/Resources"
            resources.mkdir(parents=True)
            (path / "Contents/Info.plist").write_bytes(
                plistlib.dumps({"GlyphsVersion": "3", "PyMainFileNames": ["main.py"]})
            )
            (resources / "main.py").write_text("pass\n")
        else:
            path.write_text("pass\n")
        handle = getattr(glyport, route)(
            path, profile="glyphs3", options=ExecutionOptions(cocoa_backend="qt")
        )
    try:
        assert calls == [
            (
                handle.context,
                {
                    "version": PROFILE_VERSIONS["glyphs3"],
                    "packages": None,
                    "interactive": True,
                },
            )
        ], "Every actual native GUI entrypoint must preserve profile and dialog policy"
        assert handle.context.cocoa_backend == "qt", "Cocoa routing stays explicit"
    finally:
        handle.close()


def test_direct_bridge_when_no_gui_policy_injected_then_noninteractive_default():
    from fontlab_glyport.glyphsapp.fontlab_bridge import FontLabGlyphsBridge

    bridge = FontLabGlyphsBridge(log=lambda text: None, version=(3.2, 3234.0))
    try:
        with pytest.raises(UnsupportedCapability, match="needs a modal dialog"):
            bridge.ask_string("No GUI opt-in", "", "RoboFab", None, None)
    finally:
        bridge.close()
