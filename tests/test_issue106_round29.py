# this_file: tests/test_issue106_round29.py
"""All-layer notification safety and bounded preservation snapshots."""

from types import SimpleNamespace as NS

import pytest
from history_scene import register_history_owner
from test_issue106_round28 import native as native_fixture

from fontlab_glyport.errors import UnsupportedCapability
from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("peer", [False, True])
@pytest.mark.parametrize("kind", ["layer", "glyph"])
def test_pending_sibling_or_glyph_edits_refuse_creation_before_any_restore(
    native, peer, kind
):
    glyph = native.names["Aacute"]
    bold = NS(id=905, name="Bold", autoLayer=False, recipe="A+acute")
    glyph.layers.append(bold)
    owner = native.backend
    if peer:
        owner = FontLabBackend(packages=[native.package])
        owner._font_id(native.package)
        owner._native = native.backend._native
    owner.begin_undo("Earlier Bold edit")
    register_history_owner(owner, native.package, glyph, [bold])
    item = bold if kind == "layer" else glyph
    owner._changed[kind, item.id] = item
    before = dict(owner._changed)
    with pytest.raises(UnsupportedCapability, match="Aacute"):
        native.backend.append_glyph(native.fid, "acutecomb")
    assert "acutecomb" not in native.names
    assert native.restores == []
    assert owner._changed == before
    owner.end_undo()
    assert native.calls[-1][1] == [item], (
        "Only the still-valid earlier edit may publish"
    )


@pytest.mark.parametrize("size", [100, 3000])
def test_unchanged_creation_reads_each_candidate_json_only_once(native, size):
    native.lock_only = True
    for index in range(size - 1):
        name = f"Composite{index}"
        native.names[name] = NS(
            id=1000 + index, name=name, layers=[native.make_auto(name)]
        )
        native.package.fgPackage[name] = NS(name=name, id=1000 + index)
        native.data[name] = native.original
    native.backend.append_glyph(native.fid, "zzz.test")
    assert len(native.reads) <= size, (
        "No unchanged candidate needs a second full MCP read"
    )
    assert native.restores == []
    assert all(
        g.layers[0].cheap_reads <= 2
        for name, g in native.names.items()
        if name == "Aacute" or name.startswith("Composite")
    )


def test_no_recipe_candidates_need_no_mcp_snapshot(native):
    # Explicit recipes and ordinary layers cannot be re-resolved by creation.
    auto = native.names["Aacute"].layers[0]
    native.data["Aacute"]["layers"][0]["autoRecipe"] = "A+acute"
    native.backend.append_glyph(native.fid, "zzz.test")
    assert native.reads == []
    assert native.restores == []
    assert auto.recipe == "A+acute"


def test_mcp_restore_refreshes_all_sibling_layers_in_each_backend(native, monkeypatch):
    from fontlab_glyport.model.creation import refresh

    package, glyph = native.package, native.names["Aacute"]
    glyph.isValid = True
    glyph.currentHistoryState = lambda: 1
    package.masters.append("Bold")
    seen = []
    peers = [native.backend, FontLabBackend(packages=[package])]
    for owner in peers:
        fid = owner._font_id(package)
        gid = owner._register((fid, "glyph", 901), glyph, fid)
        owner._glyph_names[gid] = "Aacute"
        tokens = set()
        for index, name in enumerate(("Regular", "Bold")):
            mid = owner._register((fid, "master", name), package, fid)
            owner._master_names[mid] = name
            old = NS(id=900 + index, isValid=True)
            lid = owner._register((fid, "layer", gid, mid), old, gid)
            owner._layer_masters[lid] = mid
            tokens.add(lid)
        owner._glyph_layer_tokens[gid] = tokens

        def reread(glyph_id, master_id, owner=owner, tokens=tokens):
            seen.append((owner, owner._master_names[master_id]))
            lid = next(t for t in tokens if owner._layer_masters[t] == master_id)
            owner._objects[lid] = NS(id=1900, isValid=True)

        monkeypatch.setattr(owner, "layer", reread)
    refresh(package, "Aacute")
    assert set(seen) == {
        (owner, name) for owner in peers for name in ("Regular", "Bold")
    }
    for owner in peers:
        assert all(
            owner._objects[t].id == 1900
            for tokens in owner._glyph_layer_tokens.values()
            for t in tokens
            if owner._parents[t] in owner._glyph_names
            and owner._glyph_names[owner._parents[t]] == "Aacute"
        )
