# this_file: tests/test_info_sidebar_support.py
"""Independent owned SidebarItem state/ordering oracles from retained C/ARM."""
import gc
from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_runtime import InfoNativeException
from fontlab_glyport.glyphsapp.info_sidebar import SidebarItem


class Provider:
    def __init__(self):
        self.events, self.defaults, self.pending = [], {}, []

    def defaults_bool_for_key(self, key):
        self.events.append(("read", key))
        return self.defaults.get(key, False)

    def defaults_set_bool_for_key(self, value, key):
        self.events.append(("write", value, key))
        self.defaults[key] = value

    def schedule_count_update(self, item, delay):
        self.events.append(("schedule", item, delay))
        self.pending.append(item._run_count_update)

    def compile_predicate(self, text, *args):
        self.events.append(("compile", text, args))
        if text == "bad":
            raise InfoNativeException("owned bad predicate")
        return SimpleNamespace(predicateFormat=text)

    def dispatch_main(self, callback):
        self.pending.append(callback)

    def show_exception_alert(self, exception):
        self.events.append(("alert", str(exception)))


def owned():
    item = SidebarItem()
    item._provider = Provider()
    return item


@pytest.mark.parametrize("selector,field", [
    ("setName_", "name"), ("setIdentifier_", "identifier"),
    ("setPredicate_", "predicate"), ("setIconName_", "iconName"),
    ("setCodes_", "codes"), ("setFilePath_", "filePath"),
    ("setBadgeString_", "badgeString"), ("setUnicharString_", "unicharString"),
    ("setCellType_", "cellType"), ("setParent_", "parent"),
])
def test_retaining_setters_preserve_identity_without_count_or_parent_notification(selector, field):
    item, value = owned(), object()
    getattr(item, selector)(value)
    assert getattr(item, field) is value
    assert item._provider.events == []


def test_native_preset_and_existing_default_are_same_slot_and_cell_alias():
    item = owned()
    assert item.preset is item.default is False
    item.setPreset_(True)
    assert item.default is True
    item.default = False
    assert item.preset is False
    item.setCellType_("OwnedCell")
    assert item.cell == "OwnedCell"
    item.cell = "OldCell"
    assert item.cellType == "OldCell"


@pytest.mark.parametrize("identifier,expected", [(None, "GSSidebarItemHidden_(null)"), ("", "GSSidebarItemHidden_"), ("a/b", "GSSidebarItemHidden_a/b")])
def test_hidden_uses_current_identifier_shared_defaults_and_does_not_cache(identifier, expected):
    item = owned()
    item.identifier = identifier
    assert item.hiddenKey() == expected
    assert item.hidden is False
    item.setHidden_(True)
    assert item.hidden is True
    item._provider.defaults[expected] = False
    assert item.hidden is False
    assert item._provider.events[1] == ("write", True, expected)


def test_hidden_missing_default_primitive_fails_explicitly():
    item = SidebarItem()
    with pytest.raises(UnsupportedCapability):
        _ = item.hidden
    with pytest.raises(UnsupportedCapability):
        item.setHidden_(True)


@pytest.mark.parametrize("identifier,expected", [("LANGUAGES", True), ("FILTERS", True), ("Languages", False), (None, False)])
def test_can_add_computes_exact_header_names_independent_of_setter(identifier, expected):
    item = owned()
    item.identifier = identifier
    item.setCanAdd_(not expected)
    assert item.canAdd() is expected


@pytest.mark.parametrize("count,expected,answer", [(-2, 1, True), (0, 0, False), (2, 3, True), (3, 3, False), (4, 3, False)])
def test_has_expected_count_and_noop_setter(count, expected, answer):
    item = owned()
    item.count, item.shallHaveCount = count, expected
    item.setHasShallHaveCount_(not answer)
    assert item.hasShallHaveCount() is answer


