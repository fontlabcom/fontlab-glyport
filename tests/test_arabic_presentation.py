# this_file: tests/test_arabic_presentation.py
"""Owned Arabic presentation-form resolver cases; native acceptance is separate."""

from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.model import GSCustomParameter, GSGlyph, Model, glyph_metadata
from fontlab_glyport.model.fake_backend import FakeBackend

KEY = "Use Arabic Presentation Form Unicodes"


@pytest.fixture
def arabic_lifecycle_info(owned_info_manager):
    """Fresh parsed rows qualify refresh; real public rows supply legacy fallback."""
    from fontlab_glyport.glyphsapp import GSGlyphsInfo

    manager = owned_info_manager(
        [
            {
                "name": "alef-ar",
                "unicode": "0627",
                "category": "Letter",
                "case": "noCase",
                "script": "arabic",
            },
            {
                "name": "A",
                "unicode": "0041",
                "category": "Letter",
                "case": "upper",
                "script": "latin",
            },
        ]
    )
    public_index = GSGlyphsInfo.sharedManager()._index
    manager._index.shared = public_index
    isolated = public_index.raw_name("alef-ar.isol")
    assert manager._index.raw_name("alef-ar.isol") is isolated
    assert isolated.unicodeLegacy == "FE8D"
    assert {"group", "groupIdx"} <= isolated._unavailable_fields
    assert manager._index.raw_name("alef-ar").unicodeLegacy is None
    return manager


def owned(name="alef-ar"):
    font = Model(FakeBackend()).font
    return font, font.glyphs[name] if font.glyphs[
        name
    ] is not None else font.glyphs.append(GSGlyph(name))


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (-1, True),
        (0.5, True),
        ("1", True),
        ("0", False),
        ("YES", False),
        ("true", False),
        ("", False),
    ],
)
def test_presentation_when_setting_changes_then_refresh_appends_only_when_enabled(
    value, expected, arabic_lifecycle_info
):
    font, glyph = owned()
    font.customParameters[KEY] = value
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == (["0627", "FE8D"] if expected else ["0627"])
    assert glyph.name == "alef-ar"


def test_presentation_when_duplicate_active_changes_then_uses_live_first_active_parameter(
    arabic_lifecycle_info,
):
    font, glyph = owned()
    first, second = GSCustomParameter(KEY, False), GSCustomParameter(KEY, True)
    font.customParameters.extend([first, second])
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627"]
    first.active = False
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627", "FE8D"]
    first.active = True
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627"], (
        "Refreshing after disabling presentation must not retain an old appended encoding"
    )


def test_presentation_when_alias_and_stored_script_conflict_then_uses_resolved_name_and_script(
    arabic_lifecycle_info,
):
    font, glyph = owned("ownedArabicAlias")
    glyph.unicode = "0627"
    glyph.storeScript = True
    glyph.script = "latin"
    font.customParameters[KEY] = True
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627", "FE8D"]
    assert glyph.name == "ownedArabicAlias" and glyph.script == "latin"


def test_presentation_when_compact_key_is_used_then_is_not_an_alias(
    arabic_lifecycle_info,
):
    font, glyph = owned()
    font.customParameters["UseArabicPresentationFormUnicodes"] = True
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627"]


def test_database_when_isolated_record_loaded_then_retains_legacy_separately():
    direct = glyph_metadata._direct("alef-ar.isol")
    assert direct.unicode is None
    assert direct.unicodeLegacy == "FE8D"
    suffix = glyph_metadata._suffix(direct, "alef-ar.isol.owned")
    assert suffix.unicodeLegacy is None, (
        "Constructed suffixes clear inherited legacy encodings"
    )


@pytest.mark.parametrize(
    "legacy, expected, fallback",
    [
        ("FE90", ["0627", "FE90"], False),
        (None, ["0627", "FE8D"], True),
        ("", ["0627"], False),
        ("0627", ["0627"], False),
        ("12345678", ["0627"], False),
    ],
)
def test_presentation_when_legacy_is_direct_or_nil_then_preserves_precedence(
    monkeypatch, legacy, expected, fallback
):
    from fontlab_glyport.model.unicode_case import presentation_unicode

    queries = []

    def direct(name):
        queries.append(name)
        return NS(unicodeLegacy="FE8D")

    monkeypatch.setattr(glyph_metadata, "_direct", direct)
    glyph = NS(parent=NS(customParameters={KEY: True}))
    info = NS(
        name="canonical-ar", script="arabic", unicode="0627", unicodeLegacy=legacy
    )
    result = presentation_unicode(glyph, info)
    assert list(getattr(result, "unicodes", (result.unicode,))) == expected
    assert queries == (["canonical-ar.isol"] if fallback else [])
    assert vars(info) == {
        'name': "canonical-ar", 'script': "arabic", 'unicode': "0627", 'unicodeLegacy': legacy
    }, "Source records must stay immutable"


def test_presentation_when_isol_glyph_exists_then_still_uses_manager_legacy(
    arabic_lifecycle_info,
):
    font, glyph = owned()
    font.glyphs.append(GSGlyph("alef-ar.isol"))
    font.customParameters[KEY] = True
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627", "FE8D"], (
        "Earlier additional-Unicode blocker does not block presentation"
    )


def test_presentation_when_setting_is_only_on_master_then_font_lookup_remains_disabled(
    arabic_lifecycle_info,
):
    font, glyph = owned()
    font.masters[0].customParameters[KEY] = True
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627"], (
        "Presentation reads the parent font, not the master"
    )


