# this_file: tests/test_info_finalize.py
"""Owned records exercise retained updater order, identity and source limits."""

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.info_finalize import finalize_info
from fontlab_glyport.model.info_records import GlyphInfoIndex, add_unicode, new_record


def graph(*records, shared=None):
    result = GlyphInfoIndex(shared=shared)
    for record in records:
        result.append(record)
    return result


def record(name, **values):
    result = new_record(name)
    vars(result).update(values)
    return result


def test_components_resolve_this_manager_raw_before_synthesis_and_retain_identity():
    shared_child = record("shared", baseString="held")
    shared = graph(shared_child)
    own = record("own", baseString="held")
    seed = record("seed", _component_names=["own", "shared", "made", "miss", "own"])
    made = record("made", unicharString="M")
    index = graph(seed, own, shared=shared)
    calls = []

    def lookup(name):
        calls.append(name)
        return made if name == "made" else None

    finalize_info(index, lookup)
    assert seed._component_records == [own, shared_child, made, own]
    assert seed._component_records[0] is seed._component_records[-1]
    assert calls == ["alef-ar", "made", "miss"]
    assert shared_child.baseString == "held"


@pytest.mark.parametrize("tokens", [None, []])
def test_zero_components_preserve_nil_or_empty(tokens):
    seed = record("owned", _component_names=tokens)
    finalize_info(graph(seed), lambda name: None)
    assert seed._component_names is tokens
    assert seed._component_records is None
    assert seed.baseString == ""


def test_refinalizing_objects_refuses_after_prior_record_mutations():
    first = record("first", marks=["=target"])
    target = record("target", marks=["known"])
    child = record("child")
    seed = record("seed", _component_names=["child"])
    index = graph(first, seed, child)
    finalize_info(index, lambda name: target if name == "target" else None)
    first.marks = ["=target"]
    with pytest.raises(UnsupportedCapability, match="name tokens"):
        finalize_info(index, lambda name: target if name == "target" else None)
    assert first.marks is target.marks
    assert seed._component_records == [child]


def test_unknown_components_do_not_erase_independent_metadata():
    seed = record("owned", _unavailable_fields=frozenset({"components", "group"}))
    finalize_info(graph(seed), lambda name: None)
    assert seed.category is None
    assert seed.marks is None
    assert seed._unavailable_fields == {"components", "group", "baseString"}


def test_arabic_defaults_snapshot_template_before_ordered_mutation():
    marks = ["=later"]
    template = record("alef-ar", marks=marks)
    arabic = record("owned-ar", script="arabic", category="Letter", marks=[])
    later = record("later", marks=["resolved"])
    index = graph(template, arabic, later)
    finalize_info(index, index.raw_name)
    assert template.marks is later.marks
    assert arabic.marks is marks


def test_arabic_unknown_fallback_marks_only_affects_marks():
    arabic = record("owned-ar", script="arabic", category="Letter")
    finalize_info(graph(arabic), lambda name: None)
    assert arabic._unavailable_fields == {"marks"}
    assert arabic.baseString == ""
    assert arabic.anchors is None


def test_arabic_explicit_owned_fallback_and_nonletters():
    arabic = record("owned-ar", script="arabic", category="Letter")
    nonletter = record("mark-ar", script="arabic", category="Mark")
    fallback = ["owned-mark"]
    finalize_info(
        graph(arabic, nonletter), lambda name: None, arabic_fallback_marks=fallback
    )
    assert arabic.marks is fallback
    assert nonletter.marks is None


@pytest.mark.parametrize("target_marks", [None, [], ["known"]])
def test_anchor_reference_gate_uses_target_marks_not_anchor_count(target_marks):
    target = record("target", marks=target_marks, anchors=None)
    seed = record("seed", anchors=["=target"])
    original = seed.anchors
    finalize_info(graph(seed), lambda name: target if name == "target" else None)
    assert seed.anchors is (None if target_marks else original)


def test_marks_and_anchors_follow_source_order_and_keep_self_or_missing_references():
    a = record("a", marks=["=b"], anchors=["=b"])
    b = record("b", marks=["=c"], anchors=["b-top"])
    c = record("c", marks=["c-mark"])
    self_ref = record("self", marks=["=self"], anchors=["=self"])
    missing = record("missing", marks=["=none"], anchors=["=none"])
    index = graph(a, b, c, self_ref, missing)
    finalize_info(index, index.raw_name)
    assert a.marks == ["=c"]
    assert a.anchors is b.anchors
    assert b.marks is c.marks
    assert self_ref.marks == ["=self"]
    assert missing.anchors == ["=none"]


def test_reference_unknown_target_marks_or_anchors_marks_only_affected_field():
    target = record("target", _unavailable_fields={"marks"})
    seed = record("seed", marks=["=target"], anchors=["=target"])
    finalize_info(graph(seed), lambda name: target if name == "target" else None)
    assert seed._unavailable_fields == {"marks", "anchors"}
    target._unavailable_fields = {"anchors"}
    target.marks = ["known"]
    seed = record("seed", anchors=["=target"])
    finalize_info(graph(seed), lambda name: target if name == "target" else None)
    assert seed._unavailable_fields == {"anchors"}


def test_second_pass_builds_text_from_resolved_components_and_cycle_names():
    a = record("a")
    add_unicode(a, "0041")
    seed = record("seed", _component_names=["a", "a"])
    cycle = record("cycle", _component_names=["cycle"])
    index = graph(seed, cycle, a)
    finalize_info(index, index.raw_name)
    assert seed.baseString == "AA"
    assert cycle.baseString == ""
    assert a.unicharString == "A"
    assert a._locked is False


