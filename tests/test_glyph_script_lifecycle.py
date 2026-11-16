# this_file: tests/test_glyph_script_lifecycle.py
"""Owned script metadata lifecycles; no native provider imports or originals."""

from contextlib import nullcontext

import pytest

from fontlab_glyport.errors import PartialFailure, UnsupportedCapability
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def script_lifecycle_info(owned_info_manager):
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
                "name": "Alpha",
                "unicode": "0391",
                "category": "Letter",
                "case": "upper",
                "script": "greek",
            },
        ]
    )


def selected_lifecycle_info(glyph, manager):
    """Use document selection when attached and an explicit scope when detached."""
    if glyph.parent is None:
        return manager._scope()
    glyph.parent.parent._local_glyph_info = manager
    return nullcontext()


def owned_glyph(name="A", attached=True):
    glyph = GSGlyph(name)
    if not attached:
        return glyph
    font = Model(FakeBackend()).font
    if name != "A":
        font.glyphs.append(glyph)
    return font.glyphs[name]


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize(
    "name, expected",
    [
        ("A", "latin"),
        ("Alpha", "greek"),
        ("A-cy", "cyrillic"),
        ("ka-deva", "devanagari"),
        ("f_f", "latin"),
        ("acutecomb", None),
        ("period", None),
    ],
)
def test_script_when_known_unencoded_name_then_metadata_default(
    attached, name, expected
):
    glyph = owned_glyph(name, attached)
    glyph.unicodes = []
    assert glyph.script == expected, "Script must use named metadata without encoding"


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("value", [None, "", "han"])
def test_script_when_assigned_without_storage_then_explicit_value_and_false_noop(
    attached, value
):
    glyph = owned_glyph(attached=attached)
    glyph.script = value
    glyph.storeScript = False
    assert (glyph.script, glyph.storeScript) == (value, False), (
        "False-to-false must preserve explicit values"
    )


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("stored", [False, True])
@pytest.mark.parametrize("operation", ["rename", "refresh"])
@pytest.mark.parametrize("value", [None, "", "han"])
def test_script_when_metadata_refreshed_then_only_stored_override_survives(
    attached, stored, operation, value, script_lifecycle_info
):
    glyph = owned_glyph(attached=attached)
    glyph.storeScript = stored
    glyph.script = value
    with selected_lifecycle_info(glyph, script_lifecycle_info):
        if operation == "rename":
            glyph.name = "Alpha"
        else:
            glyph.updateGlyphInfo(changeName=False)
    expected = value if stored else ("greek" if operation == "rename" else "latin")
    assert glyph.script == expected, "Metadata transitions must honor storage"


@pytest.mark.parametrize("name, expected", [("A", "latin"), ("period", None)])
def test_store_script_when_disabled_then_restores_known_metadata_including_none(
    name, expected
):
    glyph = owned_glyph(name)
    glyph.case = 255
    glyph.userData["owned.control"] = {"keep": [1]}
    glyph.storeScript = True
    glyph.script = "han"
    glyph.storeScript = False
    assert (glyph.script, glyph.storeScript, glyph.case) == (expected, False, 255), (
        "Reset must distinguish None metadata from a missing record"
    )
    assert glyph.userData["owned.control"] == {"keep": [1]}, (
        "Reset must preserve unrelated lib values"
    )


def test_store_script_when_detached_or_unknown_reset_then_refuses_and_preserves():
    for glyph in [
        owned_glyph(attached=False),
        owned_glyph("glyportOwnedUnknownScript"),
    ]:
        glyph.storeScript = True
        glyph.script = "han"
        with pytest.raises(UnsupportedCapability):
            glyph.storeScript = False
        assert (glyph.script, glyph.storeScript) == ("han", True), (
            "Refusal must preserve state"
        )


@pytest.mark.parametrize("attached", [False, True])
def test_script_when_same_or_missing_name_then_current_value_survives(attached):
    glyph = owned_glyph(attached=attached)
    glyph.name = "glyportOwnedUnknownScript"
    assert glyph.script == "latin", (
        "Missing record must retain previous effective value"
    )
    glyph.script = "han"
    glyph.name = glyph.name
    assert glyph.script == "han", "Same-name assignment must not refresh"


