# this_file: src/fontlab_glyport/ui/vanilla_controls.py
"""vanilla slice 2 controls: RadioGroup, RadioButton, ComboBox, TextEditor,
SquareButton, HelpButton, ProgressBar, Box and List.

They follow the core rules in ``vanilla.py``: injected ``qt`` (widgets in
``QtGui``), tracked connections, graph nodes, quiet programmatic setters.
``make_vanilla_module`` imports ``CONTROL_CLASSES`` lazily, so this module may
import the core freely.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

import fontlabapp.qt.choices as _editable_choices
import fontlabapp.qt.colors as _qt_colors
import fontlabapp.qt.numeric as _qt_numeric
import fontlabapp.qt.tables.items as _table_items
import fontlabapp.qt.tables.selection as _table_selection
from fontlabapp.core.signals.callbacks import quiet_callbacks
from fontlabapp.qt.events.key import key_press_handler
from fontlabapp.qt.layouts.content import fit_contents

from .vanilla import (
    SLIDER_STEPS,
    Button,
    CheckBox,
    Group,
    _Control,
    _ints,
    _properties,
    _unsupported,
)

# NSMatrix cell heights per sizeStyle; cells sit RADIO_SPACING apart.
RADIO_ROW_HEIGHTS = {"regular": 18, "small": 15, "mini": 12}
RADIO_SPACING = 2
_COLUMN_KEYS = {"title", "key", "editable", "width", "cell"}
_DELETE_KEYS = ("Key_Delete", "Key_Backspace")


class RadioGroup(_Control):
    """Legacy NSMatrix radio group: QRadioButtons in an exclusive QButtonGroup."""

    def __init__(self, posSize, titles, isVertical=True, callback=None, **options):
        titles = [str(title) for title in titles]
        known = {"titles": titles, "isVertical": bool(isVertical)}
        super().__init__(posSize, _properties("RadioGroup", options, **known))
        self._vertical = bool(isVertical)
        self._row = RADIO_ROW_HEIGHTS.get(options.get("sizeStyle"), 18)
        gui = self._env.qt.QtGui
        self._group = gui.QButtonGroup()
        self._group.setParent(self._view)  # deleted with the container widget
        self._group.setExclusive(True)
        self._buttons = [self._radio(gui, title, i) for i, title in enumerate(titles)]
        if self._buttons:
            self._buttons[0].setChecked(True)  # radio-mode NSMatrix starts at 0
        self._wire("idClicked", callback, source=self._group)

    def _radio(self, gui, title: str, index: int) -> Any:
        button = gui.QRadioButton()
        button.setText(title)
        button.setParent(self._view)
        button.show()
        self._group.addButton(button, index)
        return button

    def _place(self, width, height):
        _Control._place(self, width, height)
        w, h = self._size
        count = len(self._buttons)
        for index, button in enumerate(self._buttons):
            if self._vertical:
                frame = (0, index * (self._row + RADIO_SPACING), w, self._row)
            else:
                frame = (index * w / count, 0, w / count, h)
            button.setGeometry(*_ints(frame))

    def get(self) -> int:
        return self._group.checkedId()

    def set(self, index) -> None:
        """Select ``index``; -1 clears (an exclusive group refuses a plain uncheck)."""
        index = int(index)
        if not -1 <= index < len(self._buttons):
            raise IndexError(f"RadioGroup index {index} out of range")
        if index >= 0:
            self._buttons[index].setChecked(True)
            return
        current = self._group.checkedId()
        if current >= 0:
            self._group.setExclusive(False)
            self._buttons[current].setChecked(False)
            self._group.setExclusive(True)


class RadioButton(CheckBox):
    """Standalone radio: not auto-exclusive; a click always leaves it on."""

    _qt_class = "QRadioButton"

    def __init__(self, posSize, title, value=False, callback=None, **options):
        known = {"title": title, "value": bool(value)}
        _Control.__init__(self, posSize, _properties("RadioButton", options, **known))
        self._view.setAutoExclusive(False)
        self.setTitle(title)
        self.set(value)
        if callback is not None:
            self._events["action"] = callback

        def clicked(*args):
            self._view.setChecked(True)  # AppKit radios do not toggle off
            if callback is not None:
                self._env.report(callback, self)

        self._track(self._view.clicked, clicked)


class ComboBox(_Control):
    """Editable QComboBox: get/set the text; the list only offers choices."""

    _qt_class = "QComboBox"

    def __init__(
        self,
        posSize,
        items,
        callback=None,
        continuous=False,
        completes=True,
        **options,
    ):
        items = [str(item) for item in items]
        known = {
            "items": items,
            "continuous": bool(continuous),
            "completes": bool(completes),
        }
        super().__init__(posSize, _properties("ComboBox", options, **known))
        view = self._view
        _editable_choices.configure_combo(
            view, self._env.qt.QtGui.QComboBox.NoInsert
        )
        if not completes:
            view.setCompleter(None)
        self.setItems(items)
        self._connect(callback, bool(continuous))

    def _connect(self, callback, continuous: bool) -> None:
        """User-only signals: popup picks via ``activated``; typing via the line edit.

        Programmatic ``setCurrentIndex``/``setEditText`` emit neither
        ``activated`` nor ``textEdited``, and leave the line edit unmodified.
        """
        line_edit = self._view.lineEdit()
        self._wire("activated", callback, accept=self._accept_activated)
        if continuous:
            self._wire("textEdited", callback, source=line_edit)
        else:
            self._wire(
                "editingFinished", callback, source=line_edit, accept=self._commit
            )

    def _accept_activated(self, args: tuple) -> bool:
        return _editable_choices.accept_activation(self._view, args)

    def _commit(self, args: tuple) -> bool:
        # Keep continuous/finished callback selection in this foreign adapter.
        return _editable_choices.consume_commit(self._view.lineEdit())

    def get(self) -> str:
        return self._view.currentText

    def set(self, value) -> None:
        with quiet_callbacks(self):
            _editable_choices.set_combo_text(self._view, str(value))

    def getItems(self) -> list[str]:
        return list(self._items)

    def setItems(self, items) -> None:
        """Replace the choices; the edit text stays (Qt would change it)."""
        self._items = [str(item) for item in items]
        text = self.get()
        with quiet_callbacks(self):
            self._view.clear()
            self._view.addItems(self._items)
            _editable_choices.set_combo_text(self._view, text)


class TextEditor(_Control):
    """Multi-line plain text; ``checksSpelling`` is recorded only."""

    _qt_class = "QPlainTextEdit"

    def __init__(
        self,
        posSize,
        text="",
        callback=None,
        readOnly=False,
        checksSpelling=False,
        **options,
    ):
        known = {
            "text": str(text),
            "readOnly": bool(readOnly),
            "checksSpelling": bool(checksSpelling),
        }
        super().__init__(posSize, _properties("TextEditor", options, **known))
        self.set(text)
        self._view.setReadOnly(bool(readOnly))
        self._wire("textChanged", callback)

    def get(self) -> str:
        return str(self._view.toPlainText())

    def set(self, value) -> None:
        with quiet_callbacks(self):
            self._view.setPlainText(str(value))


class SquareButton(Button):
    """A push button; the square bezel has no Qt equivalent."""


class HelpButton(Button):
    def __init__(self, posSize, callback=None, **options):
        super().__init__(posSize, "?", callback, **options)


class ProgressBar(_Control):
    """Float value kept here, shown on a 0..SLIDER_STEPS Qt range."""

    _qt_class = "QProgressBar"

    def __init__(
        self, posSize, minValue=0, maxValue=100, isIndeterminate=False, **options
    ):
        if maxValue <= minValue:
            raise ValueError(f"maxValue {maxValue!r} must exceed minValue {minValue!r}")
        known = {
            "minValue": minValue,
            "maxValue": maxValue,
            "isIndeterminate": bool(isIndeterminate),
        }
        super().__init__(posSize, _properties("ProgressBar", options, **known))
        self._min, self._max = float(minValue), float(maxValue)
        self._indeterminate = bool(isIndeterminate)
        self._value = self._min
        self._view.setTextVisible(False)
        _qt_numeric.set_step_range(self._view.setRange, SLIDER_STEPS)
        self._show()

    def _show(self) -> None:
        steps = _qt_numeric.position(self._value, self._min, self._max - self._min, SLIDER_STEPS)
        _qt_numeric.set_position(self._view.setValue, steps)
        self._view.repaint()  # scripts update progress inside busy loops

    def get(self) -> float:
        return self._value

    def set(self, value) -> None:
        self._value = min(self._max, max(self._min, float(value)))
        self._show()

    def increment(self, value=1) -> None:
        self.set(self._value + float(value))

    def start(self) -> None:
        if self._indeterminate:
            _qt_numeric.set_step_range(self._view.setRange, 0)  # Qt's busy indicator

    def stop(self) -> None:
        if self._indeterminate:
            _qt_numeric.set_step_range(self._view.setRange, SLIDER_STEPS)
            self._show()


class ProgressSpinner(ProgressBar):
    """Indeterminate Qt busy indicator with vanilla's start/stop lifecycle."""

    def __init__(self, posSize, **options):
        super().__init__(posSize, isIndeterminate=True, **options)