def test_insert_remove_retains_array_duplicates_stale_parent_and_out_of_bounds_bulk_zero():
    item, a, b, c = owned(), owned(), owned(), owned()
    rows = [a]
    item.setSubItems_(rows)
    item.insertObject_inSubItemsAtIndex_(b, 1)
    item.insertSubItems_atIndex_([c, b], 100)
    assert item.subItems is rows and rows == [c, b, a, b]
    assert a.parent is b.parent is c.parent is item
    item.removeSubItemsObject_(b)
    assert rows == [c, a] and b.parent is item
    with pytest.raises(IndexError):
        item.insertObject_inSubItemsAtIndex_(b, 100)
    assert b.parent is item


def test_nil_array_insert_still_reparents_and_remove_is_noop():
    item, a = owned(), owned()
    item.insertObject_inSubItemsAtIndex_(a, 1)
    assert item.subItems is None and a.parent is item
    item.insertSubItems_atIndex_([a], 50)
    item.removeSubItemsObject_(a)
    assert item.subItems is None and a.parent is item and item.isLeaf()


def test_copy_uses_runtime_subclass_recursive_child_copy_shallow_metadata_error_sentinel():
    class Child(SidebarItem):
        pass
    item, child = Child(), owned()
    item._provider = child._provider
    item.name, item.coverage, item.infos = "Owned", ["A"], [object()]
    item.codes, item.filePath, item.cell = ["01"], "owned/path", "CustomCell"
    item.predicate, item.preset, item.editable = object(), True, True
    item.count, item.shallHaveCount, item.badgeString = 6, 10, "6/10"
    item.active, item.unicharString, item.missingInfos = True, "U", [object()]
    item.setSubItems_([child])
    result = item.copyWithZone_(None)
    assert type(result) is Child and result is not item
    for field in ("name", "coverage", "infos", "codes", "filePath", "cell", "predicate"):
        assert getattr(result, field) is getattr(item, field)
    assert result.subItems is not item.subItems and result.subItems[0] is not child
    assert child.parent is item and result.subItems[0].parent is result
    assert (result.count, result.shallHaveCount, result.badgeString) == (-1, -1, None)
    assert result.active is False and result.unicharString is result.missingInfos is result.parent is result.font is None
    item.shallHaveCount = -2
    result = item.copyWithZone_(None)
    assert (result.count, result.shallHaveCount, result.badgeString) == (6, -2, "6/10")


def test_set_predicate_format_retains_prior_on_marked_error_and_enqueues_alert_only():
    item = owned()
    item.setPredicateFormat_("good")
    previous = item.predicate
    assert item.predicateFormat is None
    item.setPredicateFormat_("bad")
    assert item.predicate is previous
    assert item.badgeString is None and item.count == -1
    item._provider.pending.pop()()
    assert item._provider.events[-1] == ("alert", "owned bad predicate")
    item.setPredicateFormat_(None)
    assert item.predicate is None


def test_set_predicate_format_does_not_catch_unmarked_python_error():
    item = owned()
    def fail(text):
        raise ValueError("owned")
    item._provider.compile_predicate = fail
    with pytest.raises(ValueError, match="owned"):
        item.setPredicateFormat_("bad")


def test_weak_font_delayed_callback_reads_current_font_and_children_are_forwarded_after_trigger():
    item, child = owned(), owned()
    item.setSubItems_([child])
    events = []
    item.expandNameList_ = lambda manager: events.append(("expand", manager))
    child.expandNameList_ = lambda manager: events.append(("child", manager))
    first, second = SimpleFont("first"), SimpleFont("second")
    item.setFont_(first)
    item.setFont_(second)
    seen = []
    item.updateCount_ = lambda font: seen.append(font)
    item._provider.pending[0]()
    assert seen == [second]
    assert events == [("expand", "first"), ("child", "first"), ("expand", "second"), ("child", "second")]
    assert item.font is child.font is second
    seen.clear()
    del second
    gc.collect()
    item.updateCount_ = lambda font: seen.append(font)
    item._provider.pending[0]()
    assert item.font is None and seen == [None]


