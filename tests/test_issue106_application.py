# this_file: tests/test_issue106_application.py
"""NSApp's explicit Qt/application facade, without native host imports."""

import gc
from types import SimpleNamespace

import pytest
from ui_doubles import make_qt
from ui_doubles_session import make_session

from fontlab_glyport.errors import UnsupportedAttribute, UnsupportedCapability


@pytest.fixture
def application(tmp_path):
    state = SimpleNamespace(title="Fixture", opacity=1.0, updates=0)
    widget = SimpleNamespace(
        windowTitle=lambda: state.title,
        windowOpacity=lambda: state.opacity,
        setWindowOpacity=lambda value: setattr(state, "opacity", value),
        isVisible=lambda: True,
        update=lambda: setattr(state, "updates", state.updates + 1),
        focusWidget=lambda: None,
        menuBar=lambda: SimpleNamespace(actions=list),
    )
    qt = make_qt()

    def widgets():
        assert not gc.isenabled(), "native widget list conversion must disable GC"
        return [widget]

    qt.QtGui.QApplication = SimpleNamespace(
        topLevelWidgets=widgets,
        activeWindow=lambda: widget,
        palette=lambda: SimpleNamespace(
            color=lambda role: SimpleNamespace(lightnessF=lambda: 0.1)
        ),
        processEvents=lambda: None,
    )
    qt.QtGui.QPalette = SimpleNamespace(Window=1)
    ctx, session = make_session(
        tmp_path, qt=qt, fontlab=SimpleNamespace(MainWindow=lambda: widget)
    )
    with ctx:
        kit = ctx.import_module("AppKit")
        app = kit.NSApp
        assert ctx.import_module("Foundation").NSApp is app
        glyphs = ctx.import_module("GlyphsApp").Glyphs
    with ctx:
        yield ctx, session, kit, app, glyphs, state
    ctx.close()


def test_nsapp_when_shared_then_alias_call_and_class_accessor_match(application):
    _, _, kit, app, glyphs, _ = application
    assert app() is app and kit.NSApplication.sharedApplication() is app
    assert app.delegate() is glyphs
    assert app.windows() == [app.mainWindow()]
    assert app.keyWindow() is app.mainWindow()
    assert app.mainWindow().title() == "Fixture"
    assert app.mainWindow().firstResponder() is None
    assert app.mainWindow().windowController().document().font is glyphs.font
    app.mainWindow().setAlphaValue_(0.5)
    assert app.mainWindow().alphaValue() == 0.5
    assert app.mainMenu().numberOfItems() == 0


def test_nsapp_when_appearance_and_update_requested_then_qt_state_is_used(application):
    _, _, _, app, _, state = application
    appearance = app.effectiveAppearance()
    assert appearance.name() == "NSAppearanceNameDarkAqua"
    assert (
        appearance.bestMatchFromAppearancesWithNames_(
            ["NSAppearanceNameAqua", "NSAppearanceNameDarkAqua"]
        )
        == "NSAppearanceNameDarkAqua"
    )
    app.updateWindows()
    assert state.updates == 1
    assert app.currentEvent() is None


def test_nsapp_when_unknown_then_feature_probes_and_precise_errors(application):
    _, _, _, app, _, _ = application
    for target in (app, app.mainWindow(), app.mainWindow().windowController()):
        assert not hasattr(target, "unknownCapability")
        assert getattr(target, "unknownCapability", "fallback") == "fallback"
        with pytest.raises(UnsupportedAttribute):
            _ = target.unknownCapability
    with pytest.raises(UnsupportedCapability) as error:
        app.runModalForWindow_(app.mainWindow())
    assert error.value.capability == "NSApp.runModalForWindow_"


def test_nsapp_when_mouse_event_scope_active_then_current_event_matches(application):
    from fontlab_glyport.drawing.events import event_scope

    _, _, _, app, _, _ = application
    event = object()
    with event_scope(event):
        assert app.currentEvent() is event
    assert app.currentEvent() is None


def test_nsapp_when_widget_has_focus_then_first_responder_is_a_probe_safe_wrapper(
    application,
):
    _, session, _, app, _, _ = application
    widget = session.fontlab.MainWindow()
    focused = object()
    widget.focusWidget = lambda: focused
    responder = app.mainWindow().firstResponder()
    assert responder is not focused and responder is not None
    assert app.mainWindow().firstResponder() is responder
    assert app.firstResponder() is responder
    assert not hasattr(responder, "unsupportedMethod")
    widget.focusWidget = lambda: None
    assert app.mainWindow().firstResponder() is None
    session.qt.QtGui.QApplication.activeWindow = lambda: None
    assert app.firstResponder() is None


def test_nsapp_when_appearance_changes_then_observer_fires_and_close_disconnects(
    application,
):
    from ui_doubles import Signal

    ctx, session, _, app, _, _ = application
    signal = Signal(app, "paletteChanged")
    native = session.qt.QtGui.QApplication
    native.instance = lambda: SimpleNamespace(paletteChanged=signal)
    lightness, calls = [0.1], []
    native.palette = lambda: SimpleNamespace(
        color=lambda role: SimpleNamespace(lightnessF=lambda: lightness[0])
    )
    observer = SimpleNamespace(
        observeValueForKeyPath_ofObject_change_context_=lambda *args: calls.append(args)
    )
    app.addObserver_forKeyPath_options_context_(
        observer, "effectiveAppearance", 3, "context"
    )
    assert len(signal.slots) == 1
    lightness[0] = 0.9
    signal.emit(None)
    assert (
        calls[0][0] == "effectiveAppearance"
        and calls[0][2]["new"].name() == "NSAppearanceNameAqua"
    )
    assert calls[0][2]["old"].name() == "NSAppearanceNameDarkAqua"
    app.removeObserver_forKeyPath_(observer, "effectiveAppearance")
    assert not signal.slots
    app.addObserver_forKeyPath_options_context_(
        observer, "effectiveAppearance", 0, None
    )
    ctx.close()
    assert not signal.slots
    with pytest.raises(RuntimeError, match="closed"):
        app.addObserver_forKeyPath_options_context_(
            observer, "effectiveAppearance", 0, None
        )
