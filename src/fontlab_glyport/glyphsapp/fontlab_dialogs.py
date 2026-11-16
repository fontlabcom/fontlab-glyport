# this_file: src/fontlab_glyport/glyphsapp/fontlab_dialogs.py
"""GlyphsApp dialogs on FontLab's PythonQt ``QtGui`` (no ``QApplication``).

``Message`` is a non-modal ``QMessageBox`` the bridge retains until ``close()``.
The other dialogs need a result, so they answer from injected ``answers``
first; without one they run a modal ``exec()`` on an owned dialog only when
``interactive=True``, and otherwise raise ``UnsupportedCapability``. Cancel
returns ``None``. No Python slot is connected to any dialog.
"""

from collections.abc import Callable, Mapping

import fontlabapp.qt.dialogs as _qt_dialogs
from fontlabapp.qt.dialogs import name_filters

from .._strict import caller_location
from ..errors import UnsupportedCapability

_MISSING = object()
_SCRIPT_NAMES = {
    "message": "Message",
    "ask_string": "AskString",
    "get_folder": "GetFolder",
    "get_open_file": "GetOpenFile",
    "get_save_file": "GetSaveFile",
}


class Dialogs:
    """Owned Qt dialogs; ``qtgui`` is a zero-argument loader of ``PythonQt.QtGui``."""

    def __init__(
        self, qtgui: Callable, interactive: bool, answers: Mapping[str, object]
    ) -> None:
        self._qtgui, self._interactive, self._answers = qtgui, interactive, answers
        self._boxes: list = []  # non-modal message boxes, closed by close()

    def _answer(self, name: str) -> object:
        answer = self._answers.get(name, _MISSING)
        if answer is _MISSING and not self._interactive:
            capability = f"GlyphsApp.{_SCRIPT_NAMES[name]}"
            raise UnsupportedCapability(
                f"Unsupported capability: {capability} needs a modal dialog",
                capability=capability,
                location=caller_location(),
                recovery_action=f"pass interactive=True or answers={{'{name}': ...}}",
            )
        return answer

    def message(self, message, title, ok_button) -> object:
        if "message" in self._answers:
            return self._answers["message"]
        qtgui = self._qtgui()
        self._release_closed()
        box = qtgui.QMessageBox()

        def configure(current):
            current.setWindowTitle(title or "")
            current.setText(str(message))
            if ok_button:
                current.addButton(ok_button, qtgui.QMessageBox.AcceptRole)

        _qt_dialogs.show_message_box(box, self._boxes, configure)
        return None

    def _release_closed(self) -> None:
        """Delete owned hidden boxes through shared Qt lifetime mechanics."""
        _qt_dialogs.release_closed_message_boxes(self._boxes)

    def ask_string(self, message, value, title, ok_button, placeholder):
        """``placeholder`` is ignored: the QInputDialog stub has no such API."""
        answer = self._answer("ask_string")
        if answer is not _MISSING:
            return answer

        # Deliberately not App ``qt_dialogs.run_text_dialog``: that helper wraps
        # every value in ``str()``. Glyphs AskString passes the script's raw
        # values to Qt, and test_glyphs_dialog_execution pins that behaviour.
        def configure(dialog):
            dialog.setWindowTitle(title or "")
            dialog.setLabelText(message or "")
            dialog.setTextValue(value or "")
            if ok_button:
                dialog.setOkButtonText(ok_button)

        return _qt_dialogs.run_owned_dialog(
            self._qtgui().QInputDialog(),
            configure,
            lambda dialog, accepted: dialog.textValue() if accepted else None,
        )

    def _files(self, configure: Callable, caption, directory) -> list[str] | None:
        qtgui = self._qtgui()

        def setup(dialog):
            dialog.setWindowTitle(caption or "")
            if directory:
                dialog.setDirectory(directory)
            configure(qtgui.QFileDialog, dialog)

        return _qt_dialogs.run_owned_dialog(
            qtgui.QFileDialog(),
            setup,
            lambda dialog, accepted: list(dialog.selectedFiles()) if accepted else None,
        )

    @staticmethod
    def _pick(files: list[str] | None, multiple: bool):
        if files is None or multiple:
            return files
        return files[0] if files else None

    def get_folder(self, message, allows_multiple, path):
        answer = self._answer("get_folder")
        if answer is not _MISSING:
            return answer

        def configure(kind, dialog):
            dialog.setFileMode(kind.Directory)
            dialog.setOption(kind.ShowDirsOnly, True)

        return self._pick(self._files(configure, message, path), allows_multiple)

    def get_open_file(self, message, title, allows_multiple, filetypes, path):
        answer = self._answer("get_open_file")
        if answer is not _MISSING:
            return answer

        def configure(kind, dialog):
            mode = kind.ExistingFiles if allows_multiple else kind.ExistingFile
            dialog.setFileMode(mode)
            if filetypes:
                dialog.setNameFilters(name_filters(filetypes))

        files = self._files(configure, title or message, path)
        return self._pick(files, allows_multiple)

    def get_save_file(self, message, proposed_file_name, filetypes):
        answer = self._answer("get_save_file")
        if answer is not _MISSING:
            return answer

        def configure(kind, dialog):
            dialog.setAcceptMode(kind.AcceptSave)
            if filetypes:
                dialog.setNameFilters(name_filters(filetypes))
            if proposed_file_name:
                dialog.selectFile(proposed_file_name)

        return self._pick(self._files(configure, message, None), False)

    def close(self) -> None:
        """Close and delete every retained message box; re-raise the first failure."""
        _qt_dialogs.close_message_boxes(self._boxes)
