# this_file: tests/test_glyph_metadata_resolver.py
"""Owned shared metadata resolver and independent classification lifecycles."""

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


def owned(name="A", attached=True):
    glyph = GSGlyph(name)
    if not attached:
        return glyph
    font = Model(FakeBackend()).font
    return font.glyphs["A"] if name == "A" else font.glyphs.append(glyph)


@pytest.mark.parametrize(
    "codes, case, script",
    [
        ([], 1, "latin"),
        (["0041"], 1, "latin"),
        (["0061"], 2, "latin"),
        (["0A15"], 0, "gurmukhi"),
        (["10FFFF", "0A15"], 0, "gurmukhi"),
    ],
)
def test_resets_when_name_conflicts_with_unicode_then_resolver_precedence(
    codes, case, script
):
    glyph = owned()
    glyph.unicodes = codes
    glyph.storeCase = glyph.storeScript = True
    glyph.case, glyph.script = 3, "han"
    glyph.storeCase = False
    assert (glyph.case, glyph.script, glyph.storeScript) == (case, "han", True), (
        "Case reset must resolve Unicode and preserve the independent stored script"
    )
    glyph.storeScript = False
    assert (glyph.case, glyph.script) == (case, script), (
        "Script reset must use the same resolver"
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize(
    "field, flag", [("category", "storeCategory"), ("subCategory", "storeSubCategory")]
)
@pytest.mark.parametrize("value", [None, "", "Owned classification"])
def test_classification_when_set_then_independent_explicit_value(
    attached, field, flag, value
):
    glyph = owned(attached=attached)
    before = (glyph.case, glyph.script)
    setattr(glyph, field, value)
    setattr(glyph, flag, False)
    assert getattr(glyph, field) == value and getattr(glyph, flag) is False, (
        "False-to-false must preserve explicit classification"
    )
    assert (glyph.case, glyph.script) == before, (
        "Classification writes must not modify case/script"
    )


@pytest.mark.parametrize("field", ["category", "subCategory"])
@pytest.mark.parametrize("value", [42, [], {}, object()])
def test_classification_when_wrong_type_then_refuses_before_mutation(field, value):
    glyph = owned()
    before = (glyph.category, glyph.subCategory)
    with pytest.raises(TypeError):
        setattr(glyph, field, value)
    assert (glyph.category, glyph.subCategory) == before, (
        "Unsupported value types must not be silently stringified"
    )


@pytest.mark.parametrize(
    "stored_category, stored_subcategory",
    [(False, False), (False, True), (True, False), (True, True)],
)
@pytest.mark.parametrize("operation", ["rename", "refresh"])
def test_classification_when_refreshed_then_flags_are_independent(
    stored_category, stored_subcategory, operation, owned_info_manager
):
    glyph = owned("acutecomb")
    glyph.parent.parent._local_glyph_info = owned_info_manager()
    glyph.storeCategory, glyph.storeSubCategory = stored_category, stored_subcategory
    glyph.category, glyph.subCategory = "Owned category", "Owned subcategory"
    if operation == "rename":
        glyph.name = "a.ss01"
        expected = ("Letter", None)
    else:
        glyph.updateGlyphInfo(changeName=False)
        expected = ("Mark", "Nonspacing")
    assert (glyph.category, glyph.subCategory) == (
        "Owned category" if stored_category else expected[0],
        "Owned subcategory" if stored_subcategory else expected[1],
    ), "Each field must honor only its own storage flag"


@pytest.mark.parametrize(
    "field, flag, expected",
    [
        ("category", "storeCategory", "Letter"),
        ("subCategory", "storeSubCategory", None),
    ],
)
def test_classification_when_reset_then_only_requested_field_changes(
    field, flag, expected
):
    glyph = owned()
    glyph.userData["owned.control"] = {"keep": [1]}
    glyph.storeCategory = glyph.storeSubCategory = True
    glyph.category, glyph.subCategory = "Owned category", "Owned subcategory"
    setattr(glyph, flag, False)
    assert getattr(glyph, field) == expected, "Reset must accept valid None metadata"
    other = "subCategory" if field == "category" else "category"
    assert getattr(glyph, other) == (
        "Owned subcategory" if other == "subCategory" else "Owned category"
    ), "Reset must preserve other stored classification"
    assert glyph.userData["owned.control"] == {"keep": [1]}, (
        "Reset must preserve unrelated glyph data"
    )


@pytest.mark.parametrize("attached", [False, True])
def test_classification_when_unicode_only_changes_then_existing_values_do_not_refresh(
    attached,
    owned_info_manager,
):
    from contextlib import nullcontext

    manager = owned_info_manager()
    glyph = owned("glyportOwnedUnencoded", attached)
    if attached:
        glyph.parent.parent._local_glyph_info = manager
    glyph.unicode = "0301"
    assert (glyph.category, glyph.subCategory) == (None, None), (
        "Unicode assignment is not a metadata-refresh operation"
    )
    with nullcontext() if attached else manager._scope():
        glyph.updateGlyphInfo(changeName=False)
    assert (glyph.category, glyph.subCategory) == ("Mark", "Nonspacing"), (
        "Explicit refresh resolves the encoding"
    )


@pytest.mark.parametrize("attached", [False, True])
def test_classification_when_missing_name_renamed_then_previous_values_survive(
    attached,
):
    glyph = owned("acutecomb", attached)
    glyph.unicodes = []
    glyph.name = "glyportOwnedUnknownClassification"
    assert (glyph.category, glyph.subCategory) == ("Mark", "Nonspacing"), (
        "Missing-name rename must preserve effective classification"
    )


@pytest.mark.parametrize(
    "stored_category, stored_subcategory",
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_classification_when_entire_resolution_missing_then_refresh_clears_only_unstored(
    stored_category, stored_subcategory
):
    glyph = owned("glyportOwnedUnknownClassification")
    glyph.storeCategory, glyph.storeSubCategory = stored_category, stored_subcategory
    glyph.category, glyph.subCategory = "Owned category", "Owned subcategory"
    glyph.case, glyph.script = 3, "han"
    glyph.updateGlyphInfo(changeName=False)
    assert (glyph.category, glyph.subCategory) == (
        "Owned category" if stored_category else None,
        "Owned subcategory" if stored_subcategory else None,
    ), "A true resolver miss clears unstored classifications"
    assert (glyph.case, glyph.script) == (3, "han"), (
        "Missing-record branch must preserve case/script"
    )


@pytest.mark.parametrize("category", ["Icon", "SF-Symbol"])
def test_resolver_when_keep_name_category_then_early_return_bypasses_unicode(category):
    glyph = owned()
    glyph.category = category
    glyph.unicode = "0A15"
    glyph.storeCase = glyph.storeScript = True
    glyph.case, glyph.script = 3, "han"
    glyph.storeCase = False
    glyph.storeScript = False
    assert (glyph.case, glyph.script, glyph.category) == (0, None, category), (
        "Keep-name category uses minimal info before Unicode/overlays"
    )


@pytest.mark.parametrize("attached", [False, True])
def test_classification_when_copy_appended_then_value_flags_and_unrelated_state_survive(
    attached,
):
    glyph = owned("glyportOwnedClassification", attached)
    glyph.category, glyph.subCategory = "Corner", ""
    glyph.storeCategory = True
    glyph.case, glyph.script = 3, None
    copied = glyph.copy()
    assert (
        copied.category,
        copied.subCategory,
        copied.storeCategory,
        copied.storeSubCategory,
        copied.case,
        copied.script,
    ) == ("Corner", "", True, False, 3, None), "Copy must snapshot each field and flag"
    copied.name = "glyportOwnedClassificationCopy"
    font = Model(FakeBackend()).font
    font.glyphs.append(copied)
    copied.subCategory = "Owned change"
    assert glyph.subCategory == "", "Copy attachment must remain independent"
    assert (copied.category, copied.case, copied.script) == ("Corner", 3, None), (
        "Append must preserve all metadata"
    )


@pytest.mark.parametrize(
    "field, flag", [("category", "storeCategory"), ("subCategory", "storeSubCategory")]
)
def test_classification_when_detached_reset_then_refuses_without_mutation(field, flag):
    glyph = owned(attached=False)
    setattr(glyph, flag, True)
    setattr(glyph, field, "Owned override")
    with pytest.raises(UnsupportedCapability):
        setattr(glyph, flag, False)
    assert getattr(glyph, field) == "Owned override" and getattr(glyph, flag), (
        "Unsupported detached reset must retain caller state"
    )


def test_classification_when_noop_values_then_no_backend_write(monkeypatch):
    glyph = owned()

    def refuse(*args):
        pytest.fail("No-op classification operation wrote backend state")

    monkeypatch.setattr(glyph._font._model._backend, "set_lib", refuse)
    assert (glyph.category, glyph.subCategory) == ("Letter", None), (
        "Named defaults remain readable"
    )
    glyph.category, glyph.subCategory = "Letter", None
    glyph.storeCategory = glyph.storeSubCategory = False


@pytest.mark.parametrize("operation", ["rename", "refresh", "reset", "attach"])
def test_classification_when_write_fails_then_preserves_state_or_removes_insertion(
    operation, monkeypatch, owned_info_manager
):
    glyph = owned(
        "glyportOwnedClassification" if operation == "attach" else "A",
        operation != "attach",
    )
    glyph.category, glyph.subCategory = "Owned category", "Owned subcategory"
    if operation == "reset":
        glyph.storeCategory = True
    before = (
        glyph.name,
        glyph.unicodes,
        glyph.category,
        glyph.subCategory,
        glyph.storeCategory,
    )
    font = glyph.parent if operation != "attach" else Model(FakeBackend()).font
    if operation in {"rename", "refresh"}:
        font.parent._local_glyph_info = owned_info_manager()
    names = [g.name for g in font.glyphs]

    def refuse(*args):
        raise RuntimeError("owned classification write failure")

    monkeypatch.setattr(font._model._backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="owned classification write failure"):
        if operation == "rename":
            glyph.name = "acutecomb"
        elif operation == "refresh":
            glyph.updateGlyphInfo(changeName=False)
        elif operation == "reset":
            glyph.storeCategory = False
        else:
            font.glyphs.append(glyph)
    assert (
        glyph.name,
        glyph.unicodes,
        glyph.category,
        glyph.subCategory,
        glyph.storeCategory,
    ) == before, "Failure must retain metadata and identity"
    assert [g.name for g in font.glyphs] == names, (
        "Failed insertion/rename must restore font membership"
    )


@pytest.mark.parametrize(
    "code, expected",
    [
        ("0378", ("Other", None, None, 0)),
        ("E000", ("Private Use", None, None, 0)),
        ("F8FF", ("Private Use", None, None, 0)),
        ("F900", ("Letter", None, "han", 0)),
        ("F0000", ("Private Use", None, None, 0)),
        ("FFFFD", ("Private Use", None, None, 0)),
        ("FFFFE", ("Other", None, None, 0)),
        ("100000", ("Private Use", None, None, 0)),
        ("10FFFD", ("Private Use", None, None, 0)),
        ("10FFFE", ("Other", None, None, 0)),
        ("2E80", ("Letter", None, "han", 0)),
        ("2E99", ("Letter", None, "han", 0)),
        ("2E9A", ("Other", None, None, 0)),
        ("2E9B", ("Letter", None, "han", 0)),
        ("1F2FF", ("Letter", None, "han", 0)),
        ("1F300", ("Other", None, None, 0)),
        ("3134A", ("Letter", None, "han", 0)),
        ("3134B", ("Other", None, None, 0)),
    ],
)
def test_unicode_synthesis_when_xml_has_no_record_then_audited_scalar_facts(
    code, expected
):
    from fontlab_glyport.model import glyph_metadata
    from fontlab_glyport.model.info_records import GlyphInfoIndex
    from fontlab_glyport.model.info_source import selected_index

    with selected_index(GlyphInfoIndex()):
        record = glyph_metadata.unicode_info(code)
    assert (
        record.category,
        record.subCategory,
        record.script,
        record.case,
    ) == expected, (
        "Synthesis must use retained scalar facts, not Unicode Script inference"
    )


def test_unicode_synthesis_when_scalar_above_native_limit_then_no_record():
    from fontlab_glyport.model import glyph_metadata
    from fontlab_glyport.model.info_records import GlyphInfoIndex
    from fontlab_glyport.model.info_source import selected_index

    with selected_index(GlyphInfoIndex()):
        assert glyph_metadata.unicode_info("10FFFF") is None, (
            "The retained native upper bound excludes 10FFFF"
        )


def test_unicode_resolution_when_first_code_synthesizes_then_later_known_code_is_not_used():
    glyph = owned()
    glyph.unicodes = ["0378", "0A15"]
    glyph.storeScript = True
    glyph.script = "han"
    glyph.storeScript = False
    assert glyph.script is None, (
        "A synthesized first result wins over later XML records"
    )


@pytest.mark.parametrize(
    "field, flag",
    [
        ("case", "storeCase"),
        ("script", "storeScript"),
        ("category", "storeCategory"),
        ("subCategory", "storeSubCategory"),
    ],
)
def test_unicode_resolution_when_xml_record_exists_then_data_precedes_synthesis(
    field, flag
):
    glyph = owned()
    glyph.unicode = "0041"
    setattr(glyph, flag, True)
    setattr(
        glyph,
        field,
        {"case": 3, "script": "han", "category": "Owned", "subCategory": "Owned"}[
            field
        ],
    )
    setattr(glyph, flag, False)
    assert (
        getattr(glyph, field)
        == {"case": 1, "script": "latin", "category": "Letter", "subCategory": None}[
            field
        ]
    ), "Known Unicode metadata must precede the scalar synthesis route"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("a.ss01", ("Letter", None, "latin", 2)),
        ("acutecomb.case", ("Mark", "Nonspacing", None, 1)),
        ("one.osf", ("Number", "Decimal Digit", None, 2)),
        ("a.case.osf", ("Letter", None, "latin", 1)),
        ("a.osf.case", ("Letter", None, "latin", 1)),
        ("a.sups", ("Letter", None, "latin", 4)),
        ("A.sc", ("Letter", None, "latin", 3)),
        ("a.sc", ("Letter", None, "latin", 3)),
        ("a.sc.sups", ("Letter", None, "latin", 3)),
    ],
)
def test_suffix_resolution_when_audited_field_modifier_then_preserves_base_metadata(
    name, expected, owned_info_manager
):
    glyph = owned(name)
    glyph.parent.parent._local_glyph_info = owned_info_manager()
    glyph.updateGlyphInfo(changeName=False)
    assert (glyph.category, glyph.subCategory, glyph.script, glyph.case) == expected, (
        "Supported suffix field modifiers must match their audited precedence"
    )


