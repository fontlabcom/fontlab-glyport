# this_file: tests/test_ui_dialogs.py
"""vanilla.dialogs over PythonQt-shaped doubles: answers, modal gate, cleanup."""

import pytest
from ui_doubles import LOG, make_qt
from ui_doubles_dialogs import QFileDialog, QMessageBox

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.ui.dialogs import dialogs_provider, make_dialogs_module
from fontlab_glyport.ui.vanilla import make_vanilla_module


def _module(qt, **options):
    errors = []
    options.setdefault("error_sink", lambda exc, s: errors.append(exc))
    return make_dialogs_module(qt, **options), errors


def _execs():
    return [entry for entry in LOG if entry[0] == "exec"]


def test_message_when_not_interactive_then_nonmodal_box_returns_none():
    qt = make_qt()
    dialogs, _ = _module(qt)
    assert dialogs.message("Title", "Details") is None
    box = next(e[1] for e in LOG if e[0] == "create")
    assert isinstance(box, QMessageBox), "message() must build a QMessageBox"
    assert (box._text, box._informative, box._modal) == ("Title", "Details", False)
    assert box.isVisible(), "the non-modal box must be shown"
    assert _execs() == [], "a non-interactive message must never run exec()"


def test_message_when_closed_then_boxes_closed_and_deleted():
    qt = make_qt()
    dialogs, _ = _module(qt)
    dialogs.message("one")
    dialogs.close()
    box = next(e[1] for e in LOG if e[0] == "create")
    assert ("close", box) in LOG and ("deleteLater", box) in LOG


@pytest.mark.parametrize(
    ("name", "call"),
    [
        ("askYesNo", lambda d: d.askYesNo("Sure?")),
        ("askYesNoCancel", lambda d: d.askYesNoCancel("Sure?")),
        ("getFile", lambda d: d.getFile()),
        ("getFolder", lambda d: d.getFolder()),
        ("putFile", lambda d: d.putFile()),
    ],
)
def test_result_dialog_when_no_answer_and_not_interactive_then_unsupported(name, call):
    dialogs, _ = _module(make_qt())
    with pytest.raises(UnsupportedCapability) as info:
        call(dialogs)
    assert info.value.capability == f"vanilla.dialogs.{name}"
    assert info.value.location is not None, "the error must point at the script line"
    assert info.value.location.path == __file__
    assert _execs() == []


def test_result_dialog_when_answered_then_answer_and_callback_once():
    qt = make_qt()
    answers = {"askYesNo": 1, "getFile": ["/tmp/a.txt"], "putFile": None}
    dialogs, _ = _module(qt, answers=answers)
    seen = []
    assert dialogs.askYesNo("Apply?", resultCallback=seen.append) == 1
    assert dialogs.getFile(fileTypes=["txt"]) == ["/tmp/a.txt"]
    assert dialogs.putFile(fileName="x.pdf") is None, "a None answer means cancel"
    assert seen == [1], "resultCallback must receive the result exactly once"
    assert _execs() == []


def test_result_callback_when_it_raises_then_error_goes_to_sink():
    boom = ValueError("boom")

    def callback(result):
        raise boom

    dialogs, errors = _module(make_qt(), answers={"askYesNo": 0})
    assert dialogs.askYesNo("x", resultCallback=callback) == 0
    assert errors == [boom]


@pytest.mark.parametrize(
    ("button", "plain", "cancel"),
    [
        (QMessageBox.Yes, 1, 1),
        (QMessageBox.No, 0, 0),
        (QMessageBox.Cancel, 0, -1),
    ],
)
def test_ask_when_interactive_then_exec_maps_buttons(
    monkeypatch, button, plain, cancel
):
    monkeypatch.setattr(QMessageBox, "exec_result", button)
    dialogs, _ = _module(make_qt(), interactive=True)
    assert dialogs.askYesNo("q") == plain
    assert dialogs.askYesNoCancel("q") == cancel
    boxes = [e[1] for e in _execs()]
    assert boxes[0]._buttons == QMessageBox.Yes | QMessageBox.No
    assert boxes[1]._buttons == QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
    assert all(("deleteLater", box) in LOG for box in boxes)


