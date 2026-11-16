# this_file: tests/test_info_manager_accessors.py
"""Owned graph cases for retained manager fields and ARM rank-cache order."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event, RLock

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo
from fontlab_glyport.glyphsapp.info_runtime import InfoState


@pytest.fixture
def manager():
    value = GSGlyphsInfo.alloc()
    value._lifecycle = InfoState(object(), None)
    return value


@pytest.mark.parametrize(
    "selector,field",
    [
        ("glyphInfos", "index.records"),
        ("name2Info", "index.names"),
        ("unicode2Info", "index.unicodes"),
        ("scriptIDs", "scriptIDs"),
        ("sidebarCategories", "sidebarCategories"),
        ("categories", "categories"),
        ("subCategories", "subCategories"),
        ("iMatraCombinations", "iMatraCombinations"),
        ("languagesGroup", "languagesGroup"),
        ("allItem", "allItem"),
        ("categoriesGroup", "categoriesGroup"),
        ("filterGroups", "filterGroups"),
    ],
)
def test_getter_returns_actual_field_identity_and_nil(manager, selector, field):
    owner = manager._lifecycle
    if field.startswith("index."):
        owner, field = owner.index, field.split(".")[1]
    for value in ([object()], {}, None):
        setattr(owner, field, value)
        assert getattr(manager, selector)() is value, selector


@pytest.mark.parametrize(
    "selector,field,getter",
    [
        ("setGlyphInfos_", "index.records", "glyphInfos"),
        ("setLanguagesGroup_", "languagesGroup", "languagesGroup"),
        ("setAllItem_", "allItem", "allItem"),
        ("setCategoriesGroup_", "categoriesGroup", "categoriesGroup"),
        ("setFilterGroups_", "filterGroups", "filterGroups"),
    ],
)
def test_retaining_setter_preserves_identity_nil_and_other_fields(
    manager, selector, field, getter
):
    state = manager._lifecycle
    names, unicodes, scripts = state.index.names, state.index.unicodes, ["latn"]
    state.scriptIDs = scripts
    rows = [object()]
    assert getattr(manager, selector)(rows) is None
    assert getattr(manager, getter)() is rows
    rows.append(object())
    assert len(getattr(manager, getter)()) == 2
    owner = state.index if field.startswith("index.") else state
    assert getattr(owner, field.split(".")[-1]) is rows
    assert state.index.names is names and state.index.unicodes is unicodes
    assert state.scriptIDs is scripts
    getattr(manager, selector)(None)
    assert getattr(manager, getter)() is None


def test_subcategory_lookup_keeps_inner_identity_and_nil_short_circuit(manager):
    inner = {"Uppercase": 10}
    manager._lifecycle.subCategoryOrder = {"Letter": inner}
    assert manager._subcategoriesForSidebarCategory_("Letter") is inner
    inner["Lowercase"] = 20
    assert manager._subcategoriesForSidebarCategory_("Letter")["Lowercase"] == 20
    assert manager._subcategoriesForSidebarCategory_("Unknown") is None
    assert GSGlyphsInfo.alloc()._subcategoriesForSidebarCategory_(None) is None
    manager._lifecycle.subCategoryOrder = None
    assert manager._subcategoriesForSidebarCategory_("Letter") is None


@pytest.mark.parametrize(
    "selector,rows_field,cache_field",
    [
        ("indexOfObjectInScripts_", "scriptIDs", "scriptOrder"),
        ("indexOfObjectInCategories_", "sidebarCategories", "categoryOrder"),
    ],
)
def test_rank_laziness_duplicates_staleness_explicit_invalidation(
    manager, selector, rows_field, cache_field
):
    state = manager._lifecycle
    rows = ["first", "duplicate", "last", "duplicate"]
    setattr(state, rows_field, rows)
    assert getattr(state, cache_field) is None
    rank = getattr(manager, selector)
    assert rank("duplicate") == 3
    cache = getattr(state, cache_field)
    rows[:] = ["new", "duplicate"]
    assert rank("duplicate") == 3
    assert rank("new") == 2**63 - 1
    assert getattr(state, cache_field) is cache
    setattr(state, cache_field, None)
    assert rank("duplicate") == 1
    assert getattr(state, cache_field) is not cache


def test_category_terminal_entries_override_duplicate_rows_in_exact_order(manager):
    manager._lifecycle.sidebarCategories = [
        "Corner",
        "Icon",
        "Private Use",
        "SF-Symbol",
        "Letter",
    ]
    rank = manager.indexOfObjectInCategories_
    assert [rank(k) for k in ("Icon", "SF-Symbol", "Private Use", "Corner")] == [
        5,
        6,
        7,
        8,
    ]
    assert rank("Letter") == 4
    assert rank("SFSymbol") == rank("PrivateUse") == 2**63 - 1


@pytest.mark.parametrize(
    "selector", ["indexOfObjectInScripts_", "indexOfObjectInCategories_"]
)
def test_nil_source_creates_persistent_cache_and_missing_is_nsnotfound(
    manager, selector
):
    rank = getattr(manager, selector)
    assert rank("missing") == 2**63 - 1
    assert rank("Icon") == (0 if selector.endswith("Categories_") else 2**63 - 1)
    with pytest.raises(UnsupportedCapability, match="key"):
        rank(None)


@pytest.mark.parametrize(
    "number,expected",
    [
        (0, 0),
        (2**31 - 1, 2**31 - 1),
        (2**31, 2**64 - 2**31),
        (2**32 - 1, 2**64 - 1),
        (2**32 + 7, 7),
        (-1, 2**64 - 1),
    ],
)
@pytest.mark.parametrize(
    "selector,field",
    [
        ("indexOfObjectInScripts_", "scriptOrder"),
        ("indexOfObjectInCategories_", "categoryOrder"),
    ],
)
def test_rank_int32_value_is_sign_extended_then_returned_uint64(
    manager, selector, field, number, expected
):
    rank = getattr(manager, selector)
    rank("initialize")
    getattr(manager._lifecycle, field)["value"] = number
    assert rank("value") == expected


@pytest.mark.parametrize(
    "selector,rows_field,cache_field",
    [
        ("indexOfObjectInScripts_", "scriptIDs", "scriptOrder"),
        ("indexOfObjectInCategories_", "sidebarCategories", "categoryOrder"),
    ],
)
def test_failed_enumeration_retains_partial_cache_without_automatic_retry(
    manager, selector, rows_field, cache_field
):
    class BrokenRows:
        def __len__(self):
            return 2

        def __iter__(self):
            yield "retained"
            raise RuntimeError("owned enumeration failed")

    setattr(manager._lifecycle, rows_field, BrokenRows())
    rank = getattr(manager, selector)
    with pytest.raises(RuntimeError, match="owned enumeration failed"):
        rank("retained")
    cache = getattr(manager._lifecycle, cache_field)
    assert cache == {"retained": 0}
    assert rank("retained") == 0
    assert rank("Icon") == 2**63 - 1


def test_count_failure_precedes_cache_publication(manager):
    class BrokenCount:
        def __len__(self):
            raise RuntimeError("count failed")

    manager._lifecycle.scriptIDs = BrokenCount()
    with pytest.raises(RuntimeError, match="count failed"):
        manager.indexOfObjectInScripts_("x")
    assert manager._lifecycle.scriptOrder is None


def test_builder_rereads_rows_after_count_and_writes_current_cache(manager):
    state = manager._lifecycle

    class ReplacingCount:
        def __len__(self):
            state.scriptIDs = ["current"]
            return 1

        def __iter__(self):
            raise AssertionError("obsolete counted array enumerated")

    state.scriptIDs = ReplacingCount()
    assert manager.indexOfObjectInScripts_("current") == 0


@pytest.mark.parametrize(
    "selector,cache_field",
    [
        ("indexOfObjectInScripts_", "scriptOrder"),
        ("indexOfObjectInCategories_", "categoryOrder"),
    ],
)
def test_lookup_locks_captured_cache_but_reads_current_field(
    manager, selector, cache_field
):
    state = manager._lifecycle
    rank = getattr(manager, selector)
    rank("initialize")
    captured = getattr(state, cache_field)
    current = type(captured)()
    current["key"] = 71
    events = []

    @contextmanager
    def swap_on_enter():
        events.append("entered captured lock")
        setattr(state, cache_field, current)
        yield
        events.append("exited captured lock")

    captured.monitor = swap_on_enter()
    assert rank("key") == 71
    assert events == ["entered captured lock", "exited captured lock"]


def test_two_outer_nil_observers_each_build_after_serialized_entry(manager):
    state = manager._lifecycle
    rendezvous = Barrier(2)
    lock = RLock()
    snapshots = []

    class Monitor:
        def __enter__(self):
            rendezvous.wait(timeout=3)
            lock.acquire()

        def __exit__(self, *exc):
            snapshots.append(state.scriptOrder)
            lock.release()

    state.monitor = Monitor()
    state.scriptIDs = ["a", "b"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(manager.indexOfObjectInScripts_, "b") for _ in range(2)
        ]
        results = [future.result(timeout=5) for future in futures]
    assert results == [1, 1]
    assert len(snapshots) == 2 and snapshots[0] is not snapshots[1]


def test_missing_initialized_graph_refuses_instead_of_making_defaults():
    manager = GSGlyphsInfo.alloc()
    with pytest.raises(UnsupportedCapability, match="not initialized"):
        manager.glyphInfos()


@pytest.mark.parametrize(
    "selector,rows_field,cache_field",
    [
        ("indexOfObjectInScripts_", "scriptIDs", "scriptOrder"),
        ("indexOfObjectInCategories_", "sidebarCategories", "categoryOrder"),
    ],
)
def test_builder_inserts_into_current_cache_after_enumerator_replaces_it(
    manager, selector, rows_field, cache_field
):
    state = manager._lifecycle
    rank = getattr(manager, selector)
    rank("initial")
    replacement = type(getattr(state, cache_field))()
    replacement["preserved"] = 13

    class ReplacingRows:
        def __len__(self):
            return 2

        def __iter__(self):
            yield "original"
            setattr(state, cache_field, replacement)
            yield "current"

    setattr(state, rows_field, ReplacingRows())
    setattr(state, cache_field, None)
    assert rank("current") == 1
    assert rank("preserved") == 13
    assert rank("original") == 2**63 - 1
    assert getattr(state, cache_field) is replacement


@pytest.mark.parametrize(
    "selector,rows_field,cache_field",
    [
        ("indexOfObjectInScripts_", "scriptIDs", "scriptOrder"),
        ("indexOfObjectInCategories_", "sidebarCategories", "categoryOrder"),
    ],
)
def test_builder_preserves_current_nil_cache_without_substitute(
    manager, selector, rows_field, cache_field
):
    state = manager._lifecycle

    class ClearingRows:
        def __len__(self):
            return 1

        def __iter__(self):
            setattr(state, cache_field, None)
            yield "not stored"

    setattr(state, rows_field, ClearingRows())
    assert getattr(manager, selector)("not stored") == 2**63 - 1
    assert getattr(state, cache_field) is None


def test_lookup_current_nil_field_is_miss_under_captured_monitor(manager):
    state = manager._lifecycle
    manager.indexOfObjectInScripts_("init")
    captured = state.scriptOrder

    @contextmanager
    def clear():
        state.scriptOrder = None
        yield

    captured.monitor = clear()
    assert manager.indexOfObjectInScripts_("anything") == 2**63 - 1


def test_setters_do_not_invalidate_ranks_and_category_rank_uses_sidebar_rows(manager):
    state = manager._lifecycle
    state.categories = ["Unrelated"]
    state.sidebarCategories = ["Actual"]
    assert manager.indexOfObjectInCategories_("Actual") == 0
    assert manager.indexOfObjectInCategories_("Unrelated") == 2**63 - 1
    cache = state.categoryOrder
    manager.setCategoriesGroup_(["Replacement"])
    manager.setGlyphInfos_(["New row"])
    assert state.categoryOrder is cache
    assert manager.indexOfObjectInCategories_("Actual") == 0


def test_second_caller_can_observe_partial_cache_during_initial_build(manager):
    state = manager._lifecycle
    paused, resume = Event(), Event()

    class PausingRows:
        def __len__(self):
            return 2

        def __iter__(self):
            yield "first"
            paused.set()
            if not resume.wait(timeout=3):
                raise TimeoutError("owned build not resumed")
            yield "last"

    state.scriptIDs = PausingRows()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(manager.indexOfObjectInScripts_, "last")
        try:
            assert paused.wait(timeout=3)
            assert manager.indexOfObjectInScripts_("first") == 0
            assert manager.indexOfObjectInScripts_("last") == 2**63 - 1
        finally:
            resume.set()
        assert future.result(timeout=5) == 1


def test_failed_dictionary_insertion_releases_build_monitor_and_keeps_partial_state(
    manager,
):
    state = manager._lifecycle
    state.scriptIDs = ["first", None, "last"]
    with pytest.raises(UnsupportedCapability, match="key"):
        manager.indexOfObjectInScripts_("last")
    assert state.scriptOrder == {"first": 0}
    assert state.monitor.acquire(blocking=False)
    state.monitor.release()
    assert manager.indexOfObjectInScripts_("first") == 0
