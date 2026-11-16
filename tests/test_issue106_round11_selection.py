# this_file: tests/test_issue106_round11_selection.py
"""Font View multi-selection without changing font geometry or Undo history."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.backend import LayerInfo, MasterInfo
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.fontlab_backend import FontLabBackend


def test_f50_fake_selection_sets_current_master_layers_without_a_tab():
    backend = FakeBackend()
    font = Model(backend).font
    font.glyphs.append(GSGlyph("A.ss01"))
    first, alternate = font.glyphs["A"], font.glyphs["A.ss01"]
    font.selection = [first, alternate]
    assert font.currentTab is None
    assert font.selection == [first, alternate]
    assert [layer.parent for layer in font.selectedLayers] == [first, alternate]
    assert all(
        layer.associatedMasterId == font.selectedFontMaster.id
        for layer in font.selectedLayers
    )
    assert first.selected and alternate.selected
    font.selection = []
    assert font.selection == [] and font.selectedLayers == []
    assert not first.selected and not alternate.selected
    assert backend.undo_events == []


def test_f50_selection_validates_whole_input_before_changing_it():
    font = Model(FakeBackend()).font
    glyph = font.glyphs[0]
    font.selection = [glyph]
    for value in ([glyph, GSGlyph("detached")], [glyph, object()], "A"):
        with pytest.raises((ValueError, TypeError)):
            font.selection = value
        assert font.selection == [glyph]


def test_f50_font_view_selection_uses_current_master_after_switch():
    backend = FakeBackend()
    backend.fonts["font"] = replace(
        backend.fonts["font"],
        masters=(MasterInfo("master", "Regular"), MasterInfo("bold", "Bold")),
    )
    backend.layers["glyph", "bold"] = LayerInfo("bold-layer", "bold", 500)
    font = Model(backend).font
    font.selection = [font.glyphs[0]]
    font.masterIndex = 1
    assert font.selectedLayers[0].associatedMasterId == "bold"


def test_f50_native_font_view_layers_use_current_master_not_old_active_layer(
    monkeypatch,
):
    native = native_selection(monkeypatch)
    tools = native.backend._fontpr()
    tools.get_current_glyphs = lambda: {
        "glyphs": [
            {"name": "A", "package_id": 100, "active_layer_name": "Backup"},
            {"name": "B", "package_id": 999, "active_layer_name": "Other"},
        ]
    }
    monkeypatch.setattr(native.backend, "_fontpr", lambda: tools)
    assert native.backend.current_layers(native.fid) == (("A", "Regular"),)
    native.workspace.activeFontPanel = None
    assert native.backend.current_layers(native.fid) == (("A", "Backup"),)


def native_selection(monkeypatch):
    package = NS(id=10, fgId=100, isValid=True, master="Regular")
    backend = FontLabBackend(packages=[package])
    fid = backend._font_id(package)
    glyph = NS(id=20, isValid=True, name="A")
    package.fgPackage = {"A": NS(index=7)}
    gid = backend._register((fid, "glyph", 200), glyph, fid)
    backend._glyph_native_ids[gid] = 200
    workspace = NS(activeFontPanel=object(), currentPackage=package)
    selected, calls = [], []

    def select(ids):
        calls.append(list(ids))
        selected[:] = ids

    import sys

    def clear():
        selected.clear()

    def select_index(index):
        calls.append([index])
        selected.append(index)

    monkeypatch.setitem(
        sys.modules, "FL", NS(fl=NS(Unselect=clear, Select=select_index))
    )
    module = NS(
        flWorkspace=NS(instance=lambda: workspace),
        MainWindow=lambda: NS(selectGlyphs=select),
    )
    monkeypatch.setattr(backend, "_native", lambda: module)
    monkeypatch.setattr(
        backend, "_fontpr", lambda: NS(get_active_font=lambda: {"id": 100})
    )
    return NS(
        backend=backend,
        fid=fid,
        gid=gid,
        workspace=workspace,
        calls=calls,
        selected=selected,
    )


def test_f50_native_font_view_batch_uses_fontgate_ids_and_no_undo(monkeypatch):
    native = native_selection(monkeypatch)
    revision = native.backend._revision
    native.backend.set_font_selection(native.fid, (native.gid,))
    assert native.calls == [[7]], "legacy selection takes glyph indices, not native IDs"
    assert native.backend._prepared == {} and native.backend._changed == {}
    assert native.backend._revision != revision


@pytest.mark.parametrize("case", ["glyph-tab", "other-font"])
def test_f50_native_refuses_unsafe_selection_contexts_precisely(monkeypatch, case):
    native = native_selection(monkeypatch)
    if case == "glyph-tab":
        native.workspace.activeFontPanel = None
    if case == "other-font":
        native.backend._fontpr = lambda: NS(get_active_font=lambda: {"id": 999})
    with pytest.raises(UnsupportedCapability) as caught:
        native.backend.set_font_selection(
            native.fid, () if case == "empty" else (native.gid,)
        )
    assert caught.value.capability == "GSFont.selection"
    assert native.calls == []