@pytest.mark.parametrize("value", [None, "", "han"])
@pytest.mark.parametrize("stored", [False, True])
def test_script_when_copied_and_appended_then_independent_value_and_flag_survive(
    value, stored
):
    glyph = owned_glyph()
    glyph.storeScript = stored
    glyph.script = value
    glyph.case = 3
    copied = glyph.copy()
    assert (copied.script, copied.storeScript, copied.case) == (value, stored, 3), (
        "Copy snapshots effective metadata"
    )
    copied.name = "glyportOwnedCopiedScript"
    font = Model(FakeBackend()).font
    font.glyphs.append(copied)
    assert (copied.script, copied.storeScript, copied.case) == (value, stored, 3), (
        "Append must transfer explicit metadata"
    )
    copied.script = "greek"
    assert glyph.script == value, "Copy mutations must not affect source"


def test_script_when_reads_and_unchanged_assignments_then_no_lib_write(monkeypatch):
    glyph = owned_glyph()
    backend = glyph._font._model._backend
    monkeypatch.setattr(
        backend,
        "set_lib",
        lambda *args: pytest.fail("No-op script operation wrote lib"),
    )
    assert glyph.script == "latin", "Known default must be readable"
    glyph.script = "latin"
    glyph.storeScript = False


@pytest.mark.parametrize("operation", ["rename", "refresh", "reset"])
def test_script_when_storage_write_fails_then_name_codes_and_metadata_preserved(
    monkeypatch, operation, script_lifecycle_info
):
    glyph = owned_glyph()
    glyph.script = "han"
    glyph.case = 3
    if operation == "reset":
        glyph.storeScript = True
    glyph.unicode = "0042"
    before = (glyph.name, glyph.unicode, glyph.script, glyph.case, glyph.storeScript)

    def refuse(*args):
        raise RuntimeError("owned metadata write failure")

    monkeypatch.setattr(glyph._font._model._backend, "set_lib", refuse)
    if operation != "reset":
        glyph.parent.parent._local_glyph_info = script_lifecycle_info
    with pytest.raises(RuntimeError, match="owned metadata write failure"):
        if operation == "rename":
            glyph.name = "Alpha"
        elif operation == "refresh":
            glyph.updateGlyphInfo(changeName=False)
        else:
            glyph.storeScript = False
    assert (
        glyph.name,
        glyph.unicode,
        glyph.script,
        glyph.case,
        glyph.storeScript,
    ) == before, "Failed transition must restore original state"


def test_script_when_attach_write_fails_then_draft_preserved_and_insertion_removed(
    monkeypatch,
):
    glyph = owned_glyph("glyportOwnedScriptDraft", attached=False)
    glyph.script = "han"
    font = Model(FakeBackend()).font
    before = [g.name for g in font.glyphs]

    def refuse(*args):
        raise RuntimeError("owned script attachment failure")

    monkeypatch.setattr(font._model._backend, "set_lib", refuse)
    with pytest.raises(RuntimeError, match="owned script attachment failure"):
        font.glyphs.append(glyph)
    assert [g.name for g in font.glyphs] == before, "Insertion must roll back"
    assert (glyph.parent, glyph.script) == (None, "han"), (
        "Detached state must remain reusable"
    )


def test_script_when_unencoded_draft_attached_then_metadata_write_has_history_scope(
    monkeypatch,
):
    glyph = owned_glyph("glyportOwnedScriptDraft", attached=False)
    glyph.script = "han"
    font = Model(FakeBackend()).font
    backend = font._model._backend
    events = []
    begin, write, end = backend.begin_undo, backend.set_lib, backend.end_undo

    def begin_scope(name):
        events.append("begin")
        begin(name)

    def write_in_scope(token, data):
        assert events == ["begin"], "Metadata write requires attachment history scope"
        events.append("write")
        write(token, data)

    def end_scope():
        events.append("end")
        end()

    monkeypatch.setattr(backend, "begin_undo", begin_scope)
    monkeypatch.setattr(backend, "set_lib", write_in_scope)
    monkeypatch.setattr(backend, "end_undo", end_scope)
    font.glyphs.append(glyph)
    assert events == ["begin", "write", "end"], (
        "History scope must enclose metadata write"
    )
    assert glyph.script == "han", "Append must retain script"


