# this_file: src/fontlab_glyport/model/revisions.py
"""Mutation-counted dictionaries for the handwritten fake backend."""


class RevisionDict(dict):
    def __init__(self, values, changed):
        super().__init__(values)
        self.changed = changed

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.changed()

    def __delitem__(self, key):
        super().__delitem__(key)
        self.changed()

    def pop(self, key, *default):
        exists = key in self
        result = super().pop(key, *default)
        if exists:
            self.changed()
        return result

    def clear(self):
        if self:
            super().clear()
            self.changed()

    def update(self, *args, **kw):
        for key, value in dict(*args, **kw).items():
            self[key] = value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def __ior__(self, other):
        self.update(other)
        return self
