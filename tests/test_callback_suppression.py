# this_file: tests/test_callback_suppression.py
"""Reentrant compatibility setters keep their outer callback suppression."""

from types import SimpleNamespace

import pytest
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa_text import NSTextView
from fontlab_glyport.ui.cocoa_views import NSControl
from fontlab_glyport.ui.vanilla import make_vanilla_module
from fontlab_glyport.ui.vanilla_controls import List


@pytest.mark.parametrize(
    "method", [NSControl._quietly, NSTextView._quietly, List._quietly]
)
@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_quietly_when_reentered_then_outer_state_is_preserved(method, initial, raises):
    owner = SimpleNamespace(_quiet=initial)
    error = ValueError("inner")

    def inner():
        assert owner._quiet, "nested action must stay quiet"
        if raises:
            raise error

    def outer():
        try:
            method(owner, inner)
        except ValueError as caught:
            assert caught is error
        assert owner._quiet, "inner finally must not unmute the outer action"

    method(owner, outer)
    assert owner._quiet is initial, "restore the original owner state"


@pytest.mark.parametrize(
    "kind", ["ComboBox.set", "ComboBox.setItems", "TextEditor", "Slider", "List"]
)
@pytest.mark.parametrize("initial", [False, True])
def test_vanilla_setter_when_outer_is_quiet_then_preserve_state(kind, initial):
    module = make_vanilla_module(make_qt(), error_sink=lambda error, sender: None)
    if kind.startswith("ComboBox"):
        control = module.ComboBox((0, 0, 100, 20), ["a", "b"])
        action = (
            (lambda: control.setItems(["b", "c"]))
            if kind.endswith("setItems")
            else (lambda: control.set("c"))
        )
    elif kind == "TextEditor":
        control = module.TextEditor((0, 0, 100, 40))
        action = lambda: control.set("new text")
    elif kind == "Slider":
        control = module.Slider((0, 0, 100, 20))
        action = lambda: control.set(50)
    else:
        control = module.List((0, 0, 100, 40), ["a"])
        action = lambda: control.set(["b", "c"])
    try:
        control._quiet = initial
        action()
        assert control._quiet is initial, "the setter must restore the incoming state"
    finally:
        control._retire()


@pytest.mark.parametrize("initial", [False, True])
def test_cocoa_control_when_nested_then_actions_only_resume_after_outer(initial):
    from fontlab_glyport.ui.cocoa import NSMakeRect
    from fontlab_glyport.ui.cocoa_views import make_appkit_classes

    seen = []
    kit = make_appkit_classes(make_qt(), error_sink=lambda error, sender: None)
    view = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 60, 20))
    target = SimpleNamespace(action_=seen.append)
    view.setTarget_(target)
    view.setAction_("action:")
    view._quiet = initial

    def outer():
        view._quietly(lambda: view.setTitle_("updated"))
        view._send()

    try:
        view._quietly(outer)
        assert seen == [], "a nested setter must not release target/action"
        assert view._quiet is initial
        view._send()
        assert seen == ([] if initial else [view]), "restore the original action policy"
    finally:
        kit["close"]()


def test_cocoa_view_when_reparented_hidden_and_disposed_then_tree_is_detached():
    from fontlab_glyport.ui.cocoa import NSMakeRect
    from fontlab_glyport.ui.cocoa_views import make_appkit_classes

    kit = make_appkit_classes(make_qt(), error_sink=lambda error, sender: None)

    def view():
        return kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 40))

    first, second, child, grandchild = (view() for _ in range(4))
    try:
        child.setHidden_(True)
        first.addSubview_(child)
        second.addSubview_(child)
        child.addSubview_(grandchild)
        assert first.subviews() == [] and second.subviews() == [child]
        assert grandchild.enclosingScrollView() is None, "walk all non-scroll ancestors"
        child.setNeedsDisplay_(False)
        child.dispose()
        assert second.subviews() == [] and child._superview is None
        child.removeFromSuperview()
        assert child._qt.parentWidget() is None
    finally:
        kit["close"]()


@pytest.mark.parametrize("text", ["", "word"])
def test_cocoa_numeric_text_when_no_leading_number_then_zero(text):
    from fontlab_glyport.ui.cocoa_views import _leading_number

    assert _leading_number(text) == 0, (
        "nonnumeric editable text has a zero numeric value"
    )


@pytest.mark.parametrize("path", ["other.key", "values.", "values"])
def test_defaults_controller_when_invalid_binding_then_explicit_refusal(path):
    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.ui.cocoa_views import NSUserDefaultsController

    with pytest.raises(UnsupportedCapability):
        NSUserDefaultsController._key(path)


def test_cocoa_defaults_when_none_then_remove_only_requested_key():
    from fontlab_glyport.ui.cocoa_views import _DefaultsValues

    mapping = {"remove": 4, "retain": 5}
    values = _DefaultsValues(mapping)
    values.setValue_forKey_(None, "remove")
    assert mapping == {"retain": 5}, "clearing one binding must preserve other defaults"
