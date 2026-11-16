# this_file: tests/test_info_generated_integration.py
"""Real generator integration with owned graphs; no provider callback shortcut."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.glyph_info import GSGlyphInfo
from fontlab_glyport.glyphsapp.info_generated import assign_components
from fontlab_glyport.glyphsapp.info_manager import GSGlyphsInfo
from fontlab_glyport.glyphsapp.info_runtime import InfoState, using_info_provider
from fontlab_glyport.model.info_records import new_record


@pytest.fixture(autouse=True)
def fresh_shared_and_resources(monkeypatch):
    from fontlab_glyport.glyphsapp import info_sidebar_resources

    monkeypatch.setattr(GSGlyphsInfo, "_shared", None)
    monkeypatch.setattr(info_sidebar_resources, "_once_arrays", {})


def test_component_assignment_replaces_storage_and_preserves_lock_and_all_other_fields():
    target = new_record("owned.syllable")
    target._locked = True
    target.baseString = "keep base"
    target.unicharString = "keep cache"
    target._component_names = ["old name"]
    target._component_records = [new_record("old record")]
    target._unavailable_fields = frozenset({"components", "private_field"})
    first, second = new_record("owned.leading"), new_record("owned.vowel")
    parts = (GSGlyphInfo.from_record(first), GSGlyphInfo.from_record(second))
    before = vars(target).copy()
    assign_components(GSGlyphInfo.from_record(target), parts)
    assert target._component_names is None
    assert target._component_records == (first, second)
    assert (
        target._component_records[0] is first and target._component_records[1] is second
    )
    assert target._unavailable_fields == frozenset({"private_field"})
    for field in before.keys() - {
        "_component_names",
        "_component_records",
        "_unavailable_fields",
        "_public_view",
    }:
        assert vars(target)[field] is before[field], field
    assert GSGlyphInfo.from_record(target).components == list(parts)


def test_nil_target_is_inert_at_setter_boundary():
    assert assign_components(None, ()) is None


@pytest.mark.parametrize("position", ["target", "part"])
@pytest.mark.parametrize("frozen", [False, True])
def test_unknown_or_frozen_views_cannot_be_mutated_by_the_internal_adapter(
    position, frozen
):
    raw = new_record("owned")
    view = GSGlyphInfo.from_record(raw)
    unknown = (
        object.__new__(GSGlyphInfo) if frozen else SimpleNamespace(name="unqualified")
    )
    with pytest.raises(UnsupportedCapability):
        assign_components(
            unknown if position == "target" else view,
            (unknown if position == "part" else view,),
        )
    assert raw._component_records is None


class Queue:
    def __init__(self):
        self.pending, self.waits = [], 0

    def setMaxConcurrentOperationCount_(self, count):
        self.maximum = count

    def addOperationWithBlock_(self, callback):
        self.pending.append(callback)

    def waitUntilAllOperationsAreFinished(self):
        self.waits += 1
        while self.pending:
            self.pending.pop(0)()


class Resources:
    """Explicit invented four-list bank and filesystem/resource policies."""

    def __init__(self, path):
        self.path, self.queue = path, Queue()
        self.bank_calls = []
        self.bank = (("2FF0",), ("20000",), ("20001",), ("20002",))

    def new_queue(self):
        return self.queue

    def active_processor_count(self):
        return 2

    def localize(self, value):
        return value

    def compare(self, a, b):
        return (a > b) - (a < b)

    def resource_url(self, name, extension):
        return (
            SimpleNamespace(path=lambda: str(self.path))
            if name == "GlyphData"
            else name
        )

    def load_array(self, url):
        return []

    def load_dictionary(self, url):
        return {"owned": "matra"}

    def application_support_paths(self):
        return []

    def user_support_path(self):
        return str(self.path.parent)

    def directory_entries(self, path):
        return []

    def resolve_path(self, path):
        return path

    def load_property_list(self, path):
        return [], None

    def draw_emoji_icon(self, width, height, flipped):
        return SimpleNamespace(setName_=lambda name: None)

    def notify(self, *args):
        pass

    def chinese_codes(self, slot):
        self.bank_calls.append(slot)
        return self.bank[slot]


def test_full_nil_url_constructor_generates_actual_rows_and_links_owned_hangul(
    tmp_path,
):
    path = tmp_path / "base.xml"
    path.write_text(
        "".join(
            f'<glyph name="{name}" unicode="{code}" script="owned" category="Letter" subCategory="Other"/>'
            for name, code in [
                ("owned.a", "0041"),
                ("owned.leading", "1100"),
                ("owned.vowel", "1161"),
                ("owned.trailing", "11A8"),
                ("owned.lv", "AC00"),
                ("owned.lvt", "AC01"),
            ]
        )
    )
    provider = Resources(path)
    assert not hasattr(provider, "add_chinese") and not hasattr(
        provider, "enqueue_hangul"
    )
    with using_info_provider(provider):
        manager = GSGlyphsInfo.alloc().initWithLocalFile_(None)
    index, state = manager._index, manager._lifecycle
    assert state.shared is False and provider.queue.waits == 2
    assert provider.queue.maximum == 2 and not provider.queue.pending
    assert provider.bank_calls == [0, 1, 2, 3]
    assert len(index.records) == 6 + 38206 + 4
    # Independent boundaries, gap and each job family, rather than a fake callback count.
    for code in [
        "2E80",
        "2E99",
        "2E9B",
        "2EF3",
        "2F00",
        "2FD5",
        "3400",
        "57EE",
        "57EF",
        "7BDC",
        "7BDD",
        "9FFF",
        "F900",
        "FAD9",
        "30000",
        "3134A",
        "31350",
        "323AF",
        "2EBF0",
        "2EE5F",
        "2FF0",
        "20000",
        "20001",
        "20002",
    ]:
        row = index.raw_unicode(code)
        assert row is not None and row.script == "han" and row.category == "Letter", (
            code
        )
        assert row._locked and index.names[row.name] is row, code
    assert index.raw_unicode("2E9A") is None and index.raw_unicode("3134B") is None
    assert index.raw_unicode("2E80").subCategory == "Radical"
    assert index.raw_unicode("F900").subCategory == "Compatibility"
    assert index.raw_unicode("30000").sortName == "unj30000"
    assert [row.index for row in index.records] == list(range(len(index.records)))
    leading, vowel, trailing = (
        index.raw_unicode(code) for code in ["1100", "1161", "11A8"]
    )
    lv, lvt = index.raw_unicode("AC00"), index.raw_unicode("AC01")
    assert lv._component_records == (leading, vowel)
    assert lvt._component_records == (leading, vowel, trailing)
    assert lv.baseString == "가" and lvt.baseString == "각"
    assert lv._locked and lvt._locked
    # Source summary precedes the generation barrier, so it need not summarize han.
    assert "han" not in state.scriptIDs and "owned" in state.scriptIDs


def test_public_hangul_entrypoint_uses_current_manager_after_enqueue_and_per_lookup():
    views = {}
    for code in ["AC00", "1100", "1161"]:
        views[code] = GSGlyphInfo.from_record(new_record(code))
    replacement = GSGlyphInfo.from_record(new_record("replacement vowel"))
    calls = []

    class Current(GSGlyphsInfo):
        def glyphInfoForUnicode_(self, code):
            calls.append(code)
            if code == "1100":
                views["1161"] = replacement
            return views.get(code, GSGlyphInfo.from_record(new_record(code)))

    manager = Current.alloc()
    manager._lifecycle = InfoState(object(), None)
    manager._lifecycle.queue = Queue()
    manager._addHangulGlyphInfos()
    assert not calls and len(manager._lifecycle.queue.pending) == 1
    target = GSGlyphInfo.from_record(new_record("new target after enqueue"))
    views["AC00"] = target
    manager._lifecycle.queue.waitUntilAllOperationsAreFinished()
    assert calls[:3] == ["AC00", "1100", "1161"] and len(calls) == 44289
    assert target.components == [views["1100"], replacement]


def test_required_embedded_bank_gap_does_not_become_successful_constructor(tmp_path):
    path = tmp_path / "base.xml"
    path.write_text(
        '<glyph name="owned.a" unicode="0041" script="owned" subCategory="Other"/>'
    )
    provider = Resources(path)
    provider.chinese_codes = lambda slot: None
    manager = GSGlyphsInfo.alloc()
    with using_info_provider(provider), pytest.raises(UnsupportedCapability):
        manager.initWithLocalFile_(None)
    assert provider.queue.waits == 1 and provider.queue.pending
    assert [row.name for row in manager._index.records] == ["owned.a"]
    assert manager._lifecycle.iMatraCombinations is None
