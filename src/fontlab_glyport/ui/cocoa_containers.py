# this_file: src/fontlab_glyport/ui/cocoa_containers.py
"""Container views a NIB can hold (R031): ``NSStackView``, ``NSScrollView``,
``NSBox``, ``NSSplitView``, ``NSGridView``, ``NSVisualEffectView``.

A stack view is a frame-based container, like every NIB view here (Auto Layout
constraints are not solved). Views loaded from a NIB keep Interface Builder's
frames. When the arranged views change (added, inserted, removed, hidden with
``detachesHiddenViews``) or the orientation, spacing, alignment or insets are
set, the stack places its arranged views again: along the axis from the
leading edge (top-down when vertical, Cocoa's y decreasing), ``spacing``
apart, inside ``edgeInsets``, each at its current size, and aligned on the
other axis (leading/top, trailing/bottom, else centred). Distributions:
gravity areas and fill keep sizes (fill's stretched view depends on hugging
priorities, which are not decoded);
fill equally/proportionally resize along the axis; equal spacing/centering
spread the views. The stack view does not resize itself.
"""

from typing import NamedTuple

import fontlabapp.qt.layouts.stack as _stack_layout

from .cocoa import NSMakeRect
from .cocoa_views import (
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
)

# NSLayoutAttribute values a stack view aligns to.
_LEFT, _RIGHT, _TOP, _BOTTOM, _LEADING, _TRAILING = 1, 2, 3, 4, 5, 6
_CENTER_X, _CENTER_Y = 9, 10
_BOX_SEPARATOR = 2  # NSBoxSeparator
# NSStackViewDistribution (gravity areas: -1)
_FILL_EQUALLY, _FILL_PROPORTIONALLY, _EQUAL_SPACING, _EQUAL_CENTERING = 1, 2, 3, 4
_DIVIDER_THICKNESS = {1: 9.0, 2: 1.0, 3: 10.0}  # NSSplitViewDividerStyle


class NSEdgeInsets(NamedTuple):
    top: float
    left: float
    bottom: float
    right: float


def NSEdgeInsetsMake(top, left, bottom, right) -> NSEdgeInsets:
    return NSEdgeInsets(float(top), float(left), float(bottom), float(right))


