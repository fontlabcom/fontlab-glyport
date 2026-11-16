# this_file: tests/test_glyphsapp.py
"""GlyphsApp host-services facade against the in-memory bridge double only.

These tests prove the facade's contract, not native FontLab integration.
"""

import subprocess
import sys

import pytest
from glyphsapp_doubles import FakeGlyphsBridge

from fontlab_glyport.errors import UnsupportedAttribute, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import (
    EVENTS,
    glyphsapp_provider,
    make_glyphsapp_module,
)
from fontlab_glyport.model import GSFont, GSPath, Model
from fontlab_glyport.model.fake_backend import FakeBackend

EXPECTED_EVENTS = {
    "UPDATEINTERFACE": "GSUpdateInterface",
    "DRAWBACKGROUND": "DrawBackground",
    "DRAWFOREGROUND": "DrawForeground",
    "DRAWINACTIVE": "DrawInactive",
    "MOUSEMOVED": "mouseMovedNotification",
    "MOUSEDRAGGED": "mouseDraggedNotification",
    "MOUSEDOWN": "mouseDownNotification",
    "MOUSEUP": "mouseUpNotification",
    "DOCUMENTOPENED": "GSDocumentWasOpenedNotification",
    "DOCUMENTACTIVATED": "GSDocumentActivateNotification",
    "DOCUMENTWASSAVED": "GSDocumentWasSavedSuccessfully",
    "DOCUMENTCLOSED": "GSDocumentWillCloseNotification",
    "TABDIDOPEN": "TabDidOpenNotification",
    "TABWILLCLOSE": "TabWillCloseNotification",
}


def _make(backend=None, bridge=None, store=None, wrap=None, errors=None):
    backend = backend or FakeBackend()
    bridge = bridge or FakeGlyphsBridge()
    errors = [] if errors is None else errors
    module = make_glyphsapp_module(
        Model(backend),
        bridge,
        defaults={} if store is None else store,
        wrap=wrap,
        error_sink=lambda exc, event: errors.append((exc, event)),
    )
    return module, bridge, errors


# Module shape ---------------------------------------------------------------


def test_module_when_made_then_exports_glyphs_events_dialogs_and_model():
    module, _, _ = _make()
    for name, value in EXPECTED_EVENTS.items():
        assert getattr(module, name) == value, name
    assert set(EXPECTED_EVENTS.values()) == set(EVENTS)
    dialogs = {
        "Message",
        "AskString",
        "GetFolder",
        "GetSaveFile",
        "GetFile",
        "GetOpenFile",
    }
    model = {"GSFont", "GSFontMaster", "GSGlyph", "GSLayer", "GSPath", "GSNode"}
    model |= {"GSAnchor", "GSComponent"}
    model |= {"GSAxis", "GSInstance", "GSGuide", "GSHint", "GSCustomParameter"}
    model |= {"GSClass", "GSFeature", "GSFeaturePrefix"}
    model |= {"TOPGHOST", "STEM", "BOTTOMGHOST", "GSLTR", "LTR"}
    model |= {"GSLINE", "GSCURVE", "GSOFFCURVE", "GSQCURVE", "GSGlyphsInfo"}
    model |= {"LINE", "CURVE", "OFFCURVE", "QCURVE"}
    model |= {"GSSHARP", "GSSMOOTH", "CAP", "CORNER"}
    model |= {"INSTANCETYPESINGLE", "INSTANCETYPEVARIABLE"}
    model |= {"GSCallbackHandler"}
    model |= {"ONSTATE", "OFFSTATE", "MIXEDSTATE", "WOFF", "WOFF2"}
    model |= {"NSMenuItem"}
    model |= {"NSAffineTransform", "Proxy", "PLAIN", "GSGlyphInfo"}
    model |= {"GSBackgroundImage", "GSBackgroundLayer", "GSEditViewController"}
    model |= {
        "GSScriptingHandler",
        "TTF",
        "OTF",
        "SEGMENT",
        "addPoints",
        "subtractPoints",
        "scalePoint",
        "distance",
        "divideCurve",
        "pointOnLine",
        "pointOnQuadratic",
        "GSAlignmentZone",
    }
    model |= {"GSControlLayer", "GSRTL", "GSBIDI"}  # matrix plain-model (mekkablue)
    model |= {"NSStr"}  # issue 201 triage (SpeedPunk)
    model |= {"GSNoCase", "GSUppercase", "GSLowercase", "GSSmallcaps", "GSMinor"}
    model |= {
        "GSMetricsType" + name
        for name in (
            "Undefined",
            "Ascender",
            "CapHeight",
            "SlantHeight",
            "xHeight",
            "MidHeight",
            "BodyHeight",
            "Descender",
            "Baseline",
            "ItalicAngle",
        )
    }
    menus = {"APP_MENU", "FILE_MENU", "EDIT_MENU", "GLYPH_MENU", "PATH_MENU"}
    menus |= {"FILTER_MENU", "VIEW_MENU", "SCRIPT_MENU", "WINDOW_MENU", "HELP_MENU"}
    expected = {"Glyphs"} | set(EXPECTED_EVENTS) | dialogs | model | menus
    from fontlab_glyport.glyphs_constants import SDK_CONSTANTS

    expected |= set(SDK_CONSTANTS) | {"GSGuideLine"}
    assert set(module.__all__) == expected
    assert module.GSFont is GSFont and module.GSPath is GSPath
    assert module.__name__ == "GlyphsApp" and module.__path__ == []


