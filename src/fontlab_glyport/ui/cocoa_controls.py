# this_file: src/fontlab_glyport/ui/cocoa_controls.py
"""Qt-backed AppKit controls: text fields, buttons, sliders, popups, progress.

They follow ``cocoa_views.NSControl``: one Qt widget each, target/action on
user input only, quiet programmatic setters, adoption of a vanilla-owned
widget. ``make_appkit_classes`` (in ``cocoa_views``) binds them to an env.
"""

from collections.abc import Callable
from functools import partial
from typing import Any
from urllib.parse import quote, unquote, urlparse

import fontlabapp.qt.choices as _editable_choices
import fontlabapp.qt.colors as _qt_colors
import fontlabapp.qt.numeric as _qt_numeric
from fontlabapp.qt.events.key import key_press_handler

from .cocoa import NSObject, NSZeroRect, unsupported
from .cocoa_views import (
    _ALIGN,
    _BUTTON_WIDGETS,
    SLIDER_STEPS,
    NSControl,
    NSImageOnly,
    NSImageScaleAxesIndependently,
    NSImageScaleProportionallyDown,
    NSImageScaleProportionallyUpOrDown,
    NSLineBreakByCharWrapping,
    NSLineBreakByClipping,
    NSLineBreakByWordWrapping,
    NSMixedState,
    NSMomentaryLightButton,
    NSMomentaryPushInButton,
    NSNoImage,
    NSOffState,
    NSOnState,
    NSRadioButton,
    NSRadioModeMatrix,
    NSSegmentSwitchTrackingMomentary,
    NSSegmentSwitchTrackingSelectAny,
    NSSegmentSwitchTrackingSelectOne,
    NSSwitchButton,
    NSView,
    _number_text,
)


class NSTextField(NSControl):
    """QLineEdit; action on Return/end of an edit, or per keystroke if continuous."""

    _qt_class = "QLineEdit"

    def initWithFrame_(self, frame):
        NSControl.initWithFrame_(self, frame)
        self._editable = True
        return self

    def _adopted_state(self) -> None:
        read_only = getattr(self._qt, "isReadOnly", None)  # a QLabel has none
        self._label = read_only is None
        self._editable = not self._label and not read_only()

    _label = False

    def _line_edit(self, capability: str) -> Any:
        """The QLineEdit; a vanilla TextBox (QLabel) cannot do ``capability``."""
        if self._label:
            raise unsupported(f"NSTextField.{capability} on a vanilla TextBox")
        return self._qt

    _formatter = None

    def becomeFirstResponder(self):
        if self._label:
            return False
        self._qt.setFocus()
        return True

    def setBackgroundColor_(self, color):
        palette = _qt_colors.color_palette(
            self._env.qt.QtGui,
            lambda: self._qt,
            None if color is None else lambda: color.qcolor(self._env.qt),
            lambda palette: palette.Window if self._label else palette.Base,
        )
        if self._label:
            self._qt.setAutoFillBackground(color is not None)
        self._qt.setPalette(palette)

    def formatter(self):
        return self._formatter

    def setFormatter_(self, formatter) -> None:
        """Kept for the script (``formatter().maximum()``); input is not validated."""
        self._formatter = formatter

    @classmethod
    def labelWithString_(cls, text):
        field = cls.alloc().initWithFrame_(NSZeroRect)
        field.setStringValue_(text)
        field.setEditable_(False)
        field.setBezeled_(False)
        field.setDrawsBackground_(False)
        return field

    def _connect(self) -> None:
        line_edit = self._line_edit("action")
        self._track(line_edit.textEdited, self._edited)
        self._track(line_edit.editingFinished, self._finished)

    def _edited(self, *args) -> None:
        if self._continuous:
            self._send()

    def _finished(self, *args) -> None:
        # Qt 5.15 emits editingFinished on every focus loss; only an edit counts.
        if not _editable_choices.consume_commit(self._qt):
            return
        if not self._continuous:
            self._send()

    def _get(self) -> str:
        return self._qt.text

    def _set(self, value) -> None:
        text = value if isinstance(value, str) else _number_text(value)
        self._qt.setText(text)
        if not self._label:
            self._qt.setModified(False)

    def setEditable_(self, flag) -> None:
        if self._label and not flag:
            return  # a label is already not editable
        self._line_edit("setEditable_").setReadOnly(not flag)
        self._editable = bool(flag)

    def isEditable(self) -> bool:
        return self._editable

    def setBezeled_(self, flag) -> None:
        if self._label and not flag:
            return  # a label has no bezel
        self._line_edit("setBezeled_").setFrame(bool(flag))

    setBordered_ = setBezeled_

    def setDrawsBackground_(self, flag) -> None:
        sheet = "" if flag else "QLineEdit { background: transparent; }"
        self._qt.setStyleSheet(sheet)

    def cell(self):
        """The field's cell: line-break mode (a label wraps; a line edit is one line)."""
        cell = self.__dict__.get("_cell")
        if cell is None:
            cell = self.__dict__["_cell"] = _TextFieldCell(self)
        return cell

    def setSelectable_(self, flag) -> None:
        self.__dict__["_selectable"] = bool(flag)

    def setPlaceholderString_(self, text) -> None:
        self._line_edit("setPlaceholderString_").setPlaceholderText(str(text or ""))

    def setTextColor_(self, color):
        palette = _qt_colors.color_palette(
            self._env.qt.QtGui,
            lambda: self._qt,
            None if color is None else lambda: color.qcolor(self._env.qt),
            lambda palette: palette.WindowText if self._label else palette.Text,
        )
        self._qt.setPalette(palette)
        self._text_color = color

    def textColor(self):
        return self.__dict__.get("_text_color")

    def setAlignment_(self, alignment) -> None:
        name = _ALIGN.get(int(alignment))
        if name is None:
            raise unsupported(f"NSTextField.alignment.{alignment}")
        flags = self._env.qt.QtCore.Qt
        self._qt.setAlignment(getattr(flags, name) | flags.AlignVCenter)


