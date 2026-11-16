# this_file: tests/test_key_event_delegation.py
"""Cocoa/Vanilla keep key policy while App owns acceptance and native forwarding."""
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from fontlabapp.qt.events.key import key_press_handler

from fontlab_glyport.ui import cocoa_controls, vanilla, vanilla_controls

CASES = [
    (cocoa_controls, '_stepping_line_edit', '_step_key', True, 'SteppingLineEdit'),
    (vanilla_controls, '_table_widget_class', '_delete_key', False, 'TableWidget'),
    (vanilla, '_window_widget_class', '_press_default', False, 'WindowWidget'),
]


@pytest.mark.parametrize('module,factory,method,event_argument,name', CASES)
@pytest.mark.parametrize('owned,handled', [(False,False),(True,False),(True,True)])
def test_adapter_when_key_received_then_shared_mechanism_and_original_policy(monkeypatch,module,factory,method,event_argument,name,owned,handled):
    seen = []
    def shared(base,handle):
        seen.append((base,handle))
        return key_press_handler(base,handle)
    monkeypatch.setattr(module,'key_press_handler',shared)
    class Base:
        def keyPressEvent(self,event):
            self.base_events.append(event)
    cls = getattr(module,factory)(Base)
    assert cls.__name__ == name and cls.__bases__ == (Base,)
    widget = cls();widget.base_events = []
    policy = Mock(return_value=handled)
    widget._owner = NS(**{method:policy}) if owned else None
    event = NS(key=lambda:127,accept=Mock())
    widget.keyPressEvent(event)
    assert len(seen) == 1 and seen[0][0] is Base
    if owned:
        policy.assert_called_once_with(event if event_argument else 127)
    else:
        policy.assert_not_called()
    if owned and handled:
        event.accept.assert_called_once_with()
        assert not widget.base_events
    else:
        event.accept.assert_not_called()
        assert widget.base_events == [event]


@pytest.mark.parametrize('module,factory,method,event_argument,name', CASES)
def test_adapter_when_policy_raises_then_no_accept_or_native_fallback(module,factory,method,event_argument,name):
    class Base:
        keyPressEvent = Mock()
    error = RuntimeError('owned callback failure')
    widget = getattr(module,factory)(Base)()
    widget._owner = NS(**{method:Mock(side_effect=error)})
    event = NS(key=lambda:127,accept=Mock())
    with pytest.raises(RuntimeError) as observed:
        widget.keyPressEvent(event)
    assert observed.value is error
    event.accept.assert_not_called()
    Base.keyPressEvent.assert_not_called()
