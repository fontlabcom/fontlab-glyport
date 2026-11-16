# this_file: tests/test_glyphsapp_fontlab_bridge.py
"""FontLab GlyphsBridge against strict native doubles (no FontLab, no Qt).

The doubles mirror stub shapes (fontlab.pyi, PythonQt QtCore/QtGui/private)
and log calls in order. Passing here is not native evidence; WORK.md lists
the native acceptance checklist.
"""

import subprocess
import sys
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import pytest

from fontlab_glyport.errors import HostUnavailable, UnsupportedCapability
from fontlab_glyport.execution import ExecutionContext
from fontlab_glyport.glyphsapp import make_glyphsapp_module
from fontlab_glyport.glyphsapp.fontlab_bridge import (
    NOTICE_TIMEOUT_MS,
    POLL_INTERVAL_MS,
    FontLabGlyphsBridge,
    fontlab_glyphsapp_provider,
    interface_state,
)
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend

LOG: list[tuple] = []


class Signal:
    __slots__ = ("fail_disconnect", "name", "slots")

    def __init__(self, name):
        self.name, self.slots, self.fail_disconnect = name, [], 0

    def connect(self, slot):
        self.slots.append(slot)
        LOG.append(("connect", self.name))

    def disconnect(self, slot):
        if self.fail_disconnect:
            self.fail_disconnect -= 1
            raise RuntimeError("native disconnect failed")
        self.slots.remove(slot)
        LOG.append(("disconnect", self.name))

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


class QTimer:
    """Native instance: rejects new attributes like PythonQt wrappers."""

    __slots__ = ("active", "interval", "timeout")
    made: ClassVar[list] = []

    def __init__(self):
        self.timeout, self.active, self.interval = Signal("timeout"), False, None
        QTimer.made.append(self)

    def start(self, msec):
        self.active, self.interval = True, msec
        LOG.append(("start", msec))

    def stop(self):
        self.active = False
        LOG.append(("stop",))

    def isActive(self):
        return self.active

    def deleteLater(self):
        LOG.append(("deleteLater", "QTimer"))


class StatusBar:
    def __init__(self):
        self.message = ""

    def showMessage(self, text, timeout):  # both arguments, explicitly
        self.message = text
        LOG.append(("showMessage", text, timeout))

    def currentMessage(self):
        return self.message


class MainWindow:
    def __init__(self):
        self.bar = StatusBar()

    def statusBar(self):
        return self.bar

    def doShowOutputPanel(self):
        LOG.append(("doShowOutputPanel",))

    def doClearOutput(self):
        LOG.append(("doClearOutput",))


class _Widget:
    __slots__ = ("calls", "files", "result", "visible")
    kind = "widget"

    def __init__(self):
        self.calls, self.result, self.files, self.visible = [], 1, (), True
        type(self).made.append(self)

    def isVisible(self):
        return self.visible

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def record(*args):
            self.calls.append((name, *args))
            LOG.append((name, self.kind, *args))

        return record

    def exec(self):
        self.calls.append(("exec",))
        return type(self).next_result

    def textValue(self):
        return type(self).text

    def selectedFiles(self):
        return type(self).files_selected


class QMessageBox(_Widget):
    __slots__ = ()
    kind, made, AcceptRole = "QMessageBox", [], "AcceptRole"


class QInputDialog(_Widget):
    __slots__ = ()
    kind, made, next_result, text = "QInputDialog", [], 1, "typed"


class QFileDialog(_Widget):
    __slots__ = ()
    kind, made, next_result, files_selected = "QFileDialog", [], 1, ("/a", "/b")
    Directory, ExistingFile, ExistingFiles = (
        "Directory",
        "ExistingFile",
        "ExistingFiles",
    )
    AcceptSave, ShowDirsOnly = "AcceptSave", "ShowDirsOnly"


