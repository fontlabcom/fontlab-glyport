# this_file: src/fontlab_glyport/glyphsapp/info_manager_observation.py
"""Retained observation, lazy font-cache and error/recovery control flow.

All font/defaults/CF/CT/workspace operations require individual lawful provider
primitives. No native framework is imported. The source cache is process-global,
published before row loading and deliberately unsynchronized; invalidation drops
its pointer without CFRelease. Owned objects do not establish CF/CT ABI parity.
"""

from .info_runtime import InfoError, provider_method, require_provider, state_for

_OBSERVER_KEY = "values.GSScriptToPlaceholderFontPath"
_DEFAULTS_KEY = "GSScriptToPlaceholderFontPath"
_script_to_placeholder_font_cache = None


def register_observer(receiver: object) -> None:
    """After the queue drains: test the flag, add, then set the flag."""
    from .info_manager import GSGlyphsInfo

    state = state_for(receiver)
    if state.observer_flag & 1:
        return
    provider_method(state.provider, "add_observer")(
        GSGlyphsInfo._shared, _OBSERVER_KEY, 0, None
    )
    state.observer_flag = 1


def deallocate(receiver: object) -> None:
    """Explicit dealloc dispatch; the provider owns the superclass primitive."""
    from .info_manager import GSGlyphsInfo

    state = vars(receiver).get("_lifecycle")
    provider = state.provider if state is not None else require_provider()
    if state is not None and state.observer_flag == 1:
        provider_method(provider, "remove_observer")(
            GSGlyphsInfo._shared, _OBSERVER_KEY
        )
        state.observer_flag = 0
    provider_method(provider, "super_dealloc")(receiver)


def _indexed_value(row: object, index: int) -> object:
    """Owned arrays or an explicit objectAtIndexedSubscript: analogue; nil stays nil."""
    if row is None:
        return None
    method = getattr(row, "objectAtIndexedSubscript_", None)
    return method(index) if callable(method) else row[index]


def _build_cache(provider: object) -> None:
    """Publish first, then load every ordered [script, path] row."""
    global _script_to_placeholder_font_cache

    rows = provider_method(provider, "defaults_object_for_key")(_DEFAULTS_KEY)
    capacity = 0 if rows is None else len(rows)
    _script_to_placeholder_font_cache = provider_method(
        provider, "cf_dictionary_create_mutable"
    )(
        None,
        capacity,
        "kCFTypeDictionaryKeyCallBacks",
        "kCFTypeDictionaryValueCallBacks",
    )
    for row in () if rows is None else rows:
        script = _indexed_value(row, 0)
        path = _indexed_value(row, 1)
        font = provider_method(provider, "cg_font_with_file_path")(path)
        if font is not None:
            provider_method(provider, "cf_dictionary_set_value")(
                _script_to_placeholder_font_cache, script, font
            )
            provider_method(provider, "cf_release")(font)


def _error_code(error: object) -> int:
    return 0 if error is None else error.code()


def _file_path(error: object) -> object:
    info = error.userInfo()
    if info is None:
        return None
    method = getattr(info, "objectForKeyedSubscript_", None)
    return method("FilePath") if callable(method) else info.get("FilePath")


class InfoReportError(InfoError):
    """English NSError fields; the native NSError object itself stays held."""

    def __init__(self) -> None:
        description = "There was a problem loading glyph data"
        super().__init__("GSGlyphsDomain", 1, description)
        self._user_info = {
            "NSLocalizedDescription": description,
            "NSLocalizedRecoverySuggestion": (
                "Please make sure the app is not damaged and maybe re-download it."
            ),
        }

    def userInfo(self) -> dict:
        return self._user_info

    def localizedRecoverySuggestion(self) -> str:
        return self._user_info["NSLocalizedRecoverySuggestion"]


class ManagerObservation:
    """Selectors that keep their native primitive dependencies explicit."""

    def observeValueForKeyPath_ofObject_change_context_(
        self, key: object, obj: object, change: object, context: object
    ) -> None:
        """Only the exact retained key dispatches invalidation."""
        method = getattr(key, "isEqualToString_", None)
        equal = method(_OBSERVER_KEY) if callable(method) else key == _OBSERVER_KEY
        if equal:
            self.setNeedsUpdateScriptToFontCache()

    def setNeedsUpdateScriptToFontCache(self) -> None:
        """Clear the global pointer without releasing it."""
        global _script_to_placeholder_font_cache
        _script_to_placeholder_font_cache = None

    @classmethod
    def fontForScript_size_(cls, script: object, size: float) -> object:
        """The CLASS selector, using the current individual primitives."""
        provider = require_provider()
        if _script_to_placeholder_font_cache is None:
            _build_cache(provider)
        font = provider_method(provider, "cf_dictionary_get_value")(
            _script_to_placeholder_font_cache, script
        )
        if font is None:
            return None
        return provider_method(provider, "ct_font_create_with_graphics_font")(
            font, size, None, None
        )

    def reportInfoError(self) -> None:
        """Present the domain, code and English fields; the return value is ignored."""
        error = InfoReportError()
        provider_method(state_for(self).provider, "present_error")(error)

    def attemptRecoveryFromError_optionIndex_(self, error: object, option: int) -> bool:
        """Read the code twice and reveal only the known cases."""
        if _error_code(error) == 0x2AE2:
            if option != 1:
                return True
        else:
            code = _error_code(error)
            if option != 1 or code != 0x8702:
                return True
        path = _file_path(error)
        provider_method(state_for(self).provider, "select_file_in_viewer")(path, "")
        return True

    def dealloc(self) -> None:
        """Explicit dispatch; no Python destructor or implicit native release."""
        deallocate(self)
