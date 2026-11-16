# this_file: tests/test_ui_vanilla_handles.py
"""vanilla native handles: _nsObject/_target/getNS*() and nsTextFieldClass (R030)."""

import pytest
from ui_doubles import LOG, make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui.cocoa_controls import GSSteppingTextField
from fontlab_glyport.ui.cocoa_views import make_appkit_classes
from fontlab_glyport.ui.objc_bridge import make_objc_module
from fontlab_glyport.ui.vanilla import make_vanilla_module

KEY_UP, SHIFT = 0x01000013, 0x02000000


@pytest.fixture
def env():
    qt = make_qt()
    errors = []
    vanilla = make_vanilla_module(qt, error_sink=lambda e, s: errors.append((e, s)))
    appkit = make_appkit_classes(qt, error_sink=lambda e, s: errors.append((e, s)))
    objc = make_objc_module({"GSSteppingTextField": appkit["GSSteppingTextField"]})
    return vanilla, objc, errors


def _arrow_edit_text(vanilla, objc):
    """The corpus pattern (forum.glyphsapp.com/t/5894), verbatim in shape."""

    class ArrowEditText(vanilla.EditText):
        nsTextFieldClass = objc.lookUpClass("GSSteppingTextField")

        def _setCallback(self, callback):
            super()._setCallback(callback)
            if callback is not None and self._continuous:
                self._nsObject.setContinuous_(True)
                self._nsObject.setAction_(self._target.action_)
                self._nsObject.setTarget_(self._target)

    return ArrowEditText


def test_arrow_edit_text_when_typing_and_stepping_then_callback_once_each(env):
    vanilla, objc, errors = env
    seen = []
    w = vanilla.Window((200, 100))
    w.f = _arrow_edit_text(vanilla, objc)((10, 10, 80, 22), "5", callback=seen.append)
    w.open()
    widget = w.f.getNSView()
    widget.user_type("6")
    assert seen == [w.f], "typing fires the vanilla callback once, not twice"
    assert widget.user_key(KEY_UP, SHIFT)
    assert w.f.get() == "16" and seen == [w.f, w.f]
    assert errors == []
    assert isinstance(w.f._nsObject, GSSteppingTextField)


def test_stepping_class_when_no_override_then_step_reaches_callback(env):
    vanilla, objc, _ = env
    seen = []

    class Stepper(vanilla.EditText):
        nsTextFieldClass = objc.lookUpClass("GSSteppingTextField")

    w = vanilla.Window((200, 100))
    w.f = Stepper((10, 10, 80, 22), "1", callback=seen.append, continuous=False)
    w.f.getNSView().user_key(KEY_UP)
    assert (w.f.get(), seen) == ("2", [w.f])


def test_ns_text_field_class_when_unknown_then_unsupported(env):
    vanilla, _, _ = env

    class Odd(vanilla.EditText):
        nsTextFieldClass = object

    with pytest.raises(UnsupportedCapability) as info:
        Odd((0, 0, 10, 10))
    assert info.value.capability == "vanilla.EditText.nsTextFieldClass.object"


def test_handles_when_property_methods_then_act_on_same_widget(env):
    vanilla, _, _ = env
    w = vanilla.Window((200, 100))
    w.e = vanilla.EditText((0, 0, 80, 22), "")
    w.t = vanilla.TextBox((0, 30, 80, 22), "label")
    w.b = vanilla.Button((0, 60, 80, 22), "Go")
    w.e.getNSTextField().setPlaceholderString_("type")
    w.e._nsObject.setToolTip_("tip")
    w.t.getNSTextField().setAlignment_(2)
    w.b.getNSButton().setAccessibilityLabel_("go button")
    assert w.e.getNSTextField() is w.e._nsObject, "one handle per control"
    assert w.e.getNSView()._placeholder == "type"
    assert w.e.getNSView().toolTip == "tip"
    assert w.t.getNSView().alignment == 0x4 | 0x80
    assert w.t.getNSTextField().stringValue() == "label"
    assert w.b.getNSView()._accessible == "go button"
    with pytest.raises(UnsupportedCapability):
        w.t.getNSTextField().setPlaceholderString_("x")


def test_handle_when_script_sets_native_target_then_vanilla_route_yields(env):
    vanilla, _, _ = env
    seen, native = [], []

    class Target:
        def clicked_(self, sender):
            native.append(sender)

    w = vanilla.Window((200, 100))
    w.b = vanilla.Button((0, 0, 80, 22), "Go", callback=seen.append)
    target = Target()
    w.b.getNSButton().setTarget_(target)
    w.b.getNSButton().setAction_("clicked:")
    w.b.getNSView().user_click()
    assert seen == [] and native == [w.b.getNSButton()]


