# this_file: src/fontlab_glyport/plugins/registry.py
"""Loaded glyport filters shared by script/plugin sessions, without owning them."""

from weakref import WeakValueDictionary

FILTERS = WeakValueDictionary()
