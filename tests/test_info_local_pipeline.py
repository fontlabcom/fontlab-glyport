# this_file: tests/test_info_local_pipeline.py
"""Owned source oracles for constructor, reload and exception boundaries."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo
from fontlab_glyport.glyphsapp.info_runtime import (
    InfoErrorSlot,
    InfoNativeException,
    using_info_provider,
)


class Queue:
    def __init__(self, events):
        self.events, self.pending = events, []

    def addOperationWithBlock_(self, callback):
        self.events.append("enqueue")
        self.pending.append(callback)

    def setMaxConcurrentOperationCount_(self, count):
        self.maxConcurrentOperationCount = count

    def waitUntilAllOperationsAreFinished(self):
        self.events.append("wait")
        while self.pending:
            self.pending.pop(0)()


class Provider:
    def __init__(self):
        self.events = []
        self.queues = []
        self.matras = {"owned": "first"}

    def new_queue(self):
        self.events.append("queue")
        queue = Queue(self.events)
        self.queues.append(queue)
        return queue

    def active_processor_count(self):
        return 3

    def resource_url(self, name, extension):
        self.events.append(("resource", name, extension))
        return name

    def load_dictionary(self, url):
        self.events.append(("dictionary", url))
        return self.matras

    def present_error(self, error):
        self.events.append(("error", error))

    def log(self, error):
        self.events.append(("log", error))

    def compare(self, a, b):
        return (a > b) - (a < b)

    def distinct_values(self, rows, field):
        """Explicit owned nil policy, without claiming native Foundation parity."""
        return list(
            dict.fromkeys(
                getattr(row, field) for row in rows if getattr(row, field) is not None
            )
        )

    def notify(self, manager, phase, key):
        self.events.append((phase, key))


class URL:
    def __init__(self, path):
        self.value = path

    def path(self):
        return self.value


class Local(GSGlyphsInfo):
    """Keep constructor dispatch real while recording unavailable host effects."""

    def loadSidebarInfoForDocument_(self, document):
        self._lifecycle.provider.events.append(("sidebar", document))

    def updateComponentsInfos(self):
        self._lifecycle.provider.events.append("components")


@pytest.fixture
def shared(monkeypatch):
    from fontlab_glyport.glyphsapp.info_runtime import InfoState

    provider = Provider()
    value = GSGlyphsInfo.alloc()
    value._lifecycle = InfoState(provider, None, True)
    value._fixed_index = value._lifecycle.index
    value._lifecycle.scriptIDs = ["shared", "shared"]
    value._lifecycle.subCategories = ["SharedSub", "SharedSub"]
    monkeypatch.setattr(GSGlyphsInfo, "_shared", value)
    return value


def make_local(provider, url):
    with using_info_provider(provider):
        return Local.alloc().initWithLocalFile_(url)


def test_local_constructor_keeps_receiver_url_and_dynamic_document_dispatch(shared):
    provider, url, document = Provider(), URL(None), object()
    receiver = Local.alloc()
    with using_info_provider(provider):
        result = receiver.initWithLocalFile_forFont_(url, document)
    assert result is receiver and result is not shared
    state = result._lifecycle
    assert state.localURL is url and state.shared is False
    assert state.queue.maxConcurrentOperationCount == 3
    assert provider.events[:2] == ["queue", ("sidebar", document)]
    assert provider.events[-1] == "wait"
    assert not state.queue.pending
    assert not hasattr(state, "document")


def test_missing_provider_is_explicit_and_does_not_initialize_receiver():
    receiver = Local.alloc()
    with pytest.raises(UnsupportedCapability, match="provider"):
        receiver.initWithLocalFile_(None)
    assert "_lifecycle" not in vars(receiver)


def test_reload_retains_old_maps_and_rows_without_relisting_them(shared, tmp_path):
    folder = tmp_path / "owned"
    folder.mkdir()
    data = folder / "GlyphData.xml"
    data.write_text(
        '<glyph name="owned.a" unicode="0041" script="fleet"/>'
        '<glyph name="owned.b" unicode="0042"/>'
    )
    provider = Provider()

    class Files(Local):
        @classmethod
        def foldersForCustomInfoForFolder_(cls, path):
            return [path]

        def loadCustomIcons_(self, path):
            self._lifecycle.provider.events.append(("icons", path))

        def loadCustomGroupsFromFolder_(self, path):
            self._lifecycle.provider.events.append(("groups", path))

    with using_info_provider(provider):
        manager = Files.alloc().initWithLocalFile_(URL(str(folder)))
    index = manager._index
    a, b = index.names["owned.a"], index.names["owned.b"]
    names, codes, first_rows = index.names, index.unicodes, index.records
    assert first_rows == [a, b] and [a.index, b.index] == [0, 1]
    data.write_text('<glyph name="owned.a" script="changed"/>')
    manager.loadGlyphInfo()
    assert index.records == [] and index.records is not first_rows
    assert index.names is names and index.unicodes is codes
    assert index.names["owned.a"] is a and index.names["owned.b"] is b
    assert a.script == "changed" and a.index == 0 and b.index == 1
    assert manager._lifecycle.queue.pending  # Standalone local load has no wait.
    data.write_text('<glyph name="owned.a"/><glyph name="owned.c"/>')
    manager.loadGlyphInfo()
    c = index.names["owned.c"]
    assert index.records == [c] and c.index == a.index == 0
    assert manager._lifecycle.scriptIDs.count("shared") == 6
    assert manager._lifecycle.subCategories.count("SharedSub") == 2


@pytest.mark.parametrize(
    "result,error,presented",
    [(False, None, False), (False, "owned", True), (True, "owned", False)],
)
def test_false_error_is_presented_conditionally_without_stopping_pipeline(
    shared, result, error, presented
):
    provider = Provider()

    class Failure(Local):
        def loadGlyphDataError_(self, slot):
            assert slot.value is None
            slot.value = error
            return result

    with using_info_provider(provider):
        manager = Failure.alloc().initWithLocalFile_(URL("owned"))
    assert (("error", error) in provider.events) is presented
    assert "components" in provider.events
    assert manager._lifecycle.iMatraCombinations is provider.matras
    assert provider.events[-1] == "wait"


@pytest.mark.parametrize(
    "failure",
    [
        UnsupportedCapability("owned", capability="owned"),
        RuntimeError("owned"),
        InfoNativeException("outside"),
    ],
)
def test_loader_exception_propagates_without_constructor_final_drain(shared, failure):
    provider = Provider()

    class Failure(Local):
        def loadSidebarInfoForDocument_(self, document):
            self._lifecycle.queue.addOperationWithBlock_(
                lambda: provider.events.append("sidebar-job")
            )

        def loadGlyphDataError_(self, slot):
            raise failure

    with using_info_provider(provider), pytest.raises(type(failure)) as caught:
        Failure.alloc().initWithLocalFile_(URL("owned"))
    assert caught.value is failure
    assert provider.queues[0].pending
    assert "wait" not in provider.events and "components" not in provider.events
    assert not any(
        isinstance(x, tuple) and x[0] == "dictionary" for x in provider.events
    )


def test_only_marked_component_exception_continues_to_index_resource_and_wait(shared):
    provider = Provider()

    class Failure(Local):
        def updateComponentsInfos(self):
            self._lifecycle.provider.events.append("components")
            raise InfoNativeException("caught")

    with using_info_provider(provider):
        manager = Failure.alloc().initWithLocalFile_(URL(None))
    assert isinstance(
        provider.events[provider.events.index("components") + 1][1], InfoNativeException
    )
    assert manager._lifecycle.iMatraCombinations is provider.matras
    assert provider.events[-1] == "wait"


def test_internal_data_error_slot_nil_path_preserves_prior_value(shared):
    manager = make_local(Provider(), URL(None))
    sentinel = object()
    slot = InfoErrorSlot(sentinel)
    assert manager.loadGlyphDataError_(slot) is False
    assert slot.value is sentinel


def test_missing_matra_capability_propagates_after_component_changes(shared):
    provider = Provider()

    def refused(url):
        raise UnsupportedCapability("owned missing iMatra", capability="iMatra")

    provider.load_dictionary = refused
    with using_info_provider(provider), pytest.raises(UnsupportedCapability):
        Local.alloc().initWithLocalFile_(URL(None))
    assert "components" in provider.events and "wait" not in provider.events


def test_repeated_summary_reads_current_rows_twice_and_current_target_arrays(shared):
    from fontlab_glyport.glyphsapp.info_lifecycle import summarize

    provider = Provider()
    manager = make_local(provider, URL(None))
    state = manager._lifecycle
    state.index.records = [SimpleNamespace(script="zeta", subCategory="Wrong")]
    state.scriptIDs = ["", "repeat", "repeat"]
    state.categories = ["", "Letter", ""]
    state.subCategories = ["Halfform", ""]
    original_compare = provider.compare

    def replace_during_first_sort(a, b):
        state.index.records = [SimpleNamespace(script="ignored", subCategory="New")]
        return original_compare(a, b)

    state.index.records.append(SimpleNamespace(script="alpha", subCategory="Wrong2"))
    provider.compare = replace_during_first_sort
    summarize(manager)
    assert state.scriptIDs == ["repeat", "repeat", "alpha", "zeta"]
    assert state.subCategories == ["Halfform", "Conjunct", "New"]
    assert state.categories == ["Letter"]


def test_icon_sidebar_dispatch_is_noop_but_glyph_pipeline_runs(shared):
    provider = Provider()
    document = SimpleNamespace(fontType=lambda: 3)

    class Icon(Local):
        loadSidebarInfoForDocument_ = GSGlyphsInfo.loadSidebarInfoForDocument_

    with using_info_provider(provider):
        manager = Icon.alloc().initWithLocalFile_forFont_(URL(None), document)
    assert manager._lifecycle.allItem is None
    assert "components" in provider.events and provider.events[-1] == "wait"


@pytest.mark.parametrize(
    "phase", ["chinese", "components", "hangul", "did", "resource"]
)
def test_nil_url_typed_catch_has_exact_protected_interval(shared, phase):
    provider = Provider()
    failure = InfoNativeException(phase)

    def fail():
        raise failure

    class Global(Local):
        def loadGlyphDataError_(self, slot):
            self._lifecycle.provider.events.append("data")
            return False

        def _addChineseGlyphInfos(self):
            provider.events.append("chinese")
            if phase == "chinese":
                fail()

        def updateComponentsInfos(self):
            provider.events.append("components")
            if phase == "components":
                fail()

        def _addHangulGlyphInfos(self):
            provider.events.append("hangul")
            if phase == "hangul":
                fail()

        def didChangeValueForKey_(self, key):
            provider.events.append("did")
            if phase == "did":
                fail()

    if phase == "resource":
        provider.resource_url = lambda *args: fail()
    if phase in {"components", "hangul"}:
        with using_info_provider(provider):
            value = Global.alloc().initWithLocalFile_(None)
        assert ("log", failure) in provider.events and provider.events[-1] == "wait"
        assert value._lifecycle.iMatraCombinations is provider.matras
    else:
        with (
            using_info_provider(provider),
            pytest.raises(InfoNativeException) as caught,
        ):
            Global.alloc().initWithLocalFile_(None)
        assert caught.value is failure and "wait" not in provider.events
        assert ("log", failure) not in provider.events


def test_deferred_summary_failure_does_not_enter_component_handler(shared):
    provider = Provider()
    value = make_local(provider, URL(None))
    value.loadGlyphInfo()
    value._index.records = [
        SimpleNamespace(script="a", subCategory="x"),
        SimpleNamespace(script="b", subCategory="y"),
    ]
    failure = InfoNativeException("queued")

    def fail(a, b):
        raise failure

    provider.compare = fail
    with pytest.raises(InfoNativeException) as caught:
        value._lifecycle.queue.waitUntilAllOperationsAreFinished()
    assert caught.value is failure and ("log", failure) not in provider.events


def test_nil_collection_field_requires_explicit_foundation_policy(shared):
    from fontlab_glyport.glyphsapp.info_lifecycle import summarize

    provider = Provider()
    value = make_local(provider, URL(None))
    provider.distinct_values = None
    value._index.records = [SimpleNamespace(script=None, subCategory="x")]
    with pytest.raises(UnsupportedCapability, match="distinct_values"):
        summarize(value)


@pytest.mark.parametrize(
    "content,success,has_error",
    [
        ('<glyph name="base" unicode="0041"/>', True, False),
        ("tiny", False, False),
        ('<glyph name="bad" unicode="unfinished/>', False, True),
    ],
)
def test_base_entrypoint_writes_slot_only_on_failure_and_never_commits_private_partial_rows(
    tmp_path, content, success, has_error
):
    from fontlab_glyport.glyphsapp.info_runtime import InfoState

    value = GSGlyphsInfo.alloc()
    value._lifecycle = InfoState(Provider(), None)
    value._fixed_index = value._lifecycle.index
    path = tmp_path / "base.xml"
    path.write_text(content)
    sentinel = object()
    slot = InfoErrorSlot(sentinel)
    assert value.loadGlyphDataFromURL_error_(URL(str(path)), slot) is success
    if success:
        assert slot.value is sentinel and value._index.names["base"].unicode == "0041"
    else:
        assert (slot.value is not None) is has_error and slot.value is not sentinel
        assert value._index.records == [] and value._index.names == {}


def test_internal_custom_slot_preserves_success_then_reports_failure_without_rollback(
    shared, tmp_path
):
    value = make_local(Provider(), URL(None))
    good = tmp_path / "good.xml"
    bad = tmp_path / "bad.xml"
    later = tmp_path / "later.xml"
    good.write_text('<glyph name="first"/>')
    bad.write_text('<glyph name="second"/><glyph name="broken" unicode="unfinished/>')
    later.write_text('<glyph name="unvisited"/>')
    sentinel = object()
    slot = InfoErrorSlot(sentinel)
    assert value.loadCustomGlyphDataFromURL_error_(URL(str(good)), slot)
    assert slot.value is sentinel
    assert not value.loadLocalGlyphInfoFiles_error_(
        [URL(str(bad)), URL(str(later))], slot
    )
    assert slot.value.code() == 0x2AE2
    assert value._index.names["first"].name == "first"
    assert value._index.names["second"].name == "second"
    assert "unvisited" not in value._index.names


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("ordinary"), UnsupportedCapability("dependency", capability="owned")],
)
def test_ordinary_component_failure_propagates_without_drain(shared, failure):
    provider = Provider()

    class Failed(Local):
        def updateComponentsInfos(self):
            raise failure

    with using_info_provider(provider), pytest.raises(type(failure)) as caught:
        Failed.alloc().initWithLocalFile_(URL(None))
    assert caught.value is failure and "wait" not in provider.events
    assert not any(isinstance(e, tuple) and e[0] == "log" for e in provider.events)