class NSSecureTextField(NSTextField):
    def initWithFrame_(self, frame):
        NSTextField.initWithFrame_(self, frame)
        self._qt.setEchoMode(self._env.qt.QtGui.QLineEdit.Password)
        return self


def _stepping_line_edit(base: type) -> type:
    class SteppingLineEdit(base):
        _owner = None

        keyPressEvent = key_press_handler(
            base,
            lambda widget, event: (
                (owner := widget._owner) is not None and owner._step_key(event)
            ),
        )

    return SteppingLineEdit


class GSSteppingTextField(NSTextField):
    """Glyphs' numeric field: Up/Down add/subtract 1, Shift makes it 10.

    Each step stores the new number and sends the action, like an edit.
    """

    STEP, SHIFT_STEP = 1.0, 10.0

    def _make_widget(self) -> Any:
        widget = self._env.subclass("QLineEdit", _stepping_line_edit)()
        widget._owner = self
        return widget

    def _step_key(self, event) -> bool:
        qt = self._env.qt.QtCore.Qt
        direction = {qt.Key_Up: 1, qt.Key_Down: -1}.get(event.key())
        if direction is None or not self._editable:
            return False
        shift = int(event.modifiers()) & int(qt.ShiftModifier)
        step = self.SHIFT_STEP if shift else self.STEP
        self._set(self.doubleValue() + direction * step)
        self._send()
        return True

    def _disconnect(self) -> None:
        NSTextField._disconnect(self)
        self._qt._owner = None


class _TextFieldCell:
    """``NSTextField.cell()``: the line-break mode; word or character wrapping
    makes a label (vanilla TextBox) wrap, other modes clip."""

    def __init__(self, field):
        self._field, self._mode = field, NSLineBreakByClipping

    def lineBreakMode(self) -> int:
        return self._mode

    def setLineBreakMode_(self, mode) -> None:
        self._mode = int(mode)
        if self._field._label:
            wrap = self._mode in (NSLineBreakByWordWrapping, NSLineBreakByCharWrapping)
            self._field._qt.setWordWrap(wrap)

    def isScrollable(self) -> bool:
        return getattr(self, "_scrollable", not self._field._label)

    def setScrollable_(self, flag) -> None:
        """A Qt line edit always scrolls its text; a label just clips."""
        if not flag and not self._field._label:
            raise unsupported("NSTextFieldCell.setScrollable_(False) on an edit field")
        self._scrollable = bool(flag)


