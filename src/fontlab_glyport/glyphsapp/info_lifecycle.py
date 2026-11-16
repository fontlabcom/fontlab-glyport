# this_file: src/fontlab_glyport/glyphsapp/info_lifecycle.py
"""Constructor, load and summary control flow over explicit dependencies.

Errors are recovered only around component finalization and the Hangul
enqueue. The constructor does not drain the queue on failure.
"""

from functools import cmp_to_key
from posixpath import join

from .info_runtime import (
    InfoErrorSlot,
    InfoNativeException,
    InfoState,
    error_slot,
    provider_method,
    require_provider,
    state_for,
)

_CATEGORIES = (
    "Letter",
    "Number",
    "Punctuation",
    "Separator",
    "Symbol",
    "Mark",
    "Icon",
    "SF-Symbol",
    "Corner",
)


def initialize_local(manager, url, document):
    """Use the allocated receiver directly, retaining its existing shared flag."""
    provider = require_provider()
    from .info_manager import GSGlyphsInfo

    if not isinstance(manager, GSGlyphsInfo):
        raise TypeError(
            "Local Glyph Info initialization requires a GSGlyphsInfo receiver"
        )
    previous = vars(manager).get("_lifecycle")
    state = (
        previous
        if previous is not None
        else InfoState(
            provider, url, bool(vars(manager).get("_shared_info_flag", False))
        )
    )
    state.localURL = url
    state.provider = provider
    state.queue = provider.new_queue()
    state.queue.setMaxConcurrentOperationCount_(provider.active_processor_count())
    manager._lifecycle = state
    manager._fixed_index = state.index
    manager.loadSidebarInfoForDocument_(document)
    manager.loadGlyphInfo()
    state.queue.waitUntilAllOperationsAreFinished()
    return manager


def summarize(manager):
    """Read current rows separately for each KVC union; preserve existing repeats."""
    state = state_for(manager)
    for field, target in (("script", "scriptIDs"), ("subCategory", "subCategories")):
        rows = state.index.records
        values = []
        if any(getattr(row, field) is None for row in rows):
            # The Foundation collection operator's nil policy is not inferred.
            values = provider_method(state.provider, "distinct_values")(rows, field)
        else:
            for row in rows:
                value = getattr(row, field)
                if value not in values:
                    values.append(value)
        for value in sorted(values, key=cmp_to_key(state.provider.compare)):
            current = getattr(state, target)
            if current is not None and value not in current:
                getattr(state, target).append(value)
    current = state.subCategories
    if current is not None and "Conjunct" not in current:
        position = (
            current.index("Halfform") + 1 if "Halfform" in current else len(current)
        )
        current.insert(position, "Conjunct")
    for target in ("scriptIDs", "categories", "subCategories"):
        current = getattr(state, target)
        if current is not None:
            current[:] = [value for value in current if value != ""]


def load_info(manager):
    """Reset listed rows, continue on false BOOL, retain precise exception range."""
    state = state_for(manager)
    if state.scriptIDs is None:
        state.scriptIDs = ["latin", "cyrillic", "greek"]
    state.categories = list(_CATEGORIES)
    state.subCategories = ["Other", "Nonspacing", "Spacing"]
    if state.localURL is not None:
        manager.willChangeValueForKey_("glyphInfos")
    state.index.records = []
    slot = InfoErrorSlot()
    success = manager.loadGlyphDataError_(slot)
    if not success and slot.value is not None:
        state.provider.present_error(slot.value)
    if state.localURL is not None:
        from .info_manager import GSGlyphsInfo

        shared = GSGlyphsInfo.sharedManager()
        if shared is not manager:
            shared_state = state_for(shared)
            state.index.shared = shared_state.index
            state.scriptIDs.extend(shared_state.scriptIDs or ())
            state.subCategories.extend(shared_state.subCategories or ())
    state.queue.addOperationWithBlock_(lambda: summarize(manager))
    if state.localURL is None:
        manager._addChineseGlyphInfos()
    try:
        manager.updateComponentsInfos()
        if state.localURL is None:
            manager._addHangulGlyphInfos()
    except InfoNativeException as error:
        state.provider.log(error)
    for index, row in enumerate(state.index.records):
        row.index = index & 0xFFFFFFFF
    if state.localURL is None:
        manager.didChangeValueForKey_("glyphInfos")
    url = state.provider.resource_url("iMatraPresCombination", "plist")
    state.iMatraCombinations = state.provider.load_dictionary(url)


def load_data(manager, error):
    """Data discovery differs for nonnil local URLs and the global bundle path."""
    state = state_for(manager)
    if state.index.names is None:
        state.index.names = {}
    if state.index.unicodes is None:
        state.index.unicodes = {}
    error_slot(error)
    if state.localURL is not None:
        path = state.localURL.path()
        if path is None:
            return False
        folders = type(manager).foldersForCustomInfoForFolder_(path)
        urls = type(manager).findLocalGlyphInfoFolders_(folders)
        if not manager.loadLocalGlyphInfoFiles_error_(urls, error):
            return False
        for folder in folders:
            manager.loadCustomIcons_(join(folder, "Icons"))
            manager.loadCustomGroupsFromFolder_(folder)
        return True
    url = state.provider.resource_url("GlyphData", "xml")
    if url is None:
        state.provider.log("Missing GlyphData.xml resource URL")
        return False
    if not manager.loadGlyphDataFromURL_error_(url, error):
        return False
    for support in state.provider.application_support_paths():
        urls = type(manager).findLocalGlyphInfoFolders_([join(support, "Info")])
        if not manager.loadLocalGlyphInfoFiles_error_(urls, error):
            return False
    manager.loadCustomIcons()
    return True


def load_base(manager, url, error):
    """Parse privately, then ordered commits; a success never clears an error slot."""
    from ..model.base_info_parser import commit_base, parse_base_file
    from .info_loading import _url_path

    state = state_for(manager)
    slot = error_slot(error)
    result = parse_base_file(_url_path(url))
    if not result.success:
        if slot is not None:
            slot.value = result.error
        return False
    return commit_base(state.index, state.name2Group, result)
