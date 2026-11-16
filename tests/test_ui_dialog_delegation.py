# this_file: tests/test_ui_dialog_delegation.py
"""Vanilla policy stays in Glyport while owned dialog operations are shared."""

from types import SimpleNamespace

import fontlabapp.qt.dialogs as shared
import pytest
from ui_doubles import make_qt

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.ui import dialogs


def test_state_when_delegating_then_arguments_parent_style_and_owned_list_preserved(
    monkeypatch,
):
    assert dialogs._qt_dialogs is shared
    state = dialogs._Dialogs(make_qt(), lambda *args: None, None, {}, True)
    parent = object()
    window = SimpleNamespace(getNSWindow=lambda: parent)
    seen = []
    sentinel = object()

    def record(*args):
        seen.append(args)
        return sentinel

    monkeypatch.setattr(shared, "create_message_box", record)
    assert state.box("title", "detail", "warning", window) is sentinel
    assert seen[-1] == (state.gui, "title", "detail", "Warning", (parent,))
    monkeypatch.setattr(shared, "run_message_box", record)
    assert state.run_box(sentinel, 7) is sentinel
    assert seen[-1] == (sentinel, 7)
    monkeypatch.setattr(shared, "run_file_dialog", record)
    configure = lambda *args: None
    assert state.run_files(configure, "title", "dir", window) is sentinel
    assert seen[-1] == (state.gui, configure, "title", "dir", (parent,))
    monkeypatch.setattr(shared, "close_message_boxes", record)
    state.close()
    assert seen[-1][0] is state.boxes


def test_message_when_modeless_then_shared_show_receives_original_owned_storage(
    monkeypatch,
):
    seen = []
    module = dialogs.make_dialogs_module(make_qt(), error_sink=lambda *args: None)
    monkeypatch.setattr(
        shared, "show_message_box", lambda box, boxes: seen.append((box, boxes))
    )
    assert module.message("text") is None
    assert seen[0][1] is module.close.__self__.boxes


def test_callback_when_wrapped_then_foreign_wrapper_and_result_once():
    seen = []

    def wrap(callback):
        seen.append("wrapped")
        return lambda value: callback(("result", value))

    module = dialogs.make_dialogs_module(
        make_qt(), error_sink=lambda *args: None, answers={"askYesNo": 1}, wrap=wrap
    )
    assert module.askYesNo(resultCallback=seen.append) == 1
    assert seen == ["wrapped", ("result", 1)]


def test_foreign_policy_when_unsupported_then_location_and_dunder_behavior_retained():
    module = dialogs.make_dialogs_module(make_qt(), error_sink=lambda *args: None)
    with pytest.raises(AttributeError):
        _ = module.__missing__
    with pytest.raises(UnsupportedCapability, match="alertStyle.True"):
        module.message(alertStyle=True)
    with pytest.raises(UnsupportedCapability) as error:
        module.getFile()
    assert error.value.location.path == __file__
    assert "interactive=True" in error.value.recovery_action
