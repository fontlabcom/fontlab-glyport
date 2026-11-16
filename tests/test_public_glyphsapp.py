# this_file: tests/test_public_glyphsapp.py
"""Direct public imports share the execution facade without eager host imports."""

import importlib
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import GlyportError
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def public(monkeypatch):
    module = importlib.import_module("fontlab_glyport.GlyphsApp")
    from fontlab_glyport.GlyphsApp import _binding

    monkeypatch.setattr(_binding, "_default", None)
    monkeypatch.setattr(_binding, "_context", None)
    monkeypatch.setattr(_binding, "_backend", None)
    monkeypatch.setattr(_binding, "_dispatch", None)
    yield module


def test_import_is_cheap_and_no_host_access_is_clear():
    code = """
import sys
class NoHost:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'fontlab', 'fontgate', 'PythonQt', 'AppKit'}:
            raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, NoHost())
import fontlab_glyport.GlyphsApp as public
assert 'Glyphs' in dir(public)
assert 'fontlab_glyport.glyphsapp' not in sys.modules
assert not {'fontlab', 'fontgate', 'PythonQt'} & sys.modules.keys()
from fontlab_glyport.errors import HostUnavailable
try:
    public.Glyphs
except HostUnavailable as error:
    assert 'use_backend' in str(error)
else:
    raise AssertionError('a host-free import must not fabricate a session')
from fontlab_glyport.model.fake_backend import FakeBackend
public.use_backend(FakeBackend())
from fontlab_glyport.GlyphsApp import *
assert Glyphs.font.familyName == 'Example'
assert not {'fontlab', 'fontgate', 'PythonQt'} & sys.modules.keys()
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        env={**os.environ, "PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_public_exports_match_factory_and_backend_is_retained(public):
    from glyphsapp_doubles import FakeGlyphsBridge

    from fontlab_glyport.glyphsapp import make_glyphsapp_module
    from fontlab_glyport.model import Model

    backend = FakeBackend()
    public.use_backend(backend)
    expected = make_glyphsapp_module(
        Model(backend), FakeGlyphsBridge(), error_sink=lambda *args: None
    )
    assert set(public.__all__) == set(expected.__all__)
    assert set(expected.__all__) <= set(dir(public))
    for name in expected.__all__:
        assert getattr(public, name) is not None, name
    assert public.Glyphs is public.Glyphs
    assert public.Glyphs.font.familyName == "Example"
    assert public.Glyphs.versionNumber == 4.1
    public.use_backend(backend)
    with pytest.raises(GlyportError, match="already bound"):
        public.use_backend(FakeBackend())
    plugins = importlib.import_module("fontlab_glyport.GlyphsApp.plugins")
    from fontlab_glyport.plugins import base

    for cls in base.PLUGIN_CLASSES:
        assert getattr(plugins, cls.__name__) is cls


def test_existing_activation_is_the_single_source(public, monkeypatch):
    from fontlab_glyport import bootstrap

    glyphs, node = object(), object()
    module = SimpleNamespace(Glyphs=glyphs, GSNode=node, __all__=["Glyphs", "GSNode"])
    monkeypatch.setattr(
        bootstrap,
        "_active",
        SimpleNamespace(modules={"GlyphsApp": module}, closed=False),
    )
    assert public.Glyphs is glyphs and public.GSNode is node
    with pytest.raises(GlyportError):
        public.use_backend(FakeBackend())


def test_unknown_names_and_profile_fail_before_binding(public):
    with pytest.raises(ValueError, match="profile"):
        public.use_backend(FakeBackend(), profile="missing")
    with pytest.raises(AttributeError):
        _ = public.__not_a_name__
    with pytest.raises(TypeError, match="ModelBackend"):
        public.use_backend(object())


def test_activate_refuses_an_independent_public_session(public, monkeypatch):
    from fontlab_glyport import bootstrap, entrypoints

    public.use_backend(FakeBackend())
    monkeypatch.setattr(
        entrypoints, "_native_host", lambda: pytest.fail("host touched")
    )
    with pytest.raises(GlyportError, match="public"):
        bootstrap.activate(namespace={})


def test_default_host_session_is_built_once(public, monkeypatch):
    from glyphsapp_doubles import FakeGlyphsBridge

    from fontlab_glyport import entrypoints
    from fontlab_glyport.glyphsapp import make_glyphsapp_module
    from fontlab_glyport.model import Model

    contexts = []
    module = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    )

    def adapters(context, font):
        contexts.append(context)
        return {"GlyphsApp": lambda: module}

    host = SimpleNamespace(
        sink=None,
        dispatch=lambda call: call(),
        current_font=lambda: None,
        adapter_factory=adapters,
    )
    monkeypatch.setattr(entrypoints, "_native_host", lambda: host)
    assert public.Glyphs is module.Glyphs
    assert public.Glyphs is module.Glyphs
    assert len(contexts) == 1 and contexts[0].profile == "glyphs4"
    contexts[0].close()


def test_real_activation_shares_exports_and_plugin_classes(public, monkeypatch):
    from types import ModuleType

    from glyphsapp_doubles import FakeGlyphsBridge

    from fontlab_glyport import bootstrap, entrypoints
    from fontlab_glyport.glyphsapp import make_glyphsapp_module
    from fontlab_glyport.model import Model

    module = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    )
    plugins = ModuleType("GlyphsApp.plugins")
    plugins.ReporterPlugin = object()
    host = SimpleNamespace(
        sink=None,
        dispatch=lambda call: call(),
        current_font=lambda: None,
        adapter_factory=lambda *args: {
            "GlyphsApp": lambda: module,
            "GlyphsApp.plugins": lambda: plugins,
        },
    )
    monkeypatch.setattr(entrypoints, "_native_host", lambda: host)
    namespace = {}
    handle = bootstrap.activate(namespace=namespace)
    try:
        assert public.Glyphs is namespace["Glyphs"] is sys.modules["GlyphsApp"].Glyphs
        child = importlib.import_module("fontlab_glyport.GlyphsApp.plugins")
        assert child.ReporterPlugin is plugins.ReporterPlugin
    finally:
        handle.close()


def test_plugins_when_unknown_name_then_attribute_error(public):
    plugins = importlib.import_module("fontlab_glyport.GlyphsApp.plugins")
    with pytest.raises(AttributeError):
        _ = plugins.NotAPlugin


def test_plugins_when_public_session_bound_then_session_plugins_are_cached(
    public, monkeypatch
):
    plugins = importlib.import_module("fontlab_glyport.GlyphsApp.plugins")
    from fontlab_glyport.GlyphsApp import _binding

    made = []
    session_plugins = SimpleNamespace(ReporterPlugin=object(), GeneralPlugin=object())

    def plugins_module():
        made.append(1)
        return session_plugins

    context = SimpleNamespace(
        fontlab_session=SimpleNamespace(_plugins_module=plugins_module)
    )
    monkeypatch.setattr(_binding, "facade", lambda: None)
    monkeypatch.setattr(_binding, "_active", lambda: None)
    monkeypatch.setattr(_binding, "_context", context)
    assert plugins.ReporterPlugin is session_plugins.ReporterPlugin
    assert plugins.GeneralPlugin is session_plugins.GeneralPlugin
    assert made == [1], "the session's plugins module is built once and reused"


def test_dir_when_no_host_then_lists_exports_without_binding(public, monkeypatch):
    from fontlab_glyport import entrypoints

    monkeypatch.setattr(
        entrypoints, "_native_host", lambda: pytest.fail("host touched")
    )
    names = dir(public)
    assert {"Glyphs", "GSNode", "GSOFFCURVE", "UPDATEINTERFACE", "unbind"} <= set(names)
    from fontlab_glyport.GlyphsApp import _binding

    assert _binding._default is None


def test_unbind_when_backend_was_bound_then_activation_can_start(public, monkeypatch):
    from types import ModuleType

    from fontlab_glyport import bootstrap, entrypoints

    public.use_backend(FakeBackend())
    with pytest.raises(GlyportError, match="unbind"):
        bootstrap.activate(namespace={})
    public.unbind()
    public.unbind()
    module = ModuleType("GlyphsApp")
    module.__path__, module.__all__ = [], []
    host = SimpleNamespace(
        sink=None,
        dispatch=lambda call: call(),
        current_font=lambda: None,
        adapter_factory=lambda *args: {"GlyphsApp": lambda: module},
    )
    monkeypatch.setattr(entrypoints, "_native_host", lambda: host)
    handle = bootstrap.activate(namespace={})
    try:
        public.unbind()
        assert not handle.closed, "Unbind must not close an independent activation"
    finally:
        handle.close()


def test_unbind_when_native_context_exists_then_closes_and_forgets_it(
    public, monkeypatch
):
    from fontlab_glyport.GlyphsApp import _binding

    closed = []
    monkeypatch.setattr(_binding, "_default", object())
    monkeypatch.setattr(
        _binding, "_context", SimpleNamespace(close=lambda: closed.append(True))
    )
    public.unbind()
    assert closed == [True]
    assert _binding._default is None and _binding._context is None


def test_public_access_when_released_then_activation_can_start(public, monkeypatch):
    from types import ModuleType

    from fontlab_glyport import bootstrap, entrypoints

    contexts = []

    def adapters(context, font):
        contexts.append(context)
        module = ModuleType("GlyphsApp")
        module.__path__, module.__all__ = [], ["Glyphs"]
        module.Glyphs = SimpleNamespace(font=None)
        return {"GlyphsApp": lambda: module}

    host = SimpleNamespace(
        sink=None,
        dispatch=lambda call: call(),
        current_font=lambda: None,
        adapter_factory=adapters,
    )
    monkeypatch.setattr(entrypoints, "_native_host", lambda: host)
    first = public.Glyphs
    with pytest.raises(GlyportError, match="unbind"):
        bootstrap.activate(namespace={})
    public.unbind()
    assert len(contexts) == 1
    handle = bootstrap.activate(namespace={})
    try:
        assert len(contexts) == 2
        assert public.Glyphs is not first
    finally:
        handle.close()
