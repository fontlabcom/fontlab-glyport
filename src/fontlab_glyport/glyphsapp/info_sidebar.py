# this_file: src/fontlab_glyport/glyphsapp/info_sidebar.py
"""Retained sidebar transforms over explicit lawful providers and owned rows.

No predicate grammar, Cocoa image registry, counter UI or private data is implied.
The provider's InfoNativeException marks the qualified compilation analogue only.
"""

from functools import cmp_to_key
from threading import RLock

from ..errors import UnsupportedCapability
from .defaults import as_bool
from .info_runtime import InfoError, InfoNativeException
from .info_sidebar_support import SidebarSupport


def _bool_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return as_bool(value)
    method = getattr(value, "boolValue", None)
    if callable(method):
        return method()
    raise UnsupportedCapability("Unqualified sidebar boolValue input")


def _append_unique(array, value):
    if array is not None and value is not None and value not in array:
        array.append(value)


def _group_key(parent, identifier, provider):
    append = getattr(provider, "append_path_component", None)
    if append is not None:
        return append(parent, identifier)
    if (
        not isinstance(identifier, str)
        or "/" in identifier
        or identifier in (".", "..")
    ):
        raise UnsupportedCapability("Unqualified sidebar path component")
    return parent + "/" + identifier if identifier else parent


class SidebarItem(SidebarSupport):
    """Source item fields; constructor dictionaries retain their raw payloads."""

    def __init__(self):
        self.name = self.identifier = self.iconName = self.predicate = None
        self.coverage = self.codes = self.subItems = self.parent = None
        self.predicateFormat = self.badgeString = self._icon = None
        self.suppressCount = self.default = self.editable = self.calculating = False
        self.itemType, self.count, self.shallHaveCount = 0, -1, -1
        self.cell, self._provider = "HeaderCell", None
        self.infos = self.missingInfos = self.filePath = self.unicharString = None
        self.active = self._badge_visible = self._can_add = False
        self._font_ref, self._item_lock = None, RLock()

    @classmethod
    def from_dict(cls, attributes, provider):
        item = cls()
        item._provider = provider
        raw = attributes.get("name")
        if not isinstance(raw, str):
            raise UnsupportedCapability("Unqualified sidebar name input")
        item.setName_(provider.localize(raw))
        identifier = attributes.get("id")
        item.setIdentifier_(raw if identifier is None else identifier)
        item.setIconName_(attributes.get("icon"))
        predicate = attributes.get("predicate")
        if predicate is not None:
            item._compile(predicate)
        item.coverage, item.codes = attributes.get("list"), attributes.get("codes")
        item.suppressCount = _bool_value(attributes.get("suppressCount"))
        item.default = _bool_value(attributes.get("default"))
        item.cell = "ImageTextCell"
        return item

    def _compile(self, predicate):
        try:
            self.setPredicate_(self._provider.compile_predicate(predicate))
        except InfoNativeException:
            message = self._provider.localize("Invalid filter in sidebar: %@")
            error = InfoError(
                "GSGlyphsDomain", 991, message.replace("%@", self.displayName)
            )
            self.setPredicate_(self._provider.compile_predicate("name == %@", "A"))
            self.count = self.shallHaveCount = -2
            self.badgeString = "🛑"
            self._provider.present_error(error)

    @property
    def displayName(self):
        return self.name

    @displayName.setter
    def displayName(self, value):
        if self.name is None or self.name != value:
            self.name = value
            if self.parent is not None:
                self.parent.didChangeSidebarItem_(self)

    def didChangeSidebarItem_(self, item):
        if self.parent is not None:
            self.parent.didChangeSidebarItem_(self)

    def setSubItems_(self, items):
        self.subItems = items
        for item in items if items is not None else ():
            item.setParent_(self)

    def setEditable_(self, editable):
        self.editable = editable
        for item in self.subItems if self.subItems is not None else ():
            item.setEditable_(editable)

    def setIconName_(self, name):
        self.iconName = name

    def setCoverage_(self, coverage):
        if isinstance(coverage, list):
            self.coverage = coverage
            self.triggerUpdateCount()

    def triggerUpdateCount(self):
        if self.isCalculating() or self.count == -2:
            return
        if self.suppressCount == 1:
            self.setBadgeString_(None)
            return
        self.setIsCalculating_(True)
        scheduler = getattr(self._provider, "schedule_count_update", None)
        if scheduler is None:
            raise UnsupportedCapability("Sidebar count update scheduler is unavailable")
        scheduler(self, 10_000_000)

    @property
    def icon(self):
        if self._icon is not None or self.iconName is None:
            return self._icon
        if self._provider is None:
            raise UnsupportedCapability("Sidebar image provider is unavailable")
        name, compact = self.iconName, self.iconName.replace(" ", "")
        for candidate in (name, compact, name + "Template", compact + "Template"):
            self._icon = self._provider.image_named(candidate)
            if self._icon is not None:
                return self._icon
        from ..model.unicode_casing import lowercase_text

        for candidate in (
            lowercase_text(name).replace(" ", "."),
            "questionmark.circle",
        ):
            self._icon = self._provider.system_symbol(candidate, name)
            if self._icon is not None:
                return self._icon
        self.iconName = None
        return None


