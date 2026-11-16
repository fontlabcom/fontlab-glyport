# this_file: tests/test_ui_cocoa.py
"""objc subset, NSObject KVC/KVO and Qt-backed AppKit views over doubles (R030)."""

import pytest
from ui_doubles import LOG, QCheckBox, QPushButton, make_qt
from ui_doubles_controls import QRadioButton

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui import cocoa_views as views
from fontlab_glyport.ui.cocoa import (
    NSKeyValueObservingOptionNew,
    NSKeyValueObservingOptionOld,
    NSMakeRect,
    NSObject,
    python_name,
    selector_of,
)
from fontlab_glyport.ui.cocoa_views import SLIDER_STEPS, make_appkit_classes
from fontlab_glyport.ui.objc_bridge import make_objc_module

KEY_UP, KEY_DOWN, SHIFT = 0x01000013, 0x01000015, 0x02000000


@pytest.fixture
def kit():
    qt = make_qt()
    errors = []
    names = make_appkit_classes(qt, error_sink=lambda e, s: errors.append((e, s)))
    names["errors"] = errors
    return names


def _geometry(widget):
    rect = widget.geometry
    return rect.x(), rect.y(), rect.width(), rect.height()


class Target:
    def __init__(self):
        self.calls = []

    def action_(self, sender):
        self.calls.append(("action:", sender))

    def ping(self):
        self.calls.append(("ping",))


# --- objc module ---------------------------------------------------------


def test_objc_when_plugin_style_class_then_outlets_actions_and_super_work(kit):
    objc = make_objc_module({"GSSteppingTextField": kit["GSSteppingTextField"]})

    class Plugin(NSObject):
        field = objc.IBOutlet()

        def init(self):
            self = objc.super(Plugin, self).init()  # noqa: PLW0642 - PyObjC idiom
            self.ready = True
            return self

        @objc.python_method
        def helper(self):
            return 42

        @objc.IBAction
        def apply_(self, sender):
            return sender

    plugin = Plugin.alloc().init()
    assert plugin.ready and plugin.helper() == 42
    assert plugin.field is None, "an unconnected outlet reads None"
    plugin.field = "x"
    assert plugin.field == "x"
    assert Plugin.apply_.__glyport_ibaction__
    assert objc.lookUpClass("GSSteppingTextField") is kit["GSSteppingTextField"]
    assert objc.nil is None


def test_objc_when_unknown_class_then_nosuchclass_error_is_catchable():
    objc = make_objc_module({})
    with pytest.raises(objc.nosuchclass_error) as info:
        objc.lookUpClass("GlyphsToolHand")
    assert isinstance(info.value, objc.error)
    assert isinstance(info.value, UnsupportedCapability)
    assert info.value.capability == "objc.lookUpClass.GlyphsToolHand"
    assert info.value.location.path == __file__


def test_objc_when_unknown_member_then_unsupported_not_attribute_error():
    objc = make_objc_module({})
    with pytest.raises(UnsupportedCapability) as info:
        _ = objc.loadBundleFunctions
    assert info.value.capability == "objc.loadBundleFunctions"


def test_objc_selector_object_when_in_class_then_method_with_selector_name():
    objc = make_objc_module({})

    class Thing(NSObject):
        def go(self, sender):
            return sender

        go = objc.selector(go, selector=b"go:", signature=b"v@:@")

    assert Thing.go.selector == "go:"
    assert Thing.alloc().init().go(5) == 5
    assert selector_of(Thing.go) == "go:"


@pytest.mark.parametrize(
    ("action", "selector"),
    [
        ("go:", "go:"),
        (b"go:", "go:"),
        (Target().action_, "action:"),
        (Target().ping, "ping"),
    ],
)
def test_selector_of_when_forms_then_objective_c_names(action, selector):
    assert selector_of(action) == selector
    assert python_name(selector) == selector.replace(":", "_")


# --- NSObject KVC/KVO ----------------------------------------------------


class Model(NSObject):
    def init(self):
        self.width = 10
        self.log = []
        return self

    def setHeight_(self, value):
        self.log.append(value)
        self.height = value


class Observer:
    def __init__(self):
        self.seen = []

    def observeValueForKeyPath_ofObject_change_context_(self, path, obj, change, ctx):
        self.seen.append((path, obj, dict(change), ctx))


