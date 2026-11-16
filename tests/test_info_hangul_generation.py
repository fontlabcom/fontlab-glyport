# this_file: tests/test_info_hangul_generation.py
"""Independent NFD and owned dispatch/state oracles for full Hangul generation."""

import unicodedata
from collections import Counter
from types import SimpleNamespace

import pytest

from fontlab_glyport.glyphsapp.info_hangul import (
    decompose_hangul,
    link_hangul,
    queue_hangul,
)
from fontlab_glyport.glyphsapp.info_runtime import InfoNativeException


def nfd_parts(code):
    """Independent Unicode database oracle; no copied runtime arithmetic."""
    return tuple(map(ord, unicodedata.normalize("NFD", chr(code))))


def test_decompose_hangul_all_bmp_inputs_match_unicode_nfd():
    valid = 0
    for code in range(0x10000):
        actual = decompose_hangul(code)
        if 0xAC00 <= code <= 0xD7A3:
            expected = nfd_parts(code)
            if len(expected) == 2:
                expected += (0xFFFF,)
            assert actual == expected, f"Wrong source decomposition at {code:04X}"
            valid += 1
        else:
            assert actual is None, f"Non-Hangul BMP value accepted: {code:04X}"
    assert valid == 11172, "Must test the complete retained 0x2BA4 range"


@pytest.mark.parametrize("value", [None, "AC00", 44032.0, True, False, object()])
def test_decompose_hangul_rejects_unqualified_python_types(value):
    with pytest.raises(TypeError):
        decompose_hangul(value)


@pytest.mark.parametrize("value", [-1, 0x10000, 0x10000000000000000])
def test_decompose_hangul_rejects_values_outside_uint16(value):
    with pytest.raises(ValueError):
        decompose_hangul(value)


def test_link_hangul_entire_range_preserves_lookup_order_and_identities():
    rows, events, assigned = {}, [], []
    for code in range(0xAC00, 0xD7A4):
        for value in (code, *nfd_parts(code)):
            rows.setdefault(f"{value:X}", object())

    def lookup(key):
        events.append(("lookup", key))
        return rows[key]

    def assign(target, parts):
        events.append(("assign", target, parts))
        assigned.append((target, parts))

    assert link_hangul(lookup, assign) is None
    expected_events = []
    for code in range(0xAC00, 0xD7A4):
        codes = (code, *nfd_parts(code))
        keys = tuple(f"{value:X}" for value in codes)
        target, *parts = (rows[key] for key in keys)
        expected_events.extend(("lookup", key) for key in keys)
        expected_events.append(("assign", target, tuple(parts)))
    assert events == expected_events, (
        "Each lookup and assignment must follow source order"
    )
    assert len(assigned) == 11172, "Every Hangul syllable needs assignment"
    assert Counter(len(parts) for _, parts in assigned) == {2: 399, 3: 10773}
    assert sum(event[0] == "lookup" for event in events) == 44289
    assert all(isinstance(parts, tuple) for _, parts in assigned)


@pytest.mark.parametrize("missing", ["1100", "1161", "11A8"])
@pytest.mark.parametrize("nil_target", [False, True])
def test_missing_part_raises_after_all_lookups_without_rolling_back(
    missing, nil_target
):
    events, assignments = [], []
    rows = {key: object() for key in ("AC00", "AC01", "1100", "1161", "11A8")}

    # Leave AC00 valid so its completed assignment survives the next failure.
    def lookup(key):
        events.append(key)
        if "AC01" in events and key == missing:
            return None
        if nil_target and key == "AC01":
            return None
        return rows[key]

    with pytest.raises(InfoNativeException, match="Hangul.*nil"):
        link_hangul(lookup, lambda target, parts: assignments.append((target, parts)))
    assert events == ["AC00", "1100", "1161", "AC01", "1100", "1161", "11A8"]
    assert assignments == [(rows["AC00"], (rows["1100"], rows["1161"]))], (
        "A later nil part must not roll back earlier assignments"
    )