@pytest.mark.parametrize("encoded", [False, True])
def test_suffix_resolution_when_font_base_has_stored_metadata_then_encoding_selects_route(
    encoded,
    owned_info_manager,
):
    font = Model(FakeBackend()).font
    font.parent._local_glyph_info = owned_info_manager()
    base = font.glyphs["A"]
    if not encoded:
        base.unicodes = []
    base.category = "Mark"
    base.subCategory = "Nonspacing"
    base.script = "han"
    base.case = 3
    base.storeCategory = base.storeSubCategory = base.storeScript = base.storeCase = (
        True
    )
    alternate = font.glyphs.append(GSGlyph("A.alt"))
    alternate.updateGlyphInfo(changeName=False)
    assert (
        alternate.category,
        alternate.subCategory,
        alternate.script,
        alternate.case,
    ) == (
        ("Mark", "Nonspacing", "han", 3) if encoded else ("Letter", None, "latin", 1)
    ), (
        "Only an encoded font base is eligible; global fallback ignores unencoded base overlays"
    )
    assert (base.category, base.subCategory, base.script, base.case) == (
        "Mark",
        "Nonspacing",
        "han",
        3,
    ), "Choosing a fallback must not alter the independently stored base metadata"


def test_classification_when_unencoded_draft_attached_then_write_has_history_scope(
    monkeypatch,
):
    glyph = owned("glyportOwnedClassificationDraft", False)
    glyph.category, glyph.subCategory = "Corner", None
    font = Model(FakeBackend()).font
    backend = font._model._backend
    events = []
    begin, write, end = backend.begin_undo, backend.set_lib, backend.end_undo

    def begin_scope(name):
        events.append("begin")
        begin(name)

    def write_in_scope(token, state):
        assert events == ["begin"], (
            "Classification attachment write needs history scope"
        )
        events.append("write")
        write(token, state)

    def end_scope():
        events.append("end")
        end()

    monkeypatch.setattr(backend, "begin_undo", begin_scope)
    monkeypatch.setattr(backend, "set_lib", write_in_scope)
    monkeypatch.setattr(backend, "end_undo", end_scope)
    font.glyphs.append(glyph)
    assert events == ["begin", "write", "end"], (
        "History must enclose classification write"
    )
    assert glyph.category == "Corner", "Attachment must preserve the authored category"


