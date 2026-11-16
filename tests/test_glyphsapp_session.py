# this_file: tests/test_glyphsapp_session.py
"""L1/L2/L3 integration wiring (issue 104 merge), against doubles.

Passing here is not native evidence; the merge drivers in the parent evidence
(glyport-merge/) are.
"""

import sys
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedAttribute, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.glyphsapp.fontlab_session import (
    FontLabSession,
    ModelPluginAdapter,
    layer_resolver,
)
from fontlab_glyport.model import GSAnchor, GSNode, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.plugins.host import AFTER_NATIVE_LAYER, MENUS


class Painters:
    """EditorPainters double: records registrations."""

    def __init__(self):
        self.registered, self.removed = {}, []

    def register(self, phase, callback, layer_filter="active", *, document_id=None):
        token = len(self.registered) + 1
        self.registered[token] = (phase, callback, layer_filter)
        return token

    def remove(self, token):
        self.removed.append(token)
        self.registered.pop(token, None)


@contextmanager
def no_scope(context):
    yield


def _bridge(painters):
    from fontlab_glyport.glyphsapp.fontlab_bridge import FontLabGlyphsBridge

    return FontLabGlyphsBridge(
        log=lambda text: None,
        version=(3.2, 3234.0),
        painters=lambda: painters,
        paint_scope=no_scope,
    )


# --- Glyphs.menu and *_MENU -------------------------------------------------------


def test_glyphs_menu_when_given_then_exposed_and_menu_constants_exported():
    menu = object()
    module = make_glyphsapp_module(
        None, object(), defaults={}, error_sink=print, menu=menu
    )
    assert module.Glyphs.menu is menu
    for name in MENUS:
        assert getattr(module, name) == name


def test_glyphs_menu_when_no_host_then_unsupported_probe():
    module = make_glyphsapp_module(None, object(), defaults={}, error_sink=print)
    with pytest.raises(UnsupportedAttribute):
        _ = module.Glyphs.menu
    assert not hasattr(module.Glyphs, "menu")


# --- DRAWFOREGROUND / DRAWBACKGROUND -----------------------------------------------


def test_drawforeground_when_subscribed_then_after_native_layer_painter():
    painters = Painters()
    bridge = _bridge(painters)
    calls = []
    token = bridge.subscribe("DrawForeground", lambda *args: calls.append(args))
    ((phase, paint, layer_filter),) = painters.registered.values()
    assert (phase, layer_filter) == (AFTER_NATIVE_LAYER, "active")
    paint(SimpleNamespace(layer="L", scale=2.0))
    assert calls == [("L", {"Scale": 2.0, "Black": False})]
    bridge.remove(token)
    assert painters.removed == [1] and painters.registered == {}


def test_drawbackground_when_subscribed_then_overlay_fallback_registered():
    painters = Painters()
    bridge = _bridge(painters)
    token = bridge.subscribe("DrawBackground", print)
    assert painters.registered[1][0] == AFTER_NATIVE_LAYER
    bridge.remove(token)
    assert not painters.registered


def test_drawbackground_when_native_painters_then_before_phase_no_overlay_note():
    painters = Painters()
    painters.supports_before_native = True
    notes = []
    bridge = _bridge(painters)
    bridge._diagnostic_sink = notes.append
    token = bridge.subscribe("DrawBackground", print)
    assert painters.registered[1][0] == "before_native_layer" and notes == []
    bridge.remove(token)
    assert not painters.registered


def test_drawforeground_when_bridge_closes_then_painters_removed():
    painters = Painters()
    bridge = _bridge(painters)
    bridge.subscribe("DrawForeground", print)
    bridge.close()
    assert painters.registered == {}


# --- model adapter and layer resolver ----------------------------------------------