def test_module_when_unknown_name_then_unsupported_with_caller_location():
    module, _, _ = _make()
    with pytest.raises(UnsupportedCapability) as info:
        module.GSUnimplementedModel  # noqa: B018
    line = sys._getframe().f_lineno - 1
    assert info.value.capability == "GlyphsApp.GSUnimplementedModel"
    assert info.value.location.line == line
    assert info.value.location.path == __file__
    with pytest.raises(AttributeError):
        module.__wrapped__  # noqa: B018 - dunders stay AttributeError


def test_glyphs_when_unknown_member_then_unsupported_with_caller_location():
    module, _, _ = _make()
    with pytest.raises(UnsupportedCapability) as info:
        module.Glyphs.menu  # noqa: B018
    assert info.value.capability == "Glyphs.menu"
    assert info.value.location.line == sys._getframe().f_lineno - 2
    with pytest.raises(UnsupportedCapability) as info:
        module.Glyphs.font = None
    assert info.value.capability == "Glyphs.font"
    with pytest.raises(UnsupportedCapability):
        module.Glyphs.anything = 1


def test_import_when_glyphsapp_imported_then_no_host_or_qt_modules_load():
    code = (
        "import sys\n"
        "import fontlab_glyport.glyphsapp\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "{'fontlab', 'fontgate', 'PythonQt', 'PySide2', 'PyQt5', 'AppKit', 'objc'}]\n"
        "assert not bad, bad\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_package_import_when_loaded_then_glyphsapp_is_not_eager():
    code = "import sys, fontlab_glyport\nprint('fontlab_glyport.glyphsapp' in sys.modules)\n"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert out.stdout.strip() == "False", out.stderr


# Fonts and documents --------------------------------------------------------


def test_font_and_fonts_when_model_has_current_font_then_proxies():
    module, _, _ = _make()
    glyphs = module.Glyphs
    assert isinstance(glyphs.font, GSFont)
    assert glyphs.font.familyName == "Example"
    assert glyphs.font is glyphs.fonts[0]
    assert len(glyphs.fonts) == 1
    assert glyphs.currentDocument.font is glyphs.font


def test_document_selected_layers_when_called_then_font_selection():
    """mekkablue Anchor Mover: Glyphs.currentDocument.selectedLayers()."""
    module, _, _ = _make()
    document = module.Glyphs.currentDocument
    assert document.selectedLayers() == list(document.font.selectedLayers)


def test_font_when_no_current_font_then_none_and_no_document():
    backend = FakeBackend()
    backend.current = None
    module, _, _ = _make(backend=backend)
    assert module.Glyphs.font is None
    assert module.Glyphs.currentDocument is None


def test_document_when_unknown_member_then_unsupported():
    module, _, _ = _make()
    document = module.Glyphs.currentDocument
    with pytest.raises(UnsupportedCapability) as info:
        document.windowController  # noqa: B018
    assert info.value.capability == "GSDocument.windowController"
    with pytest.raises(UnsupportedCapability):
        document.font = None


# Version, output, notifications, redraw ------------------------------------


def test_version_when_read_then_bridge_compatibility_values():
    module, _, _ = _make(bridge=FakeGlyphsBridge(version=(3.3, 3343.0)))
    assert module.Glyphs.versionNumber == 3.3
    assert module.Glyphs.buildNumber == 3343.0


def test_output_calls_when_made_then_reach_bridge_not_stdout(capsys):
    module, bridge, _ = _make()
    stdout = sys.stdout
    assert module.Glyphs.showMacroWindow() is None
    assert module.Glyphs.clearLog() is None
    module.Glyphs.showNotification("Export", "Done")
    module.Glyphs.redraw()
    assert sys.stdout is stdout
    assert capsys.readouterr() == ("", "")
    assert bridge.calls == [
        ("show_macro_window",),
        ("clear_log",),
        ("show_notification", "Export", "Done"),
        ("redraw",),
    ]


# localize -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "table", "expected"),
    [
        ("de", {"en": "Hi", "de": "Hallo"}, "Hallo"),
        ("de-CH", {"en": "Hi", "de-CH": "Grüezi", "de": "Hallo"}, "Grüezi"),
        ("de-CH", {"en": "Hi", "de": "Hallo"}, "Hallo"),
        ("fr", {"de": "Hallo", "en": "Hi"}, "Hi"),
        ("fr", {"de": "Hallo", "es": "Hola"}, "Hallo"),
        ("fr", {}, ""),
    ],
)
def test_localize_when_dict_then_language_primary_en_first_fallbacks(
    language, table, expected
):
    module, _, _ = _make(bridge=FakeGlyphsBridge(language=language))
    assert module.Glyphs.localize(table) == expected


