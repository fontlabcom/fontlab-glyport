# this_file: tests/test_custom_parameter_order.py
"""Source-backed ordered collection requirements; native acceptance is separate."""

import pytest

from fontlab_glyport.model import GSCustomParameter, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def font():
    return Model(FakeBackend()).font


def test_parameters_when_duplicates_are_disabled_then_first_active_value_wins(font):
    a, b = GSCustomParameter("Filter", "first"), GSCustomParameter("Filter", "second")
    font.customParameters.append(a)
    font.customParameters.append(b)
    assert font.customParameters[0] is a, "Append attaches the actual supplied object"
    a.active = False
    assert "Filter" in font.customParameters, "Membership includes disabled objects"
    assert font.customParameters["Filter"] == "second", (
        "Effective lookup skips inactive entries"
    )
    b.active = False
    assert font.customParameters["Filter"] is None
    a.active = True
    assert font.customParameters["Filter"] == "first", (
        "Active mutation must invalidate lookup"
    )


def test_parameters_when_name_assignment_targets_inactive_first_then_preserves_identity(
    font,
):
    a, b = GSCustomParameter("Filter", "first"), GSCustomParameter("Filter", "second")
    font.customParameters.append(a)
    font.customParameters.append(b)
    a.active = False
    font.customParameters["Filter"] = "changed"
    assert a.value == "changed" and a.active is False
    assert font.customParameters["Filter"] == "second"
    font.customParameters["Filter"] = None
    assert list(font.customParameters) == [b], (
        "None removes only the first matching object"
    )
    del font.customParameters["absent"]
    assert list(font.customParameters) == [b], "Missing name deletion is a no-op"


def test_parameters_when_renamed_then_lookup_and_insertion_order_follow_live_objects(
    font,
):
    a, b = GSCustomParameter("z", 1), GSCustomParameter("a", 2)
    font.customParameters.append(a)
    font.customParameters.append(b)
    a.name = "renamed"
    a.value = 3
    assert [(p.name, p.value) for p in font.customParameters] == [
        ("renamed", 3),
        ("a", 2),
    ]
    assert font.customParameters["z"] is None and font.customParameters["renamed"] == 3


def test_parameters_when_replaced_and_removed_then_obey_strict_index_contract(font):
    a, b, c = (GSCustomParameter(name, name) for name in ["a", "b", "c"])
    font.customParameters.append(a)
    font.customParameters.insert(-1, b)
    assert list(font.customParameters) == [b, a]
    font.customParameters[-1] = c
    assert list(font.customParameters) == [b, c]
    del font.customParameters[-1]
    assert list(font.customParameters) == [b]
    for index in [-3, 2]:
        with pytest.raises(IndexError):
            font.customParameters.insert(index, a)


def test_parameters_when_remove_receives_later_duplicate_then_removes_that_object(font):
    a, b = GSCustomParameter("Filter", 1), GSCustomParameter("Filter", 2)
    font.customParameters.extend([a, b])
    font.customParameters.remove(b)
    assert list(font.customParameters) == [a], "remove(p) removes p, not its name"
    assert b._binding is None and font.customParameters["Filter"] == 1


def test_parameters_when_remove_receives_non_member_then_value_error_and_kept(font):
    other = Model(FakeBackend()).font
    a, foreign = GSCustomParameter("Filter", 1), GSCustomParameter("Filter", 3)
    font.customParameters.append(a)
    other.customParameters.append(foreign)
    for stranger in (GSCustomParameter("Filter", "detached"), foreign):
        with pytest.raises(ValueError, match="not in the collection"):
            font.customParameters.remove(stranger)
    assert list(font.customParameters) == [a] and a.value == 1
    assert list(other.customParameters) == [foreign], "the other font is untouched"
    font.customParameters.remove(a)
    with pytest.raises(ValueError):
        font.customParameters.remove(a)  # already removed: detached


