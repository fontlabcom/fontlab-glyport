# this_file: tests/test_info_manager_debug.py
"""Complete debug constructor and shared observer order over owned primitives."""

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo
from fontlab_glyport.glyphsapp.info_runtime import (
    InfoErrorSlot,
    InfoState,
    using_info_provider,
)


class Queue:
    def __init__(self, provider):
        self.provider, self.maximum = provider, None

    def setMaxConcurrentOperationCount_(self, count):
        self.provider.events.append(("limit", count))
        self.maximum = count
        if self.provider.fail == "limit":
            raise RuntimeError("limit")


class Provider:
    def __init__(self, fail=None):
        self.events, self.queues, self.fail = [], [], fail
        self.cpu_counts = iter([7, 3])

    def new_queue(self):
        self.events.append("allocate-queue")
        if self.fail == "queue":
            raise RuntimeError("queue")
        queue = Queue(self)
        self.queues.append(queue)
        return queue

    def active_processor_count(self):
        self.events.append("processors")
        if self.fail == "processors":
            raise RuntimeError("processors")
        return next(self.cpu_counts)


class URL:
    def __init__(self, path):
        self.value = str(path)

    def path(self):
        return self.value


def test_debug_constructor_uses_actual_receiver_and_group_map_not_name_index(
    monkeypatch,
):
    class Child(GSGlyphsInfo):
        def loadGlyphInfo(self):
            pytest.fail("Debug init does not load GlyphData")

        def loadSidebarInfoForDocument_(self, font):
            pytest.fail("Debug init does not build sidebar")

    provider = Provider()
    old_shared = object()
    monkeypatch.setattr(GSGlyphsInfo, "_shared", old_shared)
    value = Child.alloc()
    with using_info_provider(provider):
        assert value.initDebug() is value
    state = value._lifecycle
    assert type(value) is Child and GSGlyphsInfo._shared is old_shared
    assert state.provider is provider and value._fixed_index is state.index
    assert (state.index.records, state.index.names, state.index.unicodes) == (
        None,
        None,
        None,
    )
    assert state.name2Group == {} and state.name2Group is not state.index.names
    assert state.queue is provider.queues[0] and state.queue.maximum == 7
    assert (
        state.scriptIDs is None
        and state.categories is None
        and state.subCategories is None
    )
    assert (
        state.categoriesGroup is None
        and state.languagesGroup is None
        and state.filterGroups is None
    )
    assert state.localURL is None and state.shared is False and state.observer_flag == 0
    assert provider.events == ["allocate-queue", "processors", ("limit", 7)]


@pytest.mark.parametrize("flag", [0, 1, 2, 3])
def test_debug_reinitialization_changes_only_queue_and_existing_group_slot(flag):
    old_provider, provider = Provider(), Provider()
    value = GSGlyphsInfo.alloc()
    state = value._lifecycle = InfoState(old_provider, object(), True)
    value._fixed_index = state.index
    state.index.records, state.index.names, state.index.unicodes = (
        [object()],
        {"A": object()},
        {"0041": object()},
    )
    for name in [
        "scriptIDs",
        "categories",
        "subCategories",
        "sidebarCategories",
        "subCategoryOrder",
        "categoriesGroup",
        "languagesGroup",
        "allItem",
        "filterGroups",
        "iMatraCombinations",
        "categoryOrder",
        "scriptOrder",
    ]:
        setattr(state, name, object())
    state.observer_flag = flag
    old_group, old_queue = {"old": object()}, object()
    state.name2Group = old_group
    state.queue = old_queue
    before = vars(state).copy()
    with using_info_provider(provider):
        assert value.initDebug() is value
    assert value._lifecycle is state and value._fixed_index is state.index
    assert state.name2Group == {} and state.name2Group is not old_group
    assert state.queue is not old_queue and state.queue.maximum == 7
    for name, old in before.items():
        if name not in {"provider", "queue", "name2Group"}:
            assert getattr(state, name) is old, name
    assert state.provider is provider and state.observer_flag == flag


def test_debug_repeated_calls_allocate_fresh_group_map_and_queue_but_keep_raw_containers():
    value, provider = GSGlyphsInfo.alloc(), Provider()
    with using_info_provider(provider):
        value.initDebug()
        first_state, first_group, first_queue = (
            value._lifecycle,
            value._lifecycle.name2Group,
            value._lifecycle.queue,
        )
        rows, names, codes = [object()], {}, {}
        (
            first_state.index.records,
            first_state.index.names,
            first_state.index.unicodes,
        ) = rows, names, codes
        value.initDebug()
    assert (
        value._lifecycle is first_state
        and value._lifecycle.name2Group is not first_group
    )
    assert first_state.queue is not first_queue and first_state.queue.maximum == 3
    assert (
        first_state.index.records is rows
        and first_state.index.names is names
        and first_state.index.unicodes is codes
    )
    assert provider.events == [
        "allocate-queue",
        "processors",
        ("limit", 7),
        "allocate-queue",
        "processors",
        ("limit", 3),
    ]


