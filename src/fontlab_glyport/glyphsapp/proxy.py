# this_file: src/fontlab_glyport/glyphsapp/proxy.py
"""Subclassable legacy SDK Proxy base for user-defined sequence views."""

from copy import deepcopy

from ..ui.cocoa import unsupported


class Proxy:
    def __init__(self, owner):
        self._owner = owner

    def values(self):
        raise unsupported("GlyphsApp.Proxy.values")

    def __len__(self):
        return len(self.values() or ())

    def __iter__(self):
        return iter(self.values() or ())

    def __getitem__(self, index):
        return self.values()[index]

    def index(self, value):
        return list(self).index(value)

    def pop(self, index=-1):
        value = self[index]
        del self[index]
        return value

    def __copy__(self):
        return list(self)

    def __deepcopy__(self, memo):
        return [deepcopy(value, memo) for value in self]
