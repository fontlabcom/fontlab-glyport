# this_file: tests/test_info_document_loading.py
"""Owned document source oracles; no FontLab/Foundation/observer runtime calls."""

from threading import Event, Thread
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.application import GSDocument
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo


class URL:
    def __init__(self, name, parent=None, events=None):
        self.name, self.parent = name, parent
        self.events = events if events is not None else []

    def isEqual_(self, other):
        self.events.append(("equal", self, other))
        return isinstance(other, URL) and self.name == other.name

    def URLByDeletingLastPathComponent(self):
        self.events.append(("parent", self))
        return self.parent


class Files:
    def __init__(self, url=None, file_type=None):
        self.url, self.type, self.events = url, file_type, []

    def file_url(self, document):
        self.events.append(("url", document))
        return self.url

    def set_file_url(self, document, url):
        self.events.append(("super", document, url))
        self.url = url

    def file_type(self, document):
        self.events.append(("type", document))
        return self.type


class Lock:
    def __init__(self, events):
        self.events, self.depth = events, 0

    def __enter__(self):
        self.depth += 1
        self.events.append("enter")

    def __exit__(self, *exception):
        self.events.append("exit")
        self.depth -= 1


def document(url=None, file_type=None, cls=GSDocument):
    doc = cls(SimpleNamespace(_check=lambda: None))
    doc._file_primitives = Files(url, file_type)
    return doc


def allocate(monkeypatch, initializer):
    receiver = SimpleNamespace(initWithLocalFile_forFont_=initializer)
    monkeypatch.setattr(GSGlyphsInfo, "alloc", classmethod(lambda cls: receiver))
    return receiver


def test_local_load_parent_precedes_lock_and_fixed_allocation_precedes_current_font(
    monkeypatch,
):
    events, parent, answer, current_font = [], object(), object(), object()

    class Current(GSDocument):
        @property
        def font(self):
            events.append("font")
            return current_font

    doc = document(URL("file", parent, events), cls=Current)
    doc._glyph_info_lock = Lock(events)
    old = doc._local_glyph_info = object()

    def initialize(folder, font):
        events.append(("init", folder, font))
        assert doc._local_glyph_info is old, "Replacement must follow initialization"
        return answer

    receiver = SimpleNamespace(initWithLocalFile_forFont_=initialize)

    def alloc(cls):
        events.append("alloc")
        assert cls is GSGlyphsInfo, "Document allocates the fixed manager class"
        return receiver

    monkeypatch.setattr(GSGlyphsInfo, "alloc", classmethod(alloc))
    assert doc.loadCustomGlyphsData() is True
    assert events == [
        ("parent", doc._file_primitives.url),
        "enter",
        "alloc",
        "font",
        ("init", parent, current_font),
        "exit",
    ]
    assert doc._local_glyph_info is answer


@pytest.mark.parametrize("nil_url", [True, False])
def test_nil_parent_clears_local_without_allocator_or_font_read(monkeypatch, nil_url):
    class NoFont(GSDocument):
        @property
        def font(self):
            pytest.fail("Nil-parent branch must not read font")

    doc = document(None if nil_url else URL("file", None), cls=NoFont)
    doc._local_glyph_info = object()
    monkeypatch.setattr(
        GSGlyphsInfo,
        "alloc",
        classmethod(lambda cls: pytest.fail("Unexpected allocation")),
    )
    assert doc.loadCustomGlyphsData() is True
    assert doc._local_glyph_info is None


def test_initializer_nil_return_replaces_old_local_without_manufacturing_manager(
    monkeypatch,
):
    doc = document(URL("file", object()))
    doc._local_glyph_info = object()
    allocate(monkeypatch, lambda folder, font: None)
    assert doc.loadCustomGlyphsData() is True
    assert doc._local_glyph_info is None


