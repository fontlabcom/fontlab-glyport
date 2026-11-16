# this_file: src/fontlab_glyport/glyphsapp/info_sidebar_resources.py
"""Connect retained sidebar transforms to explicit resource/file dependencies.

Initialization queues itself, then builds the trees; class resource caches
are filled once per process, including nil results. No private payload or English localization fallback.
"""

from functools import cmp_to_key
from posixpath import join
from threading import RLock

from .info_runtime import provider_method, state_for, using_info_provider
from .info_sidebar import SidebarItem, merge_groups, process_groups

_once_arrays = {}
_once_lock = RLock()


def default_array(provider, name):
    """Preserve process-once array identity, including a decoded nil value."""
    with _once_lock:
        if name not in _once_arrays:
            url = provider_method(provider, "resource_url")(name, "plist")
            _once_arrays[name] = provider_method(provider, "load_array")(url)
    return _once_arrays[name]


def header(provider, identifier, title):
    item = SidebarItem()
    item._provider = provider
    item.identifier = identifier
    item.name = provider_method(provider, "localize")(title)
    return item


def initialize_sidebar(manager):
    """Allocate persistent maps only if nil; enqueue the actual tree builder."""
    state = state_for(manager)
    if state.name2Group is None:
        state.name2Group = {}
    if state.sidebarCategories is None:
        state.sidebarCategories = []
    state.allItem = header(state.provider, "All", "All")
    state.allItem.iconName, state.allItem.cell = "LibraryTemplate", "ImageTextCell"
    state.queue.addOperationWithBlock_(lambda: build_sidebar(manager))


def build_sidebar(manager):
    state = state_for(manager)
    provider = state.provider
    # Languages' once block precedes category construction in the retained body.
    languages = default_array(provider, "defaultLanguages")
    state.categoriesGroup = header(provider, "CATEGORIES", "Categories")
    with using_info_provider(provider):
        categories = type(manager).defaultCategoriesDicts()
    state.categoriesGroup.setSubItems_(
        process_groups(state, categories, None, 1, provider)
    )
    state.languagesGroup = header(provider, "LANGUAGES", "Languages")
    rows = process_groups(state, languages, None, 2, provider)
    compare = provider_method(provider, "compare")
    rows.sort(key=cmp_to_key(lambda left, right: compare(left.name, right.name)))
    state.languagesGroup.setSubItems_(list(rows))
    for support in provider_method(provider, "application_support_paths")():
        manager.loadCustomGroupsFromFolder_(join(support, "Info"))
    if state.subCategoryOrder is None:
        manager._loadSubcategories()
    state.sidebarCategories.extend(["Corner", "SmartGlyph"])
    state.filterGroups = manager.loadCustomFilterGroups()


def load_groups_folder(manager, folder):
    """A malformed plist stops this folder, preserving earlier mutations."""
    state = state_for(manager)
    provider = state.provider
    names = provider_method(provider, "directory_entries")(folder)
    for name in names if names is not None else ():
        if not (name.startswith("Groups") and name.endswith(".plist")):
            continue
        path = provider_method(provider, "resolve_path")(join(folder, name))
        data, error = provider_method(provider, "load_property_list")(path)
        if data is None:
            provider_method(provider, "schedule")(
                0.1,
                lambda error=error: provider_method(provider, "present_error")(error),
            )
            return
        for key, destination in (
            ("categories", state.categoriesGroup),
            ("languages", state.languagesGroup),
        ):
            groups = data.get(key)
            if groups is not None:
                # Actual group processing occurs even with a nil destination.
                rows = destination.subItems if destination is not None else None
                merge_groups(state, groups, rows, provider)