def test_preserve_non_nil_empty_base_and_use_arabic_legacy_unicode():
    held = record("held", baseString="", unicharString="ignore")
    arabic = record("owned", script="arabic", unicodeLegacy="0627")
    add_unicode(arabic, "0041")
    finalize_info(graph(held, arabic), lambda name: None)
    assert held.baseString == ""
    assert arabic.baseString == "\u0627"


def test_suffix_and_production_fallback_use_resolved_selected_lookup():
    a = record("aa", unicharString="A")
    seed = record("aa.owned")
    production = record(
        "owned", _production_state=type(a._production_state)("aa.owned")
    )
    index = graph(seed, production, a)
    finalize_info(index, index.raw_name)
    assert seed.baseString == production.baseString == "A"


def test_unicode_production_uses_indexed_scalar_records_and_owned_missing_codes():
    seed = record("owned")
    seed._production_state.value = "uni00410042"
    indexed = record("indexed", unicharString="X")
    add_unicode(indexed, "0041")
    index = graph(seed, indexed)
    finalize_info(index, index.raw_name)
    assert seed.baseString == "XB"


def test_resource_branches_only_mark_base_string_unavailable():
    fraction = record("fraction", subCategory="Fraction", _component_names=["inferior"])
    inferior = record("inferior", case=4)
    arabic = record("base.medi", script="arabic")
    base = record("base", unicharString="A")
    index = graph(fraction, inferior, arabic, base)
    finalize_info(index, index.raw_name)
    assert "baseString" in fraction._unavailable_fields
    assert arabic.baseString == "\u200dA\u200d"
    assert fraction._component_records == [inferior]
    assert base.baseString == "A"


def test_cached_empty_string_is_real_unicode_result_and_unknown_dependency_is_local():
    empty = record("empty", unicharString="")
    unknown = record("unknown")
    known = record("known", unicharString="K", _unavailable_fields={"components"})
    index = graph(empty, unknown, known)
    unknown._production_state = None
    finalize_info(index, lambda name: None)
    assert empty.baseString == ""
    assert "baseString" in unknown._unavailable_fields
    assert known.baseString == "K"


def test_mixed_token_failure_preserves_prior_lookup_order_without_replacing_components():
    seed = record("seed", _component_names=["earlier", object()])
    calls = []

    def lookup(name):
        calls.append(name)

    with pytest.raises(UnsupportedCapability, match="name tokens"):
        finalize_info(graph(seed), lookup)
    assert calls == ["alef-ar", "earlier"]
    assert seed._component_records is None
    assert seed.baseString is None


def test_callback_source_refusal_does_not_hide_known_independent_fields():
    seed = record("seed", _component_names=["unknown"], unicharString="K")

    def lookup(name):
        raise UnsupportedCapability("unknown lookup domain")

    finalize_info(graph(seed), lookup)
    assert seed._unavailable_fields == {"components"}
    assert seed.baseString == "K"
    assert seed.marks is None


def test_missing_physical_recipe_field_and_nonstring_reference_are_unavailable():
    seed = record("seed", marks=[object()])
    del seed._component_names
    finalize_info(graph(seed), lambda name: None)
    assert seed._unavailable_fields == {"components", "marks", "baseString"}
    assert seed.anchors is None


def test_shared_residual_name_tokens_need_shared_synthesis_not_local_override():
    shared_seed = record("shared-seed", _component_names=["child"])
    shared = graph(shared_seed)
    seed = record("seed", _component_names=["shared-seed"])
    index = graph(seed, shared=shared)
    finalize_info(index, index.raw_name)
    assert seed._component_records == [shared_seed]
    assert seed._unavailable_fields == {"baseString"}
    assert shared_seed._component_records is None
    assert shared_seed.baseString is None


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [("fina", "\u200dA"), ("init", "A\u200d"), ("other", "A")],
)
def test_arabic_suffix_joining_constants(suffix, expected):
    seed = record("base." + suffix, script="arabic")
    base = record("base", unicharString="A")
    index = graph(seed, base)
    finalize_info(index, index.raw_name)
    assert seed.baseString == expected


@pytest.mark.parametrize("code", ["0000", "110000", "invalid"])
def test_unichar_string_invalid_or_outside_scalar_bound_is_not_text(code):
    seed = record("seed", unicodes=(code,), unicodeLegacy=code, script="arabic")
    finalize_info(graph(seed), lambda name: None)
    assert seed.baseString == ""
    assert seed.unicharString is None


def test_native_unguarded_production_cycle_is_withheld_without_infinite_recursion():
    seed = record("seed")
    other = record("other")
    seed._production_state.value = "other.suffix"
    other._production_state.value = "seed.suffix"
    index = graph(seed, other)
    finalize_info(index, index.raw_name)
    assert "baseString" in seed._unavailable_fields
    assert "baseString" in other._unavailable_fields


def test_production_dot_requires_two_character_prefix_and_self_target_stops():
    a = record("a", unicharString="A")
    short = record("short")
    short._production_state.value = "a.suffix"
    self_target = record("self")
    self_target._production_state.value = "self.suffix"
    index = graph(a, short, self_target)
    finalize_info(index, index.raw_name)
    assert short.baseString == self_target.baseString == ""


def test_short_or_plain_reference_tokens_stay_literal():
    seed = record("seed", marks=["="], anchors=["plain"])
    finalize_info(graph(seed), lambda name: None)
    assert seed.marks == ["="]
    assert seed.anchors == ["plain"]
