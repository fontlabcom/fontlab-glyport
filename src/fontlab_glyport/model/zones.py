# this_file: src/fontlab_glyport/model/zones.py
"""Alignment-zone values; live bindings write only through supported backends."""

from .proxies import _Explicit


class GSAlignmentZone(_Explicit):
    def __init__(self, pos=0, size=0):
        self._position, self._size = float(pos), float(size)
        self._read = self._write = None

    def _get(self):
        return self._read() if self._read is not None else (self._position, self._size)

    def _set(self, position, size):
        if self._write is not None:
            self._write(position, size)
        else:
            self._position, self._size = position, size

    position = property(
        lambda self: self._get()[0], lambda self, v: self._set(float(v), self.size)
    )
    size = property(
        lambda self: self._get()[1], lambda self, v: self._set(self.position, float(v))
    )