class NSButton(NSControl):
    """Push button, checkbox or radio by ``setButtonType_``; action on click."""

    _qt_class = "QPushButton"

    def initWithFrame_(self, frame):
        self._type = NSMomentaryLightButton
        return NSControl.initWithFrame_(self, frame)

    def _adopted_state(self) -> None:
        kinds = {
            v: k for k, v in _BUTTON_WIDGETS.items() if k != NSMomentaryPushInButton
        }
        name = next(
            n for n in kinds if isinstance(self._qt, getattr(self._env.qt.QtGui, n))
        )
        self.__dict__["_qt_class"] = name
        self._type = kinds[name]

    def _connect(self) -> None:
        self._track(self._qt.clicked, self._clicked)

    def _clicked(self, *args) -> None:
        if self._type == NSRadioButton:
            self._qt.setChecked(True)  # AppKit radios do not toggle off
        self._send()

    def setButtonType_(self, kind) -> None:
        widget = _BUTTON_WIDGETS.get(int(kind))
        if widget is None:
            raise unsupported(f"NSButton.buttonType.{kind}")
        self._type = int(kind)
        if widget != self._qt_class:
            self._rebuild(widget)

    def _rebuild(self, qt_class: str) -> None:
        """Swap the Qt widget class, keeping parent, geometry, title and state."""
        old, title = self._qt, self.title()
        self._disconnect()
        self.__dict__["_qt_class"] = qt_class
        self._qt = self._make_widget()
        if self._superview is not None:
            self._qt.setParent(self._superview._qt)
        self._apply_geometry()
        self.setTitle_(title)
        if self.image() is not None:
            self._qt.setIcon(self.image().icon())
        self._qt.setEnabled(old.isEnabled())
        if qt_class == "QRadioButton":
            self._qt.setAutoExclusive(False)
        old.setParent(None)
        old.deleteLater()
        if self._superview is not None and not self.isHidden():
            self._qt.show()
        self._connect()

    def title(self) -> str:
        hidden = self.__dict__.get("_hidden_title")
        return self._qt.text if hidden is None else hidden

    def setTitle_(self, title) -> None:
        title = str(title or "")
        if self.__dict__.get("_hidden_title") is not None:
            self.__dict__["_hidden_title"] = title  # image only: text stays hidden
            return
        self._qt.setText(title)

    def image(self):
        return self.__dict__.get("_image")

    def setImage_(self, image) -> None:
        """An ``NSImage`` (``ui.images``) as the button icon; ``None`` clears it."""
        self.__dict__["_image"] = image
        self._qt.setIcon(self._env.qt.QtGui.QIcon() if image is None else image.icon())

    def imagePosition(self) -> int:
        return self.__dict__.get("_image_position", NSNoImage)

    def setImagePosition_(self, position) -> None:
        """Qt draws the icon before the text; ``NSImageOnly`` hides the title."""
        title = self.title()
        self.__dict__["_image_position"] = int(position)
        image_only = int(position) == NSImageOnly
        self.__dict__["_hidden_title"] = title if image_only else None
        self._qt.setText("" if image_only else title)

    def bezelStyle(self):
        return self.__dict__.get("_bezel_style", 1)

    def setBezelStyle_(self, style):
        # NSRoundedBezelStyle is Qt's standard push-button bezel.
        self._bezel_style = int(style)
        self.setBordered_(True)

    def isBordered(self) -> bool:
        return self.__dict__.get("_bordered", True)

    def setBordered_(self, flag) -> None:
        """A borderless push button is flat; check boxes and radios have no border."""
        self.__dict__["_bordered"] = bool(flag)
        if self._qt_class == "QPushButton":
            self._qt.setFlat(not flag)

    def state(self) -> int:
        if self._qt_class == "QPushButton":
            return NSOffState
        if self._qt_class == "QCheckBox" and int(self._qt.checkState()) == 1:
            return NSMixedState
        return NSOnState if self._qt.isChecked() else NSOffState

    def setState_(self, state) -> None:
        state = int(state)
        if self._qt_class == "QPushButton":
            return
        if state == NSMixedState and self._qt_class == "QCheckBox":
            self._qt.setTristate(True)
            self._qt.setCheckState(self._env.qt.QtCore.Qt.PartiallyChecked)
            return
        self._qt.setChecked(state != NSOffState)

    def _get(self) -> int:
        return self.state()

    def _set(self, value) -> None:
        self.setState_(int(value))


class NSSearchField(NSTextField):
    """A QLineEdit with a clear button and a placeholder; with
    ``sendsSearchStringImmediately`` every keystroke sends the action."""

    def initWithFrame_(self, frame):
        NSTextField.initWithFrame_(self, frame)
        self._qt.setClearButtonEnabled(True)
        self.__dict__["_placeholder"] = ""
        return self

    def placeholderString(self) -> str:
        return self.__dict__.get("_placeholder", "")

    def setPlaceholderString_(self, text) -> None:
        self.__dict__["_placeholder"] = str(text or "")
        NSTextField.setPlaceholderString_(self, text)

    def sendsSearchStringImmediately(self) -> bool:
        return self._continuous

    def setSendsSearchStringImmediately_(self, flag) -> None:
        self.setContinuous_(flag)


class _Segment:
    def __init__(self, button):
        self._qt, self.width, self.tag, self.image = button, 0.0, 0, None
        self.slot = None  # the exact slot connected to its clicked signal


