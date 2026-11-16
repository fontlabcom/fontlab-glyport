# this_file: native-drivers/vanilla_steps.py
"""B10 actual Qt-backed controls/callbacks; physical keyboard/dialogs remain manual."""


def vanilla_phases():
    yield (
        "vanilla-create",
        """
from fly.gp.ui.session import VanillaSession
session = VanillaSession()
v = session.vanilla
window = v.Window((420, 420), 'Owned Ω')
window.group = v.Group((10, 10, -10, -10))
g = window.group
events = []
g.label = v.TextBox((0, 0, 200, 24), 'Ω label')
g.entry = v.EditText((0, 30, 200, 24), 'Ω entry', callback=lambda sender: events.append(sender))
g.button = v.Button((0, 60, 120, 24), 'Ω button', callback=lambda sender: events.append(sender))
g.check = v.CheckBox((0, 90, 180, 24), 'Ω check', callback=lambda sender: events.append(sender))
g.slider = v.Slider((0, 120, 200, 24), minValue=0, maxValue=100, callback=lambda sender: events.append(sender))
g.popup = v.PopUpButton((0, 150, 200, 24), ['Ω', '日本語'], callback=lambda sender: events.append(sender))
g.list = v.List((0, 180, 200, 120), ['Ω', '日本語'])
window.open()
""",
    )
    yield (
        "vanilla-constructor-failure",
        """
count_before = len(session._windows)
try:
    v.Window((1, 2, 3), 'Invalid frame after widget allocation')
except ValueError:
    pass
else:
    raise AssertionError('Invalid window frame accepted')
assert len(session._windows) == count_before + 1
result = {'partial_widget_retained': True}
""",
    )
    yield (
        "vanilla-unopened",
        """
import weakref
unopened = v.Window((200, 100), 'Unopened owned window')
unopened.button = v.Button((10, 10, 160, 24), 'Never opened', callback=lambda sender: events.append(sender))
unopened_ref = weakref.ref(unopened)
del unopened
assert unopened_ref() is not None and unopened_ref() in session._windows
""",
    )
    yield (
        "vanilla-set-get",
        """
g.entry.set('changed Ω'); assert g.entry.get() == 'changed Ω'
g.check.set(True); assert g.check.get()
g.slider.set(25); assert abs(g.slider.get() - 25) < 0.01
g.popup.set(1); assert g.popup.get() == 1
g.list.setSelection([1]); assert g.list.getSelection() == [1]
assert g.list.get() == ['Ω', '日本語']
assert not events, 'programmatic setters must be quiet'
""",
    )
    yield (
        "vanilla-callbacks",
        """
g.button.getNSView().click()
assert len(events) == 1 and events[-1] is g.button
g.check.getNSView().click()
assert len(events) == 2 and events[-1] is g.check
g.button.enable(False); g.button.getNSView().click()
assert len(events) == 2
g.button.show(False); assert not g.button.getNSView().isVisible()
result = {'native_callback_senders': ['button', 'checkbox'],
          'manual_remaining': ['physical typing/keyboard', 'popup user selection', 'file dialog select/cancel']}
""",
    )
    yield (
        "vanilla-close",
        "session.close()\nsession.close()\nassert not session._windows\nassert all(not control._slots for control in g._children.values())",
    )
    yield (
        "vanilla-after-event-loop",
        """
# This is a later RPC: FontLab's normal event loop runs between calls.
assert not session._windows
if unopened_ref() is not None:
    assert unopened_ref()._closed and not unopened_ref().button._slots
result = {'signals_disconnected': True, 'unopened_session_reference_released': True,
          'event_loop_returned': True, 'native_widget_destruction': 'manual observation remains'}
""",
    )