def _subclass(env: Any, name: str, factory: Callable[[type], type]) -> type:
    """Build a Python subclass of ``QtGui.<name>`` once per env."""
    classes = env.widget_classes
    if name not in classes:
        classes[name] = factory(getattr(env.qt.QtGui, name))
    return classes[name]


def _group_box_class(base: type) -> type:
    """QGroupBox subclass that refits the Box content on show and resize.

    The style polish before the first show moves contentsRect below the title,
    so a fit made earlier would overlap it (observed natively in FontLab 9).
    """

    class GroupBox(base):
        _owner = None

        def showEvent(self, event):
            base.showEvent(self, event)
            if self._owner is not None:
                self._owner._fit_content()

        def resizeEvent(self, event):
            base.resizeEvent(self, event)
            if self._owner is not None:
                self._owner._fit_content()

    return GroupBox


def _rgba_css(color) -> str:
    return _qt_colors.rgba_css(color.rgba)


class Box(Group):
    """Titled QGroupBox; children live in a content widget at its contentsRect."""

    _qt_class = "QGroupBox"

    def __init__(
        self,
        posSize,
        title=None,
        fillColor=None,
        borderColor=None,
        borderWidth=None,
        cornerRadius=None,
        **options,
    ):
        _Control.__init__(self, posSize, _properties("Box", options, title=title))
        self._children = {}
        self._content = self._env.qt.QtGui.QWidget()
        self._content.setParent(self._view)
        self._content.show()
        self._view._owner = self
        self.setTitle(title or "")
        self._style_box(fillColor, borderColor, borderWidth, cornerRadius)

    def _style_box(self, fill, border, width, radius) -> None:
        """vanilla's custom box: NSColor fill/border, width and radius as a
        QGroupBox style sheet (only when any is given)."""
        sheet = _qt_colors.group_box_style(
            None if fill is None else lambda: _rgba_css(fill),
            None if border is None else lambda: _rgba_css(border), width, radius,
        )
        if sheet is not None:
            self._view.setStyleSheet(sheet)

    def _make_view(self) -> Any:
        return _subclass(self._env, "QGroupBox", _group_box_class)()

    def _host_view(self) -> Any:
        return self._content

    def _place(self, width, height):
        _Control._place(self, width, height)
        self._fit_content()

    def _fit_content(self) -> None:
        """Put the content widget on contentsRect and lay the children out in it."""
        self._size = fit_contents(self._view, self._content)
        self._relayout()

    def _disconnect(self):
        Group._disconnect(self)
        self._view._owner = None

    def setTitle(self, title) -> None:
        self._view.setTitle(str(title))
        self._fit_content()  # the title band changes contentsRect

    def getTitle(self) -> str:
        return self._view.title


