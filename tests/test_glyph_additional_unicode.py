# this_file: tests/test_glyph_additional_unicode.py
"""Owned additional-Unicode call-order, ownership and preservation contracts."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from test_unicode_case import NEWER_CASES

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSGlyph, Model, glyph_metadata
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def additional_unicode_info(owned_info_manager):
    """Complete owned parser inputs for refresh semantics, not public resources."""
    return owned_info_manager(
        [
            {
                "name": "A",
                "unicode": "0041",
                "case": "upper",
                "script": "latin",
                "category": "Letter",
            },
            {
                "name": "a",
                "unicode": "0061",
                "case": "lower",
                "script": "latin",
                "category": "Letter",
            },
            {
                "name": "I",
                "unicode": "0049",
                "case": "upper",
                "script": "latin",
                "category": "Letter",
            },
            {
                "name": "Idotaccent",
                "unicode": "0130",
                "case": "upper",
                "script": "latin",
                "category": "Letter",
            },
            {
                "name": "Alpha",
                "unicode": "0391",
                "case": "upper",
                "script": "greek",
                "category": "Letter",
            },
            {
                "name": "alef-ar",
                "unicode": "0627",
                "case": "noCase",
                "script": "arabic",
                "category": "Letter",
            },
        ]
    )


def selected_additional_info(glyph, manager):
    """Select through the document; scope only the explicit detached operation."""
    if glyph.parent is None:
        return manager._scope()
    glyph.parent.parent._local_glyph_info = manager
    return nullcontext()


def owned(name="A", attached=True, owners=()):
    glyph = GSGlyph(name)
    if not attached:
        return glyph
    font = Model(FakeBackend()).font
    glyph = font.glyphs["A"] if name == "A" else font.glyphs.append(glyph)
    for index, code in enumerate(owners):
        other = GSGlyph(f"glyportOwnedUnicodeOwner{index}")
        other.unicode = code
        font.glyphs.append(other)
    return glyph


@pytest.mark.parametrize(
    "name, owners, expected",
    [
        ("A", [], ["0041", "0061"]),
        ("A", ["0061"], ["0041"]),
        ("I", [], ["0049", "0069", "0131"]),
        ("I", ["0069"], ["0049", "0131"]),
        ("I", ["0131"], ["0049", "0069"]),
        ("I", ["0069", "0131"], ["0049"]),
        ("Idotaccent", [], ["0130"]),
        ("Alpha", [], ["0391"]),
        ("Alpha", ["03A6"], ["0391"]),
        ("Alpha", ["03A3"], ["0391"]),
        ("Alpha", ["03A6", "03A3"], ["0391", "03B1"]),
        ("Alpha", ["03A6", "03A3", "03B1"], ["0391"]),
    ],
)
def test_additional_unicode_when_parent_ownership_gates_then_exact_order(
    name,
    owners,
    expected,
    additional_unicode_info,
):
    glyph = owned(name, owners=owners)
    selected_additional_info(glyph, additional_unicode_info)
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == expected, (
        "Additional encodings must respect native ownership gates and order"
    )


@pytest.mark.parametrize(
    "name, codes",
    [
        ("A", ["0041", "0061"]),
        ("I", ["0049", "0069", "0131"]),
    ],
)
def test_additional_unicode_when_same_glyph_owns_alias_then_ordered_dedup(
    name, codes, additional_unicode_info
):
    glyph = owned(name)
    selected_additional_info(glyph, additional_unicode_info)
    glyph.unicodes = codes
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == codes, (
        "Same-glyph ownership allows aliases without duplicates"
    )
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == codes, "Repeated refresh must preserve deduplicated order"


@pytest.mark.parametrize("stored", [False, True])
def test_additional_unicode_when_current_case_differs_from_record_then_old_value_controls(
    stored,
    additional_unicode_info,
):
    glyph = owned()
    selected_additional_info(glyph, additional_unicode_info)
    glyph.case = 2
    glyph.storeCase = stored
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041"], (
        "Resolved uppercase case must not override the pre-apply lowercase gate"
    )
    assert glyph.case == (2 if stored else 1), (
        "Stored overlays follow additional-Unicode processing"
    )


@pytest.mark.parametrize("stored", [False, True])
@pytest.mark.parametrize("sentinels", [False, True])
def test_additional_unicode_when_current_script_differs_from_record_then_old_value_controls(
    stored,
    sentinels,
    additional_unicode_info,
):
    glyph = owned(owners=["03A6", "03A3"] if sentinels else [])
    selected_additional_info(glyph, additional_unicode_info)
    glyph.script = "greek"
    glyph.storeScript = stored
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == (["0041", "0061"] if sentinels else ["0041"]), (
        "Greek gating uses pre-apply script"
    )
    assert glyph.script == ("greek" if stored else "latin"), (
        "Only stored script survives field application"
    )


@pytest.mark.parametrize("name", ["A", "I", "Alpha"])
def test_additional_unicode_when_detached_uppercase_then_no_parent_additions(
    name, additional_unicode_info
):
    glyph = owned(name, attached=False)
    before = glyph.unicodes
    with selected_additional_info(glyph, additional_unicode_info):
        glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == before, (
        "Detached uppercase glyphs return original info before parent-based aliases"
    )


@pytest.mark.parametrize("category", ["Icon", "SF-Symbol"])
def test_additional_unicode_when_keep_name_category_then_helper_is_bypassed(category):
    glyph = owned()
    glyph.category = category
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == [], "Keep-name minimal info bypasses alias processing"


def test_additional_unicode_when_no_current_encoding_then_name_record_does_not_enable_aliases(
    additional_unicode_info,
):
    glyph = owned()
    selected_additional_info(glyph, additional_unicode_info)
    glyph.unicodes = []
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041"], (
        "The helper gate uses staged current codes, not the name record's code"
    )


def test_additional_unicode_when_first_current_code_above_native_limit_then_later_record_not_used(
    additional_unicode_info,
):
    glyph = owned()
    selected_additional_info(glyph, additional_unicode_info)
    glyph.unicodes = ["10FFFF", "0041"]
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041"], (
        "First resolved record must not replace first current scalar in helper gates"
    )


@pytest.mark.parametrize("operation", ["rename", "refresh"])
def test_additional_unicode_when_private_use_then_preserves_full_encoding_array(
    operation,
):
    glyph = owned()
    glyph.unicodes = ["10FFFD", "0A15"]
    if operation == "rename":
        glyph.name = "glyportOwnedPrivateUse"
    else:
        glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["10FFFD", "0A15"], (
        "PUA preserves the complete staged array"
    )


@pytest.mark.parametrize(
    "target, expected, after_refresh",
    [
        ("A", ["0041"], ["0041", "0061"]),
        ("a", ["0061"], ["0061"]),
    ],
)
def test_additional_unicode_when_convert_name_then_only_explicit_update_adds_alias(
    target,
    expected,
    after_refresh,
    additional_unicode_info,
):
    glyph = owned("a" if target == "A" else "A")
    selected_additional_info(glyph, additional_unicode_info)
    if target == "A":
        glyph.parent.glyphs.remove(glyph.parent.glyphs["A"])
    glyph.name = target
    assert glyph.unicodes == expected, (
        "Rename uses already-cleared staged codes and must not add prematurely"
    )
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == after_refresh, (
        "Explicit subsequent update follows current case and ownership"
    )


@pytest.mark.parametrize(
    "flag, field, value",
    [
        ("storeCase", "case", 3),
        ("storeScript", "script", "han"),
        ("storeCategory", "category", "Owned"),
        ("storeSubCategory", "subCategory", "Owned"),
    ],
)
def test_additional_unicode_when_metadata_flag_reset_then_does_not_write_encoding(
    flag, field, value
):
    glyph = owned()
    setattr(glyph, flag, True)
    setattr(glyph, field, value)
    before = glyph.unicodes
    setattr(glyph, flag, False)
    assert glyph.unicodes == before, (
        "A reset consumes one metadata field, not the resolver's Unicode array"
    )


@pytest.mark.parametrize(
    "case, codes, expected_none",
    [
        (2, ["0041"], True),
        (1, ["0041"], False),
        (2, [], False),
        (1, ["0130"], False),
        (1, ["10FFFF"], False),
    ],
)
def test_additional_unicode_when_detached_arabic_then_exact_early_return(
    case, codes, expected_none
):
    glyph = owned(attached=False)
    glyph.case, glyph.script, glyph.unicodes = case, "arabic", codes
    record = glyph_metadata.resolve(glyph)
    assert (record is None) is expected_none, (
        "Arabic parentless nil must preserve earlier no-code/uppercase exceptions"
    )


def test_additional_unicode_when_arabic_nil_then_explicit_update_takes_missing_record_branch():
    glyph = owned(attached=False)
    glyph.case, glyph.script = 2, "arabic"
    glyph.updateGlyphInfo(changeName=False)
    assert (
        glyph.unicodes,
        glyph.category,
        glyph.subCategory,
        glyph.case,
        glyph.script,
    ) == ([], None, None, 2, "arabic"), (
        "Parentless Arabic nil must preserve the actual missing-info application contract"
    )


@pytest.mark.parametrize(
    "isolate_owner, primary, expected",
    [
        (False, None, ["0627"]),
        (False, "FE8D", ["0627", "FE8D"]),
        (True, "FE8D", ["0627"]),
    ],
)
def test_additional_unicode_when_arabic_isolated_record_then_only_primary_and_name_owner_control(
    monkeypatch,
    isolate_owner,
    primary,
    expected,
    additional_unicode_info,
):
    glyph = owned("alef-ar")
    selected_additional_info(glyph, additional_unicode_info)
    if isolate_owner:
        glyph.parent.glyphs.append(GSGlyph("alef-ar.isol"))
    resolve_name = glyph_metadata.name_info

    def isolated(name, font=None, *, fill_production=False):
        if name == "alef-ar.isol":
            return glyph_metadata._record(
                name,
                unicode=primary,
                unicodeLegacy="FE8D",
                category="Letter",
                subCategory=None,
                script="arabic",
                case=0,
            )
        return resolve_name(name, font, fill_production=fill_production)

    monkeypatch.setattr(glyph_metadata, "name_info", isolated)
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == expected, (
        "Legacy-only isolated forms must not be promoted to primary Unicode"
    )


def test_additional_unicode_when_existing_info_has_alias_then_ordered_append_retains_it(
    monkeypatch,
    additional_unicode_info,
):
    glyph = owned()
    selected_additional_info(glyph, additional_unicode_info)
    initial = glyph_metadata.unicode_info

    def record(code):
        result = initial(code)
        if code == "0041":
            result = SimpleNamespace(**{**vars(result), "unicodes": ("0041", "0042")})
        return result

    monkeypatch.setattr(glyph_metadata, "unicode_info", record)
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041", "0042", "0061"], (
        "Existing ordered encodings must not be replaced"
    )


def test_additional_unicode_when_casing_resource_fails_then_no_mutation(monkeypatch):
    from fontlab_glyport.model import unicode_case

    glyph = owned()
    before = (glyph.name, glyph.unicodes, glyph._case_state())

    def refuse(value):
        raise UnsupportedCapability(
            "owned unavailable lowercase data",
            capability="GSGlyph.metadata.lowercaseData",
        )

    monkeypatch.setattr(unicode_case, "lowercase_scalar", refuse)
    with pytest.raises(UnsupportedCapability, match="owned unavailable"):
        glyph.updateGlyphInfo(changeName=False)
    assert (glyph.name, glyph.unicodes, glyph._case_state()) == before, (
        "Casing errors must precede writes"
    )


def test_additional_unicode_when_numeric_glyph_name_has_no_encoding_then_not_a_character_owner(
    additional_unicode_info,
):
    glyph = owned()
    selected_additional_info(glyph, additional_unicode_info)
    collision = GSGlyph("0061")
    collision.unicodes = []
    glyph.parent.glyphs.append(collision)
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041", "0061"], (
        "A numeric glyph name without that encoding must not block Unicode ownership"
    )


def test_additional_unicode_when_resource_fails_but_rename_has_no_staged_codes_then_no_read(
    monkeypatch,
    additional_unicode_info,
):
    from fontlab_glyport.model import unicode_case

    glyph = owned("a")
    selected_additional_info(glyph, additional_unicode_info)
    glyph.parent.glyphs.remove(glyph.parent.glyphs["A"])

    def refuse(value):
        pytest.fail("Rename used unstaged old encodings to invoke the casing table")

    monkeypatch.setattr(unicode_case, "lowercase_scalar", refuse)
    glyph.name = "A"
    assert glyph.unicodes == ["0041"], "Staged zero-code rename must bypass casing data"


def test_additional_unicode_when_shared_record_reused_then_input_remains_unchanged(
    monkeypatch,
):
    glyph = owned()
    shared = SimpleNamespace(
        name="A",
        unicode="0041",
        unicodes=("0041", "0042"),
        category="Letter",
        subCategory=None,
        script="latin",
        case=1,
    )
    before = vars(shared).copy()
    monkeypatch.setattr(glyph_metadata, "unicode_info", lambda code: shared)
    first = glyph_metadata.resolve(glyph)
    second = glyph_metadata.resolve(glyph)
    assert vars(shared) == before, (
        "Alias resolution must never mutate shared input metadata"
    )
    assert first.unicodes == second.unicodes == ("0041", "0042", "0061"), (
        "Repeated resolution should use independent encoding snapshots"
    )


@pytest.mark.parametrize("code, lowered", NEWER_CASES)
def test_additional_unicode_when_newer_scalar_then_helper_uses_calibrated_mapping(
    code, lowered, owned_info_manager
):
    glyph = owned("glyportOwnedModernUppercase")
    manager = owned_info_manager(
        [
            {
                "name": "glyportOwnedModernUppercase",
                "unicode": code,
                "category": "Letter",
                "case": "upper",
                "script": "latin",
            }
        ]
    )
    selected_additional_info(glyph, manager)
    glyph.unicode = code
    glyph.case = 1
    glyph.storeCase = True
    glyph.script = "latin"
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == [code, lowered[0]], (
        "Additional-Unicode processing must not fall back to Python14 casing"
    )