def test_debug_missing_provider_refuses_before_mutating_receiver():
    value = GSGlyphsInfo.alloc()
    with using_info_provider(None), pytest.raises(UnsupportedCapability) as caught:
        value.initDebug()
    assert caught.value.capability == "GSGlyphsInfo.initialization.provider"
    assert vars(value) == {}


@pytest.mark.parametrize("phase", ["queue", "processors", "limit"])
def test_debug_failures_retain_source_partial_queue_and_original_group(phase):
    value, provider = GSGlyphsInfo.alloc(), Provider(phase)
    state = value._lifecycle = InfoState(provider, None)
    value._fixed_index = state.index
    old_group, old_queue = {"old": object()}, object()
    state.name2Group, state.queue = old_group, old_queue
    with using_info_provider(provider), pytest.raises(RuntimeError, match=phase):
        value.initDebug()
    assert value._lifecycle is state and state.name2Group is old_group
    if phase == "queue":
        assert state.queue is old_queue and provider.events == ["allocate-queue"]
    else:
        assert state.queue is provider.queues[0]
        assert provider.events[:2] == ["allocate-queue", "processors"]
        assert state.queue.maximum == (7 if phase == "limit" else None)


def test_debug_missing_queue_primitive_is_typed_and_does_not_fill_group_map():
    value = GSGlyphsInfo.alloc()
    with using_info_provider(object()), pytest.raises(UnsupportedCapability) as caught:
        value.initDebug()
    assert caught.value.capability == "GSGlyphsInfo.provider.new_queue"
    state = value._lifecycle
    assert state.name2Group is None and state.queue is None
    assert (
        state.index.names is None
        and state.index.unicodes is None
        and state.index.records is None
    )


def test_debug_then_actual_base_parser_adopts_nil_maps_and_preserves_group_dictionary(
    tmp_path,
):
    provider, value = Provider(), GSGlyphsInfo.alloc()
    with using_info_provider(provider):
        value.initDebug()
    state = value._lifecycle
    group_map = state.name2Group
    path = tmp_path / "OwnedGlyphData.xml"
    path.write_text(
        '<glyphData><glyph name="owned.debug" unicode="0041" category="Letter" script="latin"/></glyphData>'
    )
    assert value.loadGlyphDataFromURL_error_(URL(path), None) is True
    record = state.index.records[0]
    assert (
        state.index.names["owned.debug"] is record
        and state.index.unicodes["0041"] is record
    )
    assert value.infoFromDataForName_("owned.debug") is value.infoFromDataForUnicode_(
        "0041"
    )
    assert state.name2Group is group_map and state.queue.maximum == 7
    assert provider.events == ["allocate-queue", "processors", ("limit", 7)]


def test_debug_missing_base_file_preserves_nil_fields_and_returns_false_nil(tmp_path):
    provider, value = Provider(), GSGlyphsInfo.alloc()
    with using_info_provider(provider):
        value.initDebug()
    state = value._lifecycle
    group_map = state.name2Group
    path = tmp_path / "missing.xml"
    slot = InfoErrorSlot()
    assert value.loadGlyphDataFromURL_error_(URL(path), slot) is False
    assert slot.value is None
    assert (state.index.records, state.index.names, state.index.unicodes) == (
        None,
        None,
        None,
    )
    assert state.name2Group is group_map


def test_debug_unknown_row_prefix_refuses_without_inventing_parser_failure(tmp_path):
    value = GSGlyphsInfo.alloc()
    with using_info_provider(Provider()):
        value.initDebug()
    path = tmp_path / "unqualified.xml"
    path.write_text("<glyph broken")
    state = value._lifecycle
    with pytest.raises(UnsupportedCapability) as caught:
        value.loadGlyphDataFromURL_error_(URL(path), None)
    assert caught.value.capability == "GSGlyphsInfo.baseData.rowPrefix"
    assert (state.index.records, state.index.names, state.index.unicodes) == (
        None,
        None,
        None,
    )


def test_debug_preserves_the_existing_owned_raw_index_without_a_lifecycle():
    from fontlab_glyport.model.info_records import GlyphInfoIndex

    index = GlyphInfoIndex()
    rows, names, codes = index.records, index.names, index.unicodes
    value = GSGlyphsInfo._from_index(index)
    with using_info_provider(Provider()):
        assert value.initDebug() is value
    assert value._fixed_index is index is value._lifecycle.index
    assert index.records is rows and index.names is names and index.unicodes is codes


