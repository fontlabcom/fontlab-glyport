# this_file: src/fontlab_glyport/ui/dialogs.py
"""``vanilla.dialogs`` on owned Qt dialogs (adapter name ``vanilla.dialogs``).

``message`` shows a non-modal ``QMessageBox`` and returns ``None`` at once
(vanilla blocks); boxes stay retained until ``close()``. Dialogs that return a
result answer from injected ``answers`` (keyed by function name; a ``None``
answer means cancel) first. Without an answer they run a modal ``exec()`` on an
owned dialog only when ``interactive=True``, and otherwise raise
``UnsupportedCapability`` at the script line. ``resultCallback`` receives the
result once (errors go to the sink) and the function also returns it.
"""

from collections.abc import Callable, Mapping
from types import ModuleType
from typing import Any

import fontlabapp.qt.dialogs as _qt_dialogs
from fontlabapp.qt.dialogs import name_filters

from .._strict import caller_location
from ..errors import UnsupportedCapability
from .vanilla import ErrorSink, OnClose, Wrap

_MISSING = object()
# vanilla style names and NSAlertStyle values (warning 0, informational 1, critical 2).
_ALERT_ICONS = {
    "informational": "Information",
    "warning": "Warning",
    "critical": "Critical",
    0: "Warning",
    1: "Information",
    2: "Critical",
}
_EXPORTS = ("message", "askYesNoCancel", "askYesNo", "getFile", "getFolder", "putFile")


def _unsupported(capability: str, detail: str = "") -> UnsupportedCapability:
    return UnsupportedCapability(
        f"Unsupported capability: {capability}{detail}",
        capability=capability,
        location=caller_location(),
    )


class _Dialogs:
    """Module state: injected Qt, answers, modal gate, retained message boxes."""

    def __init__(self, qt, sink, wrap, answers, interactive) -> None:
        self.gui, self.sink, self.wrap = qt.QtGui, sink, wrap
        self.answers, self.interactive = answers, interactive
        self.boxes: list = []

    def finish(self, result: Any, callback: Callable | None) -> Any:
        if callback is not None:
            try:
                (self.wrap(callback) if self.wrap else callback)(result)
            except Exception as exc:  # noqa: BLE001 - the sink is the error route
                self.sink(exc, result)
        return result

    def answer(self, name: str) -> Any:
        answer = self.answers.get(name, _MISSING)
        if answer is _MISSING and not self.interactive:
            error = _unsupported(f"vanilla.dialogs.{name}", " needs a modal dialog")
            error.recovery_action = (
                f"pass interactive=True or answers={{'{name}': ...}}"
            )
            raise error
        return answer

    def box(self, text, informative, style, parent) -> Any:
        icon = _alert_icon(style)
        return _qt_dialogs.create_message_box(
            self.gui, text, informative, icon, _parent(parent)
        )

    def run_box(self, box, buttons) -> int:
        return _qt_dialogs.run_message_box(box, buttons)

    def run_files(self, configure: Callable, caption, directory, parent):
        return _qt_dialogs.run_file_dialog(
            self.gui, configure, caption, directory, _parent(parent)
        )

    def close(self) -> None:
        """Close and delete retained message boxes; re-raise the first failure."""
        _qt_dialogs.close_message_boxes(self.boxes)


def _parent(window) -> tuple:
    """``()`` or the vanilla window's top-level widget; anything else is a TypeError."""
    if window is None:
        return ()
    handle = getattr(window, "getNSWindow", None)
    if handle is None:
        raise TypeError(f"parentWindow must be a vanilla Window, got {window!r}")
    return (handle(),)


def _alert_icon(style) -> str:
    """Qt icon name for a vanilla/NSAlertStyle value; anything else is unsupported."""
    icon = None if isinstance(style, bool) else _ALERT_ICONS.get(style)
    if icon is None:
        raise _unsupported(f"vanilla.dialogs.alertStyle.{style}")
    return icon


def _module_getattr(name: str) -> Any:
    """Dunders stay AttributeError; other names are unsupported at the script line."""
    if name.startswith("__"):
        raise AttributeError(name)
    raise _unsupported(f"vanilla.dialogs.{name}")


def _reject_icon(icon) -> None:
    if icon is not None:
        raise _unsupported("vanilla.dialogs.icon")


