# this_file: tests/test_glyph_case_lifecycle.py
"""Case defaults and overrides used by original spacing and kerning scripts."""

from contextlib import nullcontext

import pytest

from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def case_lifecycle_info(owned_info_manager):
    """Complete owned parser rows for explicit lifecycle operations only."""
    return owned_info_manager(
        [
            {
                "name": "A",
                "unicode": "0041",
                "category": "Letter",
                "case": "upper",
                "script": "latin",
            },
            {
                "name": "f_f_i",
                "category": "Letter",
                "subCategory": "Ligature",
                "case": "lower",
                "script": "latin",
            },
        ]
    )


def selected_lifecycle_info(glyph, manager):
    """Use document selection when attached and an explicit scope when detached."""
    if glyph.parent is None:
        return manager._scope()
    glyph.parent.parent._local_glyph_info = manager
    return nullcontext()


def owned_glyph(name, attached):
    glyph = GSGlyph(name)
    if attached:
        font = Model(FakeBackend()).font
        if name == "A":
            return font.glyphs[name]
        font.glyphs.append(glyph)
        return font.glyphs[name]
    return glyph


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize(
    "name, expected",
    [
        ("A", 1),
        ("f_f_i", 2),
        ("ordfeminine", 4),
        ("exclam", 1),
        ("less", 2),
        ("acutecomb", 2),
    ],
)
def test_case_when_known_name_then_database_classification(name, expected, attached):
    glyph = owned_glyph(name, attached)
    assert glyph.case == expected, "Glyph case must preserve Glyph Info classification"


def test_case_when_attached_local_override_reset_then_database_default():
    glyph = owned_glyph("A", True)
    assert glyph.storeCase is False, "New glyphs derive case from Glyph Info"
    glyph.storeCase = True
    glyph.case = 3
    assert glyph.case == 3, "Explicit small-cap case must remain readable"
    glyph.storeCase = False
    assert glyph.case == 1, "Disabling stored case must restore the name default"


@pytest.mark.parametrize("attached", [False, True])
def test_case_when_unstored_assignment_then_false_assignment_is_noop(attached):
    glyph = owned_glyph("A", attached)
    glyph.case = 3
    assert glyph.case == 3 and glyph.storeCase is False, (
        "Case setter does not enable storage"
    )
    glyph.storeCase = False
    assert glyph.case == 3, "False-to-false storage assignment does not refresh case"