class NSStackView(NSView):
    """Arranged subviews in a row or column (frames, not constraints)."""

    def initWithFrame_(self, frame):
        self._arranged: list = []
        self._orientation = NSUserInterfaceLayoutOrientationHorizontal
        self._alignment, self._distribution = _CENTER_Y, -1
        self._spacing, self._detaches = 8.0, True
        self._insets = NSEdgeInsets(0.0, 0.0, 0.0, 0.0)
        return NSView.initWithFrame_(self, frame)

    @classmethod
    def stackViewWithViews_(cls, views):
        stack = cls.alloc().init()
        for view in views:
            stack.addArrangedSubview_(view)
        return stack

    # Loading: a NIB's arranged views keep their frames.
    def addSubview_(self, view) -> None:
        NSView.addSubview_(self, view)
        if view.__dict__.pop("_nib_arranged", False):
            self._arranged.append(view)

    def arrangedSubviews(self) -> list:
        return list(self._arranged)

    views = arrangedSubviews

    def addArrangedSubview_(self, view) -> None:
        self.insertArrangedSubview_atIndex_(view, len(self._arranged))

    def insertArrangedSubview_atIndex_(self, view, index) -> None:
        if view in self._arranged:
            self._arranged.remove(view)
        if view.superview() is not self:
            NSView.addSubview_(self, view)
        self._arranged.insert(int(index), view)
        self._layout()

    def removeArrangedSubview_(self, view) -> None:
        """No longer arranged; it stays a subview, as in AppKit."""
        if view in self._arranged:
            self._arranged.remove(view)
            view.__dict__.pop("_stack_natural", None)
            self._layout()

    def _will_remove_subview(self, view) -> None:
        if view in self._arranged:
            self._arranged.remove(view)
            self._layout()

    def _subview_hidden(self, view) -> None:
        if view in self._arranged and self._detaches:
            self._layout()

    def orientation(self) -> int:
        return self._orientation

    def setOrientation_(self, orientation) -> None:
        self._orientation = int(orientation)
        vertical = self._orientation == NSUserInterfaceLayoutOrientationVertical
        self._alignment = _CENTER_X if vertical else _CENTER_Y
        self._layout()

    def alignment(self) -> int:
        return self._alignment

    def setAlignment_(self, alignment) -> None:
        self._alignment = int(alignment)
        self._layout()

    def distribution(self) -> int:
        return self._distribution

    def setDistribution_(self, distribution) -> None:
        self._distribution = int(distribution)
        self._layout()

    def spacing(self) -> float:
        return self._spacing

    def setSpacing_(self, spacing) -> None:
        self._spacing = float(spacing)
        self._layout()

    def edgeInsets(self) -> NSEdgeInsets:
        return self._insets

    def setEdgeInsets_(self, insets) -> None:
        self._insets = NSEdgeInsetsMake(*insets)
        self._layout()

    def detachesHiddenViews(self) -> bool:
        return self._detaches

    def setDetachesHiddenViews_(self, flag) -> None:
        self._detaches = bool(flag)
        self._layout()

    def _layout(self) -> None:
        views = [v for v in self._arranged if not (self._detaches and v.isHidden())]
        if not views:
            return
        (_, _), (width, height) = self._frame
        top, left, bottom, right = self._insets
        vertical = self._orientation == NSUserInterfaceLayoutOrientationVertical
        length = height - top - bottom if vertical else width - left - right
        sizes = [self._natural(v, vertical) for v in views]
        starts = self._distribute(sizes, length)
        for view, start, size in zip(views, starts, sizes, strict=True):
            (_, _), (w, h) = view.frame()
            if vertical:  # top-down: Cocoa's y decreases
                x = _align(self._alignment, left, width - right, w, _LEFT, _LEADING)
                view.setFrame_(NSMakeRect(x, height - top - start - size, w, size))
            else:  # Cocoa y grows upwards: "top" is the high end
                y = _align(self._alignment, bottom, height - top, h, _BOTTOM)
                view.setFrame_(NSMakeRect(left + start, y, size, h))

    @staticmethod
    def _natural(view, vertical: bool) -> float:
        """The size the view had when it was arranged (resizing distributions
        start from it, so repeated layouts do not compound)."""
        natural = view.__dict__.get("_stack_natural")
        size = view.frame().size
        if natural is None:
            natural = view.__dict__["_stack_natural"] = (size.width, size.height)
        return natural[1] if vertical else natural[0]

    def _distribute(self, sizes: list, length: float) -> list:
        """Map foreign distribution policy to shared binding-free arithmetic.

        Gravity, fill and unknown values retain the existing fixed-size policy.
        The same adapter is used by Vanilla VerticalStackView. Original sizes
        remain the same list; widget ownership and Cocoa coordinates stay here.
        """
        mode = {
            _FILL_EQUALLY: "equal",
            _FILL_PROPORTIONALLY: "proportional",
            _EQUAL_SPACING: "spacing",
            _EQUAL_CENTERING: "centering",
        }.get(self._distribution, "fixed")
        return _stack_layout.distribute(sizes, length, self._spacing, mode)


