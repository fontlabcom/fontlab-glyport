# this_file: src/fontlab_glyport/ui/vanilla_auxiliary.py
"""Anchored tool-window popovers, with explicit scope-owned disposal."""

from .application_windows import qt_value
from .cocoa import unsupported
from .vanilla import FloatingWindow, Window, _Control


class Popover(FloatingWindow):
    """Qt tool-window fallback. Native Cocoa arrow/animation are cosmetic."""

    def __init__(
        self, posSize, behavior="applicationDefined", animates=True, **options
    ):
        if behavior not in ("applicationDefined", "transient", "semitransient"):
            raise ValueError("Unknown popover behavior")
        self._anchor_owner = None
        super().__init__(posSize, **options)
        self._env.open_windows.add(self)  # hidden popovers still own callback widgets

    def open(self, parentView=None, preferredEdge="right", relativeRect=None):
        if self._closed:
            return
        if parentView is not None:
            from .cocoa_views import NSView
            from .vanilla import _Control

            owner = parentView if isinstance(parentView, _Control) else None
            widget = (
                parentView._view
                if owner is not None
                else parentView._qt
                if isinstance(parentView, NSView)
                else parentView
            )
            rect = qt_value(widget, "rect") if relativeRect is None else None
            if relativeRect is None:
                x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            else:
                (x, y), (w, h) = relativeRect
            width, height = self._size
            edge = preferredEdge or "right"
            offsets = {
                "right": (x + w, y),
                "left": (x - width, y),
                "top": (x, y - height),
                "bottom": (x, y + h),
            }
            if edge not in offsets:
                raise ValueError("Unknown popover edge")
            point = widget.mapToGlobal(
                self._env.qt.QtCore.QPoint(*map(round, offsets[edge]))
            )
            self._view.move(point.x(), point.y())
            while owner is not None and not isinstance(owner, Window):
                owner = owner._parent
            if owner is None:
                # getNSView() returns a raw widget; follow Qt parents only to
                # windows this environment already owns.
                roots = {window._view: window for window in self._env.open_windows}
                ancestor = widget
                while ancestor is not None and ancestor not in roots:
                    ancestor = qt_value(ancestor, "parentWidget")
                owner = roots.get(ancestor)
            if self._anchor_owner is not None:
                self._anchor_owner._sheets.discard(self)
            self._anchor_owner = owner
            if owner is not None:
                owner._sheets.add(self)
        Window.open(self)

    def close(self):
        if not self._closed:
            self._view.hide()

    def _teardown(self, *, view_closing):
        if self._anchor_owner is not None:
            self._anchor_owner._sheets.discard(self)
        Window._teardown(self, view_closing=view_closing)


class ScrollView(_Control):
    """Vanilla scroll container over the existing Cocoa/Qt scroll view."""

    def __init__(
        self,
        posSize,
        documentView=None,
        hasHorizontalScroller=False,
        hasVerticalScroller=True,
        autohidesScrollers=True,
        **options,
    ):
        if options:
            raise unsupported("vanilla.ScrollView." + next(iter(options)))
        super().__init__(posSize, {})
        scroll = self.getNSScrollView()
        scroll.setHasHorizontalScroller_(hasHorizontalScroller)
        scroll.setHasVerticalScroller_(hasVerticalScroller)
        scroll.setAutohidesScrollers_(autohidesScrollers)
        if documentView is not None:
            scroll.setDocumentView_(
                documentView.getNSView()
                if hasattr(documentView, "getNSView")
                else documentView
            )

    def _make_view(self):
        from .cocoa import NSMakeRect

        self._ns = (
            self._env.appkit["NSScrollView"]
            .alloc()
            .initWithFrame_(NSMakeRect(0, 0, 0, 0))
        )
        self._ns._vanilla_control_for_widget = self._env.control_handles.get
        return self._ns._qt

    def _disconnect(self):
        from .cocoa_views import release_tree

        super()._disconnect()
        release_tree(self._ns)

    def getNSScrollView(self):
        return self._ns


class Drawer:
    def __init__(self, *args, **kwargs):
        raise unsupported("vanilla.Drawer")