@pytest.mark.parametrize("stage", ["parent", "allocation", "font", "init"])
def test_load_errors_preserve_old_manager_and_release_document_lock(monkeypatch, stage):
    class Broken(GSDocument):
        @property
        def font(self):
            if stage == "font":
                raise ValueError("font")
            return self._font

    events = []
    doc = document(URL("file", object()), cls=Broken)
    doc._glyph_info_lock = Lock(events)
    old = doc._local_glyph_info = object()

    def fail(*args):
        raise ValueError(stage)

    if stage == "parent":
        doc._file_primitives.url.URLByDeletingLastPathComponent = fail
    receiver = allocate(
        monkeypatch, fail if stage == "init" else lambda *args: object()
    )
    if stage == "allocation":
        monkeypatch.setattr(GSGlyphsInfo, "alloc", classmethod(fail))
    with pytest.raises(ValueError, match=stage):
        doc.loadCustomGlyphsData()
    assert doc._local_glyph_info is old
    assert doc._glyph_info_lock.depth == 0
    assert events == ([] if stage == "parent" else ["enter", "exit"])
    assert receiver is not None


def test_getter_releases_document_lock_before_shared_fallback(monkeypatch):
    events, shared = [], object()
    doc = document()
    doc._glyph_info_lock = Lock(events)

    def fallback(cls):
        assert doc._glyph_info_lock.depth == 0, (
            "Shared initialization is outside document synchronization"
        )
        events.append("shared")
        return shared

    monkeypatch.setattr(GSGlyphsInfo, "sharedManager", classmethod(fallback))
    assert doc.glyphsInfo() is shared
    assert events == ["enter", "exit", "shared"]
    local = doc._local_glyph_info = object()
    assert doc.valueForKey_("glyphsInfo") is local
    assert events == ["enter", "exit", "shared", "enter", "exit"]


def test_concurrent_getter_waits_for_constructor_and_observes_same_replacement(
    monkeypatch,
):
    entered, release, reading, observed = Event(), Event(), Event(), []
    doc = document(URL("file", object()))
    old, new = object(), object()
    doc._local_glyph_info = old

    def initialize(*args):
        entered.set()
        assert release.wait(5), "Test constructor timed out"
        return new

    allocate(monkeypatch, initialize)
    errors = []

    def load():
        try:
            doc.loadCustomGlyphsData()
        except BaseException as error:  # noqa: BLE001 - collect every worker-thread failure for assertion in the parent thread
            errors.append(error)

    def read():
        reading.set()
        observed.append(doc.glyphsInfo())

    writer, reader = Thread(target=load), Thread(target=read)
    writer.start()
    try:
        assert entered.wait(5), "Constructor did not start"
        reader.start()
        assert reading.wait(5), "Reader did not start"
        assert not observed, (
            "Read must not observe old value during synchronized construction"
        )
    finally:
        release.set()
        writer.join(5)
        if reader.ident is not None:
            reader.join(5)
    assert not writer.is_alive() and not reader.is_alive()
    assert errors == [] and observed == [new]


@pytest.mark.parametrize("old,new", [(None, None), (URL("same"), URL("same"))])
def test_equal_url_only_calls_super_even_when_observers_and_loader_exist(old, new):
    class Equal(GSDocument):
        def stopObservingFile(self):
            pytest.fail("Equal URL must not stop observers")

        def loadCustomGlyphsData(self):
            pytest.fail("Equal URL must not reload")

    doc = document(old, cls=Equal)
    assert doc.setFileURL_(new) is None
    assert doc._file_primitives.events == [("url", doc), ("super", doc, new)]
    assert doc._file_primitives.url is new, (
        "Equal-but-distinct URL still reaches superclass setter"
    )


@pytest.mark.parametrize("monitor", [False, True])
@pytest.mark.parametrize(
    "old_nil,new_nil", [(False, False), (True, False), (False, True)]
)
def test_changed_url_dispatches_current_receiver_in_source_order(
    monitor, old_nil, new_nil
):
    events = []

    class Changed(GSDocument):
        def stopObservingFile(self):
            events.append(("stop", self.fileURL()))

        def shouldMonitorFile_(self, file_type):
            events.append(("monitor", file_type))
            return monitor

        def startObservingFileIfSupported(self):
            events.append(("start", self.fileURL()))

        def updateFileObservers(self):
            events.append(("update", self.fileURL()))

        def loadCustomGlyphsData(self):
            events.append(("load", self.fileURL()))
            return False

    old = None if old_nil else URL("old")
    new = None if new_nil else URL("new")
    doc = document(old, "owned-type", Changed)
    doc.setFileURL_(new)
    expected = [("stop", old), ("monitor", "owned-type")]
    if monitor:
        expected.append(("start", new))
    expected += [("update", new), ("load", new)]
    assert events == expected
    assert doc._file_primitives.events.index(
        ("super", doc, new)
    ) < doc._file_primitives.events.index(("type", doc))


