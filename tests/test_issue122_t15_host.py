# this_file: tests/test_issue122_t15_host.py
"""Plugin-host fixes deferred to issue 122 T15 (App 265cc04 seams).

Each test pins one behaviour: the missing-window class, the dialog error owner,
atomic menu registration, the owned-menu fallback and the removed test shims.
"""

import inspect

import pytest
from fontlabapp.qt.menus import OwnedMenus
from fontlabapp.qt.safe import MainWindowNotFound
from host_doubles import VIOLATIONS, MainWindow, QWidget, make_host_qt

from fontlab_glyport.errors import HostUnavailable
from fontlab_glyport.plugins import fontlab_host
from fontlab_glyport.plugins.fontlab_host import OWNED_MENU, FontLabPluginHost
from fontlab_glyport.ui.cocoa_menu import NSMenuItem


def _qt_host() -> tuple[FontLabPluginHost, list[tuple[Exception, object]]]:
    """A host over PythonQt-shaped doubles; the sink records (error, owner)."""
    errors: list[tuple[Exception, object]] = []
    host = FontLabPluginHost(
        make_host_qt(),
        object(),
        error_sink=lambda error, owner: errors.append((error, owner)),
        main_window=MainWindow(),
    )
    return host, errors


def test_main_window_when_app_raises_main_window_not_found_then_host_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(self: OwnedMenus) -> object:
        raise MainWindowNotFound("FontLab main window not found")

    monkeypatch.setattr(OwnedMenus, "main_window", missing)
    host, _ = _qt_host()
    with pytest.raises(HostUnavailable, match="main window not found"):
        host.main_window()


def test_main_window_when_plain_runtime_error_names_the_window_then_it_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only App's class means "no window"; matching text is not enough."""

    def refused(self: OwnedMenus) -> object:
        raise RuntimeError("main window not found while off the GUI thread")

    monkeypatch.setattr(OwnedMenus, "main_window", refused)
    host, _ = _qt_host()
    with pytest.raises(RuntimeError) as caught:
        host.main_window()
    assert type(caught.value) is RuntimeError, "must not become HostUnavailable"


def test_dialog_when_on_close_raises_then_sink_owner_is_the_view() -> None:
    host, errors = _qt_host()
    view = QWidget()
    failure = ValueError("plugin on_close failed")

    def on_close(applied: bool) -> None:
        raise failure

    host.run_dialog(view, "Grow", "Apply", on_close)
    window = view.parent
    next(b for b in window.children if getattr(b, "text", "") == "Apply").click()
    assert errors == [(failure, view)], "the plugin view owns its callback error"
    host._reaper.fire()
    assert window.deleted and VIOLATIONS == []


def test_dialog_when_ended_then_button_release_runs_before_window_teardown() -> None:
    host, _ = _qt_host()
    view = QWidget()
    host.run_dialog(view, "Grow", "Apply", lambda applied: None)
    window = view.parent
    buttons = [b for b in window.children if hasattr(b, "clicked")]
    window.close()
    assert len(host._pending) == 2, "release and App teardown are both queued"
    host._pending[0]()  # the first queued call is Glyport's release
    assert all(b.clicked.slots == [] for b in buttons) and not window.deleted
    host._pending[1]()
    assert window.deleted


def test_register_menu_when_sync_raises_then_no_token_or_action_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host, _ = _qt_host()

    def broken(action: object, item: object) -> None:
        raise RuntimeError("bad icon")

    monkeypatch.setattr(host, "_sync", broken)
    item = NSMenuItem("Hello", lambda sender: None)
    with pytest.raises(RuntimeError, match="bad icon"):
        host.register_menu("EDIT_MENU", item)
    assert host._tokens == {} and host._actions == {}
    assert host._menu("EDIT_MENU").actions() == [], "no QAction left in the menu"
    assert item._observers == [] and host._cleanups == {}


def test_menu_when_name_is_an_unmapped_literal_title_then_owned_menu() -> None:
    host, _ = _qt_host()
    edit = host._menu("EDIT_MENU")
    literal = host._menu("Edit")
    assert literal is not edit, "a literal FontLab title is not a Glyphs menu name"
    assert literal.title == OWNED_MENU
    assert host._menu("FILTER_MENU") is literal


def test_menu_when_name_is_unmapped_then_app_never_searches_a_nul_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unmapped route uses App's own-menu seam, not a title that cannot match."""
    host, _ = _qt_host()
    searched: list[str] = []
    real = OwnedMenus._menu

    def recording(self: OwnedMenus, title: str) -> object:
        searched.append(title)
        return real(self, title)

    monkeypatch.setattr(OwnedMenus, "_menu", recording)
    assert host._menu("FILTER_MENU") is host.own_menu()
    assert host._menu("EDIT_MENU") is not host.own_menu()
    assert searched == ["Edit"], f"only real menubar titles are searched: {searched}"