@pytest.mark.parametrize("attached", [False, True])
def test_store_script_when_enabled_then_snapshots_effective_default(
    attached, monkeypatch, script_lifecycle_info
):
    glyph = owned_glyph(attached=attached)
    glyph.storeScript = True
    monkeypatch.setattr(
        GSGlyph, "_default_script", staticmethod(lambda name: (True, "greek"))
    )
    assert glyph.script == "latin", "Enabling storage must snapshot the current default"
    with selected_lifecycle_info(glyph, script_lifecycle_info):
        glyph.name = "Alpha"
    assert glyph.script == "latin", "Stored snapshot must survive rename"


@pytest.mark.parametrize("operation", ["read", "rename", "refresh", "reset"])
def test_script_when_metadata_lookup_fails_then_refuses_before_mutation(
    monkeypatch, operation
):
    glyph = owned_glyph()
    if operation != "read":
        glyph.script = "han"
    if operation == "reset":
        glyph.storeScript = True
    before = (glyph.name, glyph.unicodes, glyph._case_state())

    def refuse(name):
        raise RuntimeError("owned script metadata unavailable")

    if operation == "read":
        monkeypatch.setattr(GSGlyph, "_default_script", staticmethod(refuse))
    else:
        from fontlab_glyport.model import glyph_metadata

        def refuse_resolution(*args, **kwargs):
            raise RuntimeError("owned script metadata unavailable")

        monkeypatch.setattr(glyph_metadata, "resolve", refuse_resolution)
    with pytest.raises(RuntimeError, match="owned script metadata unavailable"):
        if operation == "read":
            _ = glyph.script
        elif operation == "rename":
            glyph.name = "Alpha"
        elif operation == "refresh":
            glyph.updateGlyphInfo(changeName=False)
        else:
            glyph.storeScript = False
    assert (glyph.name, glyph.unicodes, glyph._case_state()) == before, (
        "Lookup failure must not mutate glyph"
    )


@pytest.mark.parametrize("operation", ["rename", "refresh", "attach"])
def test_script_when_recovery_fails_then_retains_both_errors(
    monkeypatch, operation, script_lifecycle_info
):
    glyph = (
        owned_glyph()
        if operation != "attach"
        else owned_glyph("glyportOwnedScriptDraft", False)
    )
    glyph.script = "han"
    font = glyph.parent if operation != "attach" else Model(FakeBackend()).font
    backend = font._model._backend
    if operation != "attach":
        glyph.parent.parent._local_glyph_info = script_lifecycle_info

    def refuse_write(*args):
        raise RuntimeError("owned script write failure")

    def refuse_recovery(*args):
        raise RuntimeError("owned script recovery failure")

    monkeypatch.setattr(backend, "set_lib", refuse_write)
    if operation == "rename":
        rename = backend.rename_glyph

        def rename_once(font_id, token, name):
            if name == "A":
                refuse_recovery()
            return rename(font_id, token, name)

        monkeypatch.setattr(backend, "rename_glyph", rename_once)
    elif operation == "refresh":
        glyph.unicodes = ["10FFFF", "0042"]
        write = backend.set_glyph_unicodes

        def codes_once(token, codes):
            if codes == ("10FFFF", "0042"):
                refuse_recovery()
            return write(token, codes)

        monkeypatch.setattr(backend, "set_glyph_unicodes", codes_once)
    else:
        monkeypatch.setattr(backend, "remove_glyph", refuse_recovery)
    with pytest.raises(PartialFailure) as caught:
        if operation == "rename":
            glyph.name = "Alpha"
        elif operation == "refresh":
            glyph.updateGlyphInfo(changeName=False)
        else:
            font.glyphs.append(glyph)
    assert [str(error) for error in caught.value.errors] == [
        "owned script write failure",
        "owned script recovery failure",
    ], "Both failures must remain visible"