def test_changed_url_without_optional_observer_selectors_still_loads(monkeypatch):
    doc = document(URL("old"), "unsupported-type")
    allocate(monkeypatch, lambda *args: pytest.fail("Nil parent must clear"))
    doc.setFileURL_(URL("new"))
    assert doc._local_glyph_info is None


@pytest.mark.parametrize(
    "stage", ["stop", "super", "type", "monitor", "start", "update", "load"]
)
def test_url_failure_stops_at_actual_stage_without_rollback_or_continuation(stage):
    events = []

    def step(name):
        events.append(name)
        if stage == name:
            raise RuntimeError(name)

    class Failing(GSDocument):
        def stopObservingFile(self):
            step("stop")

        def shouldMonitorFile_(self, value):
            step("monitor")
            return True

        def startObservingFile(self):
            step("start")

        def updateFileObservers(self):
            step("update")

        def loadCustomGlyphsData(self):
            step("load")

    old, new = URL("old"), URL("new")
    doc = document(old, cls=Failing)
    primitive = doc._file_primitives

    def set_url(document, value):
        step("super")
        primitive.url = value

    def get_type(document):
        step("type")
        return "type"

    primitive.set_file_url, primitive.file_type = set_url, get_type
    with pytest.raises(RuntimeError, match=stage):
        doc.setFileURL_(new)
    sequence = ["stop", "super", "type", "monitor", "start", "update", "load"]
    assert events == sequence[: sequence.index(stage) + 1]
    assert primitive.url is (old if stage in ("stop", "super") else new)


@pytest.mark.parametrize(
    "file_type,expected",
    [
        ("com.schriftgestaltung.glyphs", True),
        ("org.unifiedfontobject.ufo", True),
        ("com.glyphsapp.glyphspackage", True),
        ("com.glyphsapp.iconset", True),
        (None, False),
        ("", False),
        ("COM.GLYPHSAPP.ICONSET", False),
    ],
)
def test_monitoring_uses_exact_source_type_strings(file_type, expected):
    assert document().shouldMonitorFile_(file_type) is expected


def test_monitoring_forwards_string_selector_in_short_circuit_source_order():
    seen = []

    class Kind:
        def isEqualToString_(self, literal):
            seen.append(literal)
            return literal == "org.unifiedfontobject.ufo"

    assert document().shouldMonitorFile_(Kind()) is True
    assert seen == ["com.schriftgestaltung.glyphs", "org.unifiedfontobject.ufo"]


def test_observer_start_checks_current_receiver_and_keeps_absence_explicit():
    doc = document()
    assert doc.startObservingFileIfSupported() is None
    events = []

    class Observing(GSDocument):
        def startObservingFile(self):
            events.append(self)

    observed = document(cls=Observing)
    assert observed.startObservingFileIfSupported() is None
    assert events == [observed]


@pytest.mark.parametrize(
    "selector,args",
    [
        ("fileURL", ()),
        ("fileType", ()),
        ("setFileURL_", (None,)),
        ("loadCustomGlyphsData", ()),
    ],
)
def test_missing_file_primitives_refuse_with_typed_capability(selector, args):
    doc = GSDocument(SimpleNamespace(_check=lambda: None))
    with pytest.raises(UnsupportedCapability):
        getattr(doc, selector)(*args)


def test_unqualified_url_and_type_operations_refuse_without_python_coercion():
    doc = document(object())
    with pytest.raises(UnsupportedCapability, match="URLByDeletingLastPathComponent"):
        doc.loadCustomGlyphsData()
    with pytest.raises(UnsupportedCapability, match="isEqual_"):
        doc.setFileURL_(object())
    with pytest.raises(UnsupportedCapability, match="isEqualToString_"):
        doc.shouldMonitorFile_(object())