@pytest.mark.parametrize("operation", ["rename", "refresh", "reset"])
def test_metadata_when_resolution_fails_then_no_mutation(operation, monkeypatch):
    from fontlab_glyport.model import glyph_metadata

    glyph = owned()
    glyph.category, glyph.subCategory = "Owned category", ""
    glyph.storeCategory = operation == "reset"
    before = (glyph.name, glyph.unicodes, glyph._case_state())

    def refuse(*args, **kwargs):
        raise RuntimeError("owned shared resolution failure")

    monkeypatch.setattr(glyph_metadata, "resolve", refuse)
    with pytest.raises(RuntimeError, match="owned shared resolution failure"):
        if operation == "rename":
            glyph.name = "acutecomb"
        elif operation == "refresh":
            glyph.updateGlyphInfo(changeName=False)
        else:
            glyph.storeCategory = False
    assert (glyph.name, glyph.unicodes, glyph._case_state()) == before, (
        "Resolver failures must occur before name, encoding or metadata writes"
    )


@pytest.mark.parametrize("operation", ["rename", "refresh"])
def test_private_use_resolution_when_multiple_encodings_then_preserves_complete_list(
    operation,
):
    glyph = owned()
    glyph.unicodes = ["10FFFD", "0A15"]
    if operation == "rename":
        glyph.name = "glyportOwnedPrivateUse"
    else:
        glyph.updateGlyphInfo()
    assert glyph.unicodes == ["10FFFD", "0A15"], (
        "Private-use postprocessing must preserve the entire glyph encoding array"
    )
    assert (glyph.category, glyph.script, glyph.case) == ("Private Use", None, 0), (
        "Private-use resolution must not fall through to the later Gurmukhi record"
    )
