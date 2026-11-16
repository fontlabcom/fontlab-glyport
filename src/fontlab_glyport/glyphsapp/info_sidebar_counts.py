# this_file: src/fontlab_glyport/glyphsapp/info_sidebar_counts.py
"""Complete retained list/count/publication control flow over lawful primitives.

Providers implement individual record, Foundation predicate, alert and dispatch
operations. They do not implement list expansion, precedence or publication.
The marked exception scopes are where errors are caught and recovered.
"""

from threading import RLock

from ..model.info_hex import hex_u32
from ..model.production_metadata import _utf16_length
from .info_runtime import InfoError, InfoNativeException, provider_method

_list_problems, _predicate_problems = set(), set()
_list_lock, _predicate_lock = RLock(), RLock()


def _value(provider, info, key):
    return provider_method(provider, "sidebar_info_value")(info, key)


def _name(manager, name):
    return None if manager is None else manager.glyphInfoForName_(name)


def _range_infos(provider, manager, name, result):
    """True consumes a colon token, including a well-formed but reversed range."""
    if ":" not in name:
        return False
    first, last = name.split(":", 1)
    start_info, end_info = _name(manager, first), _name(manager, last)
    start = _value(provider, start_info, "unicode")
    if not start:
        return False
    end = _value(provider, end_info, "unicode")
    if not end:
        return False
    start = provider_method(provider, "sidebar_hex_to_int")(
        _value(provider, start_info, "unicode")
    ) & 0xFFFFFFFF
    if start < 0x10FFFF:
        end = provider_method(provider, "sidebar_hex_to_int")(
            _value(provider, end_info, "unicode")
        ) & 0xFFFFFFFF
        if end < 0x10FFFF and start <= end:
            for code in range(start, end + 1):
                value = None if manager is None else manager.glyphInfoForUnicode_(hex_u32(code))
                if value is None:
                    raise InfoNativeException("Sidebar expanded range contains nil")
                result.append(value)
    return True


def _single_info(provider, manager, name):
    record = _name(manager, name)
    if record is None:
        record = provider_method(provider, "sidebar_new_info")()
        provider_method(provider, "sidebar_set_info_name")(record, name)
    elif _utf16_length(name) > 1 and name[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
        stored_name = _value(provider, record, "name")
        if stored_name != name:
            if _value(provider, record, "locked"):
                record = provider_method(provider, "sidebar_copy_info")(record)
            provider_method(provider, "sidebar_set_info_name")(record, name)
    return record


def _invalid_list(item):
    with _list_lock:
        if item.name not in _list_problems:
            if item.name is None:
                raise InfoNativeException("Sidebar problem-name set contains nil")
            _list_problems.add(item.name)
            message = provider_method(item._provider, "localize")("Invalid glyph list in sidebar item: %@")
            provider_method(item._provider, "show_modal_alert")(
                message.replace("%@", "(null)" if item.displayName is None else item.displayName)
            )
    item.coverage = None


def expand_names(item, manager):
    """Keep the original enumerator after clearing malformed coverage storage."""
    result = []
    coverage = item.coverage
    for name in coverage if coverage is not None else ():
        if not isinstance(name, str):
            _invalid_list(item)
        elif not _range_infos(item._provider, manager, name, result):
            record = _single_info(item._provider, manager, name)
            if record is None:
                raise InfoNativeException("Sidebar expanded name contains nil")
            result.append(record)
    item.infos = result if result else None


class SidebarCountError(InfoError):
    """Source count-error description plus retained failing predicate format."""

    def __init__(self, message, reason):
        super().__init__("GSGlyphsDomain", 992, message)
        self.reason = reason

    def localizedFailureReason(self):
        return self.reason


def _predicate_failure(item):
    predicate = item.predicate
    reason = predicate.predicateFormat
    if callable(reason):
        reason = reason()
    with _predicate_lock:
        if reason not in _predicate_problems:
            if reason is None:
                raise InfoNativeException("Sidebar failing-predicate set contains nil")
            _predicate_problems.add(reason)
            message = provider_method(item._provider, "localize")("Invalid filter in sidebar: %@")
            message = message.replace("%@", "(null)" if item.displayName is None else item.displayName)
            provider_method(item._provider, "present_error")(SidebarCountError(message, reason))


def _base_counts(item, font, glyphs):
    provider = item._provider
    if item.infos is not None and len(item.infos):
        count = provider_method(provider, "sidebar_count_infos")(font, item.infos)
        expected = sum(_value(provider, info, "type") == 0 for info in item.infos)
        return count, expected
    if item.predicate is not None:
        try:
            count = provider_method(provider, "count_matching_predicate")(glyphs, item.predicate)
        except InfoNativeException:
            _predicate_failure(item)
            return -2, -2
        return count, -2
    if item.codes is not None and len(item.codes):
        return provider_method(provider, "sidebar_count_codes")(font, item.codes), len(item.codes)
    return -2, -2


def _smallcaps_counts(item, font, glyphs, count, expected):
    provider = item._provider
    try:
        predicate = provider_method(provider, "compile_predicate")(
            "(case == 2) AND NOT (name contains '.0') AND (export == True)"
        )
        sources = provider_method(provider, "filter_using_predicate")(glyphs, predicate)
        expected = len(sources) if sources is not None else 0
        infos = []
        manager = font.glyphsInfo()
        for glyph in sources if sources is not None else ():
            name = _value(provider, glyph, "name")
            record = _name(manager, None if name is None else name + ".sc")
            if record is not None:
                infos.append(record)
        predicate = provider_method(provider, "compile_predicate")("case == 3")
        current = provider_method(provider, "filter_using_predicate")(glyphs, predicate)
        count = len(current) if current is not None else 0
        item.infos = infos
    except InfoNativeException as error:
        provider_method(provider, "log")("Error computing Smallcaps count: " + str(error))
    return count, expected


def update_count(item, font):
    if font is None:
        return
    provider_method(item._provider, "dispatch_main")(lambda: item.setBadgeString_("✓"))
    glyphs = provider_method(item._provider, "sidebar_font_all_glyphs")(font)
    with item._item_lock:
        count, expected = _base_counts(item, font, glyphs)
        if item.identifier == "Smallcaps":
            count, expected = _smallcaps_counts(item, font, glyphs, count, expected)
    provider_method(item._provider, "dispatch_main")(
        lambda: item._publish_count(count, expected)
    )


def publish_count(item, count, expected):
    """KVO wraps changed numbers; badges and calculating update on every publish."""
    if item.count != count or item.shallHaveCount != expected:
        notify = provider_method(item._provider, "notify")
        notify(item, "will", "hasShallHaveCount")
        item.shallHaveCount, item.count = expected, count
        notify(item, "did", "hasShallHaveCount")
    if expected > 0:
        badge = "✓" if count == expected else f"{count}/{expected}"
    else:
        badge = str(count) if item.isLeaf() and count >= 0 else None
    item.setBadgeString_(badge)
    item.setIsCalculating_(False)
