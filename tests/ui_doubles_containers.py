# this_file: tests/ui_doubles_containers.py
"""PythonQt-shaped QTabWidget double for vanilla Tabs (see ui_doubles.py).

Pages are resized by the tab widget, not by the script: a geometry change of
the tab widget gives every page ``(0, 0, w - 2*INSET, h - BAR - INSET)`` and
sends it a resize event, as Qt's internal QStackedWidget layout does.
Only the current page is visible. ``currentIndex``/``count`` are properties,
and ``currentChanged`` fires for programmatic changes too.
"""

from ui_doubles import LOG, QWidget, Signal


class QTabBar:
    __slots__ = ("_visible",)

    def __init__(self):
        self._visible = True

    def setVisible(self, visible):
        self._visible = bool(visible)

    def hide(self):
        self.setVisible(False)

    def isVisible(self):
        return self._visible


class QTabWidget(QWidget):
    __slots__ = ("_bar", "_current", "_labels", "_pages", "currentChanged")
    INSET, BAR = 4, 26

    def __init__(self):
        super().__init__()
        self._pages, self._labels, self._current = [], [], -1
        self._bar = QTabBar()
        self.currentChanged = Signal(self, "currentChanged")

    def addTab(self, page, label):
        if not isinstance(page, QWidget) or not isinstance(label, str):
            raise TypeError("doubles model only addTab(QWidget, str)")
        page.setParent(self)
        self._pages.append(page)
        self._labels.append(label)
        self._fit(page)
        page.setVisible(False)
        if self._current < 0:
            self._current = 0
            page.setVisible(True)
            self.currentChanged.emit(0)
        return len(self._pages) - 1

    @property
    def currentIndex(self):
        return self._current

    @property
    def count(self):
        return len(self._pages)

    def setCurrentIndex(self, index):
        if 0 <= index < len(self._pages) and index != self._current:
            self._pages[self._current].setVisible(False)
            self._pages[index].setVisible(True)
            self._current = index
            self.currentChanged.emit(index)

    def user_select(self, index):
        self.setCurrentIndex(index)

    def tabText(self, index):
        return self._labels[index]

    def setTabText(self, index, label):
        self._labels[index] = label

    def widget(self, index):
        return self._pages[index]

    def tabBar(self):
        return self._bar

    def _fit(self, page):
        w, h = self._rect[2:]
        page.setGeometry(0, 0, w - 2 * self.INSET, h - self.BAR - self.INSET)

    def setGeometry(self, x, y, w, h):
        super().setGeometry(x, y, w, h)
        for page in self._pages:
            self._fit(page)
        LOG.append(("tabs.fit", self))


CONTAINER_DOUBLES = {"QTabWidget": QTabWidget}
CONTAINER_ENUMS = {"Sheet": "Sheet", "WindowModal": "WindowModal"}
