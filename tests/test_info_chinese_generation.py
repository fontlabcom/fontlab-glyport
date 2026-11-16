# this_file: tests/test_info_chinese_generation.py
"""Independent retained-source controls; lists here are invented lawful fixtures."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.glyphsapp.info_chinese import add_chinese, add_codes, add_range
from fontlab_glyport.glyphsapp.info_runtime import InfoNativeException, InfoState
from fontlab_glyport.model.info_records import new_record

RANGE_SELECTOR = "_addChinese_end_subCategory_sortPrefix_infos_unicode2Info_"
LIST_SELECTOR = "_addChinese_subCategory_sortPrefix_infos_unicode2Info_"
# Independent source table from the generation callbacks, not module constants.
SOURCE_JOBS = (
    (
        (0x2E80, 0x2E99, "Radical", "uni0"),
        (0x2E9B, 0x2EF3, "Radical", "uni0"),
        (0x2F00, 0x2FD5, "Radical", "uni0"),
    ),
    ((0x3400, 0x57EE, None, "uni0"),),
    ((0x57EF, 0x7BDC, None, "uni0"),),
    ((0x7BDD, 0x9FFF, None, "uni0"),),
    ((0xF900, 0xFAD9, "Compatibility", "uni0"),),
    ((0, "Compatibility", "uni0"), (1, "Compatibility", "unj"), (2, None, "unj")),
    ((3, None, "unj"),),
    ((0x30000, 0x3134A, None, "unj"),),
    ((0x31350, 0x323AF, None, "unj"),),
    ((0x2EBF0, 0x2EE5F, None, "unj"),),
)
# Deliberately overlapping, repeated, mixed-length owned profile; no private bank.
OWNED_LISTS = (
    ("0041", "0041", "30000"),
    ("20001", "0041"),
    ("30000", "0042"),
    ("0041", "0043"),
)


class OwnedProvider:
    profile = "explicit-lawful-owned-chinese-fixture-v1"

    def __init__(self):
        self.calls = []

    def chinese_codes(self, slot):
        self.calls.append(slot)
        return OWNED_LISTS[slot]


class Queue:
    def __init__(self, reverse=False, before=None, after=None):
        self.jobs = []
        self.reverse, self.before, self.after = reverse, before, after
        self.waits = 0

    def addOperationWithBlock_(self, callback):
        self.jobs.append(callback)

    def waitUntilAllOperationsAreFinished(self):
        self.waits += 1
        if self.before:
            self.before()
        for callback in reversed(self.jobs) if self.reverse else self.jobs:
            assert callback() is None, "Each primitive callback has a void result"
            if self.after:
                self.after()


def manager(queue=None, provider=None):
    result = SimpleNamespace(_lifecycle=InfoState(provider or OwnedProvider(), None))
    result._lifecycle.queue = queue or Queue()
    setattr(result, RANGE_SELECTOR, add_range)
    setattr(result, LIST_SELECTOR, add_codes)
    return result


def fields(record):
    return (
        record.name,
        record.unicode,
        record.sortName,
        record.script,
        record.category,
        record.subCategory,
        record._locked,
        record.index,
    )


def oracle(job):
    result = []
    for call in SOURCE_JOBS[job]:
        if len(call) == 4:
            start, end, subcategory, sort = call
            prefix = "u" if start >= 65535 else "uni"
            codes = [f"{value:04X}" for value in range(start, end + 1)]
        else:
            slot, subcategory, sort = call
            codes = OWNED_LISTS[slot]
            prefix = "uni" if len(codes[0].encode("utf-16-le")) == 8 else "u"
        result.extend(
            (prefix + code, code, sort + code, "han", "Letter", subcategory, True, 0)
            for code in codes
        )
    return result


@pytest.mark.parametrize("reverse", [False, True])
def test_complete_ten_jobs_when_owned_profile_then_every_fixed_row_matches(reverse):
    target = manager(Queue(reverse=reverse))
    state = target._lifecycle
    existing = new_record("maintained")
    existing.unicode, existing.sortName = "3400", "untouched"
    state.index.records.append(existing)
    state.index.unicodes["3400"] = existing
    colliding_name = new_record("uni0041")
    state.index.names["uni0041"] = colliding_name
    jobs = range(9, -1, -1) if reverse else range(10)
    expected = [row for job in jobs for row in oracle(job) if row[1] != "3400"]
    assert add_chinese(target) is None
    assert len(state.queue.jobs) == 10 and state.queue.waits == 1
    assert state.index.records[0] is existing
    actual = state.index.records[1:]
    assert [fields(row) for row in actual] == expected
    assert len({id(row) for row in actual}) == len(actual), "Repeated rows stay fresh"
    assert existing.sortName == "untouched"
    assert state.index.unicodes["3400"] is existing
    assert state.index.names["uni0041"] is not colliding_name
    last_names = {row.name: row for row in actual}
    last_codes = {row.unicode: row for row in actual}
    for key, row in last_names.items():
        assert state.index.names[key] is row
    for key, row in last_codes.items():
        assert state.index.unicodes[key] is row
    assert sorted(state.provider.calls) == [0, 1, 2, 3]


@pytest.mark.parametrize(
    "start,end,names",
    [
        (0xFFFE, 0x10000, ["uniFFFE", "uniFFFF", "uni10000"]),
        (0xFFFF, 0x10000, ["uFFFF", "u10000"]),
        (0x10000, 0x10001, ["u10000", "u10001"]),
        (5, 4, []),
    ],
)
def test_range_when_boundary_then_prefix_selected_once(start, end, names):
    rows, index = [], {}
    assert add_range(start, end, "owned", "sort", rows, index) is None
    assert [row.name for row in rows] == names
    assert index == {}, "Jobs must not populate the Unicode index"
    for row in rows:
        assert fields(row)[2:] == (
            "sort" + row.unicode,
            "han",
            "Letter",
            "owned",
            True,
            0,
        )


@pytest.mark.parametrize(
    "codes,names",
    [
        (["0041", "20000", "0041"], ["uni0041", "uni20000", "uni0041"]),
        (["20000", "0041"], ["u20000", "u0041"]),
        (["😀AB", "0042"], ["uni😀AB", "uni0042"]),
        ([], []),
        (None, []),
    ],
)
def test_list_when_owned_mixed_lengths_then_preserves_order_and_utf16_prefix(
    codes, names
):
    rows, index = [], {}
    assert add_codes(codes, None, "x", rows, index) is None
    assert [row.name for row in rows] == names
    assert index == {}
    assert len({id(row) for row in rows}) == len(rows)


def test_primitives_when_index_has_only_selected_code_then_preserve_other_duplicates():
    existing, rows = new_record("kept"), []
    index = {"0041": existing}
    add_codes(["0041", "0042", "0042"], None, None, rows, index)
    add_range(0x41, 0x42, None, "x", rows, index)
    assert [row.unicode for row in rows] == ["0042", "0042", "0042"]
    assert [row.sortName for row in rows] == [None, None, "x0042"]
    assert index == {"0041": existing} and existing.name == "kept"
    assert add_range(0x41, 0x41, None, "x", None, None) is None
    assert add_codes(["0041"], None, "x", None, None) is None


def test_parent_when_maps_replaced_then_captures_maps_but_appends_current_rows():
    target = manager()
    state = target._lifecycle
    captured_names, captured_codes = state.index.names, state.index.unicodes
    old_rows = state.index.records
    current = new_record("current")
    calls = []

    def range_callback(start, end, category, prefix, rows, codes):
        assert codes is captured_codes
        calls.append((start, end, category, prefix))
        add_range(start, start, category, prefix, rows, codes)

    setattr(target, RANGE_SELECTOR, range_callback)

    def before():
        state.provider = SimpleNamespace()  # Entry provider must remain captured.
        state.index.names, state.index.unicodes = {}, {}
        state.index.records = [current]
        # Captured map remains live; suppress a token after scheduling.
        captured_codes["0041"] = current

    def after():
        assert captured_names == {}, "No indexes are committed during jobs"
        assert state.index.records == [current], "Chunks remain private until barrier"

    state.queue = Queue(before=before, after=after)
    add_chinese(target)
    assert old_rows == [] and state.index.records[0] is current
    assert state.index.names == {} and state.index.unicodes == {}
    assert captured_names and len(calls) == 10
    assert captured_codes["0041"] is current
    assert all(row.unicode != "0041" for row in state.index.records[1:])


def test_parent_when_selector_rebound_in_queue_then_uses_dynamic_dispatch():
    target = manager()
    seen = []

    def emit(*args):
        seen.append(args)

    target._lifecycle.queue.before = lambda: setattr(target, RANGE_SELECTOR, emit)
    add_chinese(target)
    assert len(seen) == 10, "Ten range calls across eight jobs use dynamic dispatch"
    assert all(len(call) == 6 for call in seen)


def test_parent_when_required_provider_missing_then_failure_has_no_partial_commit():
    target = manager(provider=SimpleNamespace())
    with pytest.raises(UnsupportedCapability) as error:
        add_chinese(target)
    assert error.value.capability == "GSGlyphsInfo.provider.chinese_codes"
    assert target._lifecycle.index.records == []
    assert (
        target._lifecycle.index.names == {} and target._lifecycle.index.unicodes == {}
    )
    assert len(target._lifecycle.queue.jobs) == 10


def test_parent_when_provider_fails_after_first_slot_then_no_failed_chunk_commits():
    provider = OwnedProvider()

    def failure(slot):
        if slot == 1:
            raise RuntimeError("owned provider failed")
        return OWNED_LISTS[slot]

    provider.chinese_codes = failure
    target = manager(provider=provider)
    with pytest.raises(RuntimeError, match="owned provider failed"):
        add_chinese(target)
    assert target._lifecycle.index.records == []
    assert (
        target._lifecycle.index.names == {} and target._lifecycle.index.unicodes == {}
    )


def test_parent_when_unicode_rejected_by_length_then_name_commit_precedes_nil_key_error():
    target = manager()

    def ranges(*args):
        return None

    setattr(target, RANGE_SELECTOR, ranges)
    target._lifecycle.provider.chinese_codes = lambda slot: (
        ["12345678"] if slot == 0 else []
    )
    with pytest.raises(InfoNativeException, match="nil"):
        add_chinese(target)
    state = target._lifecycle
    assert len(state.index.records) == 1
    row = state.index.records[0]
    assert row.name == "u12345678" and row.unicode is None
    assert state.index.names[row.name] is row
    assert state.index.unicodes == {}


def test_parent_when_maps_and_rows_nil_then_messages_are_noops():
    target = manager()
    target._lifecycle.index.names = None
    target._lifecycle.index.unicodes = None
    target._lifecycle.index.records = None
    setattr(target, RANGE_SELECTOR, lambda *args: None)
    assert add_chinese(target) is None


def test_parent_when_jobs_run_on_threads_then_chunks_stay_whole_and_private():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    class ConcurrentQueue(Queue):
        def waitUntilAllOperationsAreFinished(self):
            self.waits += 1
            start = Barrier(10)

            def execute(callback):
                start.wait(timeout=10)
                return callback()

            with ThreadPoolExecutor(max_workers=10) as pool:
                assert list(pool.map(execute, self.jobs)) == [None] * 10

    target = manager(ConcurrentQueue())
    state, chunks, lock = target._lifecycle, {}, Lock()

    def capture(function):
        def invoke(*args):
            assert state.index.records == []
            assert state.index.names == {} and state.index.unicodes == {}
            assert function(*args) is None
            with lock:
                chunks[id(args[-2])] = args[-2]

        return invoke

    setattr(target, RANGE_SELECTOR, capture(add_range))
    setattr(target, LIST_SELECTOR, capture(add_codes))
    assert add_chinese(target) is None
    assert len(chunks) == 10
    rows = state.index.records
    by_first = {id(chunk[0]): chunk for chunk in chunks.values()}
    position = 0
    while position < len(rows):
        chunk = by_first.pop(id(rows[position]))
        assert all(
            a is b for a, b in zip(rows[position : position + len(chunk)], chunk)
        )
        position += len(chunk)
    assert by_first == {} and position == len(rows)
    assert sorted(fields(row) for row in rows) == sorted(
        row for job in range(10) for row in oracle(job)
    )


def test_parent_when_queue_nil_then_no_jobs_or_provider_calls():
    target = manager()
    target._lifecycle.queue = None
    assert add_chinese(target) is None
    assert target._lifecycle.provider.calls == []
    assert target._lifecycle.index.records == []


def test_list_when_empty_token_then_fresh_unicode_is_nil_and_name_still_set():
    rows = []
    assert add_codes([""], None, "sort", rows, {}) is None
    assert fields(rows[0]) == ("u", None, "sort", "han", "Letter", None, True, 0)


@pytest.mark.parametrize("bank", [None, "0041", iter(["0041"]), [None], [42]])
def test_parent_when_required_bank_is_not_explicit_string_list_then_refuses(bank):
    target = manager()
    setattr(target, RANGE_SELECTOR, lambda *args: None)
    target._lifecycle.provider.chinese_codes = lambda slot: bank
    with pytest.raises(UnsupportedCapability) as error:
        add_chinese(target)
    assert error.value.capability == "GSGlyphsInfo.provider.chinese_codes"
    assert target._lifecycle.index.records == []
    assert (
        target._lifecycle.index.names == {} and target._lifecycle.index.unicodes == {}
    )