def test_kvc_when_setter_exists_then_used_and_observers_get_new_and_old():
    model, watcher = Model.new(), Observer()
    options = NSKeyValueObservingOptionNew | NSKeyValueObservingOptionOld
    model.addObserver_forKeyPath_options_context_(watcher, "width", options, "c")
    model.setValue_forKey_(20, "width")
    model.setValue_forKey_(5, "height")
    assert model.valueForKey_("width") == 20 and model.log == [5]
    assert watcher.seen == [("width", model, {"kind": 1, "new": 20, "old": 10}, "c")]
    model.removeObserver_forKeyPath_(watcher, "width")
    model.setValue_forKey_(30, "width")
    assert len(watcher.seen) == 1
    with pytest.raises(ValueError):
        model.removeObserver_forKeyPath_(watcher, "width")


def test_kvo_when_will_did_change_pair_then_notified():
    model, watcher = Model.new(), Observer()
    model.addObserver_forKeyPath_options_context_(watcher, "width", 0, None)
    model.willChangeValueForKey_("width")
    model.width = 99
    model.didChangeValueForKey_("width")
    assert [entry[0] for entry in watcher.seen] == ["width"]


# --- views ---------------------------------------------------------------


def test_view_when_subview_added_then_cocoa_frame_flipped_to_qt(kit):
    parent = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    child = kit["NSView"].alloc().initWithFrame_(((10, 20), (50, 30)))
    parent.addSubview_(child)
    assert _geometry(child._qt) == (10, 100 - 20 - 30, 50, 30)
    assert child._qt.parentWidget() is parent._qt
    assert child.superview() is parent and parent.subviews() == [child]


def test_view_when_superview_flipped_then_top_left_origin(kit):
    class Flipped(kit["NSView"]):
        def isFlipped(self):
            return True

    parent = Flipped.alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    child = kit["NSView"].alloc().initWithFrame_(NSMakeRect(10, 20, 50, 30))
    parent.addSubview_(child)
    assert _geometry(child._qt) == (10, 20, 50, 30)


def test_view_when_parent_resized_then_autoresizing_mask_applied(kit):
    parent = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    top = kit["NSView"].alloc().initWithFrame_(NSMakeRect(10, 70, 100, 20))
    top.setAutoresizingMask_(views.NSViewWidthSizable | views.NSViewMinYMargin)
    fixed = kit["NSView"].alloc().initWithFrame_(NSMakeRect(10, 10, 50, 20))
    parent.addSubview_(top)
    parent.addSubview_(fixed)
    parent.setFrame_(NSMakeRect(0, 0, 300, 150))
    assert top.frame() == NSMakeRect(10, 120, 200, 20), "stuck to the top, wider"
    assert _geometry(top._qt) == (10, 10, 200, 20)
    assert fixed.frame() == NSMakeRect(10, 10, 50, 20), "default mask keeps origin"
    assert _geometry(fixed._qt) == (10, 120, 50, 20)


def test_view_when_qt_resizes_container_then_subviews_autoresize(kit):
    parent = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    child = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    child.setAutoresizingMask_(views.NSViewWidthSizable | views.NSViewHeightSizable)
    parent.addSubview_(child)
    parent._qt.setGeometry(0, 0, 260, 140)  # a host panel resized it
    assert parent.frame().size == (260, 140)
    assert child.frame() == NSMakeRect(0, 0, 260, 140)


# --- controls ------------------------------------------------------------


def test_text_field_when_user_edits_and_returns_then_action_with_sender(kit):
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    target = Target()
    field.setTarget_(target)
    field.setAction_("action:")
    field.setStringValue_("12.5pt")
    assert target.calls == [], "programmatic values never send the action"
    assert field.floatValue() == 12.5 and field.intValue() == 12
    field._qt.user_type("7")
    field._qt.user_finish()
    field._qt.user_focus_out()
    assert target.calls == [("action:", field)]
    field.setFloatValue_(3.0)
    assert field.stringValue() == "3"


def test_text_field_when_continuous_then_action_per_keystroke(kit):
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    target = Target()
    field.setTarget_(target)
    field.setAction_(target.ping)
    field.setContinuous_(True)
    field._qt.user_type("a")
    field._qt.user_type("ab")
    field._qt.user_finish()
    assert target.calls == [("ping",), ("ping",)]


def test_action_when_target_lacks_method_then_unsupported_to_sink(kit):
    button = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    button.setTarget_(Target())
    button.setAction_("missing:")
    button._qt.user_click()
    ((error, sender),) = kit["errors"]
    assert isinstance(error, UnsupportedCapability) and sender is button
    assert error.capability == "Target.missing:"


