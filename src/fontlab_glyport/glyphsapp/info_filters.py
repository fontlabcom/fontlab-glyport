# this_file: src/fontlab_glyport/glyphsapp/info_filters.py
"""Retained primary/fallback and ordered extra-filter file loading."""

from posixpath import join, splitext

from .info_runtime import provider_method, state_for
from .info_sidebar import SidebarItem, process_groups
from .info_sidebar_resources import header


def _array_at(provider, path):
    value, _ = provider_method(provider, "load_property_list")(path)
    return value if isinstance(value, list) else None


def extra_filters(manager, folder):
    state = state_for(manager)
    provider = state.provider
    names = provider_method(provider, "directory_entries")(folder)
    primary = join(
        provider_method(provider, "user_support_path")(), "CustomFilter.plist"
    )
    result = []
    for name in names if names is not None else ():
        original = join(folder, name)
        if original == primary or not (
            name.startswith("CustomFilter") and name.endswith(".plist")
        ):
            continue
        resolved = provider_method(provider, "resolve_path")(original)
        data = _array_at(provider, resolved)
        if data is None:
            continue
        title = provider_method(provider, "trim_whitespace")(splitext(name)[0][12:])
        item = SidebarItem()
        item._provider = provider
        item.identifier = "FILTERS_FILE"
        # Extra titles are raw filenames; no localization request occurs here.
        item.name = title or "Custom"
        item.setSubItems_(process_groups(state, data, None, 3, provider))
        item.setEditable_(True)
        item.filePath = resolved
        result.append(item)
    return result


def load_filters(manager):
    state = state_for(manager)
    provider = state.provider
    primary = join(
        provider_method(provider, "user_support_path")(), "CustomFilter.plist"
    )
    rows = _array_at(provider, primary)
    if rows is None:
        url = provider_method(provider, "resource_url")("StandardFilter", "plist")
        if url is None:
            provider_method(provider, "log")(
                "Missing StandardFilter.plist resource URL"
            )
            return None
        rows = provider_method(provider, "load_array")(url)
    item = header(provider, "FILTERS", "Filters")
    item.setSubItems_(process_groups(state, rows, None, 3, provider))
    item.setEditable_(True)
    result = [item]
    for support in provider_method(provider, "application_support_paths")():
        result.extend(manager._loadCustomFilterGroupForPath_(support))
        result.extend(manager._loadCustomFilterGroupForPath_(join(support, "Filters")))
    if state.localURL is not None:
        result.extend(manager._loadCustomFilterGroupForPath_(state.localURL.path()))
    return result
