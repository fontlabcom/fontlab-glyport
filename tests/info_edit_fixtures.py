# this_file: tests/info_edit_fixtures.py
"""Explicit authored metadata for owned edit/copy mechanics, not public parity."""

import pytest


@pytest.fixture
def owned_edit_info(owned_info_manager):
    """Source-qualified fresh custom rows for independent edit regressions."""
    rows = [
        ("A", "0041", "Letter", None, "latin", "upper"),
        ("a", "0061", "Letter", None, "latin", "lower"),
        ("B", "0042", "Letter", None, "latin", "upper"),
        ("acutecomb", "0301", "Mark", "Nonspacing", None, "noCase"),
        ("gravecomb", "0300", "Mark", "Nonspacing", None, "noCase"),
        ("one", "0031", "Number", "Decimal Digit", None, "noCase"),
        ("ka-gurmukhi", "0A15", "Letter", None, "gurmukhi", "noCase"),
    ]
    keys = ("name", "unicode", "category", "subCategory", "script", "case")
    return owned_info_manager(
        [
            {key: value for key, value in zip(keys, row) if value is not None}
            for row in rows
        ]
    )


@pytest.fixture
def owned_composition_info(owned_info_manager, monkeypatch):
    """Select explicitly authored recipes; no public physical recipe inference."""
    from fontlab_glyport.glyphsapp import GSGlyphsInfo

    manager = owned_info_manager(
        [
            {
                "name": "A",
                "unicode": "0041",
                "category": "Letter",
                "script": "latin",
                "case": "upper",
                "decompose": "ownedMissingRecipeToken106",
            },
            {
                "name": "acutecomb",
                "unicode": "0301",
                "category": "Mark",
                "subCategory": "Nonspacing",
            },
            {
                "name": "Aacute",
                "unicode": "00C1",
                "category": "Letter",
                "script": "latin",
                "case": "upper",
                "decompose": "A, acutecomb",
            },
            {
                "name": "Zcaron",
                "unicode": "017D",
                "category": "Letter",
                "script": "latin",
                "case": "upper",
            },
        ]
    )
    assert manager.infoFromDataForName_("ownedMissingRecipeToken106") is None
    assert manager.glyphInfoForName_("ownedMissingRecipeToken106") is None
    manager.updateComponentsInfos()
    assert manager.infoFromDataForName_("A").components == [], (
        "Only actual nonempty-token finalization establishes this empty array"
    )
    monkeypatch.setattr(GSGlyphsInfo, "_shared", manager)
    return manager
