# this_file: tests/test_compound_position.py
"""Owned records and name classifiers for retained positional mutation semantics."""

from types import SimpleNamespace

import pytest

from fontlab_glyport.model.compound_position import apply_positions
from fontlab_glyport.model.production_metadata import StoredProduction


def record(name, locked=False, production=None):
    return SimpleNamespace(
        name=name,
        _locked=locked,
        unicode="0041",
        unicodeLegacy="F041",
        unicharString="cached",
        _production_state=StoredProduction(production),
        baseString="base",
        anchors=["owned"],
        marker=object(),
    )


@pytest.mark.parametrize(
    "position,kinds,expected",
    [
        (None, "DDD", ["a.init", "b.medi", "c.fina"]),
        ("init", "DDD", ["a.init", "b.medi", "c.medi"]),
        ("medi", "DDD", ["a.medi", "b.medi", "c.medi"]),
        ("fina", "DDD", ["a.medi", "b.medi", "c.fina"]),
        (None, "RDD", ["a", "b.init", "c.fina"]),
        (None, "DRD", ["a.init", "b.fina", "c"]),
        (None, "DDR", ["a.init", "b.medi", "c.fina"]),
        (None, "RDR", ["a", "b.init", "c.fina"]),
        (None, "RRD", ["a", "b", "c"]),
        (None, "DRR", ["a.init", "b.fina", "c"]),
        (None, "RRR", ["a", "b", "c"]),
        ("medi", "RRR", ["a.fina", "b", "c"]),
        ("fina", "RDD", ["a.fina", "b.init", "c.fina"]),
        ("init", "DRD", ["a.init", "b.fina", "c.init"]),
    ],
)
def test_positions_when_join_boundaries_and_r_vary_then_ordered_names_match(
    position, kinds, expected
):
    components = [record(name) for name in "abc"]
    source_ids = [id(item) for item in components]
    classes = dict(zip("abc", kinds))
    assert (
        apply_positions(components, position, lambda name: None, classes.__getitem__)
        is None
    )
    assert [item.name for item in components] == expected, "D/R transition mismatch"
    assert [id(item) for item in components] == source_ids, (
        "Unlocked records mutate in place"
    )


@pytest.mark.parametrize("position", [None, "init", "medi", "fina"])
@pytest.mark.parametrize("kind", ["D", "R"])
def test_positions_when_single_record_then_both_entry_flags_apply(position, kind):
    item = record("a")
    components = [item]
    expected = {None: "a", "init": "a.init", "medi": "a.medi", "fina": "a.fina"}[
        position
    ]
    if kind == "R":
        expected = {"a.init": "a", "a.medi": "a.fina"}.get(expected, expected)
    apply_positions(components, position, lambda name: None, lambda name: kind)
    assert item.name == expected and components[0] is item


@pytest.mark.parametrize("position", [None, "init", "medi", "fina"])
def test_positions_when_empty_then_callbacks_are_not_called(position):
    def forbidden(name):
        pytest.fail(f"Unexpected callback for empty components: {name}")

    components = []
    assert apply_positions(components, position, forbidden, forbidden) is None
    assert components == []


@pytest.mark.parametrize("production", [None, "", "a", "raw.other"])
@pytest.mark.parametrize("locked", [False, True])
def test_positions_when_missing_alternate_then_copy_only_locked_and_clear_encodings(
    locked, production
):
    item = record("a", locked, production)
    before = vars(item).copy()
    components = [item]
    apply_positions(components, "medi", lambda name: None, lambda name: "D")
    result = components[0]
    assert (result is item) is (not locked), "Only locked source gets copied"
    assert result.name == "a.medi" and not result._locked
    assert (result.unicode, result.unicodeLegacy, result.unicharString) == (
        None,
        None,
        None,
    )
    assert result._production_state.value == production, "No production fill"
    assert result.baseString == "base" and result.anchors == before["anchors"]
    if locked:
        assert result.anchors is not item.anchors, (
            "Mutable anchor containers detach with native copy semantics"
        )
    else:
        assert result.anchors is item.anchors
    assert result.marker is before["marker"], "Unrelated field identities survive"
    if locked:
        assert vars(item) == before, "Locked source stays unchanged"
        assert result._production_state is not item._production_state
    else:
        assert result._production_state is before["_production_state"]