def test_real_fixed_allocator_requires_real_local_initializer_provider_and_preserves_old():
    from fontlab_glyport.glyphsapp.info_runtime import using_info_provider

    old_url, new_url = URL("old"), URL("new", object())
    doc = document(old_url, "unsupported")
    old_manager = doc._local_glyph_info = object()
    with using_info_provider(None), pytest.raises(UnsupportedCapability) as raised:
        doc.setFileURL_(new_url)
    assert raised.value.capability == "GSGlyphsInfo.initialization.provider"
    assert doc._local_glyph_info is old_manager
    assert doc._file_primitives.url is new_url, (
        "Later constructor failure does not undo the superclass URL setter"
    )
    assert doc.glyphsInfo() is old_manager, (
        "Constructor failure releases synchronization"
    )


def test_real_allocator_reaches_current_font_type_boundary_without_native_inference():
    from fontlab_glyport.glyphsapp.info_runtime import using_info_provider
    from fontlab_glyport.model import Model
    from fontlab_glyport.model.fake_backend import FakeBackend

    font = Model(FakeBackend()).font
    doc = font.parent
    doc._file_primitives = Files(URL("file", object()))
    old = doc._local_glyph_info = object()
    queue = SimpleNamespace(setMaxConcurrentOperationCount_=lambda value: None)
    provider = SimpleNamespace(
        new_queue=lambda: queue, active_processor_count=lambda: 1
    )
    with using_info_provider(provider), pytest.raises(UnsupportedCapability) as raised:
        doc.loadCustomGlyphsData()
    assert raised.value.capability == "GSFont.fontType", (
        "Do not manufacture a FontLab-to-Glyphs fontType mapping"
    )
    assert doc.glyphsInfo() is old


def test_reentrant_constructor_can_select_old_manager_and_documents_have_separate_locks(
    monkeypatch,
):
    doc, other = document(URL("file", object())), document()
    assert doc._glyph_info_lock is not other._glyph_info_lock
    old, new = object(), object()
    doc._local_glyph_info = old

    def initialize(folder, font):
        assert doc.glyphsInfo() is old, (
            "Objective-C synchronized document access is recursive"
        )
        return new

    allocate(monkeypatch, initialize)
    assert doc.loadCustomGlyphsData() is True
    assert doc.glyphsInfo() is new


def test_missing_superclass_primitive_is_not_fabricated_even_for_equal_urls():
    doc = document()
    doc._file_primitives = SimpleNamespace(file_url=lambda document: None)
    with pytest.raises(UnsupportedCapability) as raised:
        doc.setFileURL_(None)
    assert raised.value.capability == "GSDocument.file_primitives.set_file_url"


def test_optional_selector_descriptor_failure_propagates_before_superclass_write():
    class BrokenObserver(GSDocument):
        @property
        def stopObservingFile(self):
            raise RuntimeError("observer descriptor")

    old, new = URL("old"), URL("new")
    doc = document(old, cls=BrokenObserver)
    with pytest.raises(RuntimeError, match="observer descriptor"):
        doc.setFileURL_(new)
    assert doc._file_primitives.url is old


def test_string_subclass_uses_explicit_string_primitive_without_python_equality():
    seen = []

    class Kind(str):
        def isEqualToString_(self, literal):
            seen.append(literal)
            return True

    assert document().shouldMonitorFile_(Kind("other")) is True
    assert seen == ["com.schriftgestaltung.glyphs"]


