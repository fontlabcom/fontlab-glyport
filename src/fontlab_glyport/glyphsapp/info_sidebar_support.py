# this_file: src/fontlab_glyport/glyphsapp/info_sidebar_support.py
"""Retained SidebarItem state algorithms over explicit primitive providers.

No Foundation defaults, alert, predicate or dispatch implementation is inferred.
Python weak references and an item RLock implement the owned object boundary.
"""

import weakref
from math import floor
from struct import pack, unpack
from threading import RLock

from .info_runtime import InfoNativeException, provider_method, require_provider

_queue_initialized = False
_sidebar_queue = None
_queue_lock = RLock()


class SidebarSupport:
    """Selectors shared by plain and dictionary-created sidebar rows."""

    @classmethod
    def initialize(cls):
        global _queue_initialized, _sidebar_queue
        with _queue_lock:
            if not _queue_initialized:
                provider = require_provider()
                _sidebar_queue = provider_method(provider, "new_queue")()
                cpu = provider_method(provider, "active_processor_count")()
                half = unpack("f", pack("f", cpu / 2))[0]
                _sidebar_queue.setMaxConcurrentOperationCount_(max(2, floor(half + 0.5)))
                _sidebar_queue.setQualityOfService_(17)
                _queue_initialized = True

    def description(self):
        class_name = provider_method(self._provider, "class_name")(self)
        detail = self.predicate
        if detail is None:
            detail = 0 if self.subItems is None else len(self.subItems)
        return provider_method(self._provider, "format_string")(
            "<%@ %p> %@ (%@)", class_name, self, self.name, detail
        )

    def setName_(self, value):
        self.name = value

    def setIdentifier_(self, value):
        self.identifier = value

    def setPredicate_(self, value):
        self.predicate = value

    def setDisplayName_(self, value):
        self.displayName = value

    def setParent_(self, value):
        self.parent = value

    def setCodes_(self, value):
        self.codes = value

    def setFilePath_(self, value):
        self.filePath = value

    def setBadgeString_(self, value):
        self.badgeString = value

    def setUnicharString_(self, value):
        self.unicharString = value

    def setCellType_(self, value):
        self.cell = value

    @property
    def cellType(self):
        return self.cell

    @property
    def preset(self):
        return self.default

    @preset.setter
    def preset(self, value):
        self.default = value

    def setPreset_(self, value):
        self.preset = value

    def setItemType_(self, value):
        self.itemType = value

    def setActive_(self, value):
        self.active = value

    def setIsCalculating_(self, value):
        self.calculating = value

    def isCalculating(self):
        return bool(self.calculating & 1)

    def setSuppressCount_(self, value):
        self.suppressCount = value

    def isSuppressingCount(self):
        return bool(self.suppressCount & 1)

    def setCanAdd_(self, value):
        self._can_add = value

    def canAdd(self):
        return self.identifier in ("LANGUAGES", "FILTERS")

    def isLeaf(self):
        return self.subItems is None or len(self.subItems) == 0

    def hasShallHaveCount(self):
        return self.shallHaveCount > 0 and self.count < self.shallHaveCount

    def setHasShallHaveCount_(self, value):
        pass

    def badgeVisible(self):
        return self._badge_visible

    @classmethod
    def keyPathsForValuesAffectingDisplayName(cls):
        return {"name"}

    def hiddenKey(self):
        return "GSSidebarItemHidden_" + (
            "(null)" if self.identifier is None else self.identifier
        )

    @property
    def hidden(self):
        return provider_method(self._provider, "defaults_bool_for_key")(self.hiddenKey())

    def setHidden_(self, value):
        provider_method(self._provider, "defaults_set_bool_for_key")(value, self.hiddenKey())

    def copyWithZone_(self, zone):
        result = type(self)()
        result._provider = self._provider
        for name in (
            "name", "identifier", "coverage", "codes", "infos", "iconName",
            "predicate", "preset", "itemType", "editable", "suppressCount",
            "cell", "filePath",
        ):
            setattr(result, name, getattr(self, name))
        if self.shallHaveCount == -2:
            result.count, result.shallHaveCount = self.count, self.shallHaveCount
            result.badgeString = self.badgeString
        if self.subItems is not None:
            result.setSubItems_([item.copyWithZone_(zone) for item in self.subItems])
        return result

    def insertObject_inSubItemsAtIndex_(self, item, index):
        if self.subItems is not None:
            if not 0 <= index <= len(self.subItems):
                raise IndexError(index)
            self.subItems.insert(index, item)
        item.setParent_(self)

    def insertSubItems_atIndex_(self, items, index):
        if self.subItems is not None:
            start = index if 0 <= index <= len(self.subItems) else 0
            self.subItems[start:start] = items
        for item in items if items is not None else ():
            item.setParent_(self)

    def removeSubItemsObject_(self, item):
        if self.subItems is not None:
            self.subItems[:] = [value for value in self.subItems if value != item]

    @property
    def font(self):
        return None if self._font_ref is None else self._font_ref()

    def setFont_(self, font):
        with self._item_lock:
            self._font_ref = None if font is None else weakref.ref(font)
            if font is not None:
                self.expandNameList_(font.glyphsInfo())
            self.triggerUpdateCount()
        for item in self.subItems if self.subItems is not None else ():
            item.setFont_(font)

    def _run_count_update(self):
        with self._item_lock:
            font = self.font
        self.updateCount_(font)

    def resetCounter(self):
        if not self.isCalculating() and self.count != -2:
            self.triggerUpdateCount()

    def setPredicateFormat_(self, value):
        if value is None:
            self.setPredicate_(None)
            return
        try:
            predicate = provider_method(self._provider, "compile_predicate")(value)
            self.setPredicate_(predicate)
        except InfoNativeException as error:
            provider_method(self._provider, "dispatch_main")(
                lambda error=error: provider_method(
                    self._provider, "show_exception_alert"
                )(error)
            )

    def expandNameList_(self, manager):
        from .info_sidebar_counts import expand_names

        expand_names(self, manager)

    def updateCount_(self, font):
        from .info_sidebar_counts import update_count

        update_count(self, font)

    def _publish_count(self, count, expected):
        from .info_sidebar_counts import publish_count

        publish_count(self, count, expected)