def test_positions_when_production_slot_absent_then_locked_copy_preserves_none():
    item = record("a", True)
    item._production_state = None
    components = [item]
    apply_positions(components, "init", lambda name: None, lambda name: "D")
    assert components[0] is not item and components[0]._production_state is None
    assert item.name == "a" and item.unicode == "0041"


@pytest.mark.parametrize("locked", [False, True])
def test_positions_when_raw_alternate_found_then_replaces_without_fill_or_copy(locked):
    source, alternate = record("a", locked, "original"), record("canonical", True)
    source_before, alternate_before = vars(source).copy(), vars(alternate).copy()
    calls, components = [], [source]

    def lookup(name):
        calls.append(name)
        return alternate

    apply_positions(components, "fina", lookup, lambda name: "D")
    assert calls == ["a.fina"] and components[0] is alternate
    assert vars(source) == source_before and vars(alternate) == alternate_before
    assert alternate._production_state.value is None, "Raw alternate stays unfilled"


@pytest.mark.parametrize(
    "name,expected,classified",
    [
        ("a.init.extra", ["a.init.extra", "b.fina"], ["b"]),
        ("a.medial", ["a.medial", "b.fina"], ["b"]),
        ("a.fina", ["a.fina", "b"], ["b"]),
        ("a.fina.extra", ["a.fina.extra.init", "b.fina"], ["a.fina.extra", "b"]),
        ("a.init.fina", ["a.init.fina", "b.fina"], ["b"]),
    ],
)
def test_positions_when_existing_suffix_then_skip_and_break_order_is_exact(
    name, expected, classified
):
    components, calls = [record(name), record("b")], []

    def classifier(name):
        calls.append(name)
        return "D"

    apply_positions(components, None, lambda name: None, classifier)
    assert [item.name for item in components] == expected
    assert calls == classified, "Skipped records never call the classifier"


@pytest.mark.parametrize("locked", [False, True])
def test_positions_when_source_repeated_then_later_slot_observes_prior_mutation(locked):
    item = record("a", locked)
    components = [item, item]
    apply_positions(components, None, lambda name: None, lambda name: "D")
    assert [c.name for c in components] == (
        ["a.init", "a.fina"] if locked else ["a.init", "a.init"]
    )
    assert (components[0] is components[1]) is (not locked)
    if locked:
        assert item.name == "a" and all(c is not item for c in components)


def test_positions_when_alternate_repeated_then_both_slots_reference_same_raw_hit():
    item, alternate = record("a", True), record("other", True)
    components = [item, item]
    apply_positions(components, "medi", lambda name: alternate, lambda name: "D")
    assert components[0] is components[1] is alternate
    assert item.name == "a" and alternate.name == "other"


@pytest.mark.parametrize("kind", ["D", "U", "r", "", "other"])
def test_positions_when_classifier_not_exact_r_then_dual_join_transition_is_used(kind):
    components = [record("a")]
    apply_positions(components, "medi", lambda name: None, lambda name: kind)
    assert components[0].name == "a.medi", "Only the supplied exact R string is special"


@pytest.mark.parametrize("name", ["a.init", "a.medi", "a.fina"])
def test_positions_when_last_record_already_positional_then_no_callback_or_copy(name):
    item = record(name, True)
    before, components = vars(item).copy(), [item]

    def forbidden(value):
        pytest.fail(f"Skipped record called a callback: {value}")

    apply_positions(components, "medi", forbidden, forbidden)
    assert components[0] is item and vars(item) == before


def test_positions_when_unicode_conflicts_then_supplied_name_classifier_alone_decides():
    item = record("owned")
    item.unicode = "0627"
    components, calls = [item], []

    def classifier(name):
        calls.append(("classify", name))
        return "D"

    def lookup(name):
        calls.append(("lookup", name))

    apply_positions(components, "medi", lookup, classifier)
    assert calls == [("classify", "owned"), ("lookup", "owned.medi")]
    assert item.name == "owned.medi", "Unicode never substitutes for supplied name data"


def test_positions_when_lookup_fails_then_exception_precedes_record_mutation():
    item = record("a", True)
    before, components = vars(item).copy(), [item]

    def fail(name):
        raise LookupError(name)

    with pytest.raises(LookupError, match=r"a\.medi"):
        apply_positions(components, "medi", fail, lambda name: "D")
    assert components[0] is item and vars(item) == before