def test_handle_when_bound_to_defaults_then_checkbox_follows(env):
    vanilla, _, _ = env
    qt = make_qt()
    defaults = {"showNodes": 1}
    vanilla = make_vanilla_module(qt, error_sink=print)
    w = vanilla.Window((200, 100))
    w.c = vanilla.CheckBox((0, 0, 80, 22), "Nodes")
    appkit = vanilla.CheckBox._env.appkit
    appkit_defaults = appkit["NSUserDefaultsController"]._env.defaults
    appkit_defaults.update(defaults)
    controller = appkit["NSUserDefaultsController"].sharedUserDefaultsController()
    w.c.getNSButton().bind_toObject_withKeyPath_options_(
        "value", controller, "values.showNodes", None
    )
    assert w.c.get() is True
    controller.setValue_forKeyPath_(0, "values.showNodes")
    assert w.c.get() is False


def test_window_close_when_handles_wired_then_handle_slots_disconnected(env):
    vanilla, objc, _ = env
    w = vanilla.Window((200, 100))
    w.f = _arrow_edit_text(vanilla, objc)((10, 10, 80, 22), "5", callback=lambda s: 0)
    w.open()
    widget = w.f.getNSView()
    w.close()
    assert ("disconnect", widget, "textEdited") in LOG
    assert widget._owner is None, "the stepping widget forgets its wrapper"


def test_handle_when_control_has_no_native_class_then_unsupported(env):
    vanilla, _, _ = env
    with pytest.raises(UnsupportedCapability):
        _ = vanilla.Group((0, 0, 10, 10))._nsObject


def test_bound_adopted_checkbox_when_user_clicks_then_default_pushed_and_callback_once():
    qt = make_qt()
    seen = []
    vanilla = make_vanilla_module(qt, error_sink=print)
    w = vanilla.Window((200, 100))
    w.c = vanilla.CheckBox((0, 0, 80, 22), "Nodes", callback=seen.append, value=True)
    appkit = vanilla.CheckBox._env.appkit
    controller = appkit["NSUserDefaultsController"].sharedUserDefaultsController()
    controller.setValue_forKeyPath_(1, "values.nodes")
    w.c.getNSButton().bind_toObject_withKeyPath_options_(
        "value", controller, "values.nodes", None
    )
    w.c.getNSView().user_click()
    assert controller.valueForKeyPath_("values.nodes") == 0
    assert seen == [w.c], "the vanilla callback still runs exactly once"


def test_adopted_slider_when_vanilla_sets_then_cocoa_reads_same_value():
    vanilla = make_vanilla_module(make_qt(), error_sink=print)
    w = vanilla.Window((200, 100))
    w.s = vanilla.Slider((0, 0, 100, 20), minValue=0, maxValue=100, value=10)
    handle = w.s.getNSSlider()
    w.s.set(80)
    assert handle.floatValue() == pytest.approx(80)
    handle.setFloatValue_(25)
    assert w.s.get() == pytest.approx(25)


def test_adopted_child_when_frame_origin_set_then_widget_moves_in_parent():
    vanilla = make_vanilla_module(make_qt(), error_sink=print)
    w = vanilla.Window((300, 200))
    w.b = vanilla.Button((10, 20, 80, 22), "Go")
    handle = w.b.getNSButton()
    handle.setFrameOrigin_((40, 50))
    rect = w.b.getNSView().geometry
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == (40, 50, 80, 22)


def kit_env_views(view):
    return view._env.views


def test_vanilla_base_object_when_custom_ns_view_then_hosted_in_window():
    """R049 custom-nsview (Waterfall): a VanillaBaseObject subclass calls
    _setupView(NSView subclass, posSize); the view's widget is the control,
    _nsObject is the NSView instance and setNeedsDisplay_ reaches it."""
    from drawing_doubles import add_drawing

    errors = []
    vanilla = make_vanilla_module(
        add_drawing(make_qt()), error_sink=lambda e, s: errors.append((e, s))
    )
    kit = vanilla.Window._env.appkit

    class Preview(kit["NSView"]):
        def drawRect_(self, rect):
            pass

    class TheView(vanilla.VanillaBaseObject):
        nsGlyphPreviewClass = Preview

        def __init__(self, posSize):
            self._setupView(self.nsGlyphPreviewClass, posSize)
            self._nsObject.wrapper = self

    w = vanilla.Window((300, 200), "Waterfall")
    w.preview = TheView((10, 10, -10, -10))
    view = w.preview._nsObject
    assert isinstance(view, Preview) and view.wrapper is w.preview
    # vanilla owns the widget's lifetime: the AppKit environment never disposes
    # it again (a second deleteLater on a destroyed widget, native custom-nsview)
    assert view not in kit_env_views(view) and view._adopted
    assert w.preview.getNSView() is view._qt
    w.open()
    assert view._qt.geometry.width() == 280
    updates = []
    view._qt.update = lambda: updates.append(True)  # QWidget.update (not in the double)
    view.setNeedsDisplay_(True)
    assert updates == [True]
    w.close()
    assert errors == []