class NSScrollView(NSView):
    """QScrollArea around a document view (no separate clip view or scrollers).

    A scroller shows when it is enabled: always, or only when needed if
    ``autohidesScrollers``. The document view keeps its frame size; Qt
    positions it (scrolled to the top-left)."""

    _qt_class = "QScrollArea"
    _container = False

    def initWithFrame_(self, frame):
        self._document = None
        self._vertical = self._horizontal = self._autohides = False
        NSView.initWithFrame_(self, frame)
        self._policies()
        return self

    def documentView(self):
        return self._document

    def _owned_views(self) -> list:
        document = [] if self._document is None else [self._document]
        return NSView._owned_views(self) + document

    def setDocumentView_(self, view) -> None:
        # Vanilla's getNSView() returns the Qt compatibility handle. Retain
        # its Python owner so callbacks can disconnect before the widget dies.
        lookup = self.__dict__.get("_vanilla_control_for_widget")
        self._vanilla_document = None if lookup is None else lookup(id(view))
        if view is not None and isinstance(view, self._env.qt.QtGui.QWidget):
            view = self._env.classes["NSView"]._wrap_widget(view)
        old = self._document
        if old is not None:
            self._qt.takeWidget()  # setWidget would delete the old widget
            old.__dict__.pop("_embedded", None)
        self._document = view
        if view is not None:
            view.__dict__["_embedded"] = self  # deleted with the scroll area
            self._qt.setWidget(view._qt)
            view._apply_geometry()

    def _release(self):
        document = self.__dict__.pop("_vanilla_document", None)
        if document is not None:
            document._disconnect()

    def hasVerticalScroller(self) -> bool:
        return self._vertical

    def setHasVerticalScroller_(self, flag) -> None:
        self._vertical = bool(flag)
        self._policies()

    def hasHorizontalScroller(self) -> bool:
        return self._horizontal

    def setHasHorizontalScroller_(self, flag) -> None:
        self._horizontal = bool(flag)
        self._policies()

    def autohidesScrollers(self) -> bool:
        return self._autohides

    def setAutohidesScrollers_(self, flag) -> None:
        self._autohides = bool(flag)
        self._policies()

    def setBorderType_(self, border) -> None:
        """Accepted; the Qt frame is kept."""

    def _policies(self) -> None:
        qt = self._env.qt.QtCore.Qt
        shown = qt.ScrollBarAsNeeded if self._autohides else qt.ScrollBarAlwaysOn
        for has, setter in (
            (self._vertical, self._qt.setVerticalScrollBarPolicy),
            (self._horizontal, self._qt.setHorizontalScrollBarPolicy),
        ):
            setter(shown if has else qt.ScrollBarAlwaysOff)


class NSBox(NSView):
    """QGroupBox holding a content view (Interface Builder's frame is kept).

    The title shows unless the position is ``noTitle`` or the box is a
    separator; separators, transparent and borderless boxes are flat."""

    _qt_class = "QGroupBox"

    def initWithFrame_(self, frame):
        self._content, self._title = None, "Box"
        self._box_type, self._position, self._border = 0, 2, 3
        self._transparent = False
        NSView.initWithFrame_(self, frame)
        self._style()
        return self

    def contentView(self):
        return self._content

    def setContentView_(self, view) -> None:
        if self._content is not None:
            self._content.removeFromSuperview()
        self._content = view
        if view is not None:
            self.addSubview_(view)

    def title(self) -> str:
        return self._title

    def setTitle_(self, title) -> None:
        self._title = str(title or "")
        self._style()

    def boxType(self) -> int:
        return self._box_type

    def setBoxType_(self, box_type) -> None:
        self._box_type = int(box_type)
        self._style()

    def titlePosition(self) -> int:
        return self._position

    def setTitlePosition_(self, position) -> None:
        self._position = int(position)
        self._style()

    def borderType(self) -> int:
        return self._border

    def setBorderType_(self, border) -> None:
        self._border = int(border)
        self._style()

    def isTransparent(self) -> bool:
        return self._transparent

    def setTransparent_(self, flag) -> None:
        self._transparent = bool(flag)
        self._style()

    def _style(self) -> None:
        separator = self._box_type == _BOX_SEPARATOR
        shown = self._position != 0 and not separator
        self._qt.setTitle(self._title if shown else "")
        self._qt.setFlat(separator or self._transparent or self._border == 0)


