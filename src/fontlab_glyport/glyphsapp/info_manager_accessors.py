# this_file: src/fontlab_glyport/glyphsapp/info_manager_accessors.py
"""Manager accessors and lazy ranks over the actual owned state graph.

Accessors synchronize on a captured cache object but reread the current field.
They also rebuild unconditionally after an outer nil observation. These choices
are intentional. Python locks/containers qualify owned graphs, not Foundation
key copying, fast-enumeration mutation detection, NSNumber or bridge ABI parity.
"""

from contextlib import nullcontext
from threading import RLock

from ..errors import UnsupportedCapability
from .info_runtime import state_for

_NS_NOT_FOUND = 2**63 - 1
_UINT64_MASK = 2**64 - 1
_TERMINAL_CATEGORIES = ("Icon", "SF-Symbol", "Private Use", "Corner")


class _RankCache(dict):
    """One owned dictionary and its own source-object synchronization monitor."""

    def __init__(self):
        super().__init__()
        self.monitor = RLock()


def _int32(value):
    return ((value + 2**31) % 2**32) - 2**31


def _key(value):
    if value is None:
        raise UnsupportedCapability(
            "Native nil dictionary key behavior is unqualified",
            capability="GSGlyphsInfo.rank.key",
        )
    return value


def _lookup(mapping, key):
    return None if mapping is None else mapping.get(_key(key))


def _build_rank(state, field, rows_field, terminals):
    cache = _RankCache()
    rows = getattr(state, rows_field)
    if rows is not None:
        len(rows)  # Source count/capacity precedes publication and enumeration.
    setattr(state, field, cache)
    rows = getattr(state, rows_field)
    index = 0
    for key in rows if rows is not None else ():
        current = getattr(state, field)
        if current is not None:
            current[_key(key)] = index
        index = _int32(index + 1)
    for offset, key in enumerate(terminals):
        current = getattr(state, field)
        if current is not None:
            current[key] = _int32(index + offset)


def _rank(manager, key, field, rows_field, terminals=()):
    state = state_for(manager)
    captured = getattr(state, field)
    if captured is None:
        with state.monitor:
            _build_rank(state, field, rows_field, terminals)
        captured = getattr(state, field)
    with nullcontext() if captured is None else captured.monitor:
        value = _lookup(getattr(state, field), key)
    return _NS_NOT_FOUND if value is None else _int32(value) & _UINT64_MASK


class ManagerAccessors:
    """Source-derived accessors share the existing manager state graph."""

    def glyphInfos(self):
        return state_for(self).index.records

    def setGlyphInfos_(self, value):
        state_for(self).index.records = value

    def scriptIDs(self):
        return state_for(self).scriptIDs

    def name2Info(self):
        return state_for(self).index.names

    def unicode2Info(self):
        return state_for(self).index.unicodes

    def sidebarCategories(self):
        return state_for(self).sidebarCategories

    def languagesGroup(self):
        return state_for(self).languagesGroup

    def setLanguagesGroup_(self, value):
        state_for(self).languagesGroup = value

    def categories(self):
        return state_for(self).categories

    def subCategories(self):
        return state_for(self).subCategories

    def iMatraCombinations(self):
        return state_for(self).iMatraCombinations

    def allItem(self):
        return state_for(self).allItem

    def setAllItem_(self, value):
        state_for(self).allItem = value

    def categoriesGroup(self):
        return state_for(self).categoriesGroup

    def setCategoriesGroup_(self, value):
        state_for(self).categoriesGroup = value

    def filterGroups(self):
        return state_for(self).filterGroups

    def setFilterGroups_(self, value):
        state_for(self).filterGroups = value

    def _subcategoriesForSidebarCategory_(self, category):
        if category is None:
            return None
        return _lookup(state_for(self).subCategoryOrder, category)

    def indexOfObjectInScripts_(self, key):
        return _rank(self, key, "scriptOrder", "scriptIDs")

    def indexOfObjectInCategories_(self, key):
        return _rank(
            self, key, "categoryOrder", "sidebarCategories", _TERMINAL_CATEGORIES
        )