class NSSegmentedControl(NSControl):
    """One checkable QPushButton per segment, laid out left to right (a width
    of 0 shares the frame). Select-one keeps exactly one segment on; select-any
    toggles; momentary only reports the clicked segment to the action."""

    _qt_class = "QWidget"

    def initWithFrame_(self, frame):
        self._segments: list = []
        self._tracking, self._selected = NSSegmentSwitchTrackingSelectOne, -1
        return NSControl.initWithFrame_(self, frame)

    def _load_segments(self, specs, tracking) -> None:
        self._tracking = int(tracking)
        self.setSegmentCount_(len(specs))
        for index, spec in enumerate(specs):
            segment = self._segments[index]
            segment.width, segment.tag = spec.get("width", 0.0), spec.get("tag", 0)
            segment._qt.setText(spec.get("label", ""))
            if spec.get("selected"):
                self.setSelected_forSegment_(True, index)
        self._layout()

    def segmentCount(self) -> int:
        return len(self._segments)

    def setSegmentCount_(self, count) -> None:
        count = int(count)
        while len(self._segments) > count:
            self._remove_segment()
        while len(self._segments) < count:
            button = self._env.qt.QtGui.QPushButton()
            button.setParent(self._qt)
            button.setCheckable(self._tracking != NSSegmentSwitchTrackingMomentary)
            button.show()
            segment = _Segment(button)
            segment.slot = partial(self._clicked, len(self._segments))
            self._track(button.clicked, segment.slot)
            self._segments.append(segment)
        if self._selected >= count:
            self._selected = -1
        self._layout()

    def _remove_segment(self) -> None:
        segment = self._segments.pop()
        # PythonQt builds a new signal wrapper per attribute access: match the
        # stored slot, and disconnect through the wrapper used to connect it.
        for entry in [e for e in self._slots if e[1] is segment.slot]:
            entry[0].disconnect(entry[1])
            self._slots.remove(entry)
        segment._qt.setParent(None)
        segment._qt.deleteLater()

    def _layout(self) -> None:
        if not self._segments:
            return
        (_, _), (width, height) = self._frame
        fixed = sum(s.width for s in self._segments)
        free = [s for s in self._segments if not s.width]
        share = (width - fixed) / len(free) if free else 0.0
        x = 0.0
        for segment in self._segments:
            w = segment.width or share
            segment._qt.setGeometry(round(x), 0, round(w), round(height))
            x += w

    def setFrame_(self, frame) -> None:
        NSControl.setFrame_(self, frame)
        self._layout()

    def _clicked(self, index, *args) -> None:
        if self._tracking == NSSegmentSwitchTrackingSelectAny:
            self._selected = index
        else:
            self._select_one(index)
        self._send()

    def _select_one(self, index: int) -> None:
        self._selected = index
        if self._tracking == NSSegmentSwitchTrackingMomentary:
            return
        for i, segment in enumerate(self._segments):
            segment._qt.setChecked(i == index)

    def trackingMode(self) -> int:
        return self._tracking

    def setTrackingMode_(self, mode) -> None:
        self._tracking = int(mode)
        for segment in self._segments:
            segment._qt.setCheckable(self._tracking != NSSegmentSwitchTrackingMomentary)

    def selectedSegment(self) -> int:
        return self._selected

    def setSelectedSegment_(self, index) -> None:
        index = int(index)
        if 0 <= index < len(self._segments):
            if self._tracking == NSSegmentSwitchTrackingSelectAny:
                self.setSelected_forSegment_(True, index)
            else:
                self._select_one(index)

    def isSelectedForSegment_(self, index) -> bool:
        return bool(self._segments[int(index)]._qt.isChecked())

    def setSelected_forSegment_(self, flag, index) -> None:
        index = int(index)
        if flag and self._tracking != NSSegmentSwitchTrackingSelectAny:
            self._select_one(index)
            return
        self._segments[index]._qt.setChecked(bool(flag))
        if flag:
            self._selected = index

    def labelForSegment_(self, index) -> str:
        return str(self._segments[int(index)]._qt.text)

    def setLabel_forSegment_(self, label, index) -> None:
        self._segments[int(index)]._qt.setText(str(label or ""))

    def widthForSegment_(self, index) -> float:
        segment = self._segments[int(index)]
        if segment.width:
            return segment.width
        rect = segment._qt.geometry
        return float(rect.width())

    def setWidth_forSegment_(self, width, index) -> None:
        self._segments[int(index)].width = float(width)
        self._layout()

    def segmentStyle(self) -> int:
        return self.__dict__.get("_style", 0)

    def setSegmentStyle_(self, style) -> None:
        """Recorded; the Qt buttons keep the platform style."""
        self.__dict__["_style"] = int(style)

    def setSelectedSegmentBezelColor_(self, color) -> None:
        """Accepted; the selected segment keeps Qt's checked colour."""

    def toolTipForSegment_(self, index) -> str:
        tip = self._segments[int(index)]._qt.toolTip
        return str(tip() if callable(tip) else tip)

    def setToolTip_forSegment_(self, text, index) -> None:
        self._segments[int(index)]._qt.setToolTip(str(text or ""))

    def tagForSegment_(self, index) -> int:
        return self._segments[int(index)].tag

    def setTag_forSegment_(self, tag, index) -> None:
        self._segments[int(index)].tag = int(tag)

    def imageForSegment_(self, index):
        return self._segments[int(index)].image

    def setImage_forSegment_(self, image, index) -> None:
        segment = self._segments[int(index)]
        segment.image = image
        icon = self._env.qt.QtGui.QIcon() if image is None else image.icon()
        segment._qt.setIcon(icon)

    def _get(self) -> int:
        return self._selected

    def _set(self, value) -> None:
        self.setSelectedSegment_(int(value))

    def _binding_setter(self, binding: str) -> Callable | None:
        if binding == "selectedIndex":
            return lambda value: self._quietly(lambda: self.setSelectedSegment_(value))
        return NSControl._binding_setter(self, binding)


class NSSwitch(NSButton):
    """An on/off switch as a QCheckBox (Qt has no switch widget); no title."""

    _qt_class = "QCheckBox"

    def initWithFrame_(self, frame):
        NSButton.initWithFrame_(self, frame)
        self._type = NSSwitchButton
        return self


class GSMouseOverButton(NSButton):
    """Glyphs' private toolbar button: borderless (a flat QPushButton, which
    Qt highlights under the mouse) and usually showing only its image."""

    def initWithFrame_(self, frame):
        NSButton.initWithFrame_(self, frame)
        self.setBordered_(False)
        return self


