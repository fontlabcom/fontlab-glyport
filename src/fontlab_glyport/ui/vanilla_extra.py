# this_file: src/fontlab_glyport/ui/vanilla_extra.py
"""Vanilla image and vertical stack views on the existing owned Qt widgets."""

from .application_windows import qt_value
from .cocoa import NSMakeRect, unsupported
from .cocoa_containers import NSStackView
from .vanilla import Group, _Control, _ints

_DISTRIBUTIONS = {
    "fill": 0,
    "fillEqually": 1,
    "fillProportionally": 2,
    "equalSpacing": 3,
    "equalCentering": 4,
}


class VerticalStackView(Group):
    def __init__(
        self,
        posSize,
        views,
        spacing=0,
        alignment="center",
        distribution="fillEqually",
        edgeInsets=(0, 0, 0, 0),
    ):
        if alignment not in {"leading", "center", "trailing"}:
            raise unsupported(f"vanilla.VerticalStackView.alignment.{alignment}")
        if distribution not in _DISTRIBUTIONS:
            raise unsupported(f"vanilla.VerticalStackView.distribution.{distribution}")
        self._alignment, self._distribution = alignment, _DISTRIBUTIONS[distribution]
        self._spacing, self._insets = float(spacing), tuple(map(float, edgeInsets))
        if len(self._insets) != 4:
            raise ValueError("edgeInsets needs four numbers")
        self._arranged = []
        self._next_view_index = 0
        Group.__init__(self, posSize)
        for definition in views:
            if isinstance(definition, dict):
                self.appendView(**definition)
            else:
                self.appendView(definition)

    def appendView(self, view, width=None, height=None, spacing=None, gravity="center"):
        self.insertView(len(self._arranged), view, width, height, spacing, gravity)

    def insertView(
        self, index, view, width=None, height=None, spacing=None, gravity="center"
    ):
        if not isinstance(view, _Control) or gravity != "center" or spacing is not None:
            raise unsupported("vanilla.VerticalStackView.viewOptions")
        for value in (width, height):
            if (
                value is not None
                and value not in ("fill", "fit")
                and not isinstance(value, (float, int))
            ):
                raise unsupported("vanilla.VerticalStackView.sizeConstraint")
        name = f"view{self._next_view_index}"
        self._next_view_index += 1
        self._attach(name, view)
        self._arranged.insert(index, (view, width, height))
        if self._size is not None:
            self._relayout()

    def removeView(self, view):
        entry = next(e for e in self._arranged if e[0] is view)
        self._arranged.remove(entry)
        name = next(name for name, child in self._children.items() if child is view)
        del self._children[name]
        view._retire()
        if self._size is not None:
            self._relayout()

    def setEdgeInsets(self, value):
        insets = tuple(map(float, value))
        if len(insets) != 4:
            raise ValueError("edgeInsets needs four numbers")
        self._insets = insets
        if self._size is not None:
            self._relayout()

    def _relayout(self):
        if self._size is None or not self._arranged:
            return
        left, top, right, bottom = self._insets
        width, height = self._size
        entries = [e for e in self._arranged if not e[0]._hidden]
        if not entries:
            return
        hints = [qt_value(e[0]._view, "sizeHint") for e in entries]
        sizes = [
            float(e[2]) if isinstance(e[2], (int, float)) else hint.height()
            for e, hint in zip(entries, hints, strict=True)
        ]
        if any(e[2] not in (None, "fit") for e in entries):
            if self._distribution != 0:
                raise unsupported("vanilla.VerticalStackView.constrainedDistribution")
            fills = [i for i, e in enumerate(entries) if e[2] == "fill"]
            if fills:
                available = height - top - bottom - self._spacing * (len(entries) - 1)
                remaining = available - sum(
                    size for i, size in enumerate(sizes) if i not in fills
                )
                for i in fills:
                    sizes[i] = max(0, remaining / len(fills))
        starts = NSStackView._distribute(self, sizes, height - top - bottom)
        for (view, width_rule, _), hint, y, h in zip(
            entries, hints, starts, sizes, strict=True
        ):
            w = (
                width - left - right
                if width_rule == "fill" or (width_rule is None and hint.width() < 0)
                else (
                    float(width_rule)
                    if isinstance(width_rule, (int, float))
                    else hint.width()
                )
            )
            x = {
                "leading": left,
                "center": left + (width - left - right - w) / 2,
                "trailing": width - right - w,
            }[self._alignment]
            view._view.setGeometry(*_ints((x, top + y, w, h)))
            view._size = (w, h)
            if isinstance(view, Group):
                view._relayout()


class ImageView(_Control):
    _qt_class, _ns_class = "QLabel", "NSImageView"

    def __init__(
        self,
        posSize,
        horizontalAlignment="center",
        verticalAlignment="center",
        scale="proportional",
    ):
        horizontal = {
            "left": "AlignLeft",
            "center": "AlignHCenter",
            "right": "AlignRight",
        }
        vertical = {
            "top": "AlignTop",
            "center": "AlignVCenter",
            "bottom": "AlignBottom",
        }
        scaling = {"proportional": 0, "fit": 1, "none": 2}
        if (
            horizontalAlignment not in horizontal
            or verticalAlignment not in vertical
            or scale not in scaling
        ):
            raise unsupported("vanilla.ImageView.options")
        _Control.__init__(self, posSize, {})
        qt = self._env.qt.QtCore.Qt
        self._view.setAlignment(
            getattr(qt, horizontal[horizontalAlignment])
            | getattr(qt, vertical[verticalAlignment])
        )
        self._nsObject.setImageScaling_(scaling[scale])

    def getNSImageView(self):
        return self._nsObject

    def _place(self, width, height):
        _Control._place(self, width, height)
        self._refresh_image()

    def _refresh_image(self):
        rect = self._view.geometry
        self._nsObject._frame = NSMakeRect(0, 0, rect.width(), rect.height())
        self._nsObject._render()

    def setImage(self, imagePath=None, imageNamed=None, imageObject=None):
        if sum(value is not None for value in (imagePath, imageNamed, imageObject)) > 1:
            raise ValueError("Pass only one image source")
        cls = self._env.appkit["NSImage"]
        image = imageObject
        if imagePath is not None:
            image = cls.alloc().initWithContentsOfFile_(str(imagePath))
        elif imageNamed is not None:
            image = cls.imageNamed_(imageNamed)
        self._nsObject.setImage_(image)
        self._refresh_image()


EXTRA_CLASSES = (VerticalStackView, ImageView)
