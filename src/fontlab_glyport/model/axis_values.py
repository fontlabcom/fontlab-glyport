# this_file: src/fontlab_glyport/model/axis_values.py
"""Fixed-length live master coordinates addressed by axis id or index."""

from collections.abc import Sequence


class AxisValues(Sequence):
    def __init__(self, owner):
        self._owner = owner

    def __len__(self):
        return len(self._owner.axes)

    def _index(self, key):
        if isinstance(key, str):
            for index, axis in enumerate(self._owner._font.axes):
                if axis.axisId == key:
                    return index
            raise KeyError(key)
        return key

    def __getitem__(self, key):
        return self._owner.axes[self._index(key)]

    def __setitem__(self, key, value):
        values = self._owner.axes
        values[self._index(key)] = value
        self._owner.axes = values

    def __eq__(self, other):
        return list(self) == other
