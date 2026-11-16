# this_file: src/fontlab_glyport/model/info_source.py
"""Scoped selected-manager recursion; no process-global data replacement."""

from contextlib import contextmanager
from contextvars import ContextVar

_active_index = ContextVar("glyport_glyph_info_index", default=None)


def current_index():
    return _active_index.get()


@contextmanager
def selected_index(index):
    token = _active_index.set(index)
    try:
        yield index
    finally:
        _active_index.reset(token)
