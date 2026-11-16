# this_file: tests/ui_doubles_dialogs.py
"""PythonQt-shaped QMessageBox/QFileDialog doubles for ``vanilla.dialogs``.

``exec()`` is the modal path: it is logged and returns the scripted result, so
tests can prove the non-interactive path never reaches it. Constructors are
positional only, and enum values are plain ints as in PythonQt.
"""

from ui_doubles import LOG, QWidget


class QMessageBox(QWidget):
    __slots__ = ("_buttons", "_icon", "_informative", "_modal", "_text")
    Information, Warning, Critical = 1, 2, 3
    Ok, Yes, No, Cancel = 0x400, 0x4000, 0x10000, 0x400000
    # Test hook: the standard button the "user" picks in exec().
    exec_result = Ok

    def __init__(self, *args):
        if args and not isinstance(args[0], QWidget):
            raise TypeError("doubles model only QMessageBox(parent)")
        super().__init__()
        if args:
            self.setParent(args[0])
        self._text = self._informative = ""
        self._icon = self._buttons = self._modal = None

    def setText(self, text):
        self._text = text

    def setInformativeText(self, text):
        self._informative = text

    def setIcon(self, icon):
        self._icon = icon

    def setStandardButtons(self, buttons):
        self._buttons = buttons

    def setModal(self, modal):
        self._modal = bool(modal)

    def exec(self):
        LOG.append(("exec", self))
        return type(self).exec_result


class QFileDialog(QWidget):
    __slots__ = ("_accept", "_directory", "_filters", "_mode", "_options", "_select")
    AnyFile, ExistingFile, Directory, ExistingFiles = 0, 1, 2, 3
    AcceptOpen, AcceptSave = 0, 1
    ShowDirsOnly, ReadOnly = 0x1, 0x20
    # Test hooks: exec() accepts when ``exec_files`` is not None.
    exec_files = None

    def __init__(self, *args):
        if args and not isinstance(args[0], QWidget):
            raise TypeError("doubles model only QFileDialog(parent)")
        super().__init__()
        if args:
            self.setParent(args[0])
        self._mode = self._accept = self._directory = self._select = None
        self._filters, self._options = [], {}

    def setFileMode(self, mode):
        self._mode = mode

    def setAcceptMode(self, mode):
        self._accept = mode

    def setOption(self, option, on=True):
        self._options[option] = bool(on)

    def setNameFilters(self, filters):
        self._filters = list(filters)

    def setDirectory(self, directory):
        self._directory = directory

    def selectFile(self, name):
        self._select = name

    def exec(self):
        LOG.append(("exec", self))
        return int(type(self).exec_files is not None)

    def selectedFiles(self):
        return tuple(type(self).exec_files or ())


DIALOG_DOUBLES = {"QMessageBox": QMessageBox, "QFileDialog": QFileDialog}