def test_parameters_when_legacy_lib_migrates_then_preserves_values_and_unrelated_keys(
    font,
):
    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    backend = font._model._backend
    backend.libs[font._id] = {
        CUSTOM_PARAMETER_PREFIX + "z": [1],
        CUSTOM_PARAMETER_PREFIX + "a": 2,
        "unrelated": {"x": [3]},
    }
    old = font.customParameters[1]
    assert old.name == "z"
    old.active = False
    font.customParameters.append(GSCustomParameter("a", 4))
    reopened = Model(backend).font
    assert [(p.name, p.value, p.active) for p in reopened.customParameters] == [
        ("a", 2, True),
        ("z", [1], False),
        ("a", 4, True),
    ], "Reconstructing Python proxies must retain duplicate order and inactive records"
    assert backend.libs[font._id]["unrelated"] == {"x": [3]}
    assert CUSTOM_PARAMETER_PREFIX + "z" not in backend.libs[font._id]
    del reopened.customParameters["a"]
    assert reopened.customParameters["a"] == 4, (
        "Mirror and effective lookup must expose next duplicate"
    )


def test_parameters_when_master_and_font_change_then_user_data_stays_separate(font):
    master = font.masters[0]
    master.userData["owned"] = {"a": [1]}
    font.userData["font-only"] = 2
    master.customParameters.append(GSCustomParameter("Filter", "master"))
    font.customParameters.append(GSCustomParameter("Filter", "font"))
    assert dict(master.userData) == {"owned": {"a": [1]}}, (
        "Internal parameter storage must not leak into userData"
    )
    master.userData["next"] = 3
    assert master.customParameters["Filter"] == "master", (
        "userData writes must preserve ordered parameters"
    )
    assert font.customParameters["Filter"] == "font"
    assert dict(font.userData) == {"font-only": 2}


def test_parameters_when_removed_or_replaced_then_old_object_detaches(font):
    from copy import copy

    a, b = GSCustomParameter("a", [1]), GSCustomParameter("b", 2)
    font.customParameters.append(a)
    assert a.parent is font
    copied = copy(a)
    assert copied.parent is font and copied is not a
    copied.value.append(3)
    assert a.value == [1], "Copies own their nested value"
    font.customParameters[0] = b
    assert a.parent is None and b.parent is font
    a.value = "detached"
    assert font.customParameters["b"] == 2
    del font.customParameters[:]
    assert b.parent is None and len(font.customParameters) == 0


def test_parameters_when_backend_refuses_write_then_objects_and_lib_remain_unchanged(
    font, monkeypatch
):
    from copy import deepcopy

    backend = font._model._backend
    a, b = GSCustomParameter("a", 1), GSCustomParameter("b", 2)
    font.customParameters.append(a)
    before = deepcopy(dict(backend.libs))

    def refuse(*args):
        raise RuntimeError("write refused")

    monkeypatch.setattr(backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="write refused"):
        font.customParameters[0] = b
    assert a.parent is font and b.parent is None
    assert a.value == 1 and backend.libs == before
    with pytest.raises(RuntimeError, match="write refused"):
        a.value = 3
    assert a.value == 1


@pytest.mark.parametrize("bad", [None, {}, [{"id": "bad"}]])
def test_parameters_when_ordered_data_is_malformed_then_refuses_without_repair(
    font, bad
):
    from copy import deepcopy

    backend = font._model._backend
    key = font.customParameters._key
    backend.libs[font._id] = {key: bad, "unrelated": 1}
    before = deepcopy(dict(backend.libs))
    with pytest.raises(ValueError, match="Invalid ordered"):
        font.customParameters.append(GSCustomParameter("x", 1))
    assert backend.libs == before, (
        "Malformed retained data must never be silently overwritten"
    )


def test_parameters_when_flat_writer_adds_new_key_then_retains_it_on_next_write(font):
    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    backend = font._model._backend
    font.customParameters.append(GSCustomParameter("a", 1))
    lib = backend.lib(font._id)
    lib[CUSTOM_PARAMETER_PREFIX + "external"] = [9]
    backend.set_lib(font._id, lib)
    assert font.customParameters["external"] == [9]
    font.customParameters.append(GSCustomParameter("next", 2))
    assert font.customParameters["external"] == [9]
    assert backend.lib(font._id)[CUSTOM_PARAMETER_PREFIX + "external"] == [9]


