# this_file: tests/test_glyphs_dialog_execution.py
"""Glyphs policy remains local while Qt execution/deletion delegates to App."""

from types import SimpleNamespace as NS

import fontlabapp.qt.dialogs as shared
import pytest

from fontlab_glyport.glyphsapp import fontlab_dialogs as api


class Dialog:
    def __init__(self, accepted=1, fail=None):
        self.events, self.accepted, self.fail = [], accepted, fail

    def record(self, name, *args):
        self.events.append((name, *args))
        if self.fail == name:
            raise RuntimeError(name)

    def setWindowTitle(self, value):
        self.record("title", value)

    def setLabelText(self, value):
        self.record("label", value)

    def setTextValue(self, value):
        self.record("value", value)

    def setOkButtonText(self, value):
        self.record("ok", value)

    def setDirectory(self, value):
        self.record("directory", value)

    def exec(self):
        self.record("exec")
        return self.accepted

    def textValue(self):
        self.record("text")
        return "answer"

    def selectedFiles(self):
        self.record("files")
        return ("a", "b")

    def deleteLater(self):
        self.record("delete")


@pytest.mark.parametrize("accepted", [0, 1])
def test_input_dialog_preserves_raw_glyphs_values_defaults_and_acceptance(
    accepted, monkeypatch
):
    dialog = Dialog(accepted)
    calls, original = [], shared.run_owned_dialog

    def execute(*args):
        calls.append(args[0])
        return original(*args)

    monkeypatch.setattr(shared, "run_owned_dialog", execute)
    bridge = api.Dialogs(lambda: NS(QInputDialog=lambda: dialog), True, {})
    message, value, title, button = (object() for _ in range(4))
    assert bridge.ask_string(message, value, title, button, "ignored") == (
        "answer" if accepted else None
    )
    assert calls == [dialog]
    assert dialog.events[:4] == [
        ("title", title),
        ("label", message),
        ("value", value),
        ("ok", button),
    ]
    assert dialog.events[-1] == ("delete",)


@pytest.mark.parametrize("failure", [None, "title", "directory", "exec", "files"])
def test_file_dialog_preserves_raw_values_and_cleanup_after_every_owned_failure(
    failure,
):
    dialog = Dialog(fail=failure)
    gui = NS(QFileDialog=lambda: dialog)
    bridge = api.Dialogs(lambda: gui, True, {})
    caption, directory = object(), object()

    def configure(kind, current):
        assert kind is gui.QFileDialog and current is dialog
        current.record("configure")

    if failure:
        with pytest.raises(RuntimeError, match=failure):
            bridge._files(configure, caption, directory)
    else:
        assert bridge._files(configure, caption, directory) == ["a", "b"]
    assert dialog.events[0] == ("title", caption)
    assert dialog.events[-1] == ("delete",)


def test_close_delegates_the_original_owned_storage_identity(monkeypatch):
    bridge, seen = api.Dialogs(lambda: None, False, {}), []
    monkeypatch.setattr(shared, "close_message_boxes", lambda boxes: seen.append(boxes))
    bridge.close()
    assert seen == [bridge._boxes] and seen[0] is bridge._boxes