def test_model_adapter_when_snapshot_and_restore_then_layer_back():
    model = Model(FakeBackend())
    adapter = ModelPluginAdapter(model)
    font = model.font
    layer = font.glyphs["A"].layers[0]
    assert adapter.current_font() is font
    snapshot = adapter.snapshot_layer(layer)
    layer.width = 900
    layer.paths.append(GSPath([GSNode((1, 2)), GSNode((3, 4))]))
    layer.anchors.append(GSAnchor("top", (5, 6)))
    adapter.restore_layer(layer, snapshot)
    assert layer.width == 500 and len(layer.paths) == 1
    assert [n.position for n in layer.paths[0].nodes] == [(0, 0)]
    with adapter.undo_group("x"):
        layer.width = 501
    assert font._model._backend.undo_events[-2:] == [("begin", "x"), ("end", None)]


def test_model_adapter_when_no_font_then_empty_selection():
    backend = FakeBackend()
    backend.current = None
    adapter = ModelPluginAdapter(Model(backend))
    assert adapter.selected_layers() == [] and adapter.current_font() is None


def test_layer_resolver_when_glyph_info_then_model_layer_of_active_master():
    model = Model(FakeBackend())

    class Backend:
        def font_id_for(self, package):
            return "font" if package == "pkg" else None

    info = SimpleNamespace(
        glyph=SimpleNamespace(
            name="A", package="pkg", activeLayer=SimpleNamespace(name="Regular")
        )
    )
    resolve = layer_resolver(model, Backend())
    assert resolve(info) is model.font.glyphs["A"].layers[0]
    # R-merge P2: a non-master active layer ("Sketch") and a missing active
    # layer fall back to the font's current master.
    package = SimpleNamespace(master="Regular")

    class PackageBackend:
        def font_id_for(self, value):
            return "font" if value is package else None

    resolve_package = layer_resolver(model, PackageBackend())
    for active in (SimpleNamespace(name="Sketch"), None):
        glyph = SimpleNamespace(name="A", package=package, activeLayer=active)
        assert (
            resolve_package(SimpleNamespace(glyph=glyph))
            is model.font.glyphs["A"].layers[0]
        )
    stranger = SimpleNamespace(glyph=SimpleNamespace(name="A", package="other"))
    assert resolve(stranger) is None
    assert resolve(SimpleNamespace()) is None, "never raises inside paintEvent"


# --- session adapters and plugin registration --------------------------------------


def _session(tmp_path):
    qtcore = SimpleNamespace(QTimer=object, QObject=object)
    qtgui = SimpleNamespace(QWidget=object)
    qt = SimpleNamespace(QtCore=qtcore, QtGui=qtgui)
    ctx = ExecutionContext(tmp_path, "glyphs3")
    session = FontLabSession(
        ctx,
        version=(3.2, 3234.0),
        packages=[],
        defaults={},
        qt=qt,
        fontlab=ModuleType("fontlab"),
    )
    ctx.adapters.update(session.adapters())
    return ctx, session