def test_presentation_when_stored_script_says_arabic_on_latin_then_resolved_script_wins(
    arabic_lifecycle_info,
):
    font, glyph = owned("A")
    glyph.storeScript = True
    glyph.script = "arabic"
    font.customParameters[KEY] = True
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0041", "0061"], (
        "Retain the prior uppercase additional-Unicode stage; stored Arabic must not add presentation data"
    )


def test_presentation_when_store_script_resets_then_does_not_write_encodings_until_refresh(
    arabic_lifecycle_info,
):
    font, glyph = owned()
    glyph.storeScript = True
    glyph.script = "latin"
    font.customParameters[KEY] = True
    glyph.storeScript = False
    assert glyph.script == "arabic" and glyph.unicodes == ["0627"]
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627", "FE8D"]


def test_presentation_when_keep_name_category_then_early_return_bypasses_parameter_stage():
    font, glyph = owned()
    glyph.category = "Icon"
    glyph.storeCategory = True
    font.customParameters[KEY] = True
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == [], "Keep-name early return has no resolved encodings"


def test_typed_parameter_when_renamed_or_changed_then_converts_atomically():
    from copy import deepcopy

    from fontlab_glyport.errors import UnsupportedCapability

    font, _ = owned()
    parameter = GSCustomParameter("Owned generic", "true")
    parameter.active = False
    font.customParameters.append(parameter)
    parameter.name = KEY
    assert parameter.value == 0 and parameter.active is False
    parameter.value = "1"
    assert parameter.value == 1
    parameter.value = None
    assert parameter.value is False, (
        "Object nil conversion is distinct from keyed removal"
    )
    before = deepcopy(dict(font._model._backend.libs))
    with pytest.raises(UnsupportedCapability):
        parameter.value = []
    assert parameter.value is False and font._model._backend.libs == before
    del font.customParameters[KEY]
    assert parameter.parent is None


def test_typed_parameter_when_legacy_values_are_read_then_normalizes_without_lib_writes():
    from copy import deepcopy

    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    font, _ = owned()
    backend = font._model._backend
    backend.libs[font._id] = {CUSTOM_PARAMETER_PREFIX + KEY: "YES", "owned": [1]}
    before = deepcopy(dict(backend.libs))
    assert font.customParameters[KEY] == 0
    assert font.customParameters[0].value == 0
    assert backend.libs == before, (
        "A typed lookup must not mutate the lib merely to validate"
    )
    font.customParameters.append(GSCustomParameter(KEY, "1"))
    assert font.customParameters[1].value == 1
    font.customParameters[0].active = False
    assert font.customParameters[KEY] == 1


@pytest.mark.parametrize(
    "script, parent, setting",
    [
        ("arabic", False, True),
        ("latin", True, True),
        ("arabic", True, False),
        ("arabic", True, None),
    ],
)
def test_presentation_when_early_gate_refuses_then_returns_original_info(
    script, parent, setting
):
    from fontlab_glyport.model.unicode_case import presentation_unicode

    glyph = NS(parent=NS(customParameters={KEY: setting}) if parent else None)
    info = NS(name="alef-ar", script=script, unicode="0627", unicodeLegacy="FE8D")
    assert presentation_unicode(glyph, info) is info
    assert presentation_unicode(glyph, None) is None


def test_presentation_when_direct_legacy_has_no_primary_unicode_then_it_becomes_first():
    from fontlab_glyport.model.unicode_case import presentation_unicode

    glyph = NS(parent=NS(customParameters={KEY: True}))
    info = NS(name="alef-ar.isol", script="arabic", unicode=None, unicodeLegacy="FE8D")
    result = presentation_unicode(glyph, info)
    assert result.unicode == "FE8D" and result.unicodes == ("FE8D",)


def test_typed_parameter_when_nan_is_retained_then_does_not_look_like_mirror_drift(
    arabic_lifecycle_info,
):
    import math

    font, glyph = owned()
    parameter = GSCustomParameter(KEY, float("nan"))
    font.customParameters.append(parameter)
    assert math.isnan(font.customParameters[KEY])
    assert math.isnan(font.customParameters[0].value)
    font.parent._local_glyph_info = arabic_lifecycle_info
    glyph.updateGlyphInfo(changeName=False)
    assert glyph.unicodes == ["0627", "FE8D"], "NSNumber NaN boolValue is true"
    parameter.value = float("nan")
    assert math.isnan(font.customParameters[KEY])


def test_typed_parameter_when_inactive_import_is_unqualified_then_structural_recovery_works():
    from fontlab_glyport.errors import UnsupportedCapability

    font, _ = owned()
    params = font.customParameters
    backend = font._model._backend
    backend.libs[font._id] = {
        params._key: [
            {'id': "inactive", 'name': KEY, 'value': [], 'active': False},
        ],
        "owned": [7],
    }
    assert len(params) == 1
    assert params[KEY] is None, (
        "Inactive objects do not enter effective-value validation"
    )
    parameter = params[0]
    assert parameter.name == KEY and parameter.active is False
    with pytest.raises(UnsupportedCapability):
        parameter.value = {}
    assert parameter.active is False
    del params[KEY]
    assert len(params) == 0 and backend.libs[font._id]["owned"] == [7]


def test_typed_parameter_when_later_active_duplicate_is_unqualified_then_validates_it_too():
    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model.proxies import CUSTOM_PARAMETER_PREFIX

    font, _ = owned()
    params = font.customParameters
    backend = font._model._backend
    backend.libs[font._id] = {
        params._key: [
            {'id': "first", 'name': KEY, 'value': True, 'active': True},
            {'id': "later", 'name': KEY, 'value': [], 'active': True},
        ],
        CUSTOM_PARAMETER_PREFIX + KEY: True,
    }
    assert len(params) == 2
    with pytest.raises(UnsupportedCapability):
        params[KEY]
    del params[1]
    assert params[KEY] is True