class SimpleFont:
    def __init__(self, manager):
        self.manager = manager
    def glyphsInfo(self):
        return self.manager


class PipelineProvider(Provider):
    def __init__(self):
        super().__init__()
        self.match_count, self.code_count, self.info_count = 7, 4, 2
        self.fail_count = self.fail_small = None
        self.filtered = []

    def sidebar_info_value(self, info, field):
        return None if info is None else getattr(info, field)

    def sidebar_new_info(self):
        return SimpleNamespace(name=None, unicode=None, locked=False, type=0)

    def sidebar_copy_info(self, info):
        self.events.append(("copy", info))
        return SimpleNamespace(**vars(info))

    def sidebar_set_info_name(self, info, name):
        self.events.append(("rename", info, name))
        info.name = name

    def sidebar_hex_to_int(self, code):
        return int(code, 16)

    def localize(self, text):
        self.events.append(("localize", text))
        return text

    def show_modal_alert(self, message):
        self.events.append(("modal", message))

    def sidebar_font_all_glyphs(self, font):
        self.events.append(("all", font))
        return font.all

    def sidebar_count_infos(self, font, infos):
        self.events.append(("infos", infos))
        return self.info_count

    def sidebar_count_codes(self, font, codes):
        self.events.append(("codes", codes))
        return self.code_count

    def count_matching_predicate(self, glyphs, predicate):
        self.events.append(("matching", glyphs, predicate))
        if self.fail_count:
            raise self.fail_count
        return self.match_count

    def filter_using_predicate(self, glyphs, predicate):
        self.events.append(("filter", glyphs, predicate.predicateFormat))
        if self.fail_small:
            raise self.fail_small
        return self.filtered.pop(0)

    def notify(self, item, phase, key):
        self.events.append((phase, key, item.count, item.shallHaveCount))

    def present_error(self, error):
        self.events.append(("error", error))

    def log(self, message):
        self.events.append(("log", message))


def pipeline():
    item = SidebarItem()
    item._provider = PipelineProvider()
    return item


class Manager:
    def __init__(self):
        self.names, self.codes, self.lookups = {}, {}, []

    def glyphInfoForName_(self, name):
        self.lookups.append(("name", name))
        return self.names.get(name)

    def glyphInfoForUnicode_(self, code):
        self.lookups.append(("code", code))
        return self.codes.get(code)


def info(name, code=None, locked=False, type=0):
    return SimpleNamespace(name=name, unicode=code, locked=locked, type=type)


def test_expand_colon_ranges_inclusive_no_dedup_and_retains_resolved_row_identity():
    item, manager = pipeline(), Manager()
    a, b, c = info("A", "0041"), info("B", "0042"), info("C", "0043")
    manager.names.update(A=a, C=c)
    manager.codes.update({"0041": a, "0042": b, "0043": c})
    coverage = ["A:C", "A"]
    item.coverage = coverage
    item.expandNameList_(manager)
    assert item.coverage is coverage and item.infos == [a, b, c, a]
    assert manager.lookups == [("name", "A"), ("name", "C"), ("code", "0041"), ("code", "0042"), ("code", "0043"), ("name", "A")]


@pytest.mark.parametrize("left,right", [("0043", "0041"), ("10FFFF", "10FFFF"), ("FFFFFFFF", "0041")])
def test_expand_valid_unicode_endpoints_invalid_range_is_dropped_without_whole_token_lookup(left, right):
    item, manager = pipeline(), Manager()
    manager.names.update(a=info("a", left), b=info("b", right))
    item.coverage, item.infos = ["a:b"], [object()]
    item.expandNameList_(manager)
    assert item.infos is None
    assert manager.lookups == [("name", "a"), ("name", "b")]


def test_expand_missing_endpoint_unicode_falls_back_to_original_name_and_new_record():
    item, manager = pipeline(), Manager()
    item.coverage = ["a:b", "owned.unknown"]
    item.expandNameList_(manager)
    assert [row.name for row in item.infos] == ["a:b", "owned.unknown"]
    assert manager.lookups == [("name", "a"), ("name", "b"), ("name", "a:b"), ("name", "owned.unknown")]