@pytest.fixture
def native(monkeypatch):
    LOG.clear()
    for cls in (QTimer, QMessageBox, QInputDialog, QFileDialog):
        cls.made = []
    QInputDialog.next_result = QFileDialog.next_result = 1
    main = MainWindow()
    package = SimpleNamespace(id=7, isValid=True)
    glyph = SimpleNamespace(id=11, isValid=True)
    workspace = SimpleNamespace(currentPackage=package, currentGlyph=glyph)
    fontlab = ModuleType("fontlab")
    fontlab.MainWindow = lambda: main
    fontlab.UpdateActiveCanvas = lambda: LOG.append(("UpdateActiveCanvas",))
    fontlab.flWorkspace = SimpleNamespace(instance=lambda: workspace)
    # Native fact (glyport-model/probe_signals.json): flItems.instance().qobject.
    items = SimpleNamespace(
        packageReaded=Signal("packageReaded"),
        signalPackageClosed=Signal("signalPackageClosed"),
    )
    fontlab.flItems = SimpleNamespace(instance=lambda: SimpleNamespace(qobject=items))
    qtcore, qtgui = ModuleType("PythonQt.QtCore"), ModuleType("PythonQt.QtGui")
    qtcore.QTimer = QTimer
    qtgui.QMessageBox, qtgui.QInputDialog = QMessageBox, QInputDialog
    qtgui.QFileDialog = QFileDialog
    pythonqt = ModuleType("PythonQt")
    pythonqt.QtCore, pythonqt.QtGui = qtcore, qtgui
    for name, module in {
        "fontlab": fontlab,
        "PythonQt": pythonqt,
        "PythonQt.QtCore": qtcore,
        "PythonQt.QtGui": qtgui,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return SimpleNamespace(main=main, workspace=workspace, fontlab=fontlab, items=items)


class State:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value


def _bridge(**options):
    log: list[str] = []
    options.setdefault("version", (3.2, 3234.0))
    return FontLabGlyphsBridge(log=log.append, **options), log


# Import boundary --------------------------------------------------------------


def test_import_when_module_loaded_then_no_native_module_imported():
    code = (
        "import sys\n"
        "import fontlab_glyport.glyphsapp.fontlab_bridge\n"
        "bad = [m for m in ('fontlab', 'fontgate', 'PythonQt') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert out.returncode == 0, out.stderr


def test_redraw_when_fontlab_missing_then_host_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "fontlab", None)
    bridge, _ = _bridge()
    with pytest.raises(HostUnavailable, match="fontlab"):
        bridge.redraw()


# Host facts, output, notification, redraw ------------------------------------


def test_facts_when_configured_then_reported_without_native_calls(monkeypatch):
    monkeypatch.setitem(sys.modules, "fontlab", None)
    bridge, _ = _bridge(language="de-CH", version=(3.3, 3300.0))
    assert bridge.ui_language() == "de-CH"
    assert (bridge.version_number(), bridge.build_number()) == (3.3, 3300.0)


def test_output_when_default_then_panel_untouched_and_no_native_import(monkeypatch):
    monkeypatch.setitem(sys.modules, "fontlab", None)
    bridge, log = _bridge()
    bridge.show_macro_window()
    bridge.clear_log()
    assert log == [], "default output calls must not touch FontLab"


def test_output_when_opted_in_then_show_and_clear_output_panel(native):
    bridge, _ = _bridge(output_panel=True)
    bridge.show_macro_window()
    bridge.clear_log()
    assert LOG == [("doShowOutputPanel",), ("doClearOutput",)]


def test_notification_when_main_window_then_status_bar_message(native):
    bridge, log = _bridge()
    bridge.show_notification("Done", "3 glyphs")
    assert LOG == [("showMessage", "Done: 3 glyphs", NOTICE_TIMEOUT_MS)]
    assert native.main.statusBar().currentMessage() == "Done: 3 glyphs"
    assert log == []


def test_notification_when_no_main_window_then_logged(native):
    native.fontlab.MainWindow = lambda: None
    bridge, log = _bridge()
    bridge.show_notification("Done", "ok")
    assert log == ["[notification] Done: ok\n"]


def test_redraw_when_called_then_update_active_canvas_only(native):
    bridge, _ = _bridge()
    bridge.redraw()
    assert LOG == [("UpdateActiveCanvas",)]


# UPDATEINTERFACE subscribe / poll / remove ------------------------------------


def test_subscribe_when_first_then_one_owned_timer_connected_and_started(native):
    bridge, _ = _bridge(state=State())
    first = bridge.subscribe("GSUpdateInterface", print)
    second = bridge.subscribe("GSUpdateInterface", repr)
    assert first != second
    assert len(QTimer.made) == 1
    assert LOG == [("connect", "timeout"), ("start", POLL_INTERVAL_MS)]


@pytest.mark.parametrize(
    "event",
    ["GSDocumentWasSavedSuccessfully", "DrawBackground", "TabDidOpenNotification"],
)
def test_subscribe_when_unsupported_event_then_named_and_nothing_started(native, event):
    bridge, _ = _bridge()
    with pytest.raises(UnsupportedCapability) as info:
        bridge.subscribe(event, print)
    assert info.value.capability == f"Glyphs.addCallback.{event}"
    assert QTimer.made == []


def test_poll_when_state_unchanged_then_nothing_runs(native):
    calls = []
    bridge, _ = _bridge(state=State())
    bridge.subscribe("GSUpdateInterface", calls.append)
    assert bridge.poll() == 0
    assert calls == []


def test_poll_when_state_changes_then_each_subscriber_once_with_notification(native):
    state, seen = State(), []
    bridge, _ = _bridge(state=state)
    bridge.subscribe("GSUpdateInterface", lambda sender: seen.append(("a", sender)))
    bridge.subscribe("GSUpdateInterface", lambda sender: seen.append(("b", sender)))
    state.value = 1
    QTimer.made[0].timeout.emit()
    assert [tag for tag, _ in seen] == ["a", "b"]
    assert seen[0][1].name() == "GSUpdateInterface" and seen[0][1].object() is None
    assert bridge.poll() == 0, "the new state is the baseline"


def test_remove_when_last_then_disconnect_stop_delete_in_order(native):
    bridge, _ = _bridge(state=State())
    token = bridge.subscribe("GSUpdateInterface", print)
    LOG.clear()
    bridge.remove(token)
    assert LOG == [("disconnect", "timeout"), ("stop",), ("deleteLater", "QTimer")]
    bridge.remove(token)  # idempotent (R026)
    assert len(LOG) == 3
    with pytest.raises(KeyError):
        bridge.remove(99)
    with pytest.raises(KeyError):
        bridge.remove("token-1")


def test_remove_when_not_last_then_timer_keeps_running(native):
    bridge, _ = _bridge(state=State())
    token = bridge.subscribe("GSUpdateInterface", print)
    bridge.subscribe("GSUpdateInterface", repr)
    bridge.remove(token)
    assert QTimer.made[0].isActive()


def test_remove_when_disconnect_fails_then_token_kept_for_retry(native):
    calls = []
    state = State()
    bridge, _ = _bridge(state=state)
    token = bridge.subscribe("GSUpdateInterface", calls.append)
    QTimer.made[0].timeout.fail_disconnect = 1
    with pytest.raises(RuntimeError):
        bridge.remove(token)
    assert QTimer.made[0].isActive(), "a failed disconnect must leave the timer running"
    state.value = 1
    QTimer.made[0].timeout.emit()
    assert len(calls) == 1, "a failed removal must keep the subscription firing"
    bridge.remove(token)
    assert ("deleteLater", "QTimer") in LOG


def test_fire_when_callback_removes_itself_and_next_then_next_skipped(native):
    calls = []
    bridge, _ = _bridge(state=State())
    tokens = {}

    def first(sender):
        calls.append("first")
        bridge.remove(tokens["first"])
        bridge.remove(tokens["second"])

    tokens["first"] = bridge.subscribe("GSUpdateInterface", first)
    tokens["second"] = bridge.subscribe("GSUpdateInterface", calls.append)
    assert bridge._fire() == 1
    assert calls == ["first"]
    assert not QTimer.made[0].isActive()


@pytest.mark.parametrize(
    "error", [RuntimeError("boom"), SystemExit(2), KeyboardInterrupt()]
)
def test_fire_when_callback_raises_then_contained_logged_and_others_run(native, error):
    calls = []
    bridge, log = _bridge(state=State())

    def bad(sender):
        raise error

    bridge.subscribe("GSUpdateInterface", bad)
    bridge.subscribe("GSUpdateInterface", calls.append)
    assert bridge._fire() == 2
    assert len(calls) == 1
    failures = [line for line in log if "GSUpdateInterface callback failed" in line]
    assert len(failures) == 1
    assert type(error).__name__ in failures[0]


def test_poll_when_state_raises_then_contained_and_baseline_kept(native):
    def broken():
        raise RuntimeError("native read failed")

    bridge, log = _bridge(state=broken)
    bridge.subscribe("GSUpdateInterface", print)
    assert bridge.poll() == 0
    assert any("interface state failed" in line for line in log)


def test_fire_when_log_also_raises_then_still_contained(native):
    def bad_log(text):
        raise RuntimeError("log broken")

    bridge = FontLabGlyphsBridge(log=bad_log, version=(3.2, 3234.0), state=State())
    bridge.subscribe("GSUpdateInterface", lambda sender: 1 / 0)
    assert bridge._fire() == 1


def test_interface_state_when_read_then_registered_ids_only(native):
    assert interface_state() == (7, 11)
    native.workspace.currentPackage = None
    native.workspace.currentGlyph = SimpleNamespace(id=3, isValid=False)
    assert interface_state() == (None, None)


def test_close_when_subscribed_and_message_open_then_all_torn_down(native):
    bridge, _ = _bridge(state=State())
    bridge.subscribe("GSUpdateInterface", print)
    bridge.message("hi", "Alert", None)
    bridge.close()
    bridge.close()
    assert ("deleteLater", "QTimer") in LOG
    assert QMessageBox.made[0].calls[-2:] == [("close",), ("deleteLater",)]
    assert bridge._fire() == 0


# Dialogs -----------------------------------------------------------------------


def test_message_when_shown_then_non_modal_retained_with_ok_button(native):
    bridge, _ = _bridge()
    assert bridge.message("Saved", "Alert", "Fine") is None
    box = QMessageBox.made[0]
    assert ("addButton", "Fine", "AcceptRole") in box.calls
    assert ("setModal", False) in box.calls and box.calls[-1] == ("show",)
    assert ("exec",) not in box.calls


def test_dialogs_when_answers_injected_then_returned_without_qt(monkeypatch):
    monkeypatch.setitem(sys.modules, "PythonQt.QtGui", None)
    answers = {
        "message": None,
        "ask_string": None,
        "get_folder": "/tmp/x",
        "get_open_file": ["/a.ufo"],
        "get_save_file": "/out.ufo",
    }
    bridge, _ = _bridge(answers=answers)
    assert bridge.message("m", "t", None) is None
    assert bridge.ask_string("m", None, "t", None, None) is None  # injected cancel
    assert bridge.get_folder(None, False, None) == "/tmp/x"
    assert bridge.get_open_file(None, None, True, None, None) == ["/a.ufo"]
    assert bridge.get_save_file(None, "a.ufo", None) == "/out.ufo"


def test_dialog_when_no_answer_and_not_interactive_then_located_unsupported(
    native, tmp_path
):
    module = make_glyphsapp_module(
        Model(FakeBackend()), _bridge()[0], defaults={}, error_sink=print
    )
    script = tmp_path / "ask.py"
    script.write_text("AskString('Name?')\n")
    with pytest.raises(UnsupportedCapability) as info:
        exec(compile(script.read_text(), str(script), "exec"), vars(module).copy())  # noqa: S102
    assert info.value.capability == "GlyphsApp.AskString"
    assert (info.value.location.path, info.value.location.line) == (str(script), 1)
    assert "interactive=True" in info.value.recovery_action
    assert QInputDialog.made == []


def test_ask_string_when_interactive_then_modal_exec_and_deleted(native):
    bridge, _ = _bridge(interactive=True)
    assert bridge.ask_string("Name?", "A", "Glyphs", "Go", "hint") == "typed"
    calls = QInputDialog.made[0].calls
    assert ("setLabelText", "Name?") in calls and ("setTextValue", "A") in calls
    assert ("setOkButtonText", "Go") in calls
    assert calls[-2:] == [("exec",), ("deleteLater",)]


def test_ask_string_when_cancelled_then_none(native):
    QInputDialog.next_result = 0
    bridge, _ = _bridge(interactive=True)
    assert bridge.ask_string("Name?", None, "Glyphs", None, None) is None
    assert QInputDialog.made[0].calls[-1] == ("deleteLater",)


def test_get_open_file_when_multiple_then_list_and_extension_filter(native):
    bridge, _ = _bridge(interactive=True)
    files = bridge.get_open_file("Pick", None, True, ["ufo", ".glyphs"], "/fonts")
    assert files == ["/a", "/b"]
    calls = QFileDialog.made[0].calls
    assert ("setFileMode", "ExistingFiles") in calls
    assert ("setNameFilters", ["Files (*.ufo *.glyphs)"]) in calls
    assert ("setDirectory", "/fonts") in calls


def test_get_folder_when_single_then_first_path_or_none_on_cancel(native):
    bridge, _ = _bridge(interactive=True)
    assert bridge.get_folder("Folder", False, None) == "/a"
    assert ("setFileMode", "Directory") in QFileDialog.made[0].calls
    QFileDialog.next_result = 0
    assert bridge.get_folder("Folder", False, None) is None


def test_get_save_file_when_interactive_then_save_mode_and_proposed_name(native):
    bridge, _ = _bridge(interactive=True)
    assert bridge.get_save_file("Save", "a.ufo", ["ufo"]) == "/a"
    calls = QFileDialog.made[0].calls
    assert ("setAcceptMode", "AcceptSave") in calls and ("selectFile", "a.ufo") in calls


# ExecutionContext wiring --------------------------------------------------------


def test_provider_when_script_runs_then_output_callbacks_and_close_hooks(
    native, tmp_path
):
    state = State()
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = fontlab_glyphsapp_provider(
        ctx, version=(3.2, 3234.0), packages=[], state=state
    )
    (tmp_path / "main.py").write_text(
        "from GlyphsApp import *\n"
        "Glyphs.clearLog()\n"
        "Glyphs.showMacroWindow()\n"
        "print('font', Glyphs.font)\n"
        "def update(sender):\n"
        "    print('update', sender.name())\n"
        "    raise ValueError('cb failed')\n"
        "Glyphs.addCallback(update, UPDATEINTERFACE)\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    state.value = 1
    assert QTimer.made[0].isActive()
    QTimer.made[0].timeout.emit()
    text = "".join(ctx.output.strings)
    assert "font None" in text and "update GSUpdateInterface" in text
    assert "ValueError: cb failed" in text
    assert ("doClearOutput",) not in LOG and ("doShowOutputPanel",) not in LOG
    hooks = [getattr(hook, "__name__", "") for hook in ctx._close_hooks]
    assert hooks == ["close", "_remove_all_callbacks"], "callbacks go first (newest)"
    ctx.close()
    assert LOG[-3:] == [("disconnect", "timeout"), ("stop",), ("deleteLater", "QTimer")]
    assert QTimer.made[0].timeout.slots == []


# Fix round 1: no teardown inside the emitting slot ---------------------------

TEARDOWN = [("disconnect", "timeout"), ("stop",), ("deleteLater", "QTimer")]


def test_emit_when_last_callback_removes_itself_then_disconnect_after_return(native):
    state = State()
    bridge, _ = _bridge(state=state)
    tokens = {}

    def once(sender):
        bridge.remove(tokens["once"])
        assert ("disconnect", "timeout") not in LOG, "no teardown inside the slot"
        LOG.append(("callback-end",))

    tokens["once"] = bridge.subscribe("GSUpdateInterface", once)
    state.value = 1
    QTimer.made[0].timeout.emit()
    assert LOG[-4:] == [("callback-end",), *TEARDOWN]
    assert bridge._timer == {}


def test_emit_when_callback_closes_ctx_then_teardown_after_return(native, tmp_path):
    state = State()
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = fontlab_glyphsapp_provider(
        ctx, version=(3.2, 3234.0), packages=[], state=state
    )
    (tmp_path / "main.py").write_text("from GlyphsApp import Glyphs\n")
    assert ctx.run(tmp_path / "main.py").status == "passed"
    module = ctx._modules[ctx.namespace + ".GlyphsApp"]

    def closer(sender):
        ctx.close()
        assert ("disconnect", "timeout") not in LOG, "no teardown inside the slot"
        LOG.append(("callback-end",))

    module.Glyphs.addCallback(closer, module.UPDATEINTERFACE)
    state.value = 1
    QTimer.made[0].timeout.emit()
    assert LOG[-4:] == [("callback-end",), *TEARDOWN]
    assert QTimer.made[0].timeout.slots == []


def test_emit_when_deferred_teardown_fails_then_logged_not_raised(native):
    state = State()
    bridge, log = _bridge(state=state)
    tokens = {}
    tokens["a"] = bridge.subscribe(
        "GSUpdateInterface", lambda sender: bridge.remove(tokens["a"])
    )
    QTimer.made[0].timeout.fail_disconnect = 1
    state.value = 1
    QTimer.made[0].timeout.emit()
    assert any("timer teardown failed" in line for line in log)
    assert QTimer.made[0].isActive(), "a failed disconnect leaves the timer running"
    bridge.close()
    assert bridge._timer == {}


def test_subscribe_when_first_then_one_time_narrow_trigger_note(native):
    bridge, log = _bridge(state=State())
    bridge.subscribe("GSUpdateInterface", print)
    bridge.subscribe("GSUpdateInterface", repr)
    notes = [line for line in log if "narrower" in line]
    assert len(notes) == 1
    assert notes[0].startswith("[GlyphsApp bridge]")


@pytest.mark.parametrize("method", ["show_macro_window", "clear_log"])
def test_output_panel_when_no_main_window_then_host_unavailable(native, method):
    native.fontlab.MainWindow = lambda: None
    bridge, _ = _bridge(output_panel=True)
    with pytest.raises(HostUnavailable, match="main window"):
        getattr(bridge, method)()


def test_message_when_earlier_box_closed_by_user_then_released(native):
    bridge, _ = _bridge()
    bridge.message("one", "Alert", None)
    first = QMessageBox.made[0]
    first.visible = False
    bridge.message("two", "Alert", None)
    assert first.calls[-1] == ("deleteLater",)
    assert bridge._dialogs._boxes == [QMessageBox.made[1]]


OPENED, CLOSED = "GSDocumentWasOpenedNotification", "GSDocumentWillCloseNotification"


def test_document_events_when_subscribed_then_one_signal_connection_per_event(native):
    seen = []
    bridge, _ = _bridge(document=lambda package: ("doc", package))
    first = bridge.subscribe(OPENED, seen.append)
    bridge.subscribe(OPENED, lambda n: seen.append(("second", n.name())))
    bridge.subscribe(CLOSED, seen.append)
    assert LOG == [("connect", "packageReaded"), ("connect", "signalPackageClosed")]
    native.items.packageReaded.emit("pkg")
    assert seen[0].name() == OPENED and seen[0].object() == ("doc", "pkg")
    assert seen[1] == ("second", OPENED) and len(seen) == 2
    assert QTimer.made == [], "document events need no polling timer"
    bridge.remove(first)
    assert ("disconnect", "packageReaded") not in LOG, "one subscriber is left"


def test_document_events_when_last_removed_then_disconnected_once(native):
    bridge, _ = _bridge()
    token = bridge.subscribe(CLOSED, print)
    bridge.remove(token)
    bridge.remove(token)  # idempotent
    assert LOG == [
        ("connect", "signalPackageClosed"),
        ("disconnect", "signalPackageClosed"),
    ]


def test_document_event_when_callback_removes_itself_then_disconnect_after_dispatch(
    native,
):
    bridge, _ = _bridge()
    tokens = []

    def once(notification):
        assert ("disconnect", "packageReaded") not in LOG, "not inside the slot"
        bridge.remove(tokens[0])
        LOG.append(("callback-end",))

    tokens.append(bridge.subscribe(OPENED, once))
    native.items.packageReaded.emit("pkg")
    assert LOG[-2:] == [("callback-end",), ("disconnect", "packageReaded")]


def test_document_event_when_callback_or_mapper_raises_then_contained(native):
    def boom(package):
        raise RuntimeError("mapper")

    seen = []
    bridge, log = _bridge(document=boom)
    bridge.subscribe(OPENED, lambda n: 1 / 0)
    bridge.subscribe(OPENED, seen.append)
    native.items.packageReaded.emit("pkg")
    assert seen[0].object() is None, "a failing mapper gives no document"
    assert any("ZeroDivisionError" in line for line in log)
    assert any("RuntimeError: mapper" in line for line in log)


def test_close_when_document_events_subscribed_then_all_disconnected(native):
    bridge, _ = _bridge()
    bridge.subscribe(OPENED, print)
    bridge.subscribe(CLOSED, print)
    bridge.close()
    assert ("disconnect", "packageReaded") in LOG
    assert ("disconnect", "signalPackageClosed") in LOG
    native.items.packageReaded.emit("pkg")  # nothing connected, nothing runs


def test_provider_when_document_opened_then_callback_gets_its_gsdocument(
    native, tmp_path
):
    package = SimpleNamespace(
        id=7,
        isValid=True,
        masters=["Regular"],
        upm=1000,
        axes=[],
        fgPackage=SimpleNamespace(info=SimpleNamespace(familyName="Doc")),
    )
    stranger = SimpleNamespace(id=8, isValid=True)
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = fontlab_glyphsapp_provider(
        ctx, version=(3.2, 3234.0), packages=[package], state=State()
    )
    (tmp_path / "main.py").write_text(
        "from GlyphsApp import *\n"
        "def opened(n):\n"
        "    doc = n.object()\n"
        "    print('opened', n.name(), doc and doc.font.familyName)\n"
        "Glyphs.addCallback(opened, DOCUMENTOPENED)\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    native.items.packageReaded.emit(package)
    native.items.packageReaded.emit(stranger)  # outside the model's scope
    text = "".join(ctx.output.strings)
    assert "opened GSDocumentWasOpenedNotification Doc" in text
    assert "opened GSDocumentWasOpenedNotification None" in text
    ctx.close()
    assert ("disconnect", "packageReaded") in LOG


def test_provider_when_no_defaults_given_then_persisted_store_at_ruled_path(
    native, tmp_path, monkeypatch
):
    import json

    target = tmp_path / "glyport" / "defaults.json"
    monkeypatch.setenv("GLYPORT_DEFAULTS", str(target))
    ctx = ExecutionContext(tmp_path, "glyphs3")
    ctx.adapters["GlyphsApp"] = fontlab_glyphsapp_provider(
        ctx, version=(3.2, 3234.0), packages=[], state=State()
    )
    (tmp_path / "main.py").write_text(
        "from GlyphsApp import Glyphs\nGlyphs.defaults['com.example.k'] = 3\n"
    )
    assert ctx.run(tmp_path / "main.py").status == "passed"
    assert json.loads(target.read_text()) == {"com.example.k": 3}
    ctx.close()


def test_nested_document_events_when_outer_callback_closes_then_teardown_after_outer(
    native,
):
    bridge, _ = _bridge()

    def inner(notification):
        LOG.append(("inner",))

    def outer(notification):
        native.items.signalPackageClosed.emit("pkg")  # nested dispatch
        assert ("disconnect", "packageReaded") not in LOG
        bridge.close()
        assert ("disconnect", "packageReaded") not in LOG, "still dispatching"
        LOG.append(("outer-end",))

    bridge.subscribe(OPENED, outer)
    bridge.subscribe(CLOSED, inner)
    native.items.packageReaded.emit("pkg")
    i = LOG.index(("outer-end",))
    assert ("disconnect", "packageReaded") in LOG[i:]
    assert ("disconnect", "signalPackageClosed") in LOG[i:]


def test_document_activated_when_current_package_changes_then_document_notified(native):
    """R049 custom-nsview (Waterfall) subscribes DOCUMENTACTIVATED. FontLab has
    no activation signal for Python: the bridge's poll fires it when the current
    package changes (a glyph change alone does not), with that package's
    document; removing the last subscriber stops the timer."""
    state, seen = State(), []
    state.value = (7, 11)
    bridge, _ = _bridge(state=state, document=lambda package: ("doc", package.id))
    token = bridge.subscribe("GSDocumentActivateNotification", seen.append)
    state.value = (7, 12)
    QTimer.made[0].timeout.emit()
    assert seen == []
    native.workspace.currentPackage = SimpleNamespace(id=8, isValid=True)
    state.value = (8, 12)
    QTimer.made[0].timeout.emit()
    assert [(n.name(), n.object()) for n in seen] == [
        ("GSDocumentActivateNotification", ("doc", 8))
    ]
    LOG.clear()
    bridge.remove(token)
    assert ("stop",) in LOG
