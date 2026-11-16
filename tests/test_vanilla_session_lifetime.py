# this_file: tests/test_vanilla_session_lifetime.py
# SPDX-License-Identifier: Apache-2.0
"""Explicit optional adapter; real Glyport factory is exercised when installed."""

import gc
import sys
import weakref
from types import ModuleType, SimpleNamespace

import pytest

from fontlab_glyport.ui.session import VanillaSession


@pytest.fixture
def tracked_session(monkeypatch):
    """Model Glyport's close/native-close routing and tracked signal pairs."""
    disconnected = []

    class Window:
        def __init__(self):
            self._slots = [object(), object()]
            self._closed = False
            self.opened = False

        def open(self):
            self.opened = True

        def close(self):
            if not self._closed:
                self._teardown(view_closing=False)

        def _teardown(self, *, view_closing):
            self._closed = True
            while self._slots:
                disconnected.append(self._slots.pop())

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(
            make_vanilla_module=lambda *a, **k: SimpleNamespace(
                Window=Window, __all__=["Window"]
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=lambda *a, **k: None),
    )
    session = VanillaSession(qt=SimpleNamespace())
    yield session, disconnected
    session.close()


def test_vanilla_when_unopened_window_dropped_then_retained_until_teardown(
    tracked_session,
):
    session, disconnected = tracked_session
    window = session.vanilla.Window()
    reference = weakref.ref(window)
    del window
    gc.collect()
    assert reference() is not None, "live Python slots require a strong owner"
    session.close()
    assert len(disconnected) == 2 and not session._windows
    gc.collect()
    assert reference() is None, "release only after all signal pairs disconnect"


@pytest.mark.parametrize("native_close", [False, True])
def test_vanilla_when_opened_window_closes_then_disconnect_and_release(
    tracked_session, native_close
):
    session, disconnected = tracked_session
    window = session.vanilla.Window()
    window.open()
    if native_close:
        window._teardown(view_closing=True)
    else:
        window.close()
    assert not window._slots and len(disconnected) == 2
    assert window not in session._windows
    reference = weakref.ref(window)
    del window
    gc.collect()
    assert reference() is None


def test_vanilla_when_explicit_session_teardown_then_every_window_disconnects(
    tracked_session,
):
    session, disconnected = tracked_session
    windows = [session.vanilla.Window(), session.vanilla.Window()]
    windows[0].open()
    session.close()
    session.close()
    assert len(disconnected) == 4 and not session._windows
    assert all(window._closed and not window._slots for window in windows)


def test_vanilla_when_teardown_fails_then_live_window_stays_strongly_owned(
    tracked_session, monkeypatch
):
    session, disconnected = tracked_session
    window = session.vanilla.Window()

    def fail(*, view_closing):
        raise RuntimeError("disconnect failed")

    with monkeypatch.context() as patch:
        patch.setattr(window, "_teardown", fail)
        with pytest.raises(RuntimeError, match="disconnect failed"):
            session.close()
        reference = weakref.ref(window)
        del window
        gc.collect()
        assert reference() in session._windows and not disconnected
    session.close()
    assert not session._windows and len(disconnected) == 2


def test_vanilla_when_failed_teardown_marked_closed_then_repeat_cannot_drop_owner(
    tracked_session, monkeypatch
):
    session, _ = tracked_session
    window = session.vanilla.Window()
    base = type(window).__mro__[1]

    def fail_after_marking_closed(self, *, view_closing):
        self._closed = True
        raise RuntimeError("native disconnect failure")

    with monkeypatch.context() as patch:
        patch.setattr(base, "_teardown", fail_after_marking_closed)
        with pytest.raises(RuntimeError, match="native disconnect failure"):
            session.close()
        with pytest.raises(RuntimeError, match="ownership retained"):
            session.close()
        assert window in session._windows and window._slots
    window._closed = False  # Restore the double so fixture cleanup can finish.


def test_vanilla_when_explicit_then_factories_close_and_no_namespace_replacement(
    monkeypatch,
):
    calls, hooks = [], []

    def factory(qt, **kwargs):
        calls.append((qt, kwargs))
        kwargs["on_close"](lambda: hooks.append("closed"))
        return ModuleType("explicit")

    for name, attribute in (
        ("vanilla", "make_vanilla_module"),
        ("dialogs", "make_dialogs_module"),
    ):
        monkeypatch.setitem(
            sys.modules,
            "fontlab_glyport.ui." + name,
            SimpleNamespace(**{attribute: factory}),
        )
    installed = ModuleType("vanilla")
    monkeypatch.setitem(sys.modules, "vanilla", installed)
    qt = SimpleNamespace()
    with VanillaSession(qt=qt) as session:
        assert session.vanilla is not installed
        assert calls[0][0] is calls[1][0] is qt
        assert calls[1][1]["interactive"] is True
        assert sys.modules["vanilla"] is installed
    assert hooks == ["closed", "closed"]
    session.close()
    assert len(hooks) == 2, "teardown must be idempotent"