def test_real_document_allocator_local_parser_sidebar_queue_and_index_remain_connected(
    monkeypatch, tmp_path
):
    """Only OS discovery/URL primitives are owned; no constructor/loader mocks."""
    from fontlab_glyport.glyphsapp import info_sidebar_resources
    from fontlab_glyport.glyphsapp.info_runtime import InfoState, using_info_provider
    from fontlab_glyport.model.custom_info_discovery import discover_folder

    folder = tmp_path / "owned-font-folder"
    folder.mkdir()
    data = folder / "GlyphData.xml"
    data.write_text(
        '<glyph name="Qowned" unicode="0041" script="latin" category="Letter" subCategory="Other"/>'
    )
    events = []

    class Queue:
        def __init__(self):
            self.pending = []

        def setMaxConcurrentOperationCount_(self, value):
            self.limit = value

        def addOperationWithBlock_(self, callback):
            events.append("enqueue")
            self.pending.append(callback)

        def waitUntilAllOperationsAreFinished(self):
            events.append("wait")
            while self.pending:
                self.pending.pop(0)()

    queue = Queue()
    arrays = {
        "defaultCategories": [{"name": "Owned categories", "id": "OWNED"}],
        "defaultLanguages": [{"name": "Owned language", "id": "LANG", "visible": True}],
        "StandardFilter": [],
    }
    matras = {"owned": "resource"}
    provider = SimpleNamespace(
        new_queue=lambda: queue,
        active_processor_count=lambda: 2,
        localize=lambda text: text,
        resource_url=lambda name, extension: name,
        load_array=lambda url: arrays[url],
        load_dictionary=lambda url: matras,
        application_support_paths=list,
        user_support_path=lambda: str(tmp_path / "owned-support"),
        directory_entries=lambda path: [],
        resolve_path=lambda path: path,
        load_property_list=lambda path: (None, None),
        compare=lambda left, right: (left > right) - (left < right),
        notify=lambda manager, phase, key: events.append((phase, key)),
        log=lambda value: pytest.fail(f"Unexpected log: {value}"),
        present_error=lambda value: pytest.fail(f"Unexpected error: {value}"),
    )

    class PathURL(URL):
        def path(self):
            return self.name

    discovered = []

    def owned_discovery(cls, path):
        discovered.append(path)
        # Preserve the actual pure filtering/resolution/URL algorithm. The
        # explicit fixture lists one file only in its authored folder.
        return discover_folder(
            path,
            entries=lambda current: [str(data)] if current == str(folder) else [],
            resolve=lambda current: current,
            make_url=PathURL,
        )

    monkeypatch.setattr(
        GSGlyphsInfo, "findCustomGlyphDataInFolder_", classmethod(owned_discovery)
    )
    monkeypatch.setattr(info_sidebar_resources, "_once_arrays", {})
    shared = GSGlyphsInfo.alloc()
    shared._lifecycle = InfoState(provider, None, True)
    shared._fixed_index = shared._lifecycle.index
    shared._lifecycle.scriptIDs = ["shared-script"]
    shared._lifecycle.subCategories = ["SharedSub"]
    monkeypatch.setattr(GSGlyphsInfo, "_shared", shared)
    parent = PathURL(str(folder))
    font = SimpleNamespace(fontType=lambda: 0, _check=lambda: None)
    doc = GSDocument(font)
    doc._file_primitives = Files(URL("font-file", parent))
    previous = doc._local_glyph_info = object()
    with using_info_provider(provider):
        assert doc.loadCustomGlyphsData() is True
    loaded = doc.glyphsInfo()
    assert (
        type(loaded) is GSGlyphsInfo and loaded is not previous and loaded is not shared
    )
    assert (
        loaded._lifecycle.provider is provider and loaded._lifecycle.localURL is parent
    )
    assert loaded._lifecycle.index is loaded._index
    assert loaded._index.shared is shared._index
    assert doc.valueForKey_("glyphsInfo") is loaded
    row = loaded._index.names["Qowned"]
    assert loaded._index.records == [row] and loaded._index.unicodes["0041"] is row
    assert (
        row.script == "latin"
        and row.category == "Letter"
        and row.index == 0
        and row._locked is True
    )
    assert loaded.infoFromDataForName_("Qowned")._resolved_record is row
    assert loaded._lifecycle.categoriesGroup.subItems[0].identifier == "OWNED"
    assert loaded._lifecycle.languagesGroup.subItems[0].identifier == "LANG"
    assert loaded._lifecycle.filterGroups[0].identifier == "FILTERS"
    assert loaded._lifecycle.iMatraCombinations is matras
    assert loaded._lifecycle.queue is queue and queue.limit == 2 and not queue.pending
    assert events == ["enqueue", ("will", "glyphInfos"), "enqueue", "wait"]
    assert discovered == [
        str(folder),
        str(folder / "Info"),
        str(tmp_path),
        str(tmp_path / "Info"),
    ]