@dataclass(frozen=True)
class CheckBoxListCell:
    """Switch-cell description, realized as a checkable Qt table item."""

    title: str | None = None


class _Column(NamedTuple):
    title: str
    key: str
    editable: bool
    width: float | None
    checkbox: bool = False
    cell_title: str = ""


def _list_columns(descriptions, has_edit_callback: bool) -> list[_Column]:
    """Parse vanilla columnDescriptions; unknown description keys are unsupported."""
    if not descriptions:
        return [_Column("", "item", has_edit_callback, None)]
    columns = []
    for description in descriptions:
        extra = sorted(set(description) - _COLUMN_KEYS)
        if extra:
            raise _unsupported("vanilla.List.columnDescriptions", extra)
        title = str(description["title"])
        cell = description.get("cell")
        if cell is not None and not isinstance(cell, CheckBoxListCell):
            raise _unsupported("vanilla.List.columnDescriptions", ["cell"])
        editable = description.get("editable")
        editable = (
            (has_edit_callback or cell is not None)
            if editable is None
            else bool(editable)
        )
        key = description.get("key", description["title"])
        columns.append(
            _Column(
                title,
                key,
                editable,
                description.get("width"),
                cell is not None,
                str(cell.title or "") if cell else "",
            )
        )
    return columns


_cell_text = _table_items.cell_text  # historical private compatibility name


