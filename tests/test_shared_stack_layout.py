# this_file: tests/test_shared_stack_layout.py
"""Exercise both compatibility callers through the public App implementation."""

from types import SimpleNamespace

import fontlabapp.qt.layouts.stack as _stack_layout
import pytest
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect
from fontlab_glyport.ui.cocoa_containers import NSStackView
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.vanilla import make_vanilla_module


@pytest.mark.parametrize(
    "foreign,mode",
    [
        (-1, "fixed"),
        (0, "fixed"),
        (1, "equal"),
        (2, "proportional"),
        (3, "spacing"),
        (4, "centering"),
        (99, "fixed"),
    ],
)
def test_adapter_when_foreign_mode_then_shared_call_preserves_storage(
    monkeypatch, foreign, mode
):
    sizes = [10.0, 20.0]
    calls = []

    def delegate(actual, length, spacing, policy):
        calls.append((actual, length, spacing, policy))
        actual[:] = [31.0, 32.0]
        return [0.0, 33.0]

    monkeypatch.setattr(_stack_layout, "distribute", delegate)
    obj = SimpleNamespace(_distribution=foreign, _spacing=2.0)
    assert NSStackView._distribute(obj, sizes, 100.0) == [0.0, 33.0]
    assert calls == [(sizes, 100.0, 2.0, mode)] and calls[0][0] is sizes
    assert sizes == [31.0, 32.0]


@pytest.mark.parametrize("vertical", [False, True])
def test_cocoa_when_real_adapter_layout_then_shared_geometry_and_cleanup(
    monkeypatch, vertical
):
    actual = _stack_layout.distribute
    calls = []

    def delegate(*args):
        calls.append(args)
        return actual(*args)

    monkeypatch.setattr(_stack_layout, "distribute", delegate)
    kit = make_appkit_classes(make_qt(), error_sink=print)
    try:
        stack = kit["NSStackView"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 100))
        stack.setOrientation_(int(vertical))
        stack.setDistribution_(1)
        stack.setSpacing_(4.0)
        views = [
            kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
            for _ in range(2)
        ]
        for view in views:
            stack.addArrangedSubview_(view)
        assert calls[-1][1:] == (100.0, 4.0, "equal")
        frames = [tuple(v.frame().origin) + tuple(v.frame().size) for v in views]
        assert frames == (
            [(45.0, 52.0, 10.0, 48.0), (45.0, 0.0, 10.0, 48.0)]
            if vertical
            else [(0.0, 45.0, 48.0, 10.0), (52.0, 45.0, 48.0, 10.0)]
        )
    finally:
        kit["close"]()
    assert not stack._env.views


def test_vanilla_when_resized_then_shared_geometry_and_cleanup(monkeypatch):
    actual = _stack_layout.distribute
    calls = []

    def delegate(*args):
        calls.append(args)
        return actual(*args)

    monkeypatch.setattr(_stack_layout, "distribute", delegate)
    vanilla = make_vanilla_module(make_qt(), error_sink=print)
    try:
        window = vanilla.Window((200, 140))
        first, second = vanilla.Button("auto", "One"), vanilla.Button("auto", "Two")
        window.stack = vanilla.VerticalStackView(
            (0, 0, 0, 0), [first, second], spacing=4, edgeInsets=(10, 8, 10, 8)
        )
        assert calls[-1][1:] == (124.0, 4.0, "equal")
        window.resize(240, 160)
        rect = second.getNSView().geometry
        assert (rect.x(), rect.y(), rect.width(), rect.height()) == (80, 82, 80, 70)
        assert calls[-1][1:] == (144.0, 4.0, "equal")
        window.open()
    finally:
        vanilla.Window._env.close_windows()
    assert not first._view.clicked.slots and not second._view.clicked.slots


def test_adapter_when_backend_fails_then_error_propagates_without_fallback(monkeypatch):
    sizes = [1.0, 2.0]

    def fail(*args):
        raise ValueError("owned failure")

    monkeypatch.setattr(_stack_layout, "distribute", fail)
    with pytest.raises(ValueError, match="owned failure"):
        NSStackView._distribute(
            SimpleNamespace(_distribution=1, _spacing=2.0), sizes, 100.0
        )
    assert sizes == [1.0, 2.0]


def test_cocoa_when_reordered_removed_hidden_then_arrangement_and_subviews_stay_distinct():
    kit = make_appkit_classes(make_qt(), error_sink=print)
    try:
        first = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
        second = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 20, 10))
        extra = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 30, 10))
        stack = kit["NSStackView"].stackViewWithViews_([first, second])
        stack.setFrame_(NSMakeRect(0, 0, 100, 20))
        stack.addSubview_(extra)
        stack.insertArrangedSubview_atIndex_(second, 0)
        assert stack.arrangedSubviews() == [second, first]
        assert stack.spacing() == 8 and stack.orientation() == 0
        assert stack.distribution() == -1 and stack.alignment() == 10
        stack.setDetachesHiddenViews_(False)
        assert not stack.detachesHiddenViews()
        first.setHidden_(True)
        extra.setHidden_(True)
        stack.removeArrangedSubview_(first)
        stack.removeArrangedSubview_(first)
        assert first.superview() is stack and stack.arrangedSubviews() == [second]
        first.removeFromSuperview()
        extra.removeFromSuperview()
        assert stack.arrangedSubviews() == [second]
    finally:
        kit["close"]()
    assert not stack._env.views
