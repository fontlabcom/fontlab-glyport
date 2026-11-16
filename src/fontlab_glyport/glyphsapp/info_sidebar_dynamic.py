# this_file: src/fontlab_glyport/glyphsapp/info_sidebar_dynamic.py
"""Retained dynamic group bodies, over explicit Foundation primitive adapters.

GlyphsCore 4108: 2337d0/23488c/234cfc/237904/237be8. No default private
resources, native predicate engine, defaults or count scheduler is fabricated.
"""

from functools import cmp_to_key
from threading import RLock

from ..errors import UnsupportedCapability
from .info_runtime import (
    provider_method,
    require_provider,
    state_for,
    using_info_provider,
)
from .info_sidebar import SidebarItem

_mapping_lock = RLock()
_mapping_ready = False
_category_mapping = None


def _read(value, name):
    """Bridge qualified zero-argument selectors or properties; nil sends nil."""
    if value is None:
        return None
    result = getattr(value, name)
    return result() if callable(result) else result


def _plain(provider):
    item = SidebarItem()
    item._provider = provider
    return item


def _script_fragment(pattern):
    """Preserve NSString's exact (11,length-12) UTF-16 range, including errors."""
    raw = pattern.encode("utf-16-le", "surrogatepass")
    length = len(raw) // 2 - 12
    if length < 0 or 11 + length > len(raw) // 2:
        raise ValueError("script predicate UTF-16 range is out of bounds")
    return raw[22 : 22 + length * 2].decode("utf-16-le", "surrogatepass")


def filter_group(manager, group, font):
    """Shallow projection; selected original children are actually reparented."""
    provider = state_for(manager).provider
    result = []
    font.lockReadGlyphs()
    values = _read(font, "glyphs").valueForKey_("script")
    scripts = provider_method(provider, "set_from_array")(values)
    font.unlockReadGlyphs()
    children = _read(group, "subItems")
    for child in children if children is not None else ():
        if not _read(child, "hidden"):
            result.append(child)
            continue
        predicate = _read(child, "predicate")
        if predicate is None:
            continue
        pattern = _read(predicate, "predicateFormat")
        if pattern is not None and not isinstance(pattern, str):
            raise UnsupportedCapability("Unqualified sidebar predicate format string")
        if (
            pattern is not None
            and pattern.startswith("script == ")
            and " OR " not in pattern
        ):
            count = _script_fragment(pattern) in scripts
        else:
            font.lockReadGlyphs()
            count = _read(font, "glyphs").countOfObjectsWithOptions_matchingPredicate_(
                1, predicate
            )
            font.unlockReadGlyphs()
        if count:
            result.append(child)
    if not result:
        return None
    # Retained body reads the original child array again for its final count.
    current = _read(group, "subItems")
    if len(result) == (0 if current is None else len(current)):
        return group
    projected = _plain(provider)
    for field, setter in (
        ("name", "setName_"),
        ("identifier", "setIdentifier_"),
        ("coverage", "setCoverage_"),
        ("iconName", "setIconName_"),
        ("predicate", "setPredicate_"),
        ("preset", "setPreset_"),
        ("itemType", "setItemType_"),
    ):
        getattr(projected, setter)(_read(group, field))
    projected.setSubItems_(result)
    return projected


def categories_from_font(manager, font, mapping):
    """Aggregate categories in encounter order, sorting only subcategories."""
    provider = state_for(manager).provider
    categories = {}
    glyphs = _read(font, "glyphs")
    for glyph in glyphs if glyphs is not None else ():
        category = _read(glyph, "category")
        key = "" if category is None else category
        subcategories = categories.setdefault(key, set())
        subcategory = _read(glyph, "subCategory")
        if subcategory is not None and len(subcategory):
            subcategories.add(subcategory)
    result = []
    for category, subcategories in categories.items():
        item = _plain(provider)
        compile_predicate = provider_method(provider, "compile_predicate")
        if category == "":
            name = "Other"
            predicate = compile_predicate("category == NULL")
        else:
            name = category
            predicate = compile_predicate("category == %@", category)
        item.setPredicate_(predicate)
        item.setName_(name)
        item.setIdentifier_(name)
        icon = None if mapping is None else mapping.get(name)
        item.setIconName_(name if icon is None else icon)
        item.setCellType_("ImageTextCell")
        if subcategories:
            children = []
            compare = provider_method(provider, "compare")
            for subcategory in sorted(subcategories, key=cmp_to_key(compare)):
                child = _plain(provider)
                child.setName_(subcategory)
                child.setIdentifier_(subcategory)
                if category == "":
                    predicate = compile_predicate(
                        "category == NULL AND subCategory == %@", subcategory
                    )
                else:
                    predicate = compile_predicate(
                        "category == %@ AND subCategory == %@", category, subcategory
                    )
                child.setPredicate_(predicate)
                child.setCellType_("ImageTextCell")
                children.append(child)
            item.setSubItems_(children)
        result.append(item)
    return result


def category_mapping(receiver):
    """Process-once mutable dictionary; first receiver and nil result persist."""
    global _mapping_ready, _category_mapping
    with _mapping_lock:
        if not _mapping_ready:
            provider = require_provider()
            url = provider_method(provider, "resource_url")("category2Icon", "plist")
            _category_mapping = provider_method(provider, "load_dictionary")(url)
            rows = receiver.defaultCategoriesDicts()
            for attributes in rows if rows is not None else ():
                name, icon = attributes.get("name"), attributes.get("icon")
                if (
                    name is not None and len(name) and icon is not None and len(icon)
                    and _category_mapping is not None
                ):
                    _category_mapping[name] = icon
            _mapping_ready = True
        return _category_mapping


def groups_tree(manager, font):
    """Build the current ordered tree; no final cache, sort or queue wait."""
    provider = state_for(manager).provider
    if font.fontType() == 3:
        manager.setCategoriesGroup_(_plain(provider))
        manager.categoriesGroup().setIdentifier_("CATEGORIES")
        title = provider_method(provider, "localize")("Categories")
        manager.categoriesGroup().setName_(title)
        with using_info_provider(provider):
            mapping = type(manager).categoryToIconMapping()
        rows = manager.categoriesFromFont_categoryToIconMapping_(font, mapping)
        manager.categoriesGroup().setSubItems_(rows)
    # NSArray varargs stop at the first nil; accessors are still both read.
    all_item, categories = manager.allItem(), manager.categoriesGroup()
    result = []
    for item in (all_item, categories):
        if item is None:
            break
        result.append(item)
    if font.fontType() != 3:
        languages = manager.filterGroup_forFont_(manager.languagesGroup(), font)
        if languages is not None:
            result.append(languages)
    tags = _read(font, "allTags")
    if tags is not None and len(tags):
        item = _plain(provider)
        item.setIdentifier_("TAGS")
        item.setName_(provider_method(provider, "localize")("Tags"))
        item.setCoverage_(_read(font, "allTags"))
        item.setCellType_("TagsCell")
        result.append(item)
    filters = manager.filterGroups()
    if filters is None:
        # The retained body still sends addObjectsFromArray:nil. Its native
        # class-cluster policy is not inferred from Python's empty iteration.
        provider_method(provider, "array_add_objects")(result, None)
    else:
        result.extend(filters)
    return result