class NSSlider(NSControl):
    """QSlider over ``SLIDER_STEPS`` integer steps; vertical when taller than wide."""

    _qt_class = "QSlider"

    _steps = 0  # widget value that ``_value`` was last exact for

    def initWithFrame_(self, frame):
        self._min, self._max, self._value = 0.0, 1.0, 0.0
        NSControl.initWithFrame_(self, frame)
        size = self._frame.size
        orientation = "Vertical" if size.height > size.width else "Horizontal"
        self._qt.setOrientation(getattr(self._env.qt.QtCore.Qt, orientation))
        _qt_numeric.set_step_range(self._qt.setRange, SLIDER_STEPS)
        return self

    def _adopted_state(self) -> None:
        owner = self._owner
        self._min, self._max = owner._min, owner._min + owner._span
        self._value, self._steps = owner.get(), self._qt.value

    def _connect(self) -> None:
        self._track(self._qt.valueChanged, self._moved)
        self._track(self._qt.sliderReleased, self._released)

    def _moved(self, steps) -> None:
        if self._quiet:
            return  # programmatic: keep the exact value set
        self._value, self._steps = self._from_steps(steps), steps
        if self._continuous or not self._qt.isSliderDown():
            self._send()

    def _released(self) -> None:
        if not self._continuous:
            self._send()

    def _from_steps(self, steps) -> float:
        return _qt_numeric.value_at(
            self._min, steps, self._max - self._min, SLIDER_STEPS
        )

    def _get(self) -> float:
        """The exact value set here, unless the shared widget moved since."""
        steps = self._qt.value
        if steps != self._steps:  # e.g. vanilla's Slider.set on the same widget
            self._value, self._steps = self._from_steps(steps), steps
        return self._value

    def _set(self, value) -> None:
        span = self._max - self._min
        self._value = min(max(float(value), self._min), self._max)
        steps = (
            0
            if span <= 0
            else _qt_numeric.position(self._value, self._min, span, SLIDER_STEPS)
        )
        self._steps = round(steps)
        self._qt.setValue(self._steps)

    def minValue(self) -> float:
        return self._min

    def maxValue(self) -> float:
        return self._max

    def setMinValue_(self, value) -> None:
        self._min = float(value)
        self.setObjectValue_(self._value)

    def setMaxValue_(self, value) -> None:
        self._max = float(value)
        self.setObjectValue_(self._value)


class NSPopUpButton(NSControl):
    """Non-editable QComboBox; the value is the selected index."""

    _qt_class = "QComboBox"

    def initWithFrame_pullsDown_(self, frame, pullsDown):
        if pullsDown:
            raise unsupported("NSPopUpButton.pullsDown")
        return self.initWithFrame_(frame)

    def _connect(self) -> None:
        self._track(self._qt.activated, self._activated)

    def _activated(self, *args) -> None:
        if args and isinstance(args[0], str):
            return  # Qt 5.15 also emits activated(QString)
        self._send()

    def addItemWithTitle_(self, title) -> None:
        self._quietly(lambda: self._qt.addItem(str(title)))

    def addItemsWithTitles_(self, titles) -> None:
        for title in titles:
            self.addItemWithTitle_(title)

    def removeAllItems(self) -> None:
        self._quietly(self._qt.clear)

    def itemTitles(self) -> list[str]:
        return [self._qt.itemText(i) for i in range(self._qt.count)]

    def numberOfItems(self) -> int:
        return int(self._qt.count)

    def indexOfSelectedItem(self) -> int:
        return int(self._qt.currentIndex)

    def selectItemAtIndex_(self, index) -> None:
        self._quietly(lambda: self._qt.setCurrentIndex(int(index)))

    def selectItemWithTitle_(self, title) -> None:
        titles = self.itemTitles()
        self.selectItemAtIndex_(titles.index(title) if title in titles else -1)

    def titleOfSelectedItem(self):
        index = self.indexOfSelectedItem()
        return None if index < 0 else self._qt.itemText(index)

    def _get(self) -> int:
        return self.indexOfSelectedItem()

    def _set(self, value) -> None:
        self._qt.setCurrentIndex(int(value))

    def _binding_setter(self, binding: str) -> Callable | None:
        if binding == "selectedIndex":
            return self.selectItemAtIndex_
        return NSControl._binding_setter(self, binding)