@pytest.mark.parametrize("name,locked,copied,renamed", [("AB", True, True, True), ("AB", False, False, True), ("A", True, False, False), ("éB", True, False, False), ("1B", True, False, False)])
def test_expand_ascii_first_scalar_and_length_gate_copies_only_locked_alias(name, locked, copied, renamed):
    item, manager = pipeline(), Manager()
    record = info("canonical", locked=locked)
    manager.names[name] = record
    item.coverage = [name]
    item.expandNameList_(manager)
    result = item.infos[0]
    assert (result is not record) is copied
    assert result.name == (name if renamed else "canonical")
    assert record.name == (name if renamed and not copied else "canonical")


def test_expand_invalid_member_clears_coverage_but_continues_retained_enumerator_and_deduplicates_alert_by_name():
    item, manager = pipeline(), Manager()
    item.name = "owned invalid list distinct"
    item.coverage = ["A", 123, "B", None]
    item.expandNameList_(manager)
    assert item.coverage is None and [row.name for row in item.infos] == ["A", "B"]
    assert len([event for event in item._provider.events if event[0] == "modal"]) == 1
    item.coverage = [False]
    item.expandNameList_(manager)
    assert item.infos is None
    assert len([event for event in item._provider.events if event[0] == "modal"]) == 1


def test_expand_nil_unicode_range_member_raises_preserving_old_infos_and_coverage():
    item, manager = pipeline(), Manager()
    manager.names.update(a=info("a", "0041"), b=info("b", "0042"))
    old = [object()]
    item.coverage, item.infos = ["a:b"], old
    with pytest.raises(InfoNativeException, match="nil"):
        item.expandNameList_(manager)
    assert item.infos is old and item.coverage == ["a:b"]


def drain(provider):
    while provider.pending:
        provider.pending.pop(0)()


@pytest.mark.parametrize("kind,count,expected,badge", [("infos", 2, 2, "✓"), ("predicate", 7, -2, "7"), ("codes", 4, 3, "4/3"), ("empty", -2, -2, None)])
def test_count_precedence_and_main_publication(kind, count, expected, badge):
    item = pipeline()
    font = SimpleNamespace(all=[object()])
    if kind == "infos":
        item.infos = [info("A"), info("B", type=1), info("C")]
    if kind in ("infos", "predicate"):
        item.predicate = SimpleNamespace(predicateFormat="owned")
    if kind != "empty":
        item.codes = ["a", "b", "c"]
    item.calculating = True
    item.updateCount_(font)
    assert (item.count, item.shallHaveCount, item.badgeString) == (-1, -1, None)
    assert item.calculating is True
    item._provider.pending.pop(0)()
    assert item.badgeString == "✓"
    item._provider.pending.pop(0)()
    assert (item.count, item.shallHaveCount, item.badgeString) == (count, expected, badge)
    assert item.calculating is False
    changes = [event for event in item._provider.events if event[0] in ("will", "did")]
    assert changes == [("will", "hasShallHaveCount", -1, -1), ("did", "hasShallHaveCount", count, expected)]


def test_nil_font_count_does_nothing_and_does_not_clear_calculating():
    item = pipeline()
    item.calculating = True
    item.updateCount_(None)
    assert item._provider.events == [] and item._provider.pending == [] and item.calculating


@pytest.mark.parametrize("count,expected,children,badge", [(0, -2, None, "0"), (3, 0, [SidebarItem()], None), (-2, -2, None, None), (8, 10, None, "8/10"), (10, 10, None, "✓")])
def test_publish_badges_use_current_leaf_and_skip_kvo_when_counts_equal(count, expected, children, badge):
    item = pipeline()
    item.count, item.shallHaveCount, item.subItems = count, expected, children
    item._publish_count(count, expected)
    assert item.badgeString == badge and item._provider.events == [] and not item.calculating