class NSSplitView(NSView):
    """QSplitter whose panes are the subviews, sized from their frames.
    ``isVertical`` (vertical dividers) puts the panes side by side. Divider
    delegate constraints are not consulted."""

    _qt_class = "QSplitter"
    _container = False

    def initWithFrame_(self, frame):
        self._vertical, self._divider_style, self._pane_sizes = False, 1, []
        NSView.initWithFrame_(self, frame)
        self.setVertical_(False)
        self.setDividerStyle_(1)
        return self

    def isVertical(self) -> bool:
        return self._vertical

    def setVertical_(self, flag) -> None:
        self._vertical = bool(flag)
        qt = self._env.qt.QtCore.Qt
        self._qt.setOrientation(qt.Horizontal if self._vertical else qt.Vertical)

    def dividerStyle(self) -> int:
        return self._divider_style

    def setDividerStyle_(self, style) -> None:
        """The Qt handle takes AppKit's divider thickness, so pane frames fit."""
        self._divider_style = int(style)
        self._qt.setHandleWidth(round(self.dividerThickness()))

    def dividerThickness(self) -> float:
        return _DIVIDER_THICKNESS.get(self._divider_style, 9.0)

    def addSubview_(self, view) -> None:
        if view._superview is not None:
            view.removeFromSuperview()
        view._superview = self
        view.__dict__["_managed"] = True  # the splitter lays the pane out
        self._subviews.append(view)
        self._qt.addWidget(view._qt)
        (_, _), (w, h) = view.frame()  # every pane's frame size, set together
        self._pane_sizes.append(round(w if self._vertical else h))
        self._qt.setSizes(self._pane_sizes)
        if not view.isHidden():
            view._qt.show()

    addArrangedSubview_ = addSubview_

    def arrangedSubviews(self) -> list:
        return list(self._subviews)

    def adjustSubviews(self) -> None:
        """Qt keeps the panes adjusted."""

    def _will_remove_subview(self, view) -> None:
        del self._pane_sizes[self._subviews.index(view)]

    def setPosition_ofDividerAtIndex_(self, position, index) -> None:
        sizes, index = list(self._qt.sizes()), int(index)
        handles = round(self.dividerThickness()) * index  # dividers before it
        before = sum(sizes[:index]) + handles
        pair = sizes[index] + sizes[index + 1]
        sizes[index] = max(0, round(position) - before)
        sizes[index + 1] = max(0, pair - sizes[index])
        self._pane_sizes = sizes
        self._qt.setSizes(sizes)


class NSGridView(NSView):
    """A frame-based container for a grid's cell views (Interface Builder's
    frames are kept; placement rules are not solved)."""

    def initWithFrame_(self, frame):
        self._rows = self._columns = 0
        self._row_spacing = self._column_spacing = 6.0
        return NSView.initWithFrame_(self, frame)

    def numberOfRows(self) -> int:
        return self._rows

    def numberOfColumns(self) -> int:
        return self._columns

    def rowSpacing(self) -> float:
        return self._row_spacing

    def setRowSpacing_(self, spacing) -> None:
        self._row_spacing = float(spacing)

    def columnSpacing(self) -> float:
        return self._column_spacing

    def setColumnSpacing_(self, spacing) -> None:
        self._column_spacing = float(spacing)


class NSVisualEffectView(NSView):
    """A plain container: Qt has no vibrancy; material and state are kept."""

    def initWithFrame_(self, frame):
        self._material = self._state = self._blending = 0
        return NSView.initWithFrame_(self, frame)

    def material(self) -> int:
        return self._material

    def setMaterial_(self, material) -> None:
        self._material = int(material)

    def state(self) -> int:
        return self._state

    def setState_(self, state) -> None:
        self._state = int(state)

    def blendingMode(self) -> int:
        return self._blending

    def setBlendingMode_(self, mode) -> None:
        self._blending = int(mode)


def _align(attribute: int, low: float, high: float, size: float, *starts: int) -> float:
    """Place ``size`` between ``low`` and ``high``: at ``low`` for the start
    attributes, at ``high`` for the opposite edge, else centred."""
    if attribute in starts:
        return low
    if attribute in (_RIGHT, _TRAILING, _TOP):
        return high - size
    return low + (high - low - size) / 2


CONTAINER_CLASSES = (
    NSStackView,
    NSScrollView,
    NSBox,
    NSSplitView,
    NSGridView,
    NSVisualEffectView,
)