def _table_widget_class(base: type) -> type:
    """Python QTableWidget subclass routing Delete/Backspace to the List."""

    class TableWidget(base):
        _owner = None

        keyPressEvent = key_press_handler(
            base,
            lambda widget, event: (
                (owner := widget._owner) is not None and owner._delete_key(event.key())
            ),
        )

    return TableWidget


class List(_Control):
    """QTableWidget rows; items are strings or dicts keyed by column ``key``."""

    _qt_class = "QTableWidget"

    def __init__(
        self,
        posSize,
        items,
        columnDescriptions=None,
        showColumnTitles=True,
        selectionCallback=None,
        doubleClickCallback=None,
        editCallback=None,
        allowsMultipleSelection=True,
        allowsEmptySelection=True,
        drawFocusRing=True,
        enableDelete=False,
        rowHeight=None,
        **options,
    ):
        items = list(items)
        columns = _list_columns(columnDescriptions, editCallback is not None)
        flags = {
            "allowsMultipleSelection": bool(allowsMultipleSelection),
            "allowsEmptySelection": bool(allowsEmptySelection),
            "drawFocusRing": bool(drawFocusRing),
            "enableDelete": bool(enableDelete),
        }
        described = [c._asdict() for c in columns] if columnDescriptions else None
        known = {
            "columns": described,
            "itemCount": len(items),
            "showColumnTitles": bool(showColumnTitles),
            **flags,
        }
        if rowHeight is not None:
            known["rowHeight"] = rowHeight
        super().__init__(posSize, _properties("List", options, **known))
        if rowHeight is not None:
            self._view.verticalHeader().setDefaultSectionSize(round(rowHeight))
        self._columns, self._dicts = columns, bool(columnDescriptions)
        self._enable_delete = flags["enableDelete"]
        self._items: list[dict] = []
        self._view._owner = self
        self._configure(bool(showColumnTitles and self._dicts), flags)
        self.set(items)
        if not flags["allowsEmptySelection"] and items:
            self._select([0])
        self._connect(selectionCallback, doubleClickCallback, editCallback)

    def _make_view(self) -> Any:
        return _subclass(self._env, "QTableWidget", _table_widget_class)()

    def _configure(self, titles: bool, flags: dict) -> None:
        view, gui = self._view, self._env.qt.QtGui
        views = gui.QAbstractItemView
        view.setColumnCount(len(self._columns))
        view.setHorizontalHeaderLabels([c.title for c in self._columns])
        view.horizontalHeader().setVisible(titles)
        view.horizontalHeader().setStretchLastSection(True)
        view.verticalHeader().setVisible(False)
        view.setSelectionBehavior(views.SelectRows)
        multiple = flags["allowsMultipleSelection"]
        view.setSelectionMode(
            views.ExtendedSelection if multiple else views.SingleSelection
        )
        view.setEditTriggers(views.DoubleClicked | views.EditKeyPressed)
        view.setAlternatingRowColors(True)
        if not flags["drawFocusRing"]:
            view.setAttribute(self._env.qt.QtCore.Qt.WA_MacShowFocusRect, False)
        for index, column in enumerate(self._columns):
            if column.width is not None:
                view.setColumnWidth(index, round(column.width))

    def _connect(self, on_selection, on_double_click, on_edit) -> None:
        self._wire("itemSelectionChanged", on_selection, event="selection")
        self._wire(
            "cellDoubleClicked",
            on_double_click,
            event="doubleClick",
            accept=self._clickable,
        )
        if on_edit is not None:
            self._events["edit"] = on_edit
        if any(c.editable for c in self._columns):
            self._track(self._view.itemChanged, self._edited)

    def _clickable(self, args: tuple) -> bool:
        # AppKit edits an editable cell on double click instead of the action.
        return not self._columns[args[1]].editable

    def _edited(self, item) -> None:
        if self._quiet:
            return
        row, column = item.row(), item.column()
        spec = self._columns[column]
        value = (
            item.checkState() == self._env.qt.QtCore.Qt.Checked
            if spec.checkbox
            else item.text()
        )
        self._items[row][spec.key] = value
        callback = self._events.get("edit")
        if callback is not None:
            self._env.report(callback, self)

    def _flags(self, editable: bool) -> Any:
        return _table_items.item_flags(self._env.qt.QtCore.Qt, editable)

    def _wrap(self, item) -> dict:
        return dict(item) if isinstance(item, dict) else {"item": item}

    def _fill_row(self, row: int) -> None:
        gui, item = self._env.qt.QtGui, self._items[row]
        _table_items.fill_row(
            gui, row, item, self._columns, lambda: self._flags,
            lambda: self._env.qt.QtCore.Qt, lambda: self._view,
        )

    def _quietly(self, action: Callable[[], None]) -> None:
        with quiet_callbacks(self):
            action()

    def _fill(self) -> None:
        def fill():
            self._view.setRowCount(0)
            self._view.setRowCount(len(self._items))
            for row in range(len(self._items)):
                self._fill_row(row)

        self._quietly(fill)

    def _select(self, indexes: Sequence[int]) -> None:
        def select():
            _table_selection.select_table_ranges(
                self._view, indexes, lambda: len(self._columns),
                lambda: self._env.qt.QtGui.QTableWidgetSelectionRange,
            )

        self._quietly(select)

    def _report_selection(self) -> None:
        callback = self._events.get("selection")
        if callback is not None:
            self._env.report(callback, self)

    def _delete_key(self, key) -> bool:
        qt_keys = self._env.qt.QtCore.Qt
        if not self._enable_delete or key not in [
            getattr(qt_keys, k) for k in _DELETE_KEYS
        ]:
            return False
        selection = self.getSelection()
        if not selection:
            return False
        for row in reversed(selection):
            del self._items[row]
            self._quietly(lambda row=row: self._view.removeRow(row))
        self._report_selection()
        return True

    def _disconnect(self) -> None:
        _Control._disconnect(self)
        self._view._owner = None

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self._unwrap(item) for item in self._items[index]]
        return self._unwrap(self._items[index])

    def _unwrap(self, item: dict):
        return item if self._dicts else item["item"]

    def get(self) -> list:
        return [self._unwrap(item) for item in self._items]

    def set(self, items) -> None:
        """Replace every row; selection and edit callbacks stay silent."""
        self._items = [self._wrap(item) for item in items]
        self._fill()

    def append(self, item) -> None:
        self._items.append(self._wrap(item))
        row = len(self._items) - 1

        def add():
            self._view.setRowCount(row + 1)
            self._fill_row(row)

        self._quietly(add)

    def extend(self, items) -> None:
        for item in items:
            self.append(item)

    def remove(self, item) -> None:
        row = self.get().index(item)
        del self._items[row]
        self._quietly(lambda: self._view.removeRow(row))

    def getSelection(self) -> list[int]:
        return _table_selection.selected_range_rows(self._view)

    def setSelection(self, indexes) -> None:
        """Select rows; vanilla's selection observer fires, so the callback does."""
        self._select(indexes)
        self._report_selection()


