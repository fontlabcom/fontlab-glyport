# this_file: tests/test_info_manager_observation.py
"""Independent owned oracles for retained observer, font-cache and recovery order."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp import GSGlyphsInfo
from fontlab_glyport.glyphsapp import info_manager_observation as observed
from fontlab_glyport.glyphsapp.info_runtime import InfoState, using_info_provider

KEY = "values.GSScriptToPlaceholderFontPath"


class Provider:
    """Individual deterministic owned primitives; never a native implementation."""

    def __init__(self, rows=None):
        self.rows = rows
        self.events = []
        self.fonts = {}
        self.hooks = {}

    def call(self, name, *args):
        self.events.append((name, *args))
        hook = self.hooks.get(name)
        if hook is not None:
            return hook(*args)

    def defaults_object_for_key(self, key):
        self.call("defaults", key)
        return self.rows

    def cf_dictionary_create_mutable(self, allocator, capacity, keys, values):
        self.call("create", allocator, capacity, keys, values)
        return {}

    def cg_font_with_file_path(self, path):
        if "font" in self.hooks:
            return self.call("font", path)
        self.call("font", path)
        return self.fonts.get(path)

    def cf_dictionary_set_value(self, cache, key, value):
        self.call("set", cache, key, value)
        cache[key] = value

    def cf_release(self, value):
        self.call("release", value)

    def cf_dictionary_get_value(self, cache, key):
        if "get" in self.hooks:
            return self.call("get", cache, key)
        self.call("get", cache, key)
        return cache.get(key)

    def ct_font_create_with_graphics_font(self, graphics, size, matrix, attributes):
        self.call("ct", graphics, size, matrix, attributes)
        return (graphics, size)

    def add_observer(self, receiver, key, options, context):
        self.call("add", receiver, key, options, context)

    def remove_observer(self, receiver, key):
        self.call("remove", receiver, key)

    def super_dealloc(self, receiver):
        self.call("super_dealloc", receiver)

    def select_file_in_viewer(self, path, root):
        self.call("select", path, root)
        return False

    def present_error(self, error):
        self.call("present", error)
        return False


def manager(provider, flag=0):
    receiver = GSGlyphsInfo.alloc()
    receiver._lifecycle = InfoState(provider, None, observer_flag=flag)
    return receiver


def fail(*args):
    raise RuntimeError("owned failure")


@pytest.fixture(autouse=True)
def isolate_cache_and_shared(monkeypatch):
    monkeypatch.setattr(
        observed, "_script_to_placeholder_font_cache", None, raising=False
    )
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)


def test_cache_selector_is_class_method_and_instance_uses_current_provider():
    assert isinstance(
        vars(observed.ManagerObservation)["fontForScript_size_"], classmethod
    )
    retained, current = Provider(), Provider([["OwnedScript", "/owned/font"]])
    font = current.fonts["/owned/font"] = object()
    receiver = manager(retained)
    with using_info_provider(current):
        assert receiver.fontForScript_size_("OwnedScript", 13.75) == (font, 13.75)
    assert retained.events == []
    assert [e[0] for e in current.events] == [
        "defaults",
        "create",
        "font",
        "set",
        "release",
        "get",
        "ct",
    ]
    assert current.events[0] == ("defaults", "GSScriptToPlaceholderFontPath")
    assert current.events[1] == (
        "create",
        None,
        1,
        "kCFTypeDictionaryKeyCallBacks",
        "kCFTypeDictionaryValueCallBacks",
    )
    assert current.events[-1] == ("ct", font, 13.75, None, None)


def test_cache_rows_preserve_order_duplicate_last_success_and_no_release_for_nil():
    p = Provider([["A", "first"], ["B", "nil"], ["A", "second"], ["A", "nil"]])
    first, second = object(), object()
    p.fonts.update(first=first, second=second)
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("A", 0.0) == (second, 0.0)
        assert GSGlyphsInfo.fontForScript_size_("B", -2.5) is None
    assert [e[1] for e in p.events if e[0] == "font"] == [
        "first",
        "nil",
        "second",
        "nil",
    ]
    assert [e[1] for e in p.events if e[0] == "release"] == [first, second]
    assert len([e for e in p.events if e[0] == "defaults"]) == 1
    assert observed._script_to_placeholder_font_cache == {"A": second}


@pytest.mark.parametrize("rows", [None, []])
def test_nil_or_empty_defaults_build_empty_cache_and_still_lookup(rows):
    p = Provider(rows)
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_(None, 100000000000.0) is None
    assert [e[0] for e in p.events] == ["defaults", "create", "get"]
    assert p.events[1][2] == 0


def test_empty_cache_is_non_nil_and_never_triggers_a_second_build():
    p = Provider([])
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("A", 12) is None
        p.rows = [["A", "new"]]
        assert GSGlyphsInfo.fontForScript_size_("A", 12) is None
    assert [e[0] for e in p.events] == ["defaults", "create", "get", "get"]


def test_shared_cache_uses_each_current_provider_for_get_and_ct():
    first, current = Provider([["A", "first"]]), Provider([["A", "ignored"]])
    font = first.fonts["first"] = object()
    with using_info_provider(first):
        assert GSGlyphsInfo.fontForScript_size_("A", 3) == (font, 3)
    with using_info_provider(current):
        assert GSGlyphsInfo.fontForScript_size_("A", 7) == (font, 7)
    assert [e[0] for e in current.events] == ["get", "ct"]


def test_early_cache_publication_allows_reentrant_reads_without_rebuilding():
    p = Provider([["A", "first"], ["B", "second"]])
    first, second = object(), object()
    p.fonts.update(first=first, second=second)
    nested = []

    def create_font(path):
        if path == "second":
            nested.append(GSGlyphsInfo.fontForScript_size_("A", 17))
            nested.append(GSGlyphsInfo.fontForScript_size_("B", 18))
        return p.fonts[path]

    p.hooks["font"] = create_font
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("B", 19) == (second, 19)
    assert nested == [(first, 17), None]
    assert len([e for e in p.events if e[0] == "create"]) == 1


def test_store_reads_current_global_after_callback_replacement_and_final_lookup_does_too():
    p = Provider([["A", "first"], ["B", "second"]])
    first, second, replacement = object(), object(), {}

    def create_font(path):
        if path == "second":
            observed._script_to_placeholder_font_cache = replacement
            return second
        return first

    p.hooks["font"] = create_font
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("B", 12) == (second, 12)
    stores = [e for e in p.events if e[0] == "set"]
    assert stores[0][1] is not replacement and stores[0][1] == {"A": first}
    assert stores[1][1] is replacement and replacement == {"B": second}
    assert next(e for e in p.events if e[0] == "get")[1] is replacement


@pytest.mark.parametrize(
    "stage", ["defaults", "create", "font", "set", "release", "get", "ct"]
)
def test_cache_failure_preserves_source_partial_state_without_extra_releases(stage):
    p = Provider([["A", "font"]])
    font = p.fonts["font"] = object()
    p.hooks[stage] = fail
    with using_info_provider(p), pytest.raises(RuntimeError, match="owned failure"):
        GSGlyphsInfo.fontForScript_size_("A", 12)
    cache = observed._script_to_placeholder_font_cache
    if stage in {"defaults", "create"}:
        assert cache is None
    elif stage in {"font", "set"}:
        assert cache == {}
    else:
        assert cache == {"A": font}
    releases = [e for e in p.events if e[0] == "release"]
    assert len(releases) == (1 if stage in {"release", "get", "ct"} else 0)


def test_build_failure_keeps_completed_rows_and_next_call_does_not_retry():
    p = Provider([["A", "font"], ["malformed"]])
    font = p.fonts["font"] = object()
    with using_info_provider(p):
        with pytest.raises(IndexError):
            GSGlyphsInfo.fontForScript_size_("A", 8)
        assert observed._script_to_placeholder_font_cache == {"A": font}
        assert GSGlyphsInfo.fontForScript_size_("A", 9) == (font, 9)
    assert len([e for e in p.events if e[0] == "defaults"]) == 1


@pytest.mark.parametrize(
    "missing",
    [
        "defaults_object_for_key",
        "cf_dictionary_create_mutable",
        "cg_font_with_file_path",
        "cf_dictionary_set_value",
        "cf_release",
        "cf_dictionary_get_value",
        "ct_font_create_with_graphics_font",
    ],
)
def test_cache_requires_each_individual_primitive(missing):
    p = Provider([["A", "font"]])
    p.fonts["font"] = object()
    setattr(p, missing, None)
    with using_info_provider(p), pytest.raises(UnsupportedCapability) as error:
        GSGlyphsInfo.fontForScript_size_("A", 8)
    assert error.value.capability == f"GSGlyphsInfo.provider.{missing}"


def test_cached_calls_still_refuse_missing_current_provider():
    observed._script_to_placeholder_font_cache = {}
    with pytest.raises(UnsupportedCapability):
        GSGlyphsInfo.fontForScript_size_("A", 8)


@pytest.mark.parametrize(
    "key",
    [
        None,
        "GSScriptToPlaceholderFontPath",
        "values.gsscripttoplaceholderfontpath",
        "values.GSScriptToPlaceholderFontPath ",
        "unrelated",
    ],
)
def test_observer_ignores_other_keys_without_state_or_provider(key):
    receiver = GSGlyphsInfo.alloc()
    cache = observed._script_to_placeholder_font_cache = {"retained": object()}
    assert (
        receiver.observeValueForKeyPath_ofObject_change_context_(
            key, object(), object(), object()
        )
        is None
    )
    assert observed._script_to_placeholder_font_cache is cache


def test_exact_observer_path_dispatches_overridable_invalidation_and_nil_has_no_release():
    calls = []

    class Receiver(GSGlyphsInfo):
        def setNeedsUpdateScriptToFontCache(self):
            calls.append(self)
            return super().setNeedsUpdateScriptToFontCache()

    receiver = Receiver.alloc()
    cache = observed._script_to_placeholder_font_cache = {"owned": object()}
    assert (
        receiver.observeValueForKeyPath_ofObject_change_context_(KEY, None, None, None)
        is None
    )
    assert calls == [receiver]
    assert observed._script_to_placeholder_font_cache is None
    assert cache
    assert receiver.setNeedsUpdateScriptToFontCache() is None


def test_invalidation_from_other_receiver_rebuilds_using_then_current_defaults():
    p = Provider([["A", "first"]])
    first, second = object(), object()
    p.fonts.update(first=first, second=second)
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("A", 1) == (first, 1)
        p.rows = [["A", "second"]]
        manager(Provider()).setNeedsUpdateScriptToFontCache()
        assert GSGlyphsInfo.fontForScript_size_("A", 2) == (second, 2)
    assert [e[1] for e in p.events if e[0] == "release"] == [first, second]


@pytest.mark.parametrize("flag", [0, 2, 254])
def test_registration_tests_low_bit_then_adds_current_global_before_flag_update(flag):
    p = Provider()
    receiver, current = manager(p, flag), GSGlyphsInfo.alloc()
    GSGlyphsInfo._shared = current

    def before_add(*args):
        assert receiver._lifecycle.observer_flag == flag

    p.hooks["add"] = before_add
    assert observed.register_observer(receiver) is None
    assert p.events == [("add", current, KEY, 0, None)]
    assert receiver._lifecycle.observer_flag == 1


@pytest.mark.parametrize("flag", [1, 3, 255])
def test_registration_skips_set_low_bit_without_requiring_primitive(flag):
    receiver = manager(object(), flag)
    assert observed.register_observer(receiver) is None
    assert receiver._lifecycle.observer_flag == flag


def test_registration_failure_keeps_original_flag_and_current_global():
    p = Provider()
    receiver = manager(p, 2)
    GSGlyphsInfo._shared = receiver
    p.hooks["add"] = fail
    with pytest.raises(RuntimeError):
        observed.register_observer(receiver)
    assert receiver._lifecycle.observer_flag == 2
    assert GSGlyphsInfo._shared is receiver


@pytest.mark.parametrize("flag", [0, 2, 3, 255])
def test_deallocation_requires_exact_one_and_otherwise_only_dispatches_super(flag):
    p = Provider()
    receiver = manager(p, flag)
    assert receiver.dealloc() is None
    assert receiver._lifecycle.observer_flag == flag
    assert p.events == [("super_dealloc", receiver)]


@pytest.mark.parametrize("global_is_nil", [False, True])
def test_deallocation_removes_current_global_not_self_then_clears_only_receiver_flag(
    global_is_nil,
):
    p = Provider()
    receiver, current = manager(p, 1), manager(object(), 3)
    GSGlyphsInfo._shared = None if global_is_nil else current
    cache = observed._script_to_placeholder_font_cache = {}
    assert receiver.dealloc() is None
    assert p.events == [
        ("remove", GSGlyphsInfo._shared, KEY),
        ("super_dealloc", receiver),
    ]
    assert receiver._lifecycle.observer_flag == 0
    assert current._lifecycle.observer_flag == 3
    assert observed._script_to_placeholder_font_cache is cache


def test_deallocation_failure_retains_flag_and_does_not_remove_global():
    p = Provider()
    receiver = manager(p, 1)
    GSGlyphsInfo._shared = receiver
    p.hooks["remove"] = fail
    with pytest.raises(RuntimeError):
        observed.deallocate(receiver)
    assert receiver._lifecycle.observer_flag == 1
    assert GSGlyphsInfo._shared is receiver
    assert p.events == [("remove", receiver, KEY)]


@pytest.mark.parametrize(
    "function,flag,name",
    [("register_observer", 0, "add_observer"), ("deallocate", 1, "remove_observer")],
)
def test_observer_missing_primitive_refuses_without_flag_change(function, flag, name):
    receiver = manager(object(), flag)
    with pytest.raises(UnsupportedCapability) as error:
        getattr(observed, function)(receiver)
    assert error.value.capability == f"GSGlyphsInfo.provider.{name}"
    assert receiver._lifecycle.observer_flag == flag


class ErrorStream:
    def __init__(self, codes, events, info=None):
        self.codes, self.events, self.info = iter(codes), events, info

    def code(self):
        value = next(self.codes)
        self.events.append(("code", value))
        return value

    def userInfo(self):
        self.events.append(("userInfo",))
        return self.info


@pytest.mark.parametrize(
    "codes,option,reads,reveal",
    [
        ([0x2AE2], 1, [0x2AE2], True),
        ([0x2AE2], 0, [0x2AE2], False),
        ([0x8702, 99], 1, [0x8702, 99], False),
        ([99, 0x8702], 1, [99, 0x8702], True),
        ([99, 0x2AE2], 1, [99, 0x2AE2], False),
        ([99, 0x8702], 0, [99, 0x8702], False),
        ([99, 99], 1, [99, 99], False),
        ([0x2AE2], 2**64 - 1, [0x2AE2], False),
    ],
)
def test_recovery_repeated_code_stream_before_option_guard(
    codes, option, reads, reveal
):
    p = Provider()
    error = ErrorStream(codes, p.events, {"FilePath": "/owned/file"})
    receiver = manager(p) if reveal else GSGlyphsInfo.alloc()
    assert receiver.attemptRecoveryFromError_optionIndex_(error, option) is True
    expected = [("code", code) for code in reads]
    if reveal:
        expected += [("userInfo",), ("select", "/owned/file", "")]
    assert p.events == expected


@pytest.mark.parametrize("info", [None, {}, {"FilePath": None}])
def test_recovery_forwards_nil_path_and_ignores_false_select_return(info):
    p = Provider()
    error = ErrorStream([0x2AE2], p.events, info)
    assert manager(p).attemptRecoveryFromError_optionIndex_(error, 1) is True
    assert p.events[-1] == ("select", None, "")


def test_recovery_select_failure_propagates_after_exact_reads():
    p = Provider()
    p.hooks["select"] = fail
    error = ErrorStream([0, 0x8702], p.events, {"FilePath": "owned"})
    with pytest.raises(RuntimeError):
        manager(p).attemptRecoveryFromError_optionIndex_(error, 1)
    assert p.events == [
        ("code", 0),
        ("code", 0x8702),
        ("userInfo",),
        ("select", "owned", ""),
    ]


def test_recovery_missing_reveal_primitive_refuses_and_nil_error_reads_as_zero():
    receiver = manager(object())
    assert GSGlyphsInfo.alloc().attemptRecoveryFromError_optionIndex_(None, 1) is True
    error = ErrorStream([0x2AE2], [], {})
    with pytest.raises(UnsupportedCapability) as caught:
        receiver.attemptRecoveryFromError_optionIndex_(error, 1)
    assert caught.value.capability == "GSGlyphsInfo.provider.select_file_in_viewer"


def test_recovery_uses_retained_receiver_provider_and_native_style_keyed_object():
    retained, current = Provider(), Provider()

    class Info:
        def objectForKeyedSubscript_(self, key):
            retained.events.append(("key", key))
            return "owned"

    error = ErrorStream([0x2AE2], retained.events, Info())
    with using_info_provider(current):
        assert manager(retained).attemptRecoveryFromError_optionIndex_(error, 1) is True
    assert retained.events == [
        ("code", 0x2AE2),
        ("userInfo",),
        ("key", "FilePath"),
        ("select", "owned", ""),
    ]
    assert current.events == []


def test_error_report_constructs_exact_source_fields_and_ignores_present_return():
    retained, current = Provider(), Provider()
    with using_info_provider(current):
        assert manager(retained).reportInfoError() is None
    assert current.events == []
    assert len(retained.events) == 1 and retained.events[0][0] == "present"
    error = retained.events[0][1]
    assert error.domain() == "GSGlyphsDomain" and error.code() == 1
    assert error.localizedDescription() == "There was a problem loading glyph data"
    assert (
        error.localizedRecoverySuggestion()
        == "Please make sure the app is not damaged and maybe re-download it."
    )
    assert error.userInfo() == {
        "NSLocalizedDescription": "There was a problem loading glyph data",
        "NSLocalizedRecoverySuggestion": "Please make sure the app is not damaged and maybe re-download it.",
    }


def test_error_report_presentation_failure_propagates_and_missing_provider_refuses():
    p = Provider()
    p.hooks["present"] = fail
    with pytest.raises(RuntimeError):
        manager(p).reportInfoError()
    assert len(p.events) == 1
    with pytest.raises(UnsupportedCapability) as error:
        manager(object()).reportInfoError()
    assert error.value.capability == "GSGlyphsInfo.provider.present_error"


def test_cache_nil_rows_and_owned_subscript_objects_keep_access_and_font_order():
    p = Provider()
    font = object()

    class Row:
        def objectAtIndexedSubscript_(self, index):
            p.events.append(("row", index))
            return "OwnedScript" if index == 0 else "owned"

    p.rows = [None, Row()]
    p.fonts["owned"] = font
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("OwnedScript", 12) == (font, 12)
    assert [e[0] for e in p.events] == [
        "defaults",
        "create",
        "font",
        "row",
        "row",
        "font",
        "set",
        "release",
        "get",
        "ct",
    ]
    assert p.events[2] == ("font", None)


def test_reentrant_allocation_rebuilds_before_outer_publication_without_inner_recheck():
    p = Provider([])
    nested_cache, outer_cache = {}, {}
    depth = 0

    def allocate(*args):
        nonlocal depth
        depth += 1
        if depth == 1:
            assert GSGlyphsInfo.fontForScript_size_("owned", 1) is None
            assert observed._script_to_placeholder_font_cache is nested_cache
            return outer_cache
        return nested_cache

    p.cf_dictionary_create_mutable = allocate
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("owned", 2) is None
    assert depth == 2
    assert observed._script_to_placeholder_font_cache is outer_cache
    assert [e[1] for e in p.events if e[0] == "get"] == [nested_cache, outer_cache]


def test_allocation_returning_nil_is_published_and_passed_to_lookup_without_fallback():
    p = Provider(None)
    p.cf_dictionary_create_mutable = lambda *args: None
    p.hooks["get"] = lambda cache, key: None
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_(None, 1) is None
    assert observed._script_to_placeholder_font_cache is None
    assert p.events == [
        ("defaults", "GSScriptToPlaceholderFontPath"),
        ("get", None, None),
    ]


def test_invalidation_during_font_load_passes_nil_current_cache_to_store_and_does_not_release():
    p = Provider([["A", "owned"]])
    font = object()

    def font_load(path):
        GSGlyphsInfo.alloc().setNeedsUpdateScriptToFontCache()
        return font

    p.hooks["font"] = font_load
    with using_info_provider(p), pytest.raises(TypeError):
        GSGlyphsInfo.fontForScript_size_("A", 1)
    assert observed._script_to_placeholder_font_cache is None
    assert p.events[-1] == ("set", None, "A", font)
    assert not any(e[0] == "release" for e in p.events)


def test_cache_never_copies_default_rows_and_observes_later_row_changes_during_load():
    rows = [["A", "first"], ["B", "old"]]
    p = Provider(rows)
    first, current = object(), object()

    def load(path):
        if path == "first":
            rows[1][1] = "current"
            return first
        assert path == "current"
        return current

    p.hooks["font"] = load
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("B", 1) == (current, 1)
    assert p.events[1][2] == 2


def test_ct_failure_or_nil_result_never_releases_borrowed_cached_font():
    p = Provider([["A", "owned"]])
    font = p.fonts["owned"] = object()
    p.ct_font_create_with_graphics_font = lambda *args: None
    with using_info_provider(p):
        assert GSGlyphsInfo.fontForScript_size_("A", float("nan")) is None
        assert GSGlyphsInfo.fontForScript_size_("A", -0.0) is None
    assert [e for e in p.events if e[0] == "release"] == [("release", font)]
    assert observed._script_to_placeholder_font_cache == {"A": font}


def test_observer_uses_explicit_string_selector_and_propagates_its_failure():
    events = []

    class Key:
        def isEqualToString_(self, value):
            events.append(value)
            return True

    receiver = GSGlyphsInfo.alloc()
    observed._script_to_placeholder_font_cache = {}
    assert (
        receiver.observeValueForKeyPath_ofObject_change_context_(
            Key(), None, None, None
        )
        is None
    )
    assert events == [KEY] and observed._script_to_placeholder_font_cache is None
    key = Key()
    key.isEqualToString_ = fail
    cache = observed._script_to_placeholder_font_cache = {}
    with pytest.raises(RuntimeError):
        receiver.observeValueForKeyPath_ofObject_change_context_(key, None, None, None)
    assert observed._script_to_placeholder_font_cache is cache


def test_uninitialized_alloc_dealloc_requires_explicit_current_super_primitive():
    receiver = GSGlyphsInfo.alloc()
    p = Provider()
    with using_info_provider(p):
        assert receiver.dealloc() is None
    assert p.events == [("super_dealloc", receiver)]
    with pytest.raises(UnsupportedCapability):
        receiver.dealloc()
    assert "__del__" not in vars(observed.ManagerObservation)
    assert "__del__" not in vars(GSGlyphsInfo)


def test_failed_recovery_code_or_user_info_never_reaches_provider():
    p = Provider()
    error = ErrorStream([], p.events)
    with pytest.raises(StopIteration):
        manager(p).attemptRecoveryFromError_optionIndex_(error, 1)
    assert p.events == []
    error = ErrorStream([0, 0x8702], p.events)
    error.userInfo = fail
    with pytest.raises(RuntimeError):
        manager(p).attemptRecoveryFromError_optionIndex_(error, 1)
    assert p.events == [("code", 0), ("code", 0x8702)]


def test_recovery_reads_provider_after_user_info_callback_updates_receiver_state():
    initial, current = Provider(), Provider()
    receiver = manager(initial)
    error = ErrorStream([0x2AE2], initial.events)

    def info():
        receiver._lifecycle.provider = current
        return {"FilePath": "owned"}

    error.userInfo = info
    assert receiver.attemptRecoveryFromError_optionIndex_(error, 1) is True
    assert initial.events == [("code", 0x2AE2)]
    assert current.events == [("select", "owned", "")]


def test_observer_flags_are_updated_after_success_even_if_callback_replaces_global():
    p = Provider()
    receiver = manager(p)
    old, new = GSGlyphsInfo.alloc(), GSGlyphsInfo.alloc()
    GSGlyphsInfo._shared = old

    def add(*args):
        assert receiver._lifecycle.observer_flag == 0
        GSGlyphsInfo._shared = new

    p.hooks["add"] = add
    observed.register_observer(receiver)
    assert p.events[0] == ("add", old, KEY, 0, None)
    assert receiver._lifecycle.observer_flag == 1

    def remove(*args):
        assert receiver._lifecycle.observer_flag == 1
        GSGlyphsInfo._shared = None

    p.hooks["remove"] = remove
    observed.deallocate(receiver)
    assert p.events[-2:] == [("remove", new, KEY), ("super_dealloc", receiver)]
    assert receiver._lifecycle.observer_flag == 0 and GSGlyphsInfo._shared is None


def test_error_report_user_info_identity_and_source_english_are_stable():
    p = Provider()
    manager(p).reportInfoError()
    error = p.events[0][1]
    assert error.userInfo() is error.userInfo()
    assert str(error) == error.localizedDescription()
    assert not hasattr(error, "recoveryAttempter")


def test_parallel_cache_misses_both_allocate_without_source_lock_or_inner_recheck():
    p = Provider([])
    barrier = Barrier(2)
    allocated = []

    def allocate(*args):
        cache = {}
        allocated.append(cache)
        barrier.wait(timeout=3)
        return cache

    def read():
        with using_info_provider(p):
            return GSGlyphsInfo.fontForScript_size_("owned", 1)

    p.cf_dictionary_create_mutable = allocate
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(read), pool.submit(read)
        assert first.result(timeout=5) is None
        assert second.result(timeout=5) is None
    assert len(allocated) == 2 and allocated[0] is not allocated[1]
    assert any(
        observed._script_to_placeholder_font_cache is cache for cache in allocated
    )
    assert [e[0] for e in p.events].count("defaults") == 2


@pytest.mark.parametrize("flag", [0, 1, 3])
def test_missing_super_dealloc_refuses_after_source_flag_work(flag):
    p = Provider()
    p.super_dealloc = None
    receiver = manager(p, flag)
    GSGlyphsInfo._shared = receiver
    with pytest.raises(UnsupportedCapability) as error:
        receiver.dealloc()
    assert error.value.capability == "GSGlyphsInfo.provider.super_dealloc"
    assert receiver._lifecycle.observer_flag == (0 if flag == 1 else flag)
    assert p.events == ([("remove", receiver, KEY)] if flag == 1 else [])


@pytest.mark.parametrize("flag", [0, 1, 3])
def test_super_dealloc_failure_preserves_earlier_flag_clear_and_other_fields(flag):
    retained, current = Provider(), Provider()
    receiver = manager(retained, flag)
    state = receiver._lifecycle
    state.categories = ["owned"]
    retained.hooks["super_dealloc"] = fail
    GSGlyphsInfo._shared = receiver
    with using_info_provider(current), pytest.raises(RuntimeError):
        receiver.dealloc()
    assert state.observer_flag == (0 if flag == 1 else flag)
    assert state.categories == ["owned"] and receiver._lifecycle is state
    assert retained.events[-1] == ("super_dealloc", receiver)
    assert current.events == []