def test_minor_figure_filter_when_metadata_defined_then_original_predicate_selects():
    glyphs = [owned_glyph(name, False) for name in ("A", "ordfeminine", "one")]
    assert [g.name for g in glyphs if g.case == 4] == ["ordfeminine"], (
        "CopyModelsToDerivatives minor-number predicate must retain the ordinal"
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("stored", [False, True])
def test_case_when_renamed_then_only_stored_override_survives(
    attached, stored, case_lifecycle_info
):
    glyph = owned_glyph("A", attached)
    glyph.storeCase = stored
    glyph.case = 3
    with selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.name = "f_f_i"
    assert glyph.case == (3 if stored else 2), "Rename must honor explicit storage"


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("stored", [False, True])
def test_case_when_info_updated_then_only_stored_override_survives(
    attached, stored, case_lifecycle_info
):
    glyph = owned_glyph("A", attached)
    glyph.storeCase = stored
    glyph.case = 3
    with selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.updateGlyphInfo(changeName=False)
    assert glyph.case == (3 if stored else 1), "Metadata refresh must honor storage"


@pytest.mark.parametrize("attached", [False, True])
def test_case_when_name_unchanged_or_unknown_then_temporary_case_survives(attached):
    glyph = owned_glyph("A", attached)
    glyph.case = 3
    glyph.name = "A"
    assert glyph.case == 3, "Same-name assignment must not refresh metadata"
    glyph.name = "glyportOwnedUnknownCaseName"
    assert glyph.case == 3, "A missing metadata record must not discard current case"


@pytest.mark.parametrize("stored", [False, True])
def test_case_when_unique_draft_attached_then_current_value_and_flag_survive(stored):
    glyph = owned_glyph("f_f_i", False)
    glyph.storeCase = stored
    glyph.case = 3
    font = Model(FakeBackend()).font
    font.glyphs.append(glyph)
    assert (glyph.case, glyph.storeCase) == (3, stored), (
        "Attachment must preserve case state"
    )


@pytest.mark.parametrize("stored", [False, True])
def test_case_when_attached_glyph_copied_then_case_and_flag_survive(stored):
    glyph = owned_glyph("A", True)
    glyph.storeCase = stored
    glyph.case = 3
    copied = glyph.copy()
    assert copied.parent is None, "Copied fixture must be detached"
    assert (copied.case, copied.storeCase) == (3, stored), (
        "Copy must retain both fields"
    )
    copied.case = 2
    assert glyph.case == 3, "Detached changes must not mutate the source"


@pytest.mark.parametrize("value", [-1, 256, 1.5, "1", None])
def test_case_when_invalid_unsigned_byte_then_preserves_state(value):
    glyph = owned_glyph("A", True)
    with pytest.raises((TypeError, ValueError)):
        glyph.case = value
    assert (glyph.case, glyph.storeCase) == (1, False), (
        "Invalid values must not mutate case"
    )


@pytest.mark.parametrize("value", [0, 5, 255])
def test_case_when_unsigned_byte_then_value_retained(value):
    glyph = owned_glyph("A", False)
    glyph.case = value
    assert glyph.case == value, "The native byte setter is not limited to named enums"


def test_store_case_when_detached_reset_then_refuses_without_mutation():
    from fontlab_glyport.errors import UnsupportedCapability

    glyph = owned_glyph("A", False)
    glyph.storeCase = True
    glyph.case = 3
    with pytest.raises(UnsupportedCapability, match="detachedReset"):
        glyph.storeCase = False
    assert (glyph.case, glyph.storeCase) == (3, True), (
        "Unsupported reset must retain state"
    )


def test_case_when_read_or_same_assignment_then_no_lib_write(monkeypatch):
    glyph = owned_glyph("A", True)
    backend = glyph._font._model._backend

    def fail(*args):
        pytest.fail("Reading or assigning unchanged case must not write a lib")

    monkeypatch.setattr(backend, "set_lib", fail)
    assert glyph.case == 1, "Known database case should be readable"
    glyph.case = 1
    glyph.storeCase = False


def test_store_case_when_enabled_then_snapshots_default(
    monkeypatch, case_lifecycle_info
):
    glyph = owned_glyph("A", True)
    glyph.storeCase = True
    monkeypatch.setattr(GSGlyph, "_default_case", staticmethod(lambda name: 2))
    assert glyph.case == 1, "Enabled storage must keep the original value"
    with selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.name = "f_f_i"
    assert glyph.case == 1, "Stored default must survive rename"


@pytest.mark.parametrize("operation", ["rename", "update", "reset"])
def test_case_when_database_failure_then_propagates_before_mutation(
    monkeypatch, operation, case_lifecycle_info
):
    from fontlab_glyport.errors import UnsupportedCapability

    glyph = owned_glyph("A", True)
    glyph.case = 3
    if operation == "reset":
        glyph.storeCase = True
    previous = glyph._case_state()
    failure = UnsupportedCapability("missing dependency", capability="owned.dependency")

    def refuse(*args, **kwargs):
        raise failure

    glyph.parent.parent._local_glyph_info = case_lifecycle_info
    monkeypatch.setattr(case_lifecycle_info, "_scope", refuse)
    with pytest.raises(UnsupportedCapability) as caught:
        if operation == "rename":
            glyph.name = "f_f_i"
        elif operation == "update":
            glyph.updateGlyphInfo(changeName=False)
        else:
            glyph.storeCase = False
    assert caught.value is failure, "Dependency failure must not become a metadata miss"
    assert (glyph.name, glyph.unicode, glyph._case_state()) == (
        "A",
        "0041",
        previous,
    ), "Metadata refusal must happen before mutation"


def test_case_when_unknown_database_enum_then_propagates(monkeypatch):
    from glyphsLib import glyphdata

    from fontlab_glyport.errors import UnsupportedCapability

    glyph = owned_glyph("A", True)
    glyph.case = 3
    attributes = dict(glyphdata.GLYPHDATA.names["f_f_i"], case="ownedUnknown")
    data = glyphdata.GLYPHDATA
    names = dict(data.names, f_f_i=attributes)
    monkeypatch.setattr(
        glyphdata,
        "GLYPHDATA",
        glyphdata.GlyphData(
            names, data.alternative_names, data.production_names, data.unicodes
        ),
    )
    with pytest.raises(UnsupportedCapability) as caught:
        glyph.name = "f_f_i"
    assert caught.value.capability == "GSGlyphInfo.case", (
        "Unknown enums must not be swallowed"
    )
    assert (glyph.name, glyph.case) == ("A", 3), "Enum refusal must preserve glyph"


def test_store_case_when_lib_write_fails_then_preserves_flag_and_case(monkeypatch):
    glyph = owned_glyph("A", True)
    glyph.storeCase = True
    glyph.case = 3

    def refuse(*args):
        raise RuntimeError("owned lib failure")

    monkeypatch.setattr(glyph._font._model._backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="owned lib failure"):
        glyph.storeCase = False
    assert (glyph.case, glyph.storeCase) == (3, True), (
        "Reset must use one atomic lib write"
    )


def test_case_when_rename_storage_fails_then_name_and_state_restored(
    monkeypatch, case_lifecycle_info
):
    glyph = owned_glyph("A", True)
    glyph.case = 3

    def refuse(*args):
        raise RuntimeError("owned lib failure")

    monkeypatch.setattr(glyph._font._model._backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="owned lib failure"), selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.name = "f_f_i"
    assert (glyph.name, glyph.unicode, glyph.case) == ("A", "0041", 3), (
        "A failed case refresh must roll back the successful rename"
    )


def test_case_when_attachment_storage_fails_then_insertion_removed_and_draft_preserved(
    monkeypatch,
):
    glyph = owned_glyph("f_f_i", False)
    glyph.case = 3
    font = Model(FakeBackend()).font
    before = [g.name for g in font.glyphs]

    def refuse(*args):
        raise RuntimeError("owned lib failure")

    monkeypatch.setattr(font._model._backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="owned lib failure"):
        font.glyphs.append(glyph)
    assert [g.name for g in font.glyphs] == before, (
        "Failed attachment must remove insertion"
    )
    assert (glyph.parent, glyph.case, glyph.storeCase) == (None, 3, False), (
        "Failed attachment must retain caller's detached state"
    )


def test_case_when_update_storage_fails_then_unicode_and_state_preserved(
    monkeypatch, case_lifecycle_info
):
    glyph = owned_glyph("A", True)
    glyph.unicode = "0042"
    glyph.case = 3

    def refuse(*args):
        raise RuntimeError("owned lib failure")

    monkeypatch.setattr(glyph._font._model._backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="owned lib failure"), selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.updateGlyphInfo(changeName=False)
    assert (glyph.name, glyph.unicode, glyph.case) == ("A", "0042", 3), (
        "A new case-write failure must not leave a partially updated Unicode"
    )


def test_case_when_rename_recovery_fails_then_both_errors_retained(
    monkeypatch, case_lifecycle_info
):
    from fontlab_glyport.errors import PartialFailure

    glyph = owned_glyph("A", True)
    glyph.case = 3
    backend = glyph._font._model._backend
    rename = backend.rename_glyph

    def refuse_lib(*args):
        raise RuntimeError("owned lib failure")

    def refuse_recovery(font, token, name):
        if name == "A":
            raise RuntimeError("owned rename recovery failure")
        rename(font, token, name)

    monkeypatch.setattr(backend, "set_lib", refuse_lib)
    monkeypatch.setattr(backend, "rename_glyph", refuse_recovery)
    with pytest.raises(PartialFailure) as caught, selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.name = "f_f_i"
    assert [str(error) for error in caught.value.errors] == [
        "owned lib failure",
        "owned rename recovery failure",
    ], "Both original and rollback failures must remain visible"


def test_case_when_unknown_name_replaces_unmaterialized_default_then_keeps_previous_case():
    glyph = owned_glyph("A", True)
    glyph.name = "glyportOwnedUnknownCaseName"
    assert glyph.case == 1, (
        "Unknown rename must preserve the previous effective default"
    )


def test_case_when_dependency_missing_then_read_refuses_and_existing_override_survives(
    monkeypatch,
):
    import sys

    from fontlab_glyport.errors import UnsupportedCapability

    default = owned_glyph("A", True)
    explicit = owned_glyph("A", False)
    explicit.case = 3
    monkeypatch.setitem(sys.modules, "glyphsLib", None)
    with pytest.raises(
        UnsupportedCapability, match="requires the glyphsLib dependency"
    ):
        _ = default.case
    assert explicit.case == 3, "Reading a known snapshot need not consult metadata"


def test_store_case_when_reset_then_preserves_other_glyph_lib_values():
    glyph = owned_glyph("A", True)
    glyph.userData["owned.case.control"] = {"keep": [1, 2]}
    glyph.storeCase = True
    glyph.case = 255
    glyph.storeCase = False
    assert glyph.userData["owned.case.control"] == {"keep": [1, 2]}, (
        "Case updates must retain unrelated glyph lib entries"
    )


def test_case_when_update_recovery_fails_then_both_errors_retained(
    monkeypatch, case_lifecycle_info
):
    from fontlab_glyport.errors import PartialFailure

    glyph = owned_glyph("A", True)
    glyph.unicodes = ["10FFFF", "0042"]
    glyph.case = 3
    backend = glyph._font._model._backend
    write_codes = backend.set_glyph_unicodes

    def refuse_lib(*args):
        raise RuntimeError("owned lib failure")

    def refuse_recovery(token, codes):
        if codes == ("10FFFF", "0042"):
            raise RuntimeError("owned Unicode recovery failure")
        write_codes(token, codes)

    monkeypatch.setattr(backend, "set_lib", refuse_lib)
    monkeypatch.setattr(backend, "set_glyph_unicodes", refuse_recovery)
    with pytest.raises(PartialFailure) as caught, selected_lifecycle_info(glyph, case_lifecycle_info):
        glyph.updateGlyphInfo(changeName=False)
    assert [str(error) for error in caught.value.errors] == [
        "owned lib failure",
        "owned Unicode recovery failure",
    ], "Both original and rollback failures must remain visible"


def test_case_when_unencoded_draft_attached_then_case_write_has_history_scope(
    monkeypatch,
):
    backend = FakeBackend()
    font = Model(backend).font
    glyph = GSGlyph("glyportOwnedUnencodedCaseName")
    glyph.case = 3
    glyph.storeCase = True
    assert glyph.unicodes == [], "Fixture must exercise unencoded attachment"
    events = []
    begin, end = backend.begin_undo, backend.end_undo
    write = backend.set_lib

    def begin_scope(name):
        events.append("begin")
        begin(name)

    def end_scope():
        events.append("end")
        end()

    def write_in_scope(token, data):
        assert events == ["begin"], "Case storage must occur inside history scope"
        events.append("write")
        write(token, data)

    monkeypatch.setattr(backend, "begin_undo", begin_scope)
    monkeypatch.setattr(backend, "end_undo", end_scope)
    monkeypatch.setattr(backend, "set_lib", write_in_scope)
    font.glyphs.append(glyph)
    assert events == ["begin", "write", "end"], "Scope must close after attachment"
    assert (glyph.case, glyph.storeCase) == (3, True), "Attachment must retain case"