class VanillaBaseObject(_Control):
    """Base of script-defined controls: ``_setupView(nsViewClass, posSize)``
    hosts an instance of that NSView class; its Qt widget is the control and
    ``_nsObject`` is the NSView (R049 custom-nsview)."""

    def __init__(self, posSize: Sequence = (0, 0, 0, 0)) -> None:
        self._setupView("NSView", posSize)

    def _setupView(self, classOrName: Any, posSize: Sequence, callback=None) -> None:
        from .cocoa import NSMakeRect

        cls = (
            classOrName
            if isinstance(classOrName, type)
            else self._env.appkit[str(classOrName)]
        )
        view = cls.alloc().initWithFrame_(NSMakeRect(0, 0, 0, 0))
        # vanilla places and deletes the widget: the view is adopted (top-left
        # frames) and its AppKit environment must not dispose it again.
        view._adopted = True
        if view in view._env.views:
            view._env.views.remove(view)
        self.__dict__["_ns"] = view
        self._make_view = lambda: view._qt  # _Control adopts the view's widget
        _Control.__init__(self, posSize, {"nsViewClass": cls.__name__})

    @property
    def _nsObject(self) -> Any:
        view = self.__dict__.get("_ns")
        if view is None:
            raise _unsupported(f"vanilla.{type(self).__name__}", ["_nsObject"])
        return view