def process_groups(state, groups, parent, item_type, provider):
    """Preserve first map identity, duplicate leaves and non-reparenting merges."""
    result = []
    for attributes in groups if groups is not None else ():
        item = SidebarItem.from_dict(attributes, provider)
        result.append(item)
        if (
            item_type == 2
            and parent is None
            and not _bool_value(attributes.get("visible"))
        ):
            provider.register_defaults({"GSSidebarItemHidden_" + item.identifier: True})
        if parent is None:
            key = item.identifier
            _append_unique(state.sidebarCategories, key)
        else:
            key = _group_key(parent, item.identifier, provider)
        existing = state.name2Group.setdefault(key, item)
        if attributes.get("subGroup") is not None:
            children = process_groups(
                state, attributes["subGroup"], key, item_type, provider
            )
            existing = state.name2Group[key]
            if existing is item or item_type == 3:
                item.setSubItems_(children)
            else:
                if existing.subItems is None:
                    existing.setSubItems_(children)
                else:
                    existing.subItems.extend(children)
                result.remove(item)
        _append_unique(state.categories, attributes.get("category"))
        _append_unique(state.subCategories, attributes.get("subCategory"))
        script = attributes.get("script")
        if script is not None and len(script) > 1:
            _append_unique(state.scriptIDs, script)
        item.itemType = item_type
        if item_type == 3 and item.iconName is None:
            item.iconName = (
                "text.alignleft"
                if item.coverage is not None
                else "gearshape"
                if item.predicate is not None
                else "folder"
            )
    return result


def merge_groups(state, groups, destination, provider):
    """Custom groups use type zero and sort only the complete top-level array."""
    if groups is not None:
        for item in process_groups(state, groups, None, 0, provider):
            existing = state.name2Group[item.identifier]
            if item.subItems is None or existing is item:
                if destination is not None:
                    destination.append(item)
            elif existing.subItems is not None:
                existing.subItems.extend(item.subItems)
        if destination is not None:
            destination.sort(
                key=cmp_to_key(
                    lambda a, b: provider.compare(a.displayName, b.displayName)
                )
            )
    return True


def load_subcategories(state):
    """Explicit rebuild; callers decide when a nil rank cache warrants loading."""
    result = {}
    rows = None if state.categoriesGroup is None else state.categoriesGroup.subItems
    for category in rows if rows is not None else ():
        if category.subItems is not None:
            ranks = {
                item.identifier: ((index * 10 + 2**31) % 2**32) - 2**31
                for index, item in enumerate(category.subItems)
            }
            if category.identifier == "Number":
                ranks.update(
                    zip(
                        (
                            "Decimal Digit_LF",
                            "Decimal Digit_OST",
                            "Decimal Digit_TF",
                            "Decimal Digit_TOST",
                        ),
                        (2, 3, 4, 5),
                    )
                )
            result[category.identifier] = ranks
    state.subCategoryOrder = dict(result)
    return state.subCategoryOrder
