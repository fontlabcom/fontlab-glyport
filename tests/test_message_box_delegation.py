# this_file: tests/test_message_box_delegation.py
"""Cocoa/Glyphs policy delegates all current message-box lifetime mechanics."""

from types import SimpleNamespace as NS

import fontlabapp.qt.dialogs as shared
import pytest

from fontlab_glyport.glyphsapp.fontlab_dialogs import Dialogs
from fontlab_glyport.ui.cocoa_alert import alert_class


class Button:
    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        self._qt = object()
        return self

    def setTitle_(self, title):
        self.title_value = title

    def title(self):
        return self.title_value


@pytest.mark.parametrize("index", [None, 0, 1])
@pytest.mark.parametrize("accessory", [None, "accessory"])
@pytest.mark.parametrize(
    "style,kind", [(0, "Warning"), (1, "Information"), (2, "Critical")]
)
def test_alert_keeps_policy_and_passes_same_borrowed_widgets(
    index, accessory, style, kind, monkeypatch
):
    qt, box, calls = NS(QtGui=object()), object(), []
    Alert = alert_class(qt, Button, answers={}, interactive=True)
    alert = Alert.alloc().init()
    alert.setMessageText_("message")
    alert.setInformativeText_("details")
    alert.setAlertStyle_(style)
    alert.setAccessoryView_(accessory)
    first, second = alert.addButtonWithTitle_("Yes"), alert.addButtonWithTitle_("No")
    monkeypatch.setattr(
        shared, "create_message_box", lambda *args: calls.append(args) or box
    )

    def run(current, buttons, extra):
        assert (
            current is box and buttons == [first._qt, second._qt] and extra is accessory
        )
        return index

    monkeypatch.setattr(shared, "run_button_message_box", run)
    assert alert.runModal() == 1000 + (index if index is not None else 0)
    assert calls == [(qt.QtGui, "message", "details", kind)]


def test_default_alert_adds_original_ok_button_without_changing_answer_gate(
    monkeypatch,
):
    Alert = alert_class(NS(QtGui=object()), Button, answers={}, interactive=True)
    alert = Alert.alloc().init()
    monkeypatch.setattr(shared, "create_message_box", lambda *args: object())
    monkeypatch.setattr(shared, "run_button_message_box", lambda *args: 0)
    assert alert.runModal() == 1000
    assert [button.title() for button in alert.buttons()] == ["OK"]


def test_glyphs_hidden_box_release_passes_same_owner_storage(monkeypatch):
    bridge, calls = Dialogs(lambda: None, False, {}), []
    monkeypatch.setattr(
        shared, "release_closed_message_boxes", lambda boxes: calls.append(boxes)
    )
    bridge._release_closed()
    assert calls == [bridge._boxes] and calls[0] is bridge._boxes
