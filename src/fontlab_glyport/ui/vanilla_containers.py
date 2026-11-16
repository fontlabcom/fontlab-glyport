# this_file: src/fontlab_glyport/ui/vanilla_containers.py
"""vanilla Tabs and Sheet on Qt (same rules as ``vanilla.py``).

``Tabs`` is a QTabWidget; each ``tabs[i]`` is a Group-like ``Tab`` whose page
widget the tab widget sizes, so its children re-lay out from the page's own
resize events. NSTabView's delegate reports programmatic selection too, so
``set()`` fires the callback. ``Sheet`` is a window-modal ``Qt.Sheet`` child
window of its parent vanilla Window; the parent tears down every sheet made
on it (opened or not) before its own teardown, so no deleted widget keeps
Python slots.
"""

from typing import Any

from fontlabapp.qt.events.resize import resize_event_handler

from .vanilla import Group, Window, _Control, _properties


def _page_class(base: type) -> type:
    """QWidget page subclass reporting resizes to its Tab (PythonQt-safe)."""

    class Page(base):
        _owner = None

        resizeEvent = resize_event_handler(base, lambda widget: widget._owner, "_resized")

    return Page


class Tab(Group):
    """One tab page; Qt sizes it, so ``_place`` from a parent does nothing."""

    def __init__(self, env: Any, title: str):
        object.__setattr__(self, "_env", env)
        _Control.__init__(self, (0, 0, 0, 0), {"title": title})
        self._children = {}
        self._view._owner = self

    def _make_view(self) -> Any:
        classes = self._env.widget_classes
        if "vanilla.Tab.page" not in classes:
            classes["vanilla.Tab.page"] = _page_class(self._env.qt.QtGui.QWidget)
        return classes["vanilla.Tab.page"]()

    def _place(self, width, height):
        """The tab widget owns the page geometry."""

    def _resized(self, width: int, height: int) -> None:
        self._size = (width, height)
        self._relayout()

    def _disconnect(self):
        Group._disconnect(self)
        self._view._owner = None


class Tabs(_Control):
    """QTabWidget; ``tabs[i]`` holds that page's controls."""

    _qt_class = "QTabWidget"

    def __init__(
        self,
        posSize,
        titles=("Tab",),
        callback=None,
        showTabs=True,
        transparent=False,
        **options,
    ):
        titles = [str(title) for title in titles]
        known = {"titles": titles, "showTabs": bool(showTabs)}
        known["transparent"] = bool(transparent)  # recorded only
        super().__init__(posSize, _properties("Tabs", options, **known))
        self._tabs = [Tab(self._env, title) for title in titles]
        for tab in self._tabs:
            tab._parent = self
            self._view.addTab(tab._view, tab._properties["title"])
        if not showTabs:
            self._view.tabBar().hide()
        self._wire("currentChanged", callback)

    def __getitem__(self, index: int) -> Tab:
        return self._tabs[index]

    def __len__(self) -> int:
        return len(self._tabs)

    def get(self) -> int:
        return self._view.currentIndex

    def set(self, index) -> None:
        index = int(index)
        if not 0 <= index < len(self._tabs):
            raise IndexError(f"Tabs index {index} out of range")
        self._view.setCurrentIndex(index)

    def _register(self, graph, parent_id, name, root_id):
        _Control._register(self, graph, parent_id, name, root_id)
        for index, tab in enumerate(self._tabs):
            tab._register(graph, self._node.node_id, str(index), root_id)

    def _disconnect(self):
        _Control._disconnect(self)
        for tab in self._tabs:
            tab._disconnect()

    def _mark_detached(self):
        _Control._mark_detached(self)
        for tab in self._tabs:
            tab._mark_detached()


class Sheet(Window):
    """Window-modal sheet attached to a vanilla Window."""

    def __init__(self, posSize, parentWindow, **options):
        if not isinstance(parentWindow, Window):
            raise TypeError(f"Sheet needs a vanilla parent Window: {parentWindow!r}")
        if parentWindow._closed:
            raise ValueError("Sheet: the parent window is closed")
        self._parent_window = parentWindow
        super().__init__(posSize, **options)
        qt = self._env.qt.QtCore.Qt
        self._view.setParent(parentWindow.getNSWindow())
        # A native child from now on: the parent must tear it down first even
        # if it is never opened (its controls hold Python slots).
        parentWindow._sheets.add(self)
        self._view.setWindowFlags(qt.Sheet)  # after setParent, which resets flags
        self._view.setWindowModality(qt.WindowModal)

    def _teardown(self, *, view_closing: bool) -> None:
        self._parent_window._sheets.discard(self)
        Window._teardown(self, view_closing=view_closing)


CONTAINER_CLASSES = (Tabs, Sheet)
