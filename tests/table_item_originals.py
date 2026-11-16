# this_file: tests/table_item_originals.py
# SPDX-License-Identifier: Apache-2.0
"""Exact reviewed dev39 methods retained as complete behavioral oracles."""
from typing import Any


def _cell_text(value):
    return "" if value is None else str(value)

def nstableview__place_item(self, row: int, index: int, value, editable: bool) -> None:
        qt = self._env.qt
        item = qt.QtGui.QTableWidgetItem("" if value is None else str(value))
        flags = qt.QtCore.Qt.ItemIsSelectable | qt.QtCore.Qt.ItemIsEnabled
        item.setFlags(flags | qt.QtCore.Qt.ItemIsEditable if editable else flags)
        self._qt.setItem(row, index, item)

def list__flags(self, editable: bool) -> Any:
        qt = self._env.qt.QtCore.Qt
        flags = qt.ItemIsSelectable | qt.ItemIsEnabled
        return flags | qt.ItemIsEditable if editable else flags

def list__fill_row(self, row: int) -> None:
        gui, item = self._env.qt.QtGui, self._items[row]
        for index, column in enumerate(self._columns):
            cell = gui.QTableWidgetItem(
                column.cell_title
                if column.checkbox
                else _cell_text(item.get(column.key))
            )
            flags = self._flags(column.editable and not column.checkbox)
            if column.checkbox:
                qt = self._env.qt.QtCore.Qt
                if column.editable:
                    flags |= qt.ItemIsUserCheckable
                cell.setCheckState(qt.Checked if item.get(column.key) else qt.Unchecked)
            cell.setFlags(flags)
            self._view.setItem(row, index, cell)