@pytest.mark.parametrize("missing", ["1100", "1161"])
def test_two_part_array_rejects_nil_after_both_part_lookups(missing):
    events = []

    def lookup(key):
        events.append(key)
        return None if key == missing else object()

    with pytest.raises(InfoNativeException):
        link_hangul(lookup, lambda *_: pytest.fail("Invalid array reached setter"))
    assert events == ["AC00", "1100", "1161"], (
        "Nil must fail only after array inputs exist"
    )


def test_nil_targets_still_lookup_all_parts_and_never_assign():
    calls = []
    parts = object()

    def lookup(key):
        calls.append(key)
        return None if 0xAC00 <= int(key, 16) <= 0xD7A3 else parts

    assert link_hangul(lookup, lambda *_: pytest.fail("Setter on nil target")) is None
    expected = [
        f"{value:X}"
        for code in range(0xAC00, 0xD7A4)
        for value in (code, *nfd_parts(code))
    ]
    assert calls == expected, "Nil syllables cannot suppress component lookups"


def test_link_hangul_uses_current_rows_between_individual_lookups():
    rows = {"AC00": object(), "1100": object(), "1161": object()}
    old_target, old_leading = rows["AC00"], rows["1100"]
    new_target, new_leading, new_vowel = object(), object(), object()
    assigned = []
    failure = RuntimeError("owned stop after full first syllable")

    def lookup(key):
        if key == "AC00":
            rows.update(AC00=new_target, **{"1100": new_leading})
            return old_target
        if key == "1100":
            rows["1161"] = new_vowel
        if key == "AC01":
            raise failure
        return rows[key]

    with pytest.raises(RuntimeError) as caught:
        link_hangul(lookup, lambda target, parts: assigned.append((target, parts)))
    assert caught.value is failure, "Arbitrary callback failures propagate unchanged"
    assert assigned == [(old_target, (new_leading, new_vowel))]
    assert old_leading not in assigned[0][1], "No stale component snapshot"
    assert rows["AC00"] is new_target, "Target lookup retains its returned object"


def test_assignment_error_propagates_without_later_lookups():
    events = []
    error = LookupError("owned setter failure")

    def lookup(key):
        events.append(key)
        return object()

    def assign(target, parts):
        raise error

    with pytest.raises(LookupError) as caught:
        link_hangul(lookup, assign)
    assert caught.value is error
    assert events == ["AC00", "1100", "1161"]


def test_queue_hangul_enqueues_once_no_wait_and_reads_replaced_rows():
    pending, events, assigned = [], [], []
    original = {"AC00": object(), "1100": object(), "1161": object()}
    state = SimpleNamespace(rows=original)
    queue = SimpleNamespace(addOperationWithBlock_=pending.append)
    failure = RuntimeError("owned stop after first syllable")

    def lookup(key):
        events.append(key)
        if key == "AC01":
            raise failure
        return state.rows[key]

    assert (
        queue_hangul(
            queue, lookup, lambda target, parts: assigned.append((target, parts))
        )
        is None
    )
    assert len(pending) == 1 and events == [], "Enqueue must neither execute nor wait"
    state.rows = {key: object() for key in original}
    with pytest.raises(RuntimeError) as caught:
        pending.pop()()
    assert caught.value is failure
    assert assigned == [(state.rows["AC00"], (state.rows["1100"], state.rows["1161"]))]
    assert all(value is not original[key] for key, value in state.rows.items())


def test_queue_hangul_does_not_reduce_complete_range():
    pending, keys, assigned = [], [], []
    queue = SimpleNamespace(addOperationWithBlock_=pending.append)
    record = object()
    queue_hangul(
        queue,
        lambda key: keys.append(key) or record,
        lambda *args: assigned.append(args),
    )
    assert not keys and not assigned
    pending.pop()()
    assert len(assigned) == 11172, "Queued job must cover the complete source range"
    assert len(keys) == 44289 and keys[0] == "AC00" and keys[-4] == "D7A3"
