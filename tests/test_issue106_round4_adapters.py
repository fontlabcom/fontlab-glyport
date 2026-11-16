# this_file: tests/test_issue106_round4_adapters.py
"""Adapter import and bootstrap regressions from real-use tickets."""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from glyphsapp_doubles import FakeGlyphsBridge
from ui_doubles_session import make_session

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend


def test_f5_current_font_when_font_closed_then_alias_reads_none():
    backend = FakeBackend()
    app = make_glyphsapp_module(
        Model(backend), FakeGlyphsBridge(), error_sink=lambda *a: None
    ).Glyphs
    assert app.currentFont is app.font
    backend.close_font("font")
    assert app.currentFont is None


def test_f6_script_bootstrap_when_font_and_layer_change_then_globals_are_refreshed(
    tmp_path,
):
    ctx, session = make_session(tmp_path)
    ctx.implicit_imports = ("GlyphsApp",)
    session.backend.current_layer_data["font"] = (("A", "Regular"),)
    script = tmp_path / "menu.py"
    script.write_text("seen = (Font, Layer, Glyphs.font)\n")
    ctx.run(script)
    assert ctx.globals["seen"] == (
        session.model.font,
        session.model.font.selectedLayers[0],
        session.model.font,
    )
    session.backend.close_font("font")
    ctx.run(script)
    assert ctx.globals["seen"] == (None, None, None)
    ctx.close()


def test_f13_glyph_info_when_font_has_data_then_global_metadata_and_components(
    tmp_path,
    owned_composition_info,
):
    ctx, _ = make_session(tmp_path)
    with ctx:
        app = ctx.import_module("GlyphsApp").Glyphs
        info = app.glyphInfoForName("A")
        assert (info.name, info.unicode, info.category, info.subCategory) == (
            "A",
            "0041",
            "Letter",
            None,
        )
        assert info.components == [], (
            "Active-font self-components are not global GlyphData"
        )
        assert [item.name for item in app.glyphInfoForName("Aacute").components] == [
            "A",
            "acutecomb",
        ]
        assert app.glyphInfoForName("missing-in-font-data") is None, (
            "A qualified missing record returns nil from the selected manager"
        )
    ctx.close()


@pytest.mark.parametrize("explicit_none", [False, True])
def test_glyph_info_global_lookup_ignores_active_font_metadata(
    monkeypatch, explicit_none, owned_composition_info
):
    app = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    ).Glyphs
    local = SimpleNamespace(
        name="A", unicode="0042", category="Symbol", subCategory="Other", layers=[]
    )
    before = vars(local).copy()
    monkeypatch.setattr(
        type(app), "font", property(lambda self: SimpleNamespace(glyphs={"A": local}))
    )
    info = (
        app.glyphInfoForName("A", font=None)
        if explicit_none
        else app.glyphInfoForName("A")
    )
    assert (info.name, info.unicode, info.category, info.subCategory) == (
        "A",
        "0041",
        "Letter",
        None,
    )
    assert info.components == []
    assert vars(local) == before, (
        "Metadata lookup must not repair or mutate the active glyph"
    )


def test_glyph_info_global_lookup_does_not_read_unavailable_active_font(monkeypatch):
    app = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    ).Glyphs

    def unavailable(self):
        raise AssertionError("Global metadata must not read the active font")

    monkeypatch.setattr(type(app), "font", property(unavailable))
    assert app.glyphInfoForName("A").unicode == "0041"
    assert app.glyphInfoForName("A", None).unicode == "0041"


@pytest.mark.parametrize("keyword", [False, True])
def test_glyph_info_explicit_local_font_refuses_before_lookup(monkeypatch, keyword):
    import fontlab_glyport.glyphsapp.glyph_info as metadata

    app = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    ).Glyphs
    monkeypatch.setattr(
        metadata,
        "glyph_info",
        lambda *args: pytest.fail(
            "Local lookup must not substitute global or outline metadata"
        ),
    )
    with pytest.raises(TypeError, match="font must be a GSFont or None, not object"):
        if keyword:
            app.glyphInfoForName("A", font=object())
        else:
            app.glyphInfoForName("A", object())


def test_glyph_info_global_dependency_failure_remains_visible(monkeypatch):
    import fontlab_glyport.glyphsapp.glyph_info as metadata

    app = make_glyphsapp_module(
        Model(FakeBackend()), FakeGlyphsBridge(), error_sink=lambda *args: None
    ).Glyphs
    failure = UnsupportedCapability(
        "Missing glyph database", capability="Glyphs.glyphInfoForName.A"
    )

    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(metadata, "glyph_categories", unavailable)
    with pytest.raises(UnsupportedCapability) as error:
        app.glyphInfoForName("A")
    assert error.value is failure, (
        "Do not hide database dependency failures behind active-font data"
    )


def test_f6_optional_bootstrap_when_model_host_unavailable_then_receipt_explains_missing_globals(
    tmp_path,
):
    from fontlab_glyport.errors import HostUnavailable

    ctx, session = make_session(tmp_path)
    ctx.implicit_imports = ("GlyphsApp",)

    def unavailable():
        raise HostUnavailable("No model service")

    session.backend.current_font_id = unavailable
    script = tmp_path / "model_free.py"
    script.write_text("assert Font is None and Layer is None\nprint('UI only')\n")
    ctx.run(script)
    assert ctx.diagnostics[0].code == "SCRIPT_GLOBALS_UNAVAILABLE"
    with ctx, pytest.raises(HostUnavailable):
        _ = ctx.import_module("GlyphsApp").Glyphs.font
    ctx.close()