def test_menu_when_app_lacks_own_menu_seam_then_unmapped_name_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The App floor is 1.2.10, so no NUL-key or ``getattr`` fallback may return."""
    host, _ = _qt_host()
    searched: list[str] = []
    real = OwnedMenus._menu

    def recording(self: OwnedMenus, title: str) -> object:
        searched.append(title)
        return real(self, title)

    monkeypatch.delattr(OwnedMenus, "own_menu")
    monkeypatch.setattr(OwnedMenus, "_menu", recording)
    with pytest.raises(AttributeError, match="own_menu"):
        host._menu("FILTER_MENU")
    assert searched == [], f"no legacy title search happened: {searched}"


def test_owned_menu_when_two_hosts_share_a_window_then_each_keeps_its_own() -> None:
    """One host per execution context: a host never adds to another's menu."""
    window = MainWindow()
    qt = make_host_qt()
    hosts = [
        FontLabPluginHost(qt, object(), error_sink=lambda e, s: None, main_window=window)
        for _ in range(2)
    ]
    first, second = hosts
    first.register_menu("FILTER_MENU", NSMenuItem("A", lambda sender: None))
    second.register_menu("FILTER_MENU", NSMenuItem("B", lambda sender: None))
    menu_a, menu_b = first._menu("FILTER_MENU"), second._menu("FILTER_MENU")
    assert menu_a is not menu_b
    assert [a.text for a in menu_b.actions()] == ["B"]
    first.close()
    first._reaper.fire()
    assert menu_a.deleted and not menu_b.deleted
    assert [a.text for a in menu_b.actions()] == ["B"], "B survives A's close"
    assert VIOLATIONS == []


def test_fontlab_host_when_read_then_no_test_shims_or_private_queue_edits() -> None:
    assert not hasattr(fontlab_host, "_Reaper"), "the legacy view lives in tests"
    assert "_main_window" not in vars(FontLabPluginHost)
    source = inspect.getsource(fontlab_host)
    assert "_pending" not in source, "use App's _defer(first=True) seam"
    assert "main window not found" not in source, "catch MainWindowNotFound"


@pytest.mark.parametrize("close_in_callback", [False, True])
def test_register_menu_when_sync_fails_in_callback_then_cleanup_is_deferred(
    close_in_callback: bool,
) -> None:
    host, errors = _qt_host()
    failure = RuntimeError("bad icon during dispatch")
    failed_actions = []
    bad_item = NSMenuItem("Broken", lambda sender: None)

    class BadIcon:
        def icon(self):
            raise failure

    bad_item.setImage_(BadIcon())

    def register(sender):
        try:
            host.register_menu("EDIT_MENU", bad_item)
        finally:
            failed = host._menu("EDIT_MENU").actions()[-1]
            assert failed is not trigger, "capture the failed registration action"
            failed_actions.append(failed)
            if close_in_callback:
                host.close()
            assert host.dispatching, "registration must fail inside owned dispatch"
            assert not failed.deleted, "teardown must wait until the slot returns"
            assert failed.triggered.slots, "do not disconnect inside dispatch"
            assert not bad_item._observers, "failed registration adds no observer"

    trigger_item = NSMenuItem("Register", register)
    token = host.register_menu("EDIT_MENU", trigger_item)
    trigger = host.action(token)
    for attempt in range(1 if close_in_callback else 2):
        trigger.trigger()
        assert errors == [(failure, trigger_item)] * (attempt + 1)
        assert not failed_actions[-1].deleted, "the event loop has not run yet"
        assert VIOLATIONS == [], "callback must not disconnect active signals"
        host._reaper.fire()
        assert all(action.deleted and not action.triggered.slots
                   for action in failed_actions), "failed actions are fully released"
        expected = set() if close_in_callback else {token}
        assert set(host._tokens) == set(host._actions) == set(host._cleanups) == expected
        assert host._menu("EDIT_MENU").actions() == ([] if close_in_callback else [trigger])
        assert not bad_item._observers and not host._pending

    bad_item.setImage_(None)
    recovered = host.register_menu("EDIT_MENU", bad_item)
    bad_item.setTitle_("Recovered")
    assert host.action(recovered).text == "Recovered", "observer sync recovers"
    host.close()
    host._reaper.fire()
    assert not host.has_items and not host._cleanups
    assert not bad_item._observers and not trigger_item._observers
    assert host._menu("EDIT_MENU").actions() == [] and VIOLATIONS == []