def _functions(state: _Dialogs) -> dict[str, Callable]:
    gui = state.gui

    def message(
        messageText="",
        informativeText="",
        alertStyle="informational",
        parentWindow=None,
        resultCallback=None,
        icon=None,
    ):
        _reject_icon(icon)
        _alert_icon(alertStyle)
        _parent(parentWindow)
        if "message" in state.answers:
            return state.finish(None, resultCallback)
        box = state.box(messageText, informativeText, alertStyle, parentWindow)
        if state.interactive:
            state.run_box(box, gui.QMessageBox.Ok)
        else:
            _qt_dialogs.show_message_box(box, state.boxes)
        return state.finish(None, resultCallback)

    def _ask(name, buttons, values, text, informative, style, parent, callback, icon):
        _reject_icon(icon)
        answer = state.answer(name)
        if answer is _MISSING:
            box = state.box(text, informative, style, parent)
            answer = values.get(state.run_box(box, buttons), values[None])
        return state.finish(answer, callback)

    def askYesNoCancel(
        messageText="",
        informativeText="",
        alertStyle="informational",
        parentWindow=None,
        resultCallback=None,
        icon=None,
    ):
        box = gui.QMessageBox
        values = {box.Yes: 1, box.No: 0, None: -1}
        buttons = box.Yes | box.No | box.Cancel
        args = (messageText, informativeText, alertStyle, parentWindow)
        return _ask("askYesNoCancel", buttons, values, *args, resultCallback, icon)

    def askYesNo(
        messageText="",
        informativeText="",
        alertStyle="informational",
        parentWindow=None,
        resultCallback=None,
        icon=None,
    ):
        box = gui.QMessageBox
        values = {box.Yes: 1, None: 0}
        args = (messageText, informativeText, alertStyle, parentWindow)
        return _ask("askYesNo", box.Yes | box.No, values, *args, resultCallback, icon)

    def getFile(
        messageText=None,
        title=None,
        directory=None,
        fileName=None,
        allowsMultipleSelection=False,
        fileTypes=None,
        parentWindow=None,
        resultCallback=None,
    ):
        _parent(parentWindow)
        answer = state.answer("getFile")
        if answer is _MISSING:

            def configure(kind, dialog):
                multiple = allowsMultipleSelection
                dialog.setFileMode(
                    kind.ExistingFiles if multiple else kind.ExistingFile
                )
                if fileTypes:
                    dialog.setNameFilters(name_filters(fileTypes))
                if fileName:
                    dialog.selectFile(str(fileName))

            caption = title or messageText
            answer = state.run_files(configure, caption, directory, parentWindow)
        return state.finish(answer, resultCallback)

    def getFolder(
        messageText=None,
        title=None,
        directory=None,
        allowsMultipleSelection=False,
        parentWindow=None,
        resultCallback=None,
    ):
        _parent(parentWindow)
        answer = state.answer("getFolder")
        if answer is _MISSING:

            def configure(kind, dialog):
                dialog.setFileMode(kind.Directory)
                dialog.setOption(kind.ShowDirsOnly, True)

            caption = title or messageText
            answer = state.run_files(configure, caption, directory, parentWindow)
        return state.finish(answer, resultCallback)

    def putFile(
        messageText=None,
        title=None,
        directory=None,
        fileName=None,
        canCreateDirectories=True,
        fileTypes=None,
        parentWindow=None,
        resultCallback=None,
        accessoryView=None,
    ):
        if accessoryView is not None:
            raise _unsupported("vanilla.dialogs.putFile.accessoryView")
        _parent(parentWindow)
        answer = state.answer("putFile")
        if answer is _MISSING:

            def configure(kind, dialog):
                dialog.setAcceptMode(kind.AcceptSave)
                if not canCreateDirectories:
                    dialog.setOption(kind.ReadOnly, True)
                if fileTypes:
                    dialog.setNameFilters(name_filters(fileTypes))
                if fileName:
                    dialog.selectFile(str(fileName))

            caption = title or messageText
            files = state.run_files(configure, caption, directory, parentWindow)
            answer = files[0] if files else None
        return state.finish(answer, resultCallback)

    return {
        "message": message,
        "askYesNoCancel": askYesNoCancel,
        "askYesNo": askYesNo,
        "getFile": getFile,
        "getFolder": getFolder,
        "putFile": putFile,
    }


def make_dialogs_module(
    qt: Any,
    *,
    error_sink: ErrorSink,
    answers: Mapping[str, Any] | None = None,
    interactive: bool = False,
    wrap: Wrap | None = None,
    on_close: OnClose | None = None,
) -> ModuleType:
    """Return a fresh ``vanilla.dialogs`` module bound to ``qt``.

    ``module.close()`` closes retained message boxes; ``on_close`` (e.g.
    ``ExecutionContext.on_close``) registers it as a close hook.
    """
    state = _Dialogs(qt, error_sink, wrap, dict(answers or {}), bool(interactive))
    if on_close is not None:
        on_close(state.close)
    module = ModuleType("vanilla.dialogs", "glyport vanilla.dialogs on Qt")
    for name, function in _functions(state).items():
        function.__module__ = "vanilla.dialogs"
        setattr(module, name, function)
    module.close = state.close
    module.__all__ = list(_EXPORTS)
    module.__getattr__ = _module_getattr
    return module


def dialogs_provider(
    qt: Any,
    error_sink: ErrorSink,
    *,
    answers: Mapping[str, Any] | None = None,
    interactive: bool = False,
    wrap: Wrap | None = None,
    on_close: OnClose | None = None,
) -> Callable[[], ModuleType]:
    """Zero-argument provider for ``ctx.adapters["vanilla.dialogs"]``."""

    def provide() -> ModuleType:
        return make_dialogs_module(
            qt,
            error_sink=error_sink,
            answers=answers,
            interactive=interactive,
            wrap=wrap,
            on_close=on_close,
        )

    return provide