class NSComboBox(NSControl):
    """Editable QComboBox (NoInsert): the value is the text; the list offers
    choices from its items or, with ``usesDataSource``, from the data source
    (``numberOfItemsInComboBox_``, ``comboBox_objectValueForItemAtIndex_``).
    A popup pick or a finished edit sends the action."""

    _qt_class = "QComboBox"

    def initWithFrame_(self, frame):
        self._data_source, self._uses_data_source = None, False
        self._completes, self._visible = True, 5
        NSControl.initWithFrame_(self, frame)
        return self

    def _make_widget(self) -> Any:
        widget = NSControl._make_widget(self)
        _editable_choices.configure_combo(widget, self._env.qt.QtGui.QComboBox.NoInsert)
        return widget

    def _connect(self) -> None:
        self._track(self._qt.activated, self._activated)
        self._track(self._qt.lineEdit().editingFinished, self._finished)

    def _activated(self, *args) -> None:
        if not _editable_choices.accept_activation(self._qt, args):
            return
        self._send()

    def _finished(self, *args) -> None:
        line_edit = self._qt.lineEdit()
        if not _editable_choices.consume_commit(line_edit):
            return
        self._send()

    def _items(self, values) -> None:
        """Replace the list, keeping the text (Qt copies item 0 into it)."""
        text = self.stringValue()
        self._quietly(self._qt.clear)
        self._quietly(lambda: self._qt.addItems([str(v) for v in values]))
        self._set(text)

    def _get(self) -> str:
        text = self._qt.currentText
        return str(text() if callable(text) else text)

    def _set(self, value) -> None:
        text = value if isinstance(value, str) else _number_text(value)
        _editable_choices.set_combo_text(self._qt, text)

    # Items
    def addItemWithObjectValue_(self, value) -> None:
        self._items([*self.objectValues(), value])

    def addItemsWithObjectValues_(self, values) -> None:
        self._items([*self.objectValues(), *values])

    def insertItemWithObjectValue_atIndex_(self, value, index) -> None:
        values = self.objectValues()
        values.insert(int(index), value)
        self._items(values)

    def removeItemAtIndex_(self, index) -> None:
        values = self.objectValues()
        del values[int(index)]
        self._items(values)

    def removeAllItems(self) -> None:
        self._items([])

    def objectValues(self) -> list:
        count = self._qt.count
        count = count() if callable(count) else count
        return [str(self._qt.itemText(i)) for i in range(count)]

    def numberOfItems(self) -> int:
        return len(self.objectValues())

    def itemObjectValueAtIndex_(self, index):
        return self.objectValues()[int(index)]

    def indexOfItemWithObjectValue_(self, value) -> int:
        values = self.objectValues()
        return values.index(str(value)) if str(value) in values else -1

    def indexOfSelectedItem(self) -> int:
        """The item matching the text, as AppKit reports after a pick or edit."""
        return self.indexOfItemWithObjectValue_(self.stringValue())

    def objectValueOfSelectedItem(self):
        index = self.indexOfSelectedItem()
        return None if index < 0 else self.objectValues()[index]

    def selectItemAtIndex_(self, index) -> None:
        self._quietly(lambda: self._qt.setCurrentIndex(int(index)))
        self._qt.lineEdit().setModified(False)

    def selectItemWithObjectValue_(self, value) -> None:
        index = self.indexOfItemWithObjectValue_(value)
        if index >= 0:
            self.selectItemAtIndex_(index)

    # Behaviour
    def completes(self) -> bool:
        return self._completes

    def setCompletes_(self, flag) -> None:
        self._completes = bool(flag)
        if not flag:
            self._qt.setCompleter(None)

    def numberOfVisibleItems(self) -> int:
        return self._visible

    def setNumberOfVisibleItems_(self, count) -> None:
        self._visible = int(count)
        self._qt.setMaxVisibleItems(self._visible)

    def isEditable(self) -> bool:
        return not self._qt.lineEdit().isReadOnly()

    def setEditable_(self, flag) -> None:
        self._qt.lineEdit().setReadOnly(not flag)

    # Data source
    def usesDataSource(self) -> bool:
        return self._uses_data_source

    def setUsesDataSource_(self, flag) -> None:
        self._uses_data_source = bool(flag)

    def dataSource(self):
        return self._data_source

    def setDataSource_(self, source) -> None:
        self._data_source = source
        if self._uses_data_source:
            self._env.dispatch.call(self.reloadData, self)

    def reloadData(self) -> None:
        source = self._data_source
        count = getattr(source, "numberOfItemsInComboBox_", None)
        value = getattr(source, "comboBox_objectValueForItemAtIndex_", None)
        if count is None or value is None or self.__dict__.get("_dead"):
            return
        generation = self.__dict__["_generation"] = (
            self.__dict__.get("_generation", 0) + 1
        )

        def stale():  # a callback disposed the combo box or reloaded it
            return (
                self.__dict__.get("_dead") or self.__dict__["_generation"] != generation
            )

        total = int(count(self))
        if stale():
            return
        values = []
        for index in range(total):
            values.append(value(self, index))
            if stale():
                return
        self._items(values)

    def _release(self) -> None:
        NSControl._release(self)
        self.__dict__["_dead"] = True
        self._data_source = None


class NSProgressIndicator(NSView):
    """QProgressBar mapped onto ``SLIDER_STEPS`` steps."""

    _qt_class = "QProgressBar"
    _container = False

    def initWithFrame_(self, frame):
        self._min, self._max, self._value, self._busy = 0.0, 100.0, 0.0, False
        NSView.initWithFrame_(self, frame)
        _qt_numeric.set_step_range(self._qt.setRange, SLIDER_STEPS)
        return self

    def _show(self) -> None:
        span = self._max - self._min
        steps = (
            0
            if span <= 0
            else _qt_numeric.position(self._value, self._min, span, SLIDER_STEPS)
        )
        _qt_numeric.set_position(self._qt.setValue, min(max(steps, 0), SLIDER_STEPS))

    def doubleValue(self) -> float:
        return self._value

    def setDoubleValue_(self, value) -> None:
        self._value = float(value)
        self._show()

    def incrementBy_(self, delta) -> None:
        self.setDoubleValue_(self._value + float(delta))

    def setMinValue_(self, value) -> None:
        self._min = float(value)
        self._show()

    def setMaxValue_(self, value) -> None:
        self._max = float(value)
        self._show()

    def setIndeterminate_(self, flag) -> None:
        self._busy = bool(flag)

    def startAnimation_(self, sender) -> None:
        if self._busy:
            _qt_numeric.set_step_range(self._qt.setRange, 0)

    def stopAnimation_(self, sender) -> None:
        _qt_numeric.set_step_range(self._qt.setRange, SLIDER_STEPS)
        self._show()