def test_session_adapters_when_imported_then_l2_names_and_l3_values(tmp_path):
    ctx, _ = _session(tmp_path)
    for name in (
        "GlyphsApp",
        "GlyphsApp.plugins",
        "vanilla",
        "vanilla.dialogs",
        "AppKit",
        "Foundation",
        "Cocoa",
        "objc",
    ):
        assert name in ctx.adapters, name
    (tmp_path / "main.py").write_text(
        "from GlyphsApp import Glyphs, EDIT_MENU\n"
        "from GlyphsApp.plugins import ReporterPlugin\n"
        "from AppKit import NSColor, NSBezierPath, NSMenuItem, NSView, NSEvent\n"
        "from Foundation import NSMakeRect, NSZeroRect, NSRange\n"
        "from AppKit import NSOnState, NSOffState, NSSwitchButton, NSViewWidthSizable\n"
        "import objc\n"
        "assert objc.lookUpClass('NSView') is NSView\n"
        "assert Glyphs.menu[EDIT_MENU] is not None\n"
        "result = [ReporterPlugin.__module__, NSMakeRect(1, 2, 3, 4)]\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    assert ctx.globals["result"][0] == "GlyphsApp.plugins"
    ctx.close()


def test_session_appkit_when_unknown_name_then_located_unsupported(tmp_path):
    ctx, _ = _session(tmp_path)
    (tmp_path / "main.py").write_text("from AppKit import NSWorkspace\n")
    with pytest.raises(UnsupportedCapability) as info:
        ctx.run(tmp_path / "main.py")
    assert info.value.capability == "AppKit.NSWorkspace"
    ctx.close()


def test_register_plugin_when_principal_class_then_loader_handle(tmp_path):
    from fontlab_glyport.entrypoints import PluginRegistration
    from fontlab_glyport.plugins import register_plugin

    ctx, session = _session(tmp_path)
    calls = []

    class Host:
        def register_menu(self, menu, item, index=None):
            calls.append(("menu", menu, item.title()))
            return 7

        def remove(self, token):
            calls.append(("remove", token))

        def redraw(self):
            pass

        def close(self):
            calls.append(("close",))

    session._plugin_host = Host()
    (tmp_path / "main.py").write_text(
        "from GlyphsApp import Glyphs, EDIT_MENU\n"
        "from GlyphsApp.plugins import GeneralPlugin\n"
        "from AppKit import NSMenuItem\n"
        "class Hello(GeneralPlugin):\n"
        "    def settings(self):\n"
        "        self.name = 'Hello'\n"
        "    def start(self):\n"
        "        Glyphs.menu[EDIT_MENU].append(NSMenuItem('Say Hello', self.hi_))\n"
        "    def hi_(self, sender):\n"
        "        pass\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    assessment = SimpleNamespace(principal_class="Hello")
    with ctx:
        registration = register_plugin(ctx, assessment)
    assert isinstance(registration, PluginRegistration)
    assert registration.evidence and "GeneralPlugin" in registration.evidence[0]
    assert type(registration.plugin).__name__ == "Hello"
    assert ("menu", "EDIT_MENU", "Say Hello") in calls
    registration.unload()
    assert ("remove", 7) in calls
    ctx.close()
    assert calls[-1] == ("close",)


def test_register_plugin_when_no_session_then_unsupported(tmp_path):
    from fontlab_glyport.plugins import register_plugin

    ctx = ExecutionContext(tmp_path, "glyphs3")
    with pytest.raises(UnsupportedCapability):
        register_plugin(ctx, SimpleNamespace(principal_class=None))


def test_register_plugin_when_class_missing_or_ambiguous_then_unsupported(tmp_path):
    from fontlab_glyport.plugins import register_plugin

    ctx, _ = _session(tmp_path)
    with pytest.raises(UnsupportedCapability):
        register_plugin(ctx, SimpleNamespace(principal_class="Nope"))
    with pytest.raises(UnsupportedCapability):
        register_plugin(ctx, SimpleNamespace(principal_class=None))
    ctx.close()


def test_glyphsapp_module_unchanged_without_session(monkeypatch):
    monkeypatch.delitem(sys.modules, "PythonQt", raising=False)
    module = make_glyphsapp_module(None, object(), defaults={}, error_sink=print)
    assert module.EDIT_MENU == "EDIT_MENU"


def test_register_plugin_when_principal_class_not_a_plugin_then_typed_failure(
    tmp_path,
):
    from fontlab_glyport.plugins import register_plugin

    ctx, _ = _session(tmp_path)
    (tmp_path / "main.py").write_text("class Fixture:\n    pass\n")
    assert ctx.run(tmp_path / "main.py").status == "passed"
    with pytest.raises(UnsupportedCapability) as info:
        register_plugin(ctx, SimpleNamespace(principal_class="Fixture"))
    assert info.value.capability == "plugin:principal-class"
    ctx.close()


def test_session_geometry_when_imported_then_one_consistent_implementation(tmp_path):
    """Review R-merge P2: constructors, types and zero values agree in every
    Cocoa module of a session context."""
    ctx, _ = _session(tmp_path)
    (tmp_path / "geometry.py").write_text(
        "import AppKit, Foundation, Cocoa\n"
        "checks = []\n"
        "for m in (AppKit, Foundation, Cocoa):\n"
        "    p, s, r = m.NSMakePoint(1, 2), m.NSMakeSize(3, 4), m.NSMakeRect(1, 2, 3, 4)\n"
        "    checks += [isinstance(p, m.NSPoint), isinstance(s, m.NSSize), isinstance(r, m.NSRect),\n"
        "               isinstance(r.origin, m.NSPoint), isinstance(r.size, m.NSSize),\n"
        "               m.NSZeroPoint == m.NSMakePoint(0, 0), m.NSZeroSize == m.NSMakeSize(0, 0),\n"
        "               m.NSZeroRect == m.NSMakeRect(0, 0, 0, 0), isinstance(m.NSZeroRect, m.NSRect),\n"
        "               m.NSPoint is AppKit.NSPoint, m.NSRect is AppKit.NSRect,\n"
        "               m.NSPoint(5, 6) == m.NSMakePoint(5, 6), r == ((1, 2), (3, 4))]\n"
    )
    assert ctx.run(tmp_path / "geometry.py").status == "passed"
    assert all(ctx.globals["checks"]), ctx.globals["checks"]
    ctx.close()


def test_session_foundation_names_when_imported_then_shared_defaults_and_values(
    tmp_path,
):
    """Matrix plain-model (mekkablue) and others import these at module level;
    NSUserDefaults and Glyphs.defaults share the session's store."""
    ctx, session = _session(tmp_path)
    (tmp_path / "names.py").write_text(
        "from AppKit import NSUserDefaults, NSImageLeading, NSLineBreakByClipping, "
        "NSPasteboard, NSStringPboardType, NSTimer\n"
        "from Foundation import NSClassFromString, NSHeight, NSMutableSet, "
        "NSMutableOrderedSet, NSArray, NSMaxXEdge, NSMakeRect\n"
        "from GlyphsApp import Glyphs, GSUppercase, GSLowercase, GSSmallcaps, GSMinor, "
        "GSNoCase, GSControlLayer\n"
        "Glyphs.registerDefault('t.flag', True)\n"
        "Glyphs.defaults['t.size'] = '12'\n"
        "d = NSUserDefaults.standardUserDefaults()\n"
        "values = [d.boolForKey_('t.flag'), d.integerForKey_('t.size'),\n"
        "          NSHeight(NSMakeRect(0, 0, 5, 7)), NSClassFromString('NSMenuItem') is not None,\n"
        "          NSClassFromString('GSAddParameterViewController'),\n"
        "          (GSNoCase, GSUppercase, GSLowercase, GSSmallcaps, GSMinor),\n"
        "          GSControlLayer.newline().char]\n"
    )
    assert ctx.run(tmp_path / "names.py").status == "passed"
    assert ctx.globals["values"] == [True, 12, 7.0, True, None, (0, 1, 2, 3, 4), 10]
    assert session.defaults["t.flag"] is True
    ctx.close()


def test_session_when_glyphsapp_ui_imported_then_glyph_view_on_the_sessions_vanilla(
    tmp_path,
):
    """Matrix general-plugin: from GlyphsApp.UI import GlyphView."""
    ctx, _ = _session(tmp_path)
    (tmp_path / "ui.py").write_text(
        "import vanilla\nfrom GlyphsApp.UI import GlyphView\n"
        "ok = issubclass(GlyphView, vanilla.VanillaBaseObject)\n"
    )
    assert ctx.run(tmp_path / "ui.py").status == "passed"
    assert ctx.globals["ok"] is True
    ctx.close()