def test_localize_when_string_then_returned_unchanged():
    module, _, _ = _make()
    assert module.Glyphs.localize("Plain") == "Plain"


# defaults -------------------------------------------------------------------


def test_defaults_when_set_read_and_none_then_store_semantics():
    store = {}
    module, _, _ = _make(store=store)
    defaults = module.Glyphs.defaults
    assert defaults["com_x_missing"] is None
    assert defaults.get("com_x_missing", 7) == 7
    defaults["com_x_size"] = 12
    assert store == {"com_x_size": 12}
    assert defaults["com_x_size"] == 12 and defaults.get("com_x_size") == 12
    defaults["com_x_size"] = None
    assert store == {}
    defaults["com_x_size"] = None  # deleting an absent key is harmless
    defaults["com_x_a"] = "v"
    del defaults["com_x_a"]
    del defaults["com_x_a"]
    assert store == {}


def test_defaults_when_key_not_str_then_type_error():
    module, _, _ = _make()
    glyphs = module.Glyphs
    for proxy in (glyphs.defaults, glyphs.boolDefaults, glyphs.intDefaults):
        with pytest.raises(TypeError):
            proxy[1]
        with pytest.raises(TypeError):
            proxy[1] = None


def test_register_default_when_absent_then_set_else_kept():
    store = {"com_x_kept": "user"}
    module, _, _ = _make(store=store)
    glyphs = module.Glyphs
    assert glyphs.registerDefault("com_x_new", 5) is None
    glyphs.registerDefault("com_x_kept", "registered")
    assert store == {"com_x_kept": "user", "com_x_new": 5}


@pytest.mark.parametrize(("key", "value"), [(None, 1), ("com_x", None), ("ab", 1)])
def test_register_default_when_invalid_then_key_error(key, value):
    module, _, _ = _make()
    with pytest.raises(KeyError):
        module.Glyphs.registerDefault(key, value)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, False),
        (True, True),
        (False, False),
        (0, False),
        (2, True),
        (0.0, False),
        (0.5, True),
        ("YES", True),
        ("true", True),
        ("  t", True),
        ("1", True),
        ("0", False),
        ("007", True),
        ("-1", True),
        ("no", False),
        ("", False),
        ([1], False),
    ],
)
def test_bool_defaults_when_read_then_nsuserdefaults_coercion(stored, expected):
    store = {} if stored is None else {"com_x_flag": stored}
    module, _, _ = _make(store=store)
    assert module.Glyphs.boolDefaults["com_x_flag"] is expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, 0),
        (True, 1),
        (False, 0),
        (7, 7),
        (3.9, 3),
        (-3.9, -3),
        (float("nan"), 0),
        (float("inf"), 0),
        ("42", 42),
        ("  -5px", -5),
        ("3.7", 3),
        ("x1", 0),
        ("", 0),
        ([1], 0),
    ],
)
def test_int_defaults_when_read_then_nsuserdefaults_coercion(stored, expected):
    store = {} if stored is None else {"com_x_n": stored}
    module, _, _ = _make(store=store)
    value = module.Glyphs.intDefaults["com_x_n"]
    assert value == expected and type(value) is int


def test_typed_defaults_when_set_then_typed_values_and_none_deletes():
    store = {}
    module, _, _ = _make(store=store)
    glyphs = module.Glyphs
    glyphs.boolDefaults["com_x_flag"] = True
    glyphs.intDefaults["com_x_n"] = 4.8
    assert store == {"com_x_flag": True, "com_x_n": 4}
    assert glyphs.boolDefaults.get("com_x_missing", "d") == "d"
    assert glyphs.intDefaults.get("com_x_missing") is None
    assert glyphs.intDefaults.get("com_x_n") == 4
    glyphs.boolDefaults["com_x_flag"] = None
    glyphs.intDefaults["com_x_n"] = None
    assert store == {}


@pytest.mark.parametrize(
    ("accessor", "value"), [("boolDefaults", 1), ("intDefaults", "3")]
)
def test_typed_defaults_when_wrong_value_type_then_type_error(accessor, value):
    module, _, _ = _make()
    with pytest.raises(TypeError):
        getattr(module.Glyphs, accessor)["com_x_key"] = value


def test_defaults_when_not_injected_then_shared_in_memory_store():
    first = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=print
    )
    second = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=print
    )
    first.Glyphs.defaults["com_glyport_test_shared"] = 1
    try:
        assert second.Glyphs.defaults["com_glyport_test_shared"] == 1
    finally:
        first.Glyphs.defaults["com_glyport_test_shared"] = None


# Callbacks ------------------------------------------------------------------