class NSButtonCell(NSObject):
    """One matrix cell: its own Qt button inside the matrix widget."""

    def title(self) -> str:
        return str(self._qt.text)

    def setTitle_(self, title) -> None:
        self._qt.setText(str(title or ""))

    def state(self) -> int:
        return NSOnState if self._qt.isChecked() else NSOffState

    def setState_(self, state) -> None:
        if self._type != NSMomentaryPushInButton:
            self._qt.setChecked(int(state) == NSOnState)

    def tag(self) -> int:
        return self._tag

    def setTag_(self, tag) -> None:
        self._tag = int(tag)

    def isEnabled(self) -> bool:
        return bool(self._qt.isEnabled())

    def setEnabled_(self, flag) -> None:
        self._qt.setEnabled(bool(flag))


class NSMatrix(NSControl):
    """A grid of button cells (radio groups, checkbox columns) in one widget.

    Cells sit at ``cellSize`` plus ``intercellSpacing`` from the top-left, row 0
    on top. A click selects the cell and sends the action with the matrix as
    sender; radio cells in one matrix are exclusive (Qt auto-exclusive
    siblings). ``selectedIndex`` binds both ways (row-major index)."""

    _qt_class = "QWidget"

    def initWithFrame_(self, frame):
        self._cells: list = []
        self._rows = self._columns = 0
        self._selected, self._mode = -1, NSRadioModeMatrix
        self._cell_size, self._spacing = (100.0, 18.0), (0.0, 0.0)
        return NSControl.initWithFrame_(self, frame)

    def _load_cells(self, specs, rows, columns, mode, cell_size, spacing) -> None:
        """Build the cells a NIB declares (row-major); they must fill the grid
        and stay within the NIB node budget."""
        from .nib_archive import NibFormatError
        from .nib_graph import MAX_NODES

        if int(rows) * int(columns) != len(specs) or len(specs) > MAX_NODES:
            raise NibFormatError(f"matrix of {rows}x{columns} with {len(specs)} cells")
        self._rows, self._columns, self._mode = int(rows), int(columns), int(mode)
        self._cell_size = tuple(cell_size or self._cell_size)
        self._spacing = tuple(spacing or self._spacing)
        for index, spec in enumerate(specs):
            kind = spec.get("buttonType", 0)
            cell = NSButtonCell.alloc().init()
            cell._type, cell._tag = kind, spec.get("tag", 0)
            qt_class = _BUTTON_WIDGETS.get(kind, "QPushButton")
            cell._qt = getattr(self._env.qt.QtGui, qt_class)()
            cell._qt.setParent(self._qt)
            cell.setTitle_(spec.get("title", ""))
            cell.setState_(spec.get("state", 0))
            cell.setEnabled_(spec.get("enabled", True))
            row, column = divmod(index, self._columns or 1)
            (w, h), (sx, sy) = self._cell_size, self._spacing
            cell._qt.setGeometry(
                round(column * (w + sx)), round(row * (h + sy)), round(w), round(h)
            )
            cell._qt.show()
            self._track(cell._qt.clicked, partial(self._cell_clicked, index))
            self._cells.append(cell)
            if spec.get("state") == NSOnState and self._selected < 0:
                self._selected = index

    def _cell_clicked(self, index, *args) -> None:
        cell = self._cells[index]
        if cell._type == NSRadioButton:
            cell._qt.setChecked(True)  # AppKit radios do not toggle off
        self._selected = index
        self._send()

    def mode(self) -> int:
        return self._mode

    def cells(self) -> list:
        return list(self._cells)

    def numberOfRows(self) -> int:
        return self._rows

    def numberOfColumns(self) -> int:
        return self._columns

    def cellAtRow_column_(self, row, column):
        index = int(row) * self._columns + int(column)
        return self._cells[index] if 0 <= index < len(self._cells) else None

    def cellWithTag_(self, tag):
        return next((c for c in self._cells if c.tag() == int(tag)), None)

    def selectedCell(self):
        return self._cells[self._selected] if self._selected >= 0 else None

    def selectedRow(self) -> int:
        return self._selected // self._columns if self._selected >= 0 else -1

    def selectedColumn(self) -> int:
        return self._selected % self._columns if self._selected >= 0 else -1

    def selectCellAtRow_column_(self, row, column) -> None:
        self._select(int(row) * self._columns + int(column))

    def selectCellWithTag_(self, tag) -> bool:
        cell = self.cellWithTag_(tag)
        if cell is not None:
            self._select(self._cells.index(cell))
        return cell is not None

    def _select(self, index: int) -> None:
        if not 0 <= index < len(self._cells):
            return
        self._selected = index
        cell = self._cells[index]
        if self._mode == NSRadioModeMatrix and cell._type == NSRadioButton:
            cell.setState_(NSOnState)

    def _get(self):
        return self._selected

    def _set(self, value) -> None:
        self._select(int(value))

    def _binding_setter(self, binding: str) -> Callable | None:
        if binding == "selectedIndex":
            return lambda value: self._quietly(lambda: self._select(int(value)))
        return NSControl._binding_setter(self, binding)


