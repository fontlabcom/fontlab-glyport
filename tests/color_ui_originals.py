# this_file: tests/color_ui_originals.py
# SPDX-License-Identifier: Apache-2.0
"""Exact original owned Glyport color methods from reviewed dev40; no corpus code."""
# Retain the donor methods' own relative-import resolution.
__package__ = "fontlab_glyport.ui"

def _rgba_css(color) -> str:
    r, g, b, a = (round(v * 255) for v in color.rgba)
    return f"rgba({r}, {g}, {b}, {a})"

def Box___style_box(self, fill, border, width, radius) -> None:
    """vanilla's custom box: NSColor fill/border, width and radius as a
    QGroupBox style sheet (only when any is given)."""
    rules = []
    if fill is not None:
        rules.append(f"background-color: {_rgba_css(fill)};")
    if border is not None:
        rules.append(f"border: {round(width or 1)}px solid {_rgba_css(border)};")
    if radius is not None:
        rules.append(f"border-radius: {round(radius)}px;")
    if rules:
        self._view.setStyleSheet("QGroupBox { " + " ".join(rules) + " }")

def ColorWell___rgba255(self) -> tuple[int, int, int, int]:
    return tuple(round(v * 255) for v in self._color.rgba)

def ColorWell__set(self, color) -> None:
    self._color = color
    r, g, b, a = self._rgba255()
    self._view.setStyleSheet(f"background-color: rgba({r}, {g}, {b}, {a});")

def ColorWell___pick(self) -> None:
    if self._dialog is not None:
        return
    qtgui = self._env.qt.QtGui
    dialog = qtgui.QColorDialog(qtgui.QColor(*self._rgba255()), self._view)
    self._dialog = dialog
    self._track(dialog.colorSelected, self._picked)
    dialog.open()

def ColorWell___picked(self, qcolor) -> None:
    from ..drawing.cocoa_drawing import NSColor

    self.set(
        NSColor(qcolor.redF(), qcolor.greenF(), qcolor.blueF(), qcolor.alphaF())
    )
    if self._callback is not None and not self._quiet:
        self._env.report(self._callback, self)

def NSTextField__setBackgroundColor_(self, color):
    from .application_windows import qt_value

    palette_class = self._env.qt.QtGui.QPalette
    palette = palette_class() if color is None else qt_value(self._qt, "palette")
    if color is not None:
        role = palette_class.Window if self._label else palette_class.Base
        palette.setColor(role, color.qcolor(self._env.qt))
    if self._label:
        self._qt.setAutoFillBackground(color is not None)
    self._qt.setPalette(palette)

def NSTextField__setTextColor_(self, color):
    from .application_windows import qt_value

    palette_class = self._env.qt.QtGui.QPalette
    if color is None:
        palette = palette_class()
    else:
        palette = qt_value(self._qt, "palette")
        role = palette_class.WindowText if self._label else palette_class.Text
        palette.setColor(role, color.qcolor(self._env.qt))
    self._qt.setPalette(palette)
    self._text_color = color