def test_add_callback_when_registered_then_bridge_token_and_dispatch():
    module, bridge, errors = _make()
    seen = []
    assert module.Glyphs.addCallback(seen.append, module.UPDATEINTERFACE) is None
    assert [ev for ev, _ in bridge.subscriptions.values()] == ["GSUpdateInterface"]
    assert bridge.fire("GSUpdateInterface", "sender") == 1
    assert seen == ["sender"] and errors == []


def test_add_callback_when_raw_event_string_then_accepted():
    module, bridge, _ = _make()
    module.Glyphs.addCallback(print, "GSUpdateInterface")
    assert len(bridge.subscriptions) == 1


def test_add_callback_when_repeated_then_replaced_not_duplicated():
    module, bridge, _ = _make()
    seen = []
    module.Glyphs.addCallback(seen.append, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(seen.append, module.UPDATEINTERFACE)
    assert list(bridge.subscriptions) == ["token-2"]
    assert bridge.removed == ["token-1"]
    bridge.fire("GSUpdateInterface", 1)
    assert seen == [1]


def test_add_callback_when_bound_method_then_removed_by_equality():
    module, bridge, _ = _make()

    class Plugin:
        def __init__(self):
            self.hits = 0

        def update(self, sender=None):
            self.hits += 1

    plugin = Plugin()
    module.Glyphs.addCallback(plugin.update, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(plugin.update, module.DOCUMENTOPENED)
    assert plugin.update is not plugin.update  # fresh bound method each access
    module.Glyphs.removeCallback(plugin.update, module.DOCUMENTOPENED)
    assert [ev for ev, _ in bridge.subscriptions.values()] == ["GSUpdateInterface"]
    module.Glyphs.removeCallback(plugin.update)
    assert bridge.subscriptions == {}
    assert sorted(bridge.removed) == ["token-1", "token-2"]


def test_remove_callback_when_unknown_or_repeated_then_idempotent():
    module, bridge, _ = _make()
    module.Glyphs.removeCallback(print)
    module.Glyphs.addCallback(print, module.MOUSEMOVED)
    module.Glyphs.addCallback(print, module.MOUSEUP)
    module.Glyphs.removeCallback(print, module.MOUSEMOVED)
    module.Glyphs.removeCallback(print, module.MOUSEMOVED)
    module.Glyphs.removeCallback(print, "not-an-event")
    module.Glyphs.removeCallback(print)
    module.Glyphs.removeCallback(print)
    assert bridge.removed == ["token-1", "token-2"]  # bridge strict: no double remove
    assert bridge.subscriptions == {}


def test_add_callback_when_unknown_event_then_unsupported_and_nothing_registered():
    module, bridge, _ = _make()
    with pytest.raises(UnsupportedCapability) as info:
        module.Glyphs.addCallback(print, "GSContextMenuCallbackName")
    assert info.value.capability == "Glyphs.addCallback.GSContextMenuCallbackName"
    assert info.value.location.line == sys._getframe().f_lineno - 2
    assert bridge.subscriptions == {}


def test_add_callback_when_target_not_callable_then_type_error():
    module, bridge, _ = _make()
    with pytest.raises(TypeError):
        module.Glyphs.addCallback("update", module.UPDATEINTERFACE)
    assert bridge.subscriptions == {}


def test_callback_when_raises_then_error_sink_gets_exception_and_event():
    module, bridge, errors = _make()

    def broken(*args):
        raise ValueError("boom")

    module.Glyphs.addCallback(broken, module.DRAWBACKGROUND)
    bridge.fire("DrawBackground", "layer", {"Scale": 1.0})
    assert [(type(e), ev) for e, ev in errors] == [(ValueError, "DrawBackground")]


def test_callback_when_wrap_given_then_called_through_wrap_with_args():
    calls = []

    def wrap(fn):
        def wrapped(*args, **kwargs):
            calls.append(("wrapped", args))
            return fn(*args, **kwargs)

        return wrapped

    module, bridge, _ = _make(wrap=wrap)
    seen = []
    module.Glyphs.addCallback(
        lambda layer, info: seen.append((layer, info)), module.DRAWFOREGROUND
    )
    bridge.fire("DrawForeground", "layer", {"Scale": 2.0})
    assert calls == [("wrapped", ("layer", {"Scale": 2.0}))]
    assert seen == [("layer", {"Scale": 2.0})]


def test_callback_when_wrap_fails_then_error_reaches_sink():
    def wrap(fn):
        def closed(*args):
            raise RuntimeError("Execution context is closed")

        return closed

    module, bridge, errors = _make(wrap=wrap)
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    bridge.fire("GSUpdateInterface", None)
    assert [type(e) for e, _ in errors] == [RuntimeError]


def test_remove_all_callbacks_when_torn_down_then_every_token_removed_once():
    module, bridge, _ = _make()
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(repr, module.TABDIDOPEN)
    module.Glyphs._remove_all_callbacks()
    module.Glyphs._remove_all_callbacks()
    assert bridge.subscriptions == {}
    assert sorted(bridge.removed) == ["token-1", "token-2"]


# Dialogs --------------------------------------------------------------------


def test_message_and_ask_string_when_called_then_bridge_answers():
    module, bridge, _ = _make()
    bridge.answers["ask_string"] = "typed"
    assert module.Message("Hello") is None
    module.Message("Saved", title="Done", OKButton="OK")
    assert (
        module.AskString("Name?", value="A", OKButton="Go", placeholder="name")
        == "typed"
    )
    assert module.AskString("Plain") == "typed"
    assert bridge.calls == [
        ("message", "Hello", "Alert", None),
        ("message", "Saved", "Done", "OK"),
        ("ask_string", "Name?", "A", "Glyphs", "Go", "name"),
        ("ask_string", "Plain", None, "Glyphs", None, None),
    ]


def test_file_dialogs_when_called_then_bridge_receives_normalised_arguments():
    module, bridge, _ = _make()
    bridge.answers.update(
        get_folder="/f", get_open_file=["/a", "/b"], get_save_file="/s.txt"
    )
    assert module.GetFolder("Pick", allowsMultipleSelection=True, path="/p") == "/f"
    assert module.GetOpenFile(message="Open", filetypes=["py"], path="/p") == [
        "/a",
        "/b",
    ]
    # SDK order is (message, title, allowsMultipleSelection, filetypes): this
    # corpus call shape passes True as title and ["json"] as the multiple flag.
    module.GetFile("Template", True, ["json"])
    module.GetSaveFile(message="Save", ProposedFileName="x.txt", filetypes=["txt"])
    module.GetSaveFile("Save", proposedFileName="y.fea")
    module.GetSaveFile("Export", "z.pdf", "pdf")
    module.GetSaveFile(filetype="otf")
    assert bridge.calls == [
        ("get_folder", "Pick", True, "/p"),
        ("get_open_file", "Open", None, False, ["py"], "/p"),
        ("get_open_file", "Template", True, ["json"], None, None),
        ("get_save_file", "Save", "x.txt", ["txt"]),
        ("get_save_file", "Save", "y.fea", None),
        ("get_save_file", "Export", "z.pdf", ["pdf"]),
        ("get_save_file", None, None, ["otf"]),
    ]


def test_get_save_file_when_both_name_spellings_then_type_error():
    module, bridge, _ = _make()
    with pytest.raises(TypeError):
        module.GetSaveFile(ProposedFileName="a", proposedFileName="b")
    assert bridge.calls == []


# ExecutionContext integration ----------------------------------------------


def _script(tmp_path, body):
    path = tmp_path / "main.py"
    path.write_text(body)
    return path


def test_script_when_run_with_provider_then_star_import_print_callback_defaults(
    tmp_path,
):
    bridge, errors = FakeGlyphsBridge(), []
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = glyphsapp_provider(
        Model(FakeBackend()),
        bridge,
        defaults={"com_test_seen": "yes"},
        wrap=ctx.wrap,
        error_sink=lambda exc, event: errors.append(exc),
    )
    body = (
        "from GlyphsApp import *\n"
        "print('font', Glyphs.font.familyName)\n"
        "Glyphs.registerDefault('com_test_size', 12)\n"
        "print('defaults', Glyphs.intDefaults['com_test_size'], Glyphs.defaults['com_test_seen'])\n"
        "Glyphs.clearLog()\n"
        "def update(sender):\n"
        "    print('updated', sender, Glyphs.font.familyName)\n"
        "Glyphs.addCallback(update, UPDATEINTERFACE)\n"
    )
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    assert bridge.fire("GSUpdateInterface", "tab") == 1  # after run() returned
    assert "".join(ctx.output.strings) == (
        "font Example\ndefaults 12 yes\nupdated tab Example\n"
    )
    assert ("clear_log",) in bridge.calls and errors == []
    ctx.close()
    bridge.fire("GSUpdateInterface", "late")
    assert [type(e) for e in errors] == [RuntimeError]


def test_script_when_unknown_import_then_unsupported_at_script_line(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = glyphsapp_provider(
        Model(FakeBackend()), FakeGlyphsBridge(), defaults={}, error_sink=print
    )
    script = _script(tmp_path, "x = 1\nfrom GlyphsApp import GSUnimplementedModel\n")
    with pytest.raises(UnsupportedCapability) as info:
        ctx.run(script)
    assert info.value.capability == "GlyphsApp.GSUnimplementedModel"
    assert (info.value.location.path, info.value.location.line) == (str(script), 2)


def test_script_when_provider_given_then_submodules_stay_placeholders(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = glyphsapp_provider(
        Model(FakeBackend()), FakeGlyphsBridge(), defaults={}, error_sink=print
    )
    script = _script(tmp_path, "from GlyphsApp.plugins import ReporterPlugin\n")
    with pytest.raises(UnsupportedCapability) as info:
        ctx.run(script)
    assert info.value.capability == "GlyphsApp.plugins.ReporterPlugin"


def test_script_when_no_provider_then_default_placeholder_still_raises(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    script = _script(tmp_path, "from GlyphsApp import Glyphs\n")
    with pytest.raises(UnsupportedCapability) as info:
        ctx.run(script)
    assert info.value.capability == "GlyphsApp.Glyphs"


def test_provider_when_called_twice_then_fresh_modules_sharing_defaults():
    store = {}
    provide = glyphsapp_provider(
        Model(FakeBackend()), FakeGlyphsBridge(), defaults=store, error_sink=print
    )
    first, second = provide(), provide()
    assert first is not second and first.Glyphs is not second.Glyphs
    first.Glyphs.defaults["com_x_k"] = 1
    assert second.Glyphs.defaults["com_x_k"] == 1


# Fix round 1 ----------------------------------------------------------------


def test_glyphs_when_attribute_probed_then_hasattr_false_and_getattr_default():
    module, _, _ = _make()
    glyphs = module.Glyphs
    assert hasattr(glyphs, "showPreviewWindow") is False
    assert glyphs.versionString == "3.2"
    assert getattr(glyphs, "appVersion", "?") == "?"
    assert getattr(glyphs, "filters", None) == []
    assert hasattr(glyphs, "font") and hasattr(glyphs, "addCallback")


def test_document_when_attribute_probed_then_hasattr_false_and_getattr_default():
    module, _, _ = _make()
    document = module.Glyphs.currentDocument
    assert hasattr(document, "windowController") is False
    assert getattr(document, "fileURL", "?") == "?"


def test_glyphs_when_unknown_read_uncaught_then_unsupported_attribute_with_line():
    module, _, _ = _make()
    with pytest.raises(UnsupportedCapability) as info:
        module.Glyphs.menu  # noqa: B018
    assert isinstance(info.value, UnsupportedAttribute)
    assert isinstance(info.value, AttributeError)
    assert info.value.code == "UNSUPPORTED_CAPABILITY"
    assert info.value.capability == "Glyphs.menu"
    assert info.value.location.line == sys._getframe().f_lineno - 5
    assert info.value.location.path == __file__


def test_glyphs_when_unknown_read_in_script_then_located_at_script_line(tmp_path):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = glyphsapp_provider(
        Model(FakeBackend()), FakeGlyphsBridge(), defaults={}, error_sink=print
    )
    body = (
        "from GlyphsApp import Glyphs\n"
        "assert not hasattr(Glyphs, 'showPreviewWindow')\n"
        "doc = Glyphs.currentDocument\n"
        "doc.windowController\n"
    )
    script = _script(tmp_path, body)
    with pytest.raises(UnsupportedAttribute) as info:
        ctx.run(script)
    assert info.value.capability == "GSDocument.windowController"
    assert (info.value.location.path, info.value.location.line) == (str(script), 4)


def test_glyphs_when_unknown_write_then_still_plain_unsupported_capability():
    module, _, _ = _make()
    with pytest.raises(UnsupportedCapability) as info:
        module.Glyphs.menu = 1
    assert not isinstance(info.value, AttributeError)


def test_module_when_unknown_name_then_not_attribute_error():
    module, _, _ = _make()
    with pytest.raises(UnsupportedCapability) as info:
        module.GSUnimplementedModel  # noqa: B018
    assert not isinstance(info.value, AttributeError)


class _FlakyRemoveBridge(FakeGlyphsBridge):
    def __init__(self):
        super().__init__()
        self.failures = 1

    def remove(self, token):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("native remove failed")
        super().remove(token)


def test_remove_callback_when_bridge_remove_fails_then_token_kept_for_retry():
    bridge = _FlakyRemoveBridge()
    module, _, _ = _make(bridge=bridge)
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    with pytest.raises(RuntimeError):
        module.Glyphs.removeCallback(print)
    assert list(bridge.subscriptions) == ["token-1"]
    module.Glyphs.removeCallback(print)
    assert bridge.subscriptions == {} and bridge.removed == ["token-1"]


def test_remove_all_when_bridge_remove_fails_then_token_kept_for_retry():
    bridge = _FlakyRemoveBridge()
    module, _, _ = _make(bridge=bridge)
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    with pytest.raises(RuntimeError):
        module.Glyphs._remove_all_callbacks()
    module.Glyphs._remove_all_callbacks()
    assert bridge.subscriptions == {} and bridge.removed == ["token-1"]


def test_callback_when_error_sink_raises_then_propagates_to_host_dispatch():
    bridge = FakeGlyphsBridge()

    def sink(exc, event):
        raise LookupError("sink failed") from exc

    module = make_glyphsapp_module(
        Model(FakeBackend()), bridge, defaults={}, error_sink=sink
    )
    module.Glyphs.addCallback(lambda *a: 1 / 0, module.UPDATEINTERFACE)
    with pytest.raises(LookupError):
        bridge.fire("GSUpdateInterface", None)


@pytest.mark.parametrize(
    ("value", "expected"), [(5, "5"), (None, "None"), (["a"], "['a']")]
)
def test_localize_when_neither_str_nor_dict_then_str_of_value(value, expected):
    module, _, _ = _make()
    assert module.Glyphs.localize(value) == expected


# Context close hooks and model probes (integration task 1) -------------------


def _context(tmp_path, bridge, errors=None):
    ctx = ExecutionContext(tmp_path, "glyphs3")
    sink = (lambda exc, event: errors.append(exc)) if errors is not None else print
    ctx.adapters["GlyphsApp"] = glyphsapp_provider(
        Model(FakeBackend()),
        bridge,
        defaults={},
        wrap=ctx.wrap,
        error_sink=sink,
        on_close=ctx.on_close,
    )
    return ctx


def test_ctx_close_when_callbacks_registered_then_each_removed_exactly_once(tmp_path):
    bridge = FakeGlyphsBridge()
    ctx = _context(tmp_path, bridge)
    body = (
        "from GlyphsApp import Glyphs, UPDATEINTERFACE, TABDIDOPEN\n"
        "def a(*args): pass\n"
        "def b(*args): pass\n"
        "Glyphs.addCallback(a, UPDATEINTERFACE)\n"
        "Glyphs.addCallback(b, TABDIDOPEN)\n"
        "Glyphs.addCallback(a, TABDIDOPEN)\n"
    )
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    assert len(bridge.subscriptions) == 3
    ctx.close()
    ctx.close()
    assert bridge.subscriptions == {}
    assert sorted(bridge.removed) == ["token-1", "token-2", "token-3"]


def test_ctx_close_when_script_raised_after_add_callback_then_still_removed(tmp_path):
    bridge = FakeGlyphsBridge()
    ctx = _context(tmp_path, bridge)
    body = (
        "from GlyphsApp import Glyphs, UPDATEINTERFACE\n"
        "Glyphs.addCallback(print, UPDATEINTERFACE)\n"
        "raise RuntimeError('script failed')\n"
    )
    with pytest.raises(RuntimeError):
        ctx.run(_script(tmp_path, body))
    assert ctx.run(_script(tmp_path, body.replace("raise", "# raise"))).status == (
        "passed"
    )
    assert len(bridge.subscriptions) == 2
    ctx.close()
    assert bridge.subscriptions == {} and len(bridge.removed) == 2


def test_on_close_when_no_callback_added_then_no_hook_registered():
    hooks = []
    module = make_glyphsapp_module(
        Model(FakeBackend()),
        FakeGlyphsBridge(),
        defaults={},
        error_sink=print,
        on_close=hooks.append,
    )
    assert hooks == []
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(repr, module.UPDATEINTERFACE)
    assert len(hooks) == 1
    hooks[0]()
    assert module.Glyphs._tokens == {}


def test_on_close_when_registrar_rejects_then_nothing_subscribed():
    bridge = FakeGlyphsBridge()

    def closed(hook):
        raise RuntimeError("Execution context is closed")

    module = make_glyphsapp_module(
        Model(FakeBackend()), bridge, defaults={}, error_sink=print, on_close=closed
    )
    with pytest.raises(RuntimeError):
        module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    assert bridge.subscriptions == {}


class _FailFirstRemoveBridge(FakeGlyphsBridge):
    def __init__(self):
        super().__init__()
        self.failures = 1

    def remove(self, token):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("native remove failed")
        super().remove(token)


def test_remove_all_when_one_remove_fails_then_others_still_removed():
    bridge = _FailFirstRemoveBridge()
    module, _, _ = _make(bridge=bridge)
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(repr, module.TABDIDOPEN)
    with pytest.raises(RuntimeError):
        module.Glyphs._remove_all_callbacks()
    assert list(bridge.subscriptions) == ["token-1"]
    module.Glyphs._remove_all_callbacks()
    assert bridge.subscriptions == {}
    assert sorted(bridge.removed) == ["token-1", "token-2"]


def test_script_when_model_members_probed_then_hasattr_false(tmp_path):
    ctx = _context(tmp_path, FakeGlyphsBridge())
    body = (
        "from GlyphsApp import Glyphs\n"
        "font = Glyphs.font\n"
        "layer = font.glyphs[0].layers[0]\n"
        "assert not hasattr(font, 'gridLength')\n"
        "assert not hasattr(layer, 'smartComponentPoleMapping')\n"
        "assert getattr(layer, 'leftMetricsKey', None) is None\n"
        "assert hasattr(layer, 'shapes') and hasattr(layer, 'paths')\n"
        "layer.syncMetrics()\n"
    )
    script = _script(tmp_path, body)
    with pytest.raises(UnsupportedAttribute) as info:
        ctx.run(script)
    assert info.value.capability == "GSLayer.syncMetrics"
    assert (info.value.location.path, info.value.location.line) == (str(script), 8)
    ctx.close()


def test_glyphs_property_when_model_raises_attribute_error_then_not_probe_false():
    class BrokenModel:
        @property
        def font(self):
            raise UnsupportedAttribute("probe", capability="GSFont.notAThing")

    module = make_glyphsapp_module(
        BrokenModel(), FakeGlyphsBridge(), defaults={}, error_sink=print
    )
    with pytest.raises(UnsupportedCapability) as info:
        hasattr(module.Glyphs, "font")
    assert info.value.capability == "GSFont.notAThing"
    assert not isinstance(info.value, AttributeError)


# Task 1 review minors (integration task 2) ----------------------------------


def test_add_callback_when_after_ctx_close_then_rejected_and_nothing_subscribed(
    tmp_path,
):
    bridge = FakeGlyphsBridge()
    ctx = _context(tmp_path, bridge)
    body = (
        "from GlyphsApp import Glyphs, UPDATEINTERFACE\n"
        "Glyphs.addCallback(print, UPDATEINTERFACE)\n"
    )
    assert ctx.run(_script(tmp_path, body)).status == "passed"
    glyphs = ctx._modules[ctx.namespace + ".GlyphsApp"].Glyphs
    ctx.close()
    with pytest.raises(RuntimeError, match="closed"):
        glyphs.addCallback(repr, "GSUpdateInterface")
    assert bridge.subscriptions == {}, "closed context must reject a late callback"


def test_remove_all_when_hook_consumed_even_on_failure_then_rehooks_next_add():
    hooks = []
    bridge = _FailFirstRemoveBridge()
    module = make_glyphsapp_module(
        Model(FakeBackend()),
        bridge,
        defaults={},
        error_sink=print,
        on_close=hooks.append,
    )
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    with pytest.raises(RuntimeError):
        hooks[0]()
    module.Glyphs.addCallback(repr, module.UPDATEINTERFACE)
    assert len(hooks) == 2, "a consumed hook must be registered again on next add"


class _ExitFirstRemoveBridge(FakeGlyphsBridge):
    def __init__(self):
        super().__init__()
        self.exits = 1

    def remove(self, token):
        if self.exits:
            self.exits -= 1
            raise SystemExit(3)
        super().remove(token)


def test_remove_all_when_remove_exits_then_others_attempted_and_exit_reraised():
    bridge = _ExitFirstRemoveBridge()
    module, _, _ = _make(bridge=bridge)
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(repr, module.TABDIDOPEN)
    with pytest.raises(SystemExit):
        module.Glyphs._remove_all_callbacks()
    assert list(bridge.subscriptions) == ["token-1"], "token-2 must still be removed"


class _ExitThenFailBridge(FakeGlyphsBridge):
    def remove(self, token):
        raise RuntimeError("fail") if token == "token-1" else SystemExit(4)


def test_remove_all_when_error_then_exit_then_exit_is_reraised_first():
    module, _, _ = _make(bridge=_ExitThenFailBridge())
    module.Glyphs.addCallback(print, module.UPDATEINTERFACE)
    module.Glyphs.addCallback(repr, module.TABDIDOPEN)
    with pytest.raises(SystemExit):
        module.Glyphs._remove_all_callbacks()


def test_dialog_paths_when_returned_then_nsstring_path_methods():
    """Glyphs returns NSString paths; ExportCSV calls Glyphs' dotSuffix helpers."""
    module, bridge, _ = _make()
    bridge.answers.update(
        get_save_file="/out/Glyph info.csv", get_open_file=["/a/b.ufo"], get_folder=None
    )
    path = module.GetSaveFile("Save")
    assert path == "/out/Glyph info.csv" and isinstance(path, str)
    assert (path.stringByDeletingDotSuffix(), path.dotSuffix()) == (
        "/out/Glyph info",
        ".csv",
    )
    assert (path.lastPathComponent(), path.pathExtension()) == ("Glyph info.csv", "csv")
    assert path.stringByDeletingLastPathComponent() == "/out"
    assert path.stringByAppendingString_("x") == "/out/Glyph info.csvx"
    assert module.GetOpenFile()[0].stringByDeletingPathExtension() == "/a/b"
    assert module.GetFolder() is None, "cancel stays None"


def test_constants_and_host_info_when_imported_then_glyphs_values(
    monkeypatch, tmp_path
):
    """R049: node types (Anchor Mover, Angularizzle), metric types (Anchor
    Mover), GSGlyphsInfo (EOD) and GSScriptingHandler (fontc export)."""
    module, _, _ = _make()
    assert (module.GSLINE, module.GSCURVE, module.GSOFFCURVE, module.GSQCURVE) == (
        "line",
        "curve",
        "offcurve",
        "qcurve",
    )
    assert (module.GSMetricsTypeAscender, module.GSMetricsTypexHeight) == (1, 4)
    assert (module.GSMetricsTypeBaseline, module.GSMetricsTypeItalicAngle) == (8, 9)
    monkeypatch.setenv("GLYPORT_DEFAULTS", str(tmp_path / "glyport" / "defaults.json"))
    assert module.GSGlyphsInfo.applicationSupportPath() == str(tmp_path / "glyport")
    python = module.GSScriptingHandler.sharedHandler().currentPythonPath()
    import sys

    assert python == sys.base_prefix