def test_debug_reads_current_queue_after_processor_query():
    value, provider = GSGlyphsInfo.alloc(), Provider()
    replacement = Queue(provider)

    def processors():
        value._lifecycle.queue = replacement
        return 11

    provider.active_processor_count = processors
    with using_info_provider(provider):
        value.initDebug()
    assert value._lifecycle.queue is replacement and replacement.maximum == 11
    assert provider.queues[0].maximum is None


def test_debug_keeps_existing_shared_flag_without_publishing_a_new_singleton(
    monkeypatch,
):
    value = GSGlyphsInfo.alloc()
    value._shared_info_flag = True
    shared = object()
    monkeypatch.setattr(GSGlyphsInfo, "_shared", shared)
    with using_info_provider(Provider()):
        value.initDebug()
    assert value._lifecycle.shared and value._shared_info_flag
    assert GSGlyphsInfo._shared is shared


def test_debug_invalid_python_receiver_is_not_a_native_abi_claim():
    with using_info_provider(Provider()), pytest.raises(TypeError, match="receiver"):
        GSGlyphsInfo.initDebug(object())


class SharedProvider(Provider):
    def __init__(self, fail=None):
        super().__init__(fail)
        self.pending = []

    def new_queue(self):
        queue = super().new_queue()

        def wait():
            self.events.append("wait")
            while self.pending:
                self.pending.pop(0)()

        queue.waitUntilAllOperationsAreFinished = wait
        return queue

    def add_observer(self, receiver, key, options, context):
        self.events.append(("observer", receiver, key, options, context))
        assert not self.pending, "Observer registration follows all queued work"
        if self.fail == "observer":
            raise RuntimeError("observer")


class Shared(GSGlyphsInfo):
    """Actual shared constructor with source-valid overrides of load selectors."""

    def loadSidebarInfoForDocument_(self, font):
        assert font is None
        p = self._lifecycle.provider
        p.events.append("sidebar")
        p.pending.append(lambda: p.events.append("sidebar-job"))

    def loadGlyphInfo(self):
        p = self._lifecycle.provider
        p.events.append("info")
        p.pending.append(lambda: p.events.append("info-job"))


@pytest.mark.parametrize("flag,added", [(0, True), (1, False), (2, True), (3, False)])
def test_shared_callback_retains_existing_state_and_registers_after_drain(
    monkeypatch, flag, added
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    p, value = SharedProvider(), Shared.alloc()
    local_url = object()
    state = value._lifecycle = InfoState(p, local_url)
    state.observer_flag = flag
    group_map = state.name2Group = {"owned": object()}
    with using_info_provider(p):
        assert value.init() is value
    assert GSGlyphsInfo._shared is value and value._lifecycle is state
    assert (
        state.shared and state.localURL is local_url and state.name2Group is group_map
    )
    assert state.observer_flag == (1 if added else flag)
    expected = [
        "allocate-queue",
        "processors",
        ("limit", 7),
        "sidebar",
        "info",
        "wait",
        "sidebar-job",
        "info-job",
    ]
    if added:
        expected += [
            ("observer", value, "values.GSScriptToPlaceholderFontPath", 0, None)
        ]
    assert p.events == expected


def test_shared_registration_failure_keeps_published_pointer_and_prior_flag(
    monkeypatch,
):
    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    p, value = SharedProvider("observer"), Shared.alloc()
    state = value._lifecycle = InfoState(p, None)
    state.observer_flag = 2
    with using_info_provider(p), pytest.raises(RuntimeError, match="observer"):
        value.init()
    assert GSGlyphsInfo._shared is value and value._lifecycle is state
    assert state.shared and state.observer_flag == 2
    assert p.events[-1] == (
        "observer",
        value,
        "values.GSScriptToPlaceholderFontPath",
        0,
        None,
    )


def test_debug_actual_base_parse_error_preserves_nil_maps_and_group_identity(tmp_path):
    value = GSGlyphsInfo.alloc()
    with using_info_provider(Provider()):
        value.initDebug()
    state = value._lifecycle
    groups = state.name2Group
    path = tmp_path / "OwnedMalformedGlyphData.xml"
    path.write_text("<glyph name=/>")
    slot = InfoErrorSlot()
    assert value.loadGlyphDataFromURL_error_(URL(path), slot) is False
    assert slot.value is not None
    assert (state.index.records, state.index.names, state.index.unicodes) == (
        None,
        None,
        None,
    )
    assert state.name2Group is groups