def test_action_when_selector_has_two_arguments_then_type_error(kit):
    button = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    with pytest.raises(TypeError):
        button.setAction_("a:b:")


def test_stepping_field_when_arrow_keys_then_steps_and_sends(kit):
    field = kit["GSSteppingTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 60, 22))
    target = Target()
    field.setTarget_(target)
    field.setAction_("action:")
    field.setFloatValue_(5)
    assert field._qt.user_key(KEY_UP)
    assert field.stringValue() == "6"
    assert field._qt.user_key(KEY_DOWN, SHIFT)
    assert field.floatValue() == -4.0
    assert target.calls == [("action:", field)] * 2
    assert not field._qt.user_key(0x41), "other keys reach QLineEdit"
    field.setEditable_(False)
    assert not field._qt.user_key(KEY_UP)
    assert field.floatValue() == -4.0


def test_button_when_switch_type_then_rebuilt_as_checkbox_in_place(kit):
    parent = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    button = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(10, 10, 120, 20))
    parent.addSubview_(button)
    button.setTitle_("Bold")
    old = button._qt
    button.setButtonType_(views.NSSwitchButton)
    assert isinstance(button._qt, QCheckBox) and old._deleted
    assert button._qt.parentWidget() is parent._qt
    assert _geometry(button._qt) == (10, 70, 120, 20)
    assert button.title() == "Bold"
    target = Target()
    button.setTarget_(target)
    button.setAction_("action:")
    button._qt.user_click()
    assert button.state() == views.NSOnState
    assert target.calls == [("action:", button)]
    button.setState_(views.NSMixedState)
    assert button.state() == views.NSMixedState
    assert ("disconnect", old, "clicked") in LOG


def test_button_when_radio_clicked_twice_then_stays_on(kit):
    button = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 20))
    button.setButtonType_(views.NSRadioButton)
    assert isinstance(button._qt, QRadioButton)
    button._qt.user_click()
    button._qt.user_click()
    assert button.state() == views.NSOnState


def test_button_when_push_then_state_off_and_unknown_type_unsupported(kit):
    button = kit["NSButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 20))
    assert isinstance(button._qt, QPushButton) and button.state() == views.NSOffState
    with pytest.raises(UnsupportedCapability):
        button.setButtonType_(6)


def test_slider_when_values_then_mapped_and_actions_follow_continuity(kit):
    slider = kit["NSSlider"].alloc().initWithFrame_(NSMakeRect(0, 0, 120, 20))
    slider.setMinValue_(-10)
    slider.setMaxValue_(10)
    slider.setFloatValue_(5)
    assert slider._qt.value == SLIDER_STEPS * 3 // 4 and slider.floatValue() == 5
    target = Target()
    slider.setTarget_(target)
    slider.setAction_("action:")
    slider._qt.user_press_drag_release(0, SLIDER_STEPS)
    assert target.calls == [("action:", slider)], "non-continuous: on release"
    assert slider.floatValue() == 10
    slider.setContinuous_(True)
    slider._qt.user_press_drag_release(SLIDER_STEPS // 2)
    assert len(target.calls) == 2
    tall = kit["NSSlider"].alloc().initWithFrame_(NSMakeRect(0, 0, 20, 120))
    assert tall._qt._orientation == "Vertical"


def test_popup_when_items_and_user_pick_then_index_and_action(kit):
    popup = (
        kit["NSPopUpButton"]
        .alloc()
        .initWithFrame_pullsDown_(NSMakeRect(0, 0, 100, 22), False)
    )
    target = Target()
    popup.setTarget_(target)
    popup.setAction_("action:")
    popup.addItemsWithTitles_(["Regular", "Bold"])
    popup.selectItemWithTitle_("Bold")
    assert (popup.indexOfSelectedItem(), popup.titleOfSelectedItem()) == (1, "Bold")
    assert popup.itemTitles() == ["Regular", "Bold"] and target.calls == []
    popup._qt.user_choose(0)
    assert target.calls == [("action:", popup)] and popup.intValue() == 0
    with pytest.raises(UnsupportedCapability):
        kit["NSPopUpButton"].alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 1, 1), 1)


def test_progress_when_values_then_steps(kit):
    bar = kit["NSProgressIndicator"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 10))
    bar.setMaxValue_(50)
    bar.setDoubleValue_(25)
    bar.incrementBy_(5)
    assert bar._qt.value == SLIDER_STEPS * 30 // 50
    bar.setIndeterminate_(True)
    bar.startAnimation_(None)
    assert (bar._qt.minimum, bar._qt.maximum) == (0, 0)
    bar.stopAnimation_(None)
    assert bar._qt.maximum == SLIDER_STEPS


