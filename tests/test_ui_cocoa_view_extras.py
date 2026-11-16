# this_file: tests/test_ui_cocoa_view_extras.py
"""NSView.setNeedsLayout_ and performSelector_withObject_afterDelay_ (R049
custom-nsview target, Tosche's Waterfall; code and tests from L2m)."""

from types import SimpleNamespace

from test_drawing_views import _kit

from fontlab_glyport.ui.cocoa import NSMakeRect


def test_view_when_needs_layout_then_widget_geometry_updated():
    """Waterfall: getNSTextField().setNeedsLayout_(True)."""
    kit, errors = _kit()
    view = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    updates = []
    view._qt.updateGeometry = lambda: updates.append(True)  # not in the double
    view.setNeedsLayout_(True)
    view.setNeedsLayout_(False)
    assert updates == [True] and errors == []
    kit["close"]()


def test_view_when_perform_selector_after_delay_then_timer_calls_it_with_errors_sunk():
    """Waterfall's drawRect_ defers its exception with
    performSelector_withObject_afterDelay_("showException:", e, 0.1)."""
    kit, errors = _kit()
    shots = []
    view_env = kit["NSView"].alloc().initWithFrame_(NSMakeRect(0, 0, 1, 1))._env
    view_env.qt.QtCore.QTimer = SimpleNamespace(
        singleShot=lambda ms, fn: shots.append((ms, fn))
    )

    class Late(kit["NSView"]):
        def showException_(self, error):
            raise error

    view = Late.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    view.performSelector_withObject_afterDelay_(
        "showException:", ValueError("late"), 0.1
    )
    ((ms, fire),) = shots
    assert ms == 100
    fire()
    assert [str(e) for e in errors] == ["late"]
    kit["close"]()