def _flat_edit(font, **values):
    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    backend = font._model._backend
    lib = backend.lib(font._id)
    for name, value in values.items():
        if value is None:
            del lib[CUSTOM_PARAMETER_PREFIX + name]
        else:
            lib[CUSTOM_PARAMETER_PREFIX + name] = value
    backend.set_lib(font._id, lib)


def _drained(font):
    out = []
    font._finish_undo(out.append)
    return [d.code for d in out]


def test_parameters_when_flat_writer_changes_existing_mirror_then_flat_wins(font):
    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    a, dup, z = (GSCustomParameter(n, v) for n, v in [("a", 1), ("a", 5), ("z", 0)])
    font.customParameters.extend([a, dup, z])
    _flat_edit(font, a=7)
    cp = font.customParameters
    assert (len(cp), cp["a"], a.value, dup.value) == (3, 7, 7, 5), (
        "reads never raise; the effective row takes the flat value, keeping order"
    )
    assert list(cp) == [a, dup, z] and [p.name for p in cp] == ["a", "a", "z"]
    assert _drained(font) == ["CUSTOM_PARAMETERS_REBUILT"] and _drained(font) == []
    cp["y"] = 3  # writes persist the repair
    lib = font._model._backend.lib(font._id)
    assert lib[CUSTOM_PARAMETER_PREFIX + "a"] == 7 and cp["y"] == 3
    assert _drained(font) == [], "repaired once: no further drift"


def test_parameters_when_flat_key_deleted_or_revived_then_follows_flat_keys(font):
    a, b = GSCustomParameter("a", 1), GSCustomParameter("b", 2)
    off = GSCustomParameter("c", 3)
    font.customParameters.extend([a, b, off])
    off.active = False
    _flat_edit(font, a=None, c=9)  # a deleted outside; c set while only inactive
    cp = font.customParameters
    assert (cp["a"], cp["b"], cp["c"]) == (None, 2, 9)
    assert [(p.name, p.active) for p in cp] == [("b", True), ("c", False), ("c", True)]
    assert "CUSTOM_PARAMETERS_REBUILT" in _drained(font)
    cp.append(GSCustomParameter("d", 4))
    assert [p.name for p in cp] == ["b", "c", "c", "d"] and cp["c"] == 9


def test_parameters_when_empty_name_then_indexed_object_remains_but_name_lookup_is_absent(
    font,
):
    p = GSCustomParameter(None, 7)
    assert p.name == "", "Native setter normalizes nil name to empty"
    font.customParameters.append(p)
    assert font.customParameters[0] is p
    assert font.customParameters[""] is None and "" not in font.customParameters
    del font.customParameters[""]
    assert len(font.customParameters) == 1
    p.name = "renamed"
    assert font.customParameters["renamed"] == 7
    p.name = None
    assert p.name == ""


def test_parameters_when_mutated_during_iteration_then_uses_initial_count(font):
    font.customParameters.extend([GSCustomParameter("a", 1), GSCustomParameter("b", 2)])
    iterator = iter(font.customParameters)
    assert next(iterator).name == "a"
    font.customParameters.append(GSCustomParameter("c", 3))
    assert [p.name for p in iterator] == ["b"], (
        "An appended item is outside the initial count"
    )
    iterator = iter(font.customParameters)
    next(iterator)
    del font.customParameters[1:]
    with pytest.raises(IndexError):
        next(iterator)


def test_parameters_when_legacy_name_is_reused_then_imported_identity_stays_distinct(
    font,
):
    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    backend = font._model._backend
    backend.libs[font._id] = {CUSTOM_PARAMETER_PREFIX + "external": 1}
    original = font.customParameters[0]
    original.name = "renamed"
    lib = backend.lib(font._id)
    lib[CUSTOM_PARAMETER_PREFIX + "external"] = 2
    backend.set_lib(font._id, lib)
    added = font.customParameters[1]
    assert added is not original and font.customParameters[1] is added
    added.value = 3
    reopened = Model(backend).font
    assert [(p.name, p.value) for p in reopened.customParameters] == [
        ("renamed", 1),
        ("external", 3),
    ]