def test_predicate_count_exception_deduplicates_by_predicate_format_then_publishes_sentinel():
    item = pipeline()
    item.name = "Owned count error"
    item.predicate = SimpleNamespace(predicateFormat="distinct owned failure 17")
    item._provider.fail_count = InfoNativeException("owned count failure")
    font = SimpleNamespace(all=[])
    for _ in range(2):
        item.updateCount_(font)
        drain(item._provider)
    errors = [event[1] for event in item._provider.events if event[0] == "error"]
    assert len(errors) == 1 and errors[0].code() == 992
    assert errors[0].domain() == "GSGlyphsDomain"
    assert errors[0].localizedDescription() == "Invalid filter in sidebar: Owned count error"
    assert errors[0].localizedFailureReason() == "distinct owned failure 17"
    assert (item.count, item.shallHaveCount, item.badgeString) == (-2, -2, None)


def test_unmarked_count_error_and_infos_native_error_propagate_without_publish():
    item = pipeline()
    item.predicate = SimpleNamespace(predicateFormat="owned")
    item._provider.fail_count = ValueError("owned")
    with pytest.raises(ValueError, match="owned"):
        item.updateCount_(SimpleNamespace(all=[]))
    assert len(item._provider.pending) == 1
    item.infos = [info("A")]
    def fail(font, infos):
        raise InfoNativeException("infos outside predicate catch")
    item._provider.sidebar_count_infos = fail
    with pytest.raises(InfoNativeException, match="outside"):
        item.updateCount_(SimpleNamespace(all=[]))
    assert len(item._provider.pending) == 2


def test_smallcaps_exact_predicates_replace_infos_with_existing_sc_records_keep_missing_infos():
    item, manager = pipeline(), Manager()
    item.identifier = "Smallcaps"
    a = info("A.sc")
    manager.names["A.sc"] = a
    font = SimpleFont(manager)
    font.all = [object()]
    item._provider.filtered = [[SimpleNamespace(name="A"), SimpleNamespace(name="B")], [object()]]
    item.updateCount_(font)
    drain(item._provider)
    assert (item.count, item.shallHaveCount, item.badgeString) == (1, 2, "1/2")
    assert item.infos == [a] and item.infos[0] is a and item.missingInfos is None
    formats = [event[1] for event in item._provider.events if event[0] == "compile"]
    assert formats == ["(case == 2) AND NOT (name contains '.0') AND (export == True)", "case == 3"]


def test_smallcaps_marked_failure_logs_then_publishes_partial_prior_count_state():
    item = pipeline()
    item.identifier = "Smallcaps"
    item.codes = ["a"]
    item._provider.fail_small = InfoNativeException("owned small error")
    item.updateCount_(SimpleNamespace(all=[]))
    drain(item._provider)
    assert (item.count, item.shallHaveCount) == (4, 1)
    assert ("log", "Error computing Smallcaps count: owned small error") in item._provider.events


@pytest.mark.parametrize("cpu,limit", [(0, 2), (1, 2), (4, 2), (5, 3), (7, 4), (8, 4), (9, 5)])
def test_class_queue_once_uses_float32_half_and_arm_nearest_away(cpu, limit, monkeypatch):
    import fontlab_glyport.glyphsapp.info_sidebar_support as support
    from fontlab_glyport.glyphsapp.info_runtime import using_info_provider
    monkeypatch.setattr(support, "_queue_initialized", False)
    monkeypatch.setattr(support, "_sidebar_queue", None)
    events = []
    class Queue:
        def setMaxConcurrentOperationCount_(self, value):
            events.append(("limit", value))
        def setQualityOfService_(self, value):
            events.append(("qos", value))
    queue = Queue()
    provider = SimpleNamespace(new_queue=lambda: queue, active_processor_count=lambda: cpu)
    class Subclass(SidebarItem):
        pass
    with using_info_provider(provider):
        assert Subclass.initialize() is None
    SidebarItem.initialize()
    assert support._sidebar_queue is queue
    assert events == [("limit", limit), ("qos", 17)]