def test_get_file_when_interactive_then_file_dialog_configured(monkeypatch):
    monkeypatch.setattr(QFileDialog, "exec_files", ["/a.txt", "/b.txt"])
    dialogs, _ = _module(make_qt(), interactive=True)
    files = dialogs.getFile(
        title="Load",
        directory="/tmp",
        fileName="a.txt",
        allowsMultipleSelection=True,
        fileTypes=["txt", ".md"],
    )
    assert files == ["/a.txt", "/b.txt"], "getFile returns a list"
    dialog = _execs()[0][1]
    assert dialog._mode == QFileDialog.ExistingFiles
    assert dialog._filters == ["Files (*.txt *.md)"]
    assert (dialog._directory, dialog._select, dialog.windowTitle) == (
        "/tmp",
        "a.txt",
        "Load",
    )


def test_get_folder_and_put_file_when_interactive_then_modes(monkeypatch):
    monkeypatch.setattr(QFileDialog, "exec_files", ["/out/x.pdf"])
    dialogs, _ = _module(make_qt(), interactive=True)
    assert dialogs.getFolder(messageText="Pick") == ["/out/x.pdf"]
    assert dialogs.putFile(fileName="x.pdf", canCreateDirectories=False) == "/out/x.pdf"
    folder, save = (e[1] for e in _execs())
    assert folder._mode == QFileDialog.Directory
    assert folder._options == {QFileDialog.ShowDirsOnly: True}
    assert save._accept == QFileDialog.AcceptSave
    assert save._options == {QFileDialog.ReadOnly: True}
    assert save._select == "x.pdf"


def test_dialog_when_interactive_and_cancelled_then_none(monkeypatch):
    monkeypatch.setattr(QFileDialog, "exec_files", None)
    dialogs, _ = _module(make_qt(), interactive=True)
    assert dialogs.getFile() is None
    assert dialogs.putFile() is None


def test_dialog_when_parent_window_then_dialog_parented_to_its_widget(monkeypatch):
    qt = make_qt()
    vanilla = make_vanilla_module(qt, error_sink=lambda e, s: None)
    window = vanilla.Window((200, 100))
    monkeypatch.setattr(QFileDialog, "exec_files", ["/f"])
    dialogs, _ = _module(qt, interactive=True)
    dialogs.getFile(parentWindow=window)
    assert _execs()[0][1].parentWidget() is window.getNSWindow()


@pytest.mark.parametrize(
    "call",
    [
        lambda d: d.message("x", icon="note"),
        lambda d: d.putFile(accessoryView=object()),
        lambda d: d.message("x", alertStyle="loud"),
        lambda d: d.getFile(parentWindow=object()),
    ],
)
def test_dialog_when_unsupported_option_then_raises(call):
    dialogs, _ = _module(make_qt(), answers={"putFile": None, "getFile": None})
    with pytest.raises((UnsupportedCapability, TypeError)):
        call(dialogs)


def test_alert_style_when_ns_integer_then_icon_mapped():
    qt = make_qt()
    dialogs, _ = _module(qt)
    dialogs.message("x", alertStyle=2)
    dialogs.message("y", alertStyle="informational")
    boxes = [e[1] for e in LOG if e[0] == "create"]
    assert [b._icon for b in boxes] == [QMessageBox.Critical, QMessageBox.Information]


def test_unknown_name_when_read_then_unsupported_with_location():
    dialogs, _ = _module(make_qt())
    with pytest.raises(UnsupportedCapability) as info:
        dialogs.askString("t", "m", "")
    assert info.value.capability == "vanilla.dialogs.askString"


def test_provider_when_imported_as_submodule_then_resolves(tmp_path):
    qt = make_qt()
    script = tmp_path / "script.py"
    script.write_text(
        "import vanilla.dialogs\n"
        "from vanilla.dialogs import askYesNo\n"
        "RESULT = (askYesNo('q'), vanilla.dialogs.askYesNo is askYesNo)\n"
    )
    vanilla = lambda: make_vanilla_module(qt, error_sink=lambda e, s: None)
    sink = lambda e, s: None
    ctx = ExecutionContext(
        tmp_path,
        "glyphs3",
        {
            "vanilla": vanilla,
            "vanilla.dialogs": dialogs_provider(qt, sink, answers={"askYesNo": 1}),
        },
    )
    stage = ctx.run(script)
    assert stage.status == "passed", stage
    assert ctx.globals["RESULT"] == (1, True)
    ctx.close()


def test_provider_when_on_close_then_context_close_closes_boxes(tmp_path):
    qt = make_qt()
    hooks = []
    provide = dialogs_provider(qt, lambda e, s: None, on_close=hooks.append)
    module = provide()
    module.message("bye")
    assert len(hooks) == 1
    hooks[0]()
    box = next(e[1] for e in LOG if e[0] == "create")
    assert ("deleteLater", box) in LOG
