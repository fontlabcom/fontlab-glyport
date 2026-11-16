# this_file: tests/test_ui_shared_numeric.py
"""Every proportional Qt caller delegates without relocating foreign policy."""

from unittest.mock import Mock

import fontlabapp.qt.numeric as shared
import pytest
from ui_doubles import make_qt

from fontlab_glyport.ui.cocoa import NSMakeRect
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.vanilla import make_vanilla_module


@pytest.mark.parametrize(
    "profile", ["vanilla-slider", "vanilla-progress", "cocoa-slider", "cocoa-progress"]
)
def test_every_complete_caller_uses_shared_range_and_position(profile, monkeypatch):
    position = Mock(wraps=shared.position)
    ranges = Mock(wraps=shared.set_step_range)
    monkeypatch.setattr(shared, "position", position)
    monkeypatch.setattr(shared, "set_step_range", ranges)
    qt = make_qt()
    if profile.startswith("vanilla"):
        v = make_vanilla_module(qt, error_sink=lambda *args: None)
        obj = (
            v.Slider((0, 0, 100, 20))
            if profile.endswith("slider")
            else v.ProgressBar((0, 0, 100, 20))
        )
        obj.set(12.345)
    else:
        kit = make_appkit_classes(qt, error_sink=lambda *args: None)
        obj = (
            kit["NSSlider" if profile.endswith("slider") else "NSProgressIndicator"]
            .alloc()
            .initWithFrame_(NSMakeRect(0, 0, 100, 20))
        )
        obj.setDoubleValue_(0.12345)
    assert ranges.call_count >= 1 and position.call_count >= 1


def test_native_value_getter_keeps_original_lower_bound_read_order():
    v = make_vanilla_module(make_qt(), error_sink=lambda *args: None)
    obj = v.Slider((0, 0, 100, 20), minValue=0, maxValue=100, value=25)
    cls = type(obj._view)
    old = cls.value

    def value(widget):
        obj._min = 100
        obj._span = 200
        return old.__get__(widget, cls)

    try:
        cls.value = property(value)
        assert obj.get() == 50.0
    finally:
        cls.value = old


def test_bound_setter_is_resolved_before_rounding_argument_mutates_state():
    seen = []

    class Number:
        def __round__(self):
            seen.append("round")
            return 2

    class Widget:
        @property
        def setValue(self):
            seen.append("lookup")
            return lambda value: seen.append(value)

    shared.set_position(Widget().setValue, Number())
    assert seen == ["lookup", "round", 2]