def test_description_forwards_class_pointer_name_and_predicate_or_child_count():
    item = owned()
    captured = []
    item._provider.class_name = lambda obj: "QualifiedClass"
    item._provider.format_string = lambda *args: captured.append(args) or "formatted"
    item.name = "Name"
    assert item.description() == "formatted"
    assert captured[-1] == ("<%@ %p> %@ (%@)", "QualifiedClass", item, "Name", 0)
    item.predicate = object()
    item.setSubItems_([owned()])
    item.description()
    assert captured[-1][-1] is item.predicate


def test_raw_flags_reset_and_keypath_selectors_have_source_no_side_effects():
    item = owned()
    assert item.badgeVisible() is False
    assert item.keyPathsForValuesAffectingDisplayName() == {"name"}
    item.setActive_(True)
    item.setItemType_(3)
    item.setIsCalculating_(True)
    item.setSuppressCount_(True)
    assert item.active and item.itemType == 3 and item.isCalculating() and item.isSuppressingCount()
    item.resetCounter()
    assert item._provider.events == []
    item.setIsCalculating_(False)
    item.count = -2
    item.resetCounter()
    assert item._provider.events == []
    item.count = -1
    item.resetCounter()
    assert item.badgeString is None and not item.calculating
    item.setSuppressCount_(False)
    item.resetCounter()
    assert item._provider.events[-1] == ("schedule", item, 10_000_000)


def test_trigger_dispatches_actual_selector_overrides_and_checks_stored_suppression_equals_one():
    item = owned()
    events = []
    item.isCalculating = lambda: events.append("read") or False
    original = item.setIsCalculating_
    item.setIsCalculating_ = lambda value: events.append(("set", value)) or original(value)
    item.calculating, item.suppressCount = 2, 2
    item.triggerUpdateCount()
    assert events == ["read", ("set", True)]
    assert item._provider.events[-1] == ("schedule", item, 10_000_000)


def test_dictionary_construction_uses_actual_setters_in_source_order():
    events = []
    class Row(SidebarItem):
        def setName_(self, value):
            events.append(("name", value))
            super().setName_(value)
        def setIdentifier_(self, value):
            events.append(("id", value))
            super().setIdentifier_(value)
        def setIconName_(self, value):
            events.append(("icon", value))
            super().setIconName_(value)
        def setPredicate_(self, value):
            events.append(("predicate", value))
            super().setPredicate_(value)
    provider = PipelineProvider()
    row = Row.from_dict({"name": "Owned", "predicate": "ok"}, provider)
    assert events == [("name", "Owned"), ("id", "Owned"), ("icon", None), ("predicate", row.predicate)]
    assert row.preset is row.default is False


def test_marked_set_predicate_failure_on_nil_format_is_outside_compile_handler():
    item = owned()
    def fail(value):
        raise InfoNativeException("nil setter outside handler")
    item.setPredicate_ = fail
    with pytest.raises(InfoNativeException, match="outside"):
        item.setPredicateFormat_(None)
    assert item._provider.pending == []



def test_expand_reloads_unicode_after_length_checks_and_skips_end_conversion_for_large_current_start():
    item, manager = pipeline(), Manager()
    start, end = info("a", "0041"), info("b", "0042")
    manager.names.update(a=start, b=end)
    stream = iter(["0041", "0042", "10FFFF"])
    calls = []
    def value(record, field):
        calls.append((record, field))
        return next(stream)
    item._provider.sidebar_info_value = value
    item.coverage = ["a:b"]
    item.expandNameList_(manager)
    assert item.infos is None
    assert calls == [(start, "unicode"), (end, "unicode"), (start, "unicode")]
    stream = iter(["0041", "0042", "0043", "0043"])
    calls.clear()
    record = info("C", "0043")
    manager.codes["0043"] = record
    item.expandNameList_(manager)
    assert item.infos == [record]
    assert calls == [(start, "unicode"), (end, "unicode"), (start, "unicode"), (end, "unicode")]
