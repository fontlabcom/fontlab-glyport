# this_file: tests/test_ui_resize_events.py
"""Compare frozen first-party resize behavior with all four shared callers."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.ui import cocoa_views, cocoa_window, vanilla, vanilla_containers

CALLERS = [
    (vanilla, "_window_widget_class", "_resized"),
    (cocoa_window, "_window_widget_class", "_qt_resized"),
    (cocoa_views, "_container_class", "_qt_resized"),
    (vanilla_containers, "_page_class", "_resized"),
]


# Exact complete factory at reviewed Glyport5671934, including closeEvent.
def _prior_cocoa_window_class(base: type) -> type:
    """QWidget subclass: resizes reach the content view, a title-bar close the
    delegate (PythonQt: call the native handler explicitly, no ``super()``)."""

    class WindowWidget(base):
        _owner = None

        def resizeEvent(self, event):
            base.resizeEvent(self, event)
            if self._owner is not None:
                size = event.size()
                self._owner._qt_resized(size.width(), size.height())

        def closeEvent(self, event):
            owner = self._owner
            if owner is not None and not owner._title_bar_close():
                event.ignore()
                return
            base.closeEvent(self, event)

    return WindowWidget


@pytest.mark.parametrize("module,factory,method", CALLERS)
def test_resize_when_class_created_then_delegates_to_shared_factory(
    module, factory, method, monkeypatch
):
    seen = []

    def shared(base, owner, name):
        seen.append((base, owner, name))
        return "owned sentinel"

    monkeypatch.setattr(module, "resize_event_handler", shared)
    cls = getattr(module, factory)(object)
    owner = object()
    assert cls.resizeEvent == "owned sentinel"
    assert len(seen) == 1 and seen[0][0] is object and seen[0][2] == method
    assert seen[0][1](SimpleNamespace(_owner=owner)) is owner


@pytest.mark.parametrize("module,factory,method", CALLERS)
@pytest.mark.parametrize(
    "case",
    [
        "present",
        "none",
        "repeat",
        "base-error",
        "base-missing",
        "size-error",
        "width-error",
        "height-error",
        "callback-error",
        "base-change",
        "size-change",
        "width-change",
        "height-change",
        "size-remove",
        "base-remove",
        "method-missing",
        "method-error",
        "event-size-missing",
        "width-missing",
        "height-missing",
    ],
)
def test_resize_when_owned_event_runs_then_frozen_and_shared_traces_match(
    module, factory, method, case
):
    """Compare original Cocoa factory and the other callers' original bodies."""
    failure = RuntimeError("owned failure")

    def run(current):
        trace = []

        def step(name, result=None):
            trace.append(name)
            if case == str(name) + "-error":
                raise failure
            if case == str(name) + "-remove":
                widget._owner = None
            if case == str(name) + "-change":
                widget._owner = replacement
            return result

        class Base:
            def resizeEvent(self, event):
                return step("base", 123)

        if case == "base-missing":
            del Base.resizeEvent

        if current:
            cls = getattr(module, factory)(Base)
        elif module is cocoa_window:
            cls = _prior_cocoa_window_class(Base)
        else:

            class cls(Base):
                def resizeEvent(self, event):
                    base = Base
                    base.resizeEvent(self, event)
                    if self._owner is not None:
                        size = event.size()
                        getattr(self._owner, method)(size.width(), size.height())

        widget = cls()
        original = SimpleNamespace(**{method: lambda w, h: step("callback", (w, h))})
        replacement = SimpleNamespace(
            **{method: lambda w, h: step("replacement", (w, h))}
        )
        if case == "method-missing":
            original = SimpleNamespace()
        if case == "method-error":

            class FailingOwner:
                def __getattribute__(self, name):
                    if name == method:
                        step("method")
                    return object.__getattribute__(self, name)

            original = FailingOwner()
        widget._owner = None if case == "none" else original

        def size():
            step("size")
            if case == "size-remove":
                widget._owner = None
            dimensions = {
                "width": lambda: step("width", 321),
                "height": lambda: step("height", 654),
            }
            dimensions.pop(case.removesuffix("-missing"), None)
            return SimpleNamespace(**dimensions)

        event = (
            SimpleNamespace()
            if case == "event-size-missing"
            else SimpleNamespace(size=size)
        )
        error = None
        try:
            assert widget.resizeEvent(event) is None
            if case == "repeat":
                widget._owner = None
                assert widget.resizeEvent(event) is None
        except (RuntimeError, AttributeError) as caught:
            error = caught if caught is failure else type(caught)
        return trace, error

    assert run(True) == run(False), (factory, case)
