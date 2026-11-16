# this_file: tests/host_doubles.py
"""PythonQt-shaped doubles for FontLabPluginHost: menus, actions, tool windows.

``Signal.emit`` marks the dispatch; disconnecting a slot of a signal that is
dispatching, or deleting a widget while one of its children's signals is
dispatching, is recorded in ``VIOLATIONS`` (the PythonQtSignalReceiver crash
pattern in the workspace AGENTS.md). ``QTimer.fire()`` stands in for the
event loop running a queued timeout.
"""

from types import SimpleNamespace

LOG: list = []
VIOLATIONS: list = []


class Signal:
    def __init__(self, owner, name):
        self.owner, self.name, self.slots, self.dispatching = owner, name, [], False

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        if self.dispatching:
            VIOLATIONS.append(("disconnect during dispatch", self.owner, self.name))
        self.slots.remove(slot)
        LOG.append(("disconnect", self.owner, self.name))

    def emit(self, *args):
        self.dispatching = True
        try:
            for slot in list(self.slots):
                slot(*args)
        finally:
            self.dispatching = False


class Rect:
    def __init__(self, x, y, w, h):
        self._r = (x, y, w, h)

    def width(self):
        return self._r[2]

    def height(self):
        return self._r[3]


class QWidget:
    def __init__(self, *args):
        self.parent = args[0] if args else None
        self.children, self.visible, self.deleted = [], False, False
        self.title, self.flags, self._geometry = "", None, (0, 0, 120, 60)
        if self.parent is not None:
            self.parent.children.append(self)

    @property
    def geometry(self):
        return Rect(*self._geometry)

    def setWindowFlags(self, flags):
        self.flags = flags

    def setWindowTitle(self, title):
        self.title = title

    @property
    def windowTitle(self):
        return self.title

    def setParent(self, parent):
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = parent
        if parent is not None:
            parent.children.append(self)

    def move(self, x, y):
        pass

    def resize(self, w, h):
        self._geometry = self._geometry[:2] + (w, h)

    def setGeometry(self, x, y, w, h):
        self._geometry = (x, y, w, h)

    def setMinimumHeight(self, h):
        self.min_height = h

    def setMaximumHeight(self, h):
        self.max_height = h

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def isVisible(self):
        return self.visible

    def close(self):
        self.closeEvent(SimpleNamespace(accept=lambda: None))
        self.visible = False
        return True

    def closeEvent(self, event):
        pass

    def _tree(self):
        yield self
        for child in self.children:
            yield from child._tree()

    def deleteLater(self):
        for widget in self._tree():
            for value in vars(widget).values():
                if isinstance(value, Signal) and value.dispatching:
                    VIOLATIONS.append(("delete during dispatch", widget, value.name))
        LOG.append(("deleteLater", self))
        for widget in self._tree():
            widget.deleted = True


class QPushButton(QWidget):
    def __init__(self, *args):
        super().__init__(*args)
        self.text, self.clicked = "", Signal(self, "clicked")

    def setText(self, text):
        self.text = text

    def click(self):
        self.clicked.emit(False)


class QAction:
    def __init__(self, text, parent=None):
        self.text, self.enabled, self.checkable, self.checked = text, True, False, False
        self.triggered, self.deleted, self._menu = (
            Signal(self, "triggered"),
            False,
            None,
        )

    def setText(self, text):
        self.text = text

    def setEnabled(self, flag):
        self.enabled = flag

    def setCheckable(self, flag):
        self.checkable = flag

    def isCheckable(self):
        return self.checkable

    def setChecked(self, flag):
        self.checked = flag

    def setIcon(self, icon):
        self.icon = icon

    def menu(self):
        return self._menu

    def trigger(self):
        self.triggered.emit(False)

    def deleteLater(self):
        self.deleted = True


class QMenu:
    def __init__(self, title=""):
        self.title, self._actions, self.deleted = title, [], False

    def actions(self):
        return list(self._actions)

    def addAction(self, action):
        self._actions.append(action)

    def insertAction(self, before, action):
        self._actions.insert(self._actions.index(before), action)

    def removeAction(self, action):
        self._actions.remove(action)

    def deleteLater(self):
        self.deleted = True


class QMenuBar:
    def __init__(self, titles):
        self._actions = []
        for title in titles:
            action = QAction(title)
            action._menu = QMenu(title)
            self._actions.append(action)

    def actions(self):
        return list(self._actions)

    def addMenu(self, menu):
        action = QAction(menu.title)
        action._menu = menu
        self._actions.append(action)
        return action

    def removeAction(self, action):
        self._actions.remove(action)


class QTimer:
    def __init__(self):
        self.timeout, self.active, self.deleted = Signal(self, "timeout"), False, False

    def setSingleShot(self, flag):
        self.single = flag

    def setInterval(self, ms):
        self.interval = ms

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def deleteLater(self):
        self.deleted = True

    def fire(self):
        """The event loop runs the queued timeout."""
        if self.active:
            self.active = False
            self.timeout.emit()


class MainWindow:
    def __init__(self):
        self.bar = QMenuBar(["&File", "&Edit", "&View", "&Window", "Script"])
        self.messages = []

    def menuBar(self):
        return self.bar

    def statusBar(self):
        return SimpleNamespace(showMessage=lambda m, t: self.messages.append(m))


def make_host_qt():
    LOG.clear()
    VIOLATIONS.clear()
    gui = SimpleNamespace(
        QWidget=QWidget, QPushButton=QPushButton, QAction=QAction, QMenu=QMenu
    )
    core = SimpleNamespace(
        QTimer=QTimer, Qt=SimpleNamespace(Tool=11, WindowStaysOnTopHint=0x40000)
    )
    return SimpleNamespace(QtGui=gui, QtCore=core)
