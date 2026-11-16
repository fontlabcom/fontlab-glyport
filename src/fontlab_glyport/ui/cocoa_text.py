# this_file: src/fontlab_glyport/ui/cocoa_text.py
"""Qt-backed ``NSTextView`` (R031): plain text in a QPlainTextEdit.

Only user edits reach the delegate's ``textDidChange_`` (QPlainTextEdit also
reports programmatic changes; those are kept quiet, as in AppKit). Rich text,
fonts and attributes are not modelled; ``textStorage()`` offers the string.
"""

from fontlabapp.core.signals.callbacks import quiet_callbacks

from .cocoa import NSObject
from .cocoa_views import NSView


class _Notification:
    def __init__(self, name: str, obj):
        self._name, self._object = name, obj

    def name(self) -> str:
        return self._name

    def object(self):
        return self._object


class _MutableString:
    def __init__(self, view):
        self._view = view

    def setString_(self, text) -> None:
        self._view.setString_(text)

    def appendString_(self, text) -> None:
        self._view.setString_(self._view.string() + str(text))


class _TextStorage(NSObject):
    """``textView.textStorage()``: the text as a string (no attributes)."""

    def initWithView_(self, view):
        self._view = view
        return self

    def string(self) -> str:
        return self._view.string()

    def length(self) -> int:
        return len(self._view.string())

    def mutableString(self):
        return _MutableString(self._view)


class NSTextView(NSView):
    """QPlainTextEdit with ``string``/``setString_``, editability and a delegate."""

    _qt_class = "QPlainTextEdit"
    _container = False

    def initWithFrame_(self, frame):
        self._delegate, self._selectable, self._quiet = None, True, False
        NSView.initWithFrame_(self, frame)
        self._interaction()
        self._track(self._qt.textChanged, self._changed)
        return self

    def _changed(self, *args) -> None:
        notify = getattr(self._delegate, "textDidChange_", None)
        if notify is not None and not self._quiet:
            note = _Notification("NSTextDidChangeNotification", self)
            self._env.dispatch.call(lambda: notify(note), self)

    def _quietly(self, action) -> None:
        with quiet_callbacks(self):
            action()

    def string(self) -> str:
        return str(self._qt.toPlainText())

    def setString_(self, text) -> None:
        self._quietly(lambda: self._qt.setPlainText(str(text or "")))

    def insertText_(self, text) -> None:
        self._quietly(lambda: self._qt.insertPlainText(str(text)))

    def textStorage(self):
        return _TextStorage.alloc().initWithView_(self)

    def isEditable(self) -> bool:
        return not self._qt.isReadOnly()

    def setEditable_(self, flag) -> None:
        """Editable implies selectable, as in AppKit."""
        self._qt.setReadOnly(not flag)
        if flag:
            self._selectable = True
        self._interaction()

    def isSelectable(self) -> bool:
        return self._selectable

    def setSelectable_(self, flag) -> None:
        """Not selectable means not editable either, as in AppKit."""
        self._selectable = bool(flag)
        if not flag:
            self._qt.setReadOnly(True)
        self._interaction()

    def _interaction(self) -> None:
        """Qt's text interaction flags carry editability and selectability."""
        qt = self._env.qt.QtCore.Qt
        if self.isEditable():
            flags = qt.TextEditorInteraction
        elif self._selectable:
            flags = qt.TextSelectableByMouse | qt.TextSelectableByKeyboard
        else:
            flags = qt.NoTextInteraction
        self._qt.setTextInteractionFlags(flags)

    def delegate(self):
        return self._delegate

    def setDelegate_(self, delegate) -> None:
        self._delegate = delegate

    def scrollRangeToVisible_(self, text_range) -> None:
        """Accepted; Qt keeps the cursor visible."""

    def _release(self) -> None:
        self._delegate = None


TEXT_CLASSES = (NSTextView,)