@pytest.mark.parametrize("created_widget", [False, True])
def test_vanilla_when_base_constructor_raises_then_created_widget_is_retained(
    monkeypatch, created_widget
):
    closed, references = [], []

    class View:
        def deleteLater(self):
            closed.append(self)

    class Window:
        def __init__(self):
            references.append(weakref.ref(self))
            if created_widget:
                self._view = View()
            raise ValueError("constructor failed")

        def close(self):
            closed.append(self._view)

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(
            make_vanilla_module=lambda *a, **k: SimpleNamespace(
                Window=Window, __all__=["Window"]
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=lambda *a, **k: None),
    )
    session = VanillaSession(qt=SimpleNamespace())
    with pytest.raises(ValueError, match="constructor failed"):
        session.vanilla.Window()
    gc.collect()
    assert bool(session._windows) is created_widget
    assert (references[0]() is not None) is created_widget
    session.close()
    gc.collect()
    assert len(closed) == int(created_widget) and references[0]() is None


def test_vanilla_when_earliest_constructor_failure_then_teardown_needs_only_view(
    monkeypatch,
):
    deleted = []

    class Window:
        def __init__(self):
            self._view = SimpleNamespace(deleteLater=lambda: deleted.append(True))
            raise RuntimeError("before children and binds")

        def close(self):
            raise AssertionError("incomplete window cannot use base close")

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(
            make_vanilla_module=lambda *a, **k: SimpleNamespace(
                Window=Window, __all__=["Window"]
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=lambda *a, **k: None),
    )
    session = VanillaSession(qt=SimpleNamespace())
    with pytest.raises(RuntimeError, match="before children"):
        session.vanilla.Window()
    assert len(session._windows) == 1
    session.close()
    session.close()
    assert deleted == [True] and not session._windows


def test_vanilla_when_second_factory_fails_then_first_factory_is_closed(monkeypatch):
    closed = []

    def first(qt, **kwargs):
        kwargs["on_close"](lambda: closed.append(True))
        return ModuleType("explicit")

    def fail(*args, **kwargs):
        raise ValueError("second factory failed")

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(make_vanilla_module=first),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=fail),
    )
    with pytest.raises(ValueError, match="second factory"):
        VanillaSession(qt=SimpleNamespace())
    assert closed == [True]


def test_vanilla_when_real_factory_available_then_common_controls_and_dialogs():
    pytest.importorskip("fontlab_glyport.ui.vanilla")
    qt = SimpleNamespace(QtGui=SimpleNamespace(QWidget=type("Widget", (), {})))
    with VanillaSession(qt=qt) as session:
        for name in (
            "Window",
            "TextBox",
            "EditText",
            "Button",
            "CheckBox",
            "Slider",
            "PopUpButton",
            "List",
            "Group",
        ):
            assert callable(getattr(session.vanilla, name)), name
        assert callable(session.dialogs.getFile) and callable(session.dialogs.putFile)


def test_vanilla_when_unopened_windows_or_cleanup_error_then_all_owned_hooks_run(
    monkeypatch,
):
    closed = []

    class Window:
        def close(self):
            closed.append("window")

    def factory(qt, **kwargs):
        return SimpleNamespace(Window=Window, __all__=["Window"])

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(make_vanilla_module=factory),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=lambda *a, **k: None),
    )
    session = VanillaSession(qt=SimpleNamespace())
    windows = [session.vanilla.Window(), session.vanilla.Window()]

    def fail():
        raise ValueError("cleanup failure")

    session._hooks.append(fail)
    with pytest.raises(ValueError, match="cleanup failure"):
        session.close()
    assert closed == ["window", "window"], (
        "one failure cannot strand the other owned windows"
    )
    assert len(windows) == 2
    with pytest.raises(RuntimeError, match="closed"):
        session.vanilla.Window()
    session.close()


def test_vanilla_when_closed_windows_released_then_session_does_not_retain_them(
    monkeypatch,
):
    import gc
    import weakref

    class Window:
        def close(self):
            pass

    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.vanilla",
        SimpleNamespace(
            make_vanilla_module=lambda *a, **k: SimpleNamespace(
                Window=Window, __all__=["Window"]
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "fontlab_glyport.ui.dialogs",
        SimpleNamespace(make_dialogs_module=lambda *a, **k: None),
    )
    session = VanillaSession(qt=SimpleNamespace())
    for _ in range(100):
        window = session.vanilla.Window()
        reference = weakref.ref(window)
        window.close()
        del window
        gc.collect()
        assert reference() is None
    assert not session._windows and not session._hooks
    session.close()