def test_binding_when_bound_to_user_defaults_then_two_way(kit):
    defaults = {"com.test.width": 40}
    names = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    controller = names["NSUserDefaultsController"].sharedUserDefaultsController()
    assert (
        controller is names["NSUserDefaultsController"].sharedUserDefaultsController()
    )
    field = names["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    field.bind_toObject_withKeyPath_options_(
        "value", controller, "values.com.test.width", None
    )
    assert field.stringValue() == "40", "the binding pulls the current value"
    field._qt.user_type("55")
    field._qt.user_finish()
    assert defaults["com.test.width"] == "55", "an edit pushes to defaults"
    controller.setValue_forKeyPath_(7, "values.com.test.width")
    assert field.stringValue() == "7", "a defaults change updates the field"
    field.unbind_("value")
    controller.setValue_forKeyPath_(8, "values.com.test.width")
    assert field.stringValue() == "7"


def test_binding_when_unsupported_binding_then_raises(kit):
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    with pytest.raises(UnsupportedCapability):
        field.bind_toObject_withKeyPath_options_(
            "textColor", Model.new(), "width", None
        )


def test_binding_when_enabled_and_selected_index_then_follow_defaults(kit):
    defaults = {"flag": 0, "com.x.option": 1}
    names = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    controller = names["NSUserDefaultsController"].sharedUserDefaultsController()
    popup = names["NSPopUpButton"].alloc().initWithFrame_(NSMakeRect(0, 0, 90, 22))
    popup.addItemsWithTitles_(["a", "b", "c"])
    popup.bind_toObject_withKeyPath_options_("enabled", controller, "values.flag", None)
    popup.bind_toObject_withKeyPath_options_(
        "selectedIndex", controller, "values.com.x.option", None
    )
    assert not popup.isEnabled() and popup.indexOfSelectedItem() == 1
    controller.setValue_forKeyPath_(True, "values.flag")
    assert popup.isEnabled()
    popup._qt.user_choose(2)
    assert defaults["com.x.option"] == 2


def test_binding_when_bound_to_model_then_kvo_updates_control(kit):
    model = Model.new()
    slider = kit["NSSlider"].alloc().initWithFrame_(NSMakeRect(0, 0, 100, 20))
    slider.setMaxValue_(100)
    slider.bind_toObject_withKeyPath_options_("value", model, "width", None)
    assert slider.floatValue() == 10
    model.setValue_forKey_(60, "width")
    assert slider.floatValue() == 60
    slider._qt.user_press_drag_release(SLIDER_STEPS // 4)
    assert model.width == 25


def test_close_when_env_closed_then_every_slot_disconnected(kit):
    parent = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    parent.addSubview_(field)
    kit["close"]()
    assert ("disconnect", field._qt, "textEdited") in LOG
    assert ("disconnect", field._qt, "editingFinished") in LOG
    assert ("deleteLater", parent._qt) in LOG
    assert field._qt._deleted, "children go with the top-level widget"


def test_close_when_bound_then_observers_removed_and_no_late_updates(kit):
    defaults = {"k": 1}
    names = make_appkit_classes(make_qt(), error_sink=print, defaults=defaults)
    controller = names["NSUserDefaultsController"].sharedUserDefaultsController()
    field = names["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    field.bind_toObject_withKeyPath_options_("value", controller, "values.k", None)
    target = Target()
    field.setTarget_(target)
    names["close"]()
    assert controller.values().__dict__.get("_kvo_observers") == []
    assert field.target() is None, "targets are released"
    controller.setValue_forKeyPath_(9, "values.k")
    assert field.stringValue() == "1", "a closed control never updates"


def test_dispose_when_view_tree_then_disconnected_unbound_deleted_once(kit):
    model = Model.new()
    parent = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 200, 100))
    field = kit["NSTextField"].alloc().initWithFrame_(NSMakeRect(0, 0, 80, 22))
    parent.addSubview_(field)
    field.bind_toObject_withKeyPath_options_("value", model, "width", None)
    parent.dispose()
    parent.dispose()
    assert ("disconnect", field._qt, "textEdited") in LOG
    assert model.__dict__["_kvo_observers"] == []
    assert LOG.count(("deleteLater", parent._qt)) == 1 and field._qt._deleted
    kit["close"]()
    assert LOG.count(("deleteLater", parent._qt)) == 1, "disposed views leave the env"