class ColorWell(_Control):
    """A colour swatch (QPushButton); a click opens a non-modal QColorDialog
    whose selection becomes the value and reports the callback. Values are
    NSColor (drawing.cocoa_drawing)."""

    _qt_class = "QPushButton"

    def __init__(
        self, posSize, color=None, callback=None, colorWellStyle=None, **options
    ):
        from ..drawing.cocoa_drawing import NSColor

        super().__init__(posSize, _properties("ColorWell", options))
        self._callback = callback
        self._color_dialog = _qt_colors.ColorDialog()
        self._track(self._view.clicked, lambda *args: self._pick())
        self.set(color if color is not None else NSColor(1, 1, 1, 1))

    def _rgba255(self) -> tuple[int, int, int, int]:
        return _qt_colors.rgba255(self._color.rgba)

    def get(self):
        return self._color

    def set(self, color) -> None:
        self._color = color
        sheet = _qt_colors.swatch_style(self._rgba255())
        self._view.setStyleSheet(sheet)

    def _pick(self) -> None:
        if self._dialog is not None:
            return
        self._color_dialog.open(
            self._env.qt.QtGui, lambda: self._rgba255(), lambda: self._view,
            lambda: self._track, lambda: self._picked,
        )

    def _picked(self, qcolor) -> None:
        from ..drawing.cocoa_drawing import NSColor

        self.set(
            NSColor(qcolor.redF(), qcolor.greenF(), qcolor.blueF(), qcolor.alphaF())
        )
        if self._callback is not None and not self._quiet:
            self._env.report(self._callback, self)

    def _disconnect(self) -> None:
        super()._disconnect()
        self._color_dialog.dispose()

    @property
    def _dialog(self) -> Any:
        return self._color_dialog.dialog

    @_dialog.setter
    def _dialog(self, dialog: Any) -> None:
        self._color_dialog.dialog = dialog


class SegmentedButton(_Control):
    """Segments as push buttons side by side in one widget (equal widths).
    selectionStyle "one" (default): get() is the selected index (-1 none);
    "any": a list of selected indexes; "momentary": the last clicked."""

    _qt_class = "QWidget"
    _ns_class = "NSControl"

    def __init__(
        self,
        posSize,
        segmentDescriptions,
        callback=None,
        selectionStyle="one",
        **options,
    ):
        super().__init__(
            posSize,
            _properties("SegmentedButton", options, selectionStyle=selectionStyle),
        )
        self._style, self._callback = selectionStyle, callback
        self._selected: list[int] = []
        self._buttons = []
        for index, description in enumerate(segmentDescriptions):
            button = self._env.qt.QtGui.QPushButton()
            button.setParent(self._view)
            button.setText(str(description.get("title", "")))
            button.setCheckable(selectionStyle != "momentary")
            self._track(button.clicked, lambda *args, i=index: self._clicked(i))
            self._buttons.append(button)

    def getNSSegmentedButton(self) -> Any:
        return self._nsObject

    def _place(self, width: float, height: float) -> None:
        super()._place(width, height)
        w, h = self._size
        count = max(len(self._buttons), 1)
        for index, button in enumerate(self._buttons):
            left, right = round(w * index / count), round(w * (index + 1) / count)
            button.setGeometry(left, 0, right - left, round(h))

    def _show_selection(self) -> None:
        for index, button in enumerate(self._buttons):
            button.setChecked(index in self._selected)

    def _clicked(self, index: int) -> None:
        if self._style == "any":
            if index in self._selected:
                self._selected.remove(index)
            else:
                self._selected.append(index)
        else:
            self._selected = [index]
        self._show_selection()
        if self._callback is not None and not self._quiet:
            self._env.report(self._callback, self)

    def get(self):
        if self._style == "any":
            return sorted(self._selected)
        return self._selected[0] if self._selected else -1

    def set(self, value) -> None:
        self._selected = list(value) if self._style == "any" else [int(value)]
        self._show_selection()


class ActionButton(_Control):
    """vanilla's gear pop-up: a push button with a menu of the items
    (dicts with "title" and optional "callback"; "----" is a separator)."""

    _qt_class = "QPushButton"

    def __init__(self, posSize, items, **options):
        super().__init__(posSize, _properties("ActionButton", options))
        self._view.setText("\u2699")
        menu = self._env.qt.QtGui.QMenu(self._view)
        for item in items:
            if item == "----" or item is None:
                menu.addSeparator()
                continue
            action = menu.addAction(str(item.get("title", "")))
            callback = item.get("callback")
            if callback is not None:
                self._track(
                    action.triggered,
                    lambda *args, c=callback: self._env.report(c, self),
                )
        self._view.setMenu(menu)


CONTROL_CLASSES = (
    VanillaBaseObject,
    ColorWell,
    SegmentedButton,
    ActionButton,
    RadioGroup,
    RadioButton,
    ComboBox,
    TextEditor,
    SquareButton,
    HelpButton,
    ProgressBar,
    ProgressSpinner,
    Box,
    List,
)