class NSURL(NSObject):
    """A file URL: the subset path controls and open panels hand to scripts."""

    @classmethod
    def fileURLWithPath_(cls, path):
        """A trailing slash marks a directory URL (kept in ``absoluteString``)."""
        url, path = cls.alloc().init(), str(path)
        url._path, url._directory = path.rstrip("/") or "/", path.endswith("/")
        return url

    @classmethod
    def URLWithString_(cls, text):
        parsed = urlparse(str(text))
        if parsed.scheme not in ("", "file"):
            raise unsupported(f"NSURL.scheme.{parsed.scheme}")
        return cls.fileURLWithPath_(unquote(parsed.path))

    def path(self) -> str:
        return self._path

    def isFileURL(self) -> bool:
        return True

    def absoluteString(self) -> str:
        slash = "/" if self._directory and self._path != "/" else ""
        return "file://" + quote(self._path + slash)

    def lastPathComponent(self) -> str:
        return self._path.rsplit("/", 1)[-1]


class NSPathControl(NSControl):
    """QLineEdit showing a file URL's path. Editable: a finished edit sets the
    URL and sends the action; read-only otherwise. ``value`` binds the path."""

    _qt_class = "QLineEdit"

    def initWithFrame_(self, frame):
        self._url, self._allowed = None, None
        NSControl.initWithFrame_(self, frame)
        return self

    def _connect(self) -> None:
        self._track(self._qt.editingFinished, self._edited)

    def _edited(self, *args) -> None:
        if not _editable_choices.consume_commit(self._qt):
            return
        text = str(self._qt.text).strip()
        self._url = NSURL.fileURLWithPath_(text) if text else None
        self._send()

    def URL(self):
        return self._url

    def setURL_(self, url) -> None:
        """An NSURL, a ``file:`` URL string, or a plain filesystem path."""
        if url is None or isinstance(url, NSURL):
            self._url = url
        elif str(url).startswith("file:"):
            self._url = NSURL.URLWithString_(str(url))
        else:  # a path: '#', '?' and '%' are file name characters
            self._url = NSURL.fileURLWithPath_(str(url))
        self._qt.setText("" if self._url is None else self._url.path())

    def _get(self):
        return None if self._url is None else self._url.path()

    def _set(self, value) -> None:
        if value is None or isinstance(value, NSURL):
            self.setURL_(value)
        elif hasattr(value, "path"):  # another URL object
            self.setURL_(NSURL.fileURLWithPath_(str(value.path())))
        else:
            self.setURL_(str(value))

    def isEditable(self) -> bool:
        return not self._qt.isReadOnly()

    def setEditable_(self, flag) -> None:
        self._qt.setReadOnly(not flag)

    def allowedTypes(self):
        return self._allowed

    def setAllowedTypes_(self, types) -> None:
        self._allowed = None if types is None else list(types)


class NSImageView(NSControl):
    """QLabel showing an ``NSImage`` (``ui.images``) scaled to the frame:
    proportionally down (default), up or down, not at all, or stretched."""

    _qt_class = "QLabel"

    def initWithFrame_(self, frame):
        self._image, self._scaling = None, NSImageScaleProportionallyDown
        NSControl.initWithFrame_(self, frame)
        self._qt.setAlignment(self._env.qt.QtCore.Qt.AlignCenter)
        return self

    def _adopted_state(self):
        self._image, self._scaling = None, NSImageScaleProportionallyDown

    def image(self):
        return self._image

    def setImage_(self, image) -> None:
        self._image = image
        self._render()

    def _get(self):
        return self._image

    def _set(self, value) -> None:
        self.setImage_(value)

    def imageScaling(self) -> int:
        return self._scaling

    def setImageScaling_(self, scaling) -> None:
        self._scaling = int(scaling)
        self._render()

    def setFrame_(self, frame) -> None:
        NSControl.setFrame_(self, frame)
        self._render()

    def _render(self) -> None:
        from fontlabapp.qt.images.view import present

        image = self._image
        if image is None:
            present(self._env.qt, self._qt)
            return
        natural = image.size()
        mode = {
            NSImageScaleProportionallyDown: "down",
            NSImageScaleProportionallyUpOrDown: "fit",
            NSImageScaleAxesIndependently: "stretch",
        }.get(self._scaling, "none")
        present(
            self._env.qt,
            self._qt,
            image.pixmap,
            size=tuple(self._frame.size),
            natural=(0.0, 0.0)
            if mode == "stretch"
            else (natural.width, natural.height),
            mode=mode,
        )


class NSNumberFormatter(NSObject):
    """The range a NIB number formatter declares (``minimum``/``maximum``)."""

    def init(self):
        self._minimum = self._maximum = None
        return self

    def minimum(self):
        return self._minimum

    def setMinimum_(self, value) -> None:
        self._minimum = value

    def maximum(self):
        return self._maximum

    def setMaximum_(self, value) -> None:
        self._maximum = value


CONTROL_CLASSES = (
    NSTextField,
    NSSecureTextField,
    GSSteppingTextField,
    NSButton,
    NSSlider,
    NSPopUpButton,
    NSProgressIndicator,
    NSImageView,
    NSMatrix,
    NSPathControl,
    NSComboBox,
    NSSwitch,
    GSMouseOverButton,
    NSSearchField,
    NSSegmentedControl,
)