def test_f17_f22_exports_when_imported_then_values_types_and_geometry_match(tmp_path):
    ctx, _ = make_session(tmp_path)
    with ctx:
        ga = ctx.import_module("GlyphsApp")
        kit, cocoa = ctx.import_module("AppKit"), ctx.import_module("Cocoa")
        assert ga.MOUSEDRAGGED == "mouseDraggedNotification"
        assert ga.PLAIN == "plain"
        assert ga.NSAffineTransform is kit.NSAffineTransform
        assert kit.NSInsetRect(((0, 10), (50, 80)), 2, 3) == ((2, 13), (46, 74))
        assert (
            kit.NSAlertStyleWarning,
            kit.NSAlertStyleInformational,
            kit.NSAlertStyleCritical,
        ) == (0, 1, 2)
        assert kit.NSTextAlignmentRight == 1 and kit.NSFontWeightRegular == 0.0
        assert cocoa.NSAffineTransformStruct is kit.NSAffineTransformStruct
        assert isinstance(ga.Glyphs.font.newTab(), ga.GSEditViewController)
        assert issubclass(ga.GSBackgroundLayer, ga.GSLayer)
        background = ga.GSBackgroundLayer()
        background.paths.append(ga.GSPath([ga.GSNode((7, 9))]))
        assert background.parent is None and not background.isMasterLayer
        assert background.paths[0].nodes[0].position == (7, 9)
        with pytest.raises(UnsupportedCapability) as error:
            ga.GSBackgroundImage()
        assert error.value.capability == "GlyphsApp.GSBackgroundImage"

        class Names(ga.Proxy):
            def values(self):
                return self._owner

        proxy = Names(["one", "two"])
        assert list(proxy) == ["one", "two"] and len(proxy) == 2
    ctx.close()


def test_f19_vanilla_test_when_imported_then_precise_capability_instead_of_missing_module(
    tmp_path,
):
    ctx, _ = make_session(tmp_path)
    script = tmp_path / "test_ui.py"
    script.write_text("from vanilla.test.testAll import Test\n")
    ctx.run(script)
    with pytest.raises(UnsupportedCapability) as error:
        ctx.globals["Test"]()
    assert error.value.capability == "vanilla.test.Test"
    ctx.close()


@pytest.mark.parametrize("cache", [False, True])
def test_f21_bundle_helpers_when_nested_imports_then_adapters_scoped_and_host_modules_restored(
    tmp_path, cache
):
    resources = tmp_path / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "drawing.py").write_text(
        "from AppKit import NSColor\n"
        "from Foundation import NSMakePoint\n"
        "import GlyphsApp, vanilla, objc\n"
        "def later():\n    from AppKit import NSColor\n    return NSColor\n"
    )
    script = resources / "plugin.py"
    script.write_text("import drawing\ncolor = drawing.NSColor\n")
    original = sys.modules.get("AppKit")
    foreign = ModuleType("AppKit")
    foreign.NSColor = object()
    sys.modules["AppKit"] = foreign
    ctx, _ = make_session(tmp_path)
    if cache:
        ctx.cache_dir = tmp_path / "cache"
    try:
        ctx.run(script)
        assert ctx.globals["color"] is not foreign.NSColor
        assert ctx.wrap(ctx.globals["drawing"].later)() is ctx.globals["color"]
        assert sys.modules["AppKit"] is foreign
    finally:
        ctx.close()
        if original is None:
            sys.modules.pop("AppKit", None)
        else:
            sys.modules["AppKit"] = original


@pytest.mark.parametrize(
    "name", ["org.example.changed", "myToolChanged", "TableDataChanged"]
)
def test_n1_custom_notification_when_registered_before_post_then_delivered(name):
    from fontlab_glyport.notifications import notification_center_class

    calls = []
    center = notification_center_class().defaultCenter()
    center.addObserver_selector_name_object_(
        SimpleNamespace(receive_=calls.append), "receive:", name, None
    )
    center.postNotificationName_object_(name, None)
    assert len(calls) == 1 and calls[0].name() == name


def test_f21_helper_from_script_added_sibling_path_when_imported_then_scoped_and_path_restored(
    tmp_path,
):
    source, shared = tmp_path / "reporter", tmp_path / "sibling-resources"
    source.mkdir()
    (shared / "helpers").mkdir(parents=True)
    (shared / "helpers" / "__init__.py").write_text("from . import drawing\n")
    (shared / "helpers" / "drawing.py").write_text("from AppKit import NSColor\n")
    script = source / "plugin.py"
    script.write_text(
        f"import sys\nsys.path.insert(0, {str(shared)!r})\n"
        "from helpers import drawing\ncolor = drawing.NSColor\n"
    )
    ctx, _ = make_session(source)
    previous = list(sys.path)
    try:
        ctx.run(script)
        with ctx:
            assert ctx.globals["color"] is ctx.import_module("AppKit").NSColor
        assert "helpers" not in sys.modules
        assert sys.path == previous
    finally:
        ctx.close()
        sys.path[:] = previous
        for name in ("helpers", "helpers.drawing"):
            sys.modules.pop(name, None)
