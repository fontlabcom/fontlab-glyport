# this_file: tests/test_background_auxiliary.py
"""Ordinary auxiliary layers and read-only absent-mask clearing."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round7_native import Layer
from test_issue106_round7_native import native as native_fixture

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import Model


@pytest.fixture
def layers(monkeypatch):
    native = native_fixture.__wrapped__(monkeypatch)
    native.package.axes, native.package.upm = [], 1000
    native.package.masters = ["Regular", "Bold"]
    native.package.fgPackage.info = NS(familyName="Owned")
    native.package.findFgId = lambda identity: native.glyph
    native.glyph.findLayer = lambda name: next(
        (layer for layer in native.glyph.layers if layer.name == name), None
    )
    native.glyph.currentHistoryState = lambda: native.marker
    native.marker = 0
    native.layer.name = "Regular"
    bold, aux, duplicate, service = [Layer(i) for i in (40, 50, 60, 70)]
    bold.name, aux.name, duplicate.name, service.name = "Bold", "Aux", "Aux", "img"
    native.glyph.layers = [service, aux, bold, duplicate, native.layer]
    for layer in native.glyph.layers:
        layer.isService = layer is service
        layer.isMaskLayer = False
        layer.isMasterLayer = layer.name in native.package.masters
        layer.mask = Layer(layer.id + 100)
        layer.mask.name = "mask." + layer.name
        layer.mask.isMasterLayer, layer.mask.isMaskLayer, layer.mask.isService = (
            False,
            True,
            True,
        )
    native.glyph.removeLayer = lambda mask: next(
        setattr(layer, "mask", None)
        for layer in native.glyph.layers
        if layer.mask is mask
    )
    native.bold, native.aux, native.duplicate, native.service = (
        bold,
        aux,
        duplicate,
        service,
    )
    native.font = Model(native.backend).font
    native.proxy = native.font.glyphs[0]
    return native


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("invalid_mask", [False, True])
def test_missing_auto_background_clear_has_no_edits_or_revision(
    layers, pending, invalid_mask
):
    b = layers.backend
    layers.layer.autoLayer, layers.layer.mask = True, None
    if invalid_mask:
        layers.layer.mask = Layer(900)
        layers.layer.mask.isValid = False
    layer = layers.proxy.layers[0]
    background = layer.background if pending else None
    before = b.revision(layers.fid)
    layer.background = None
    assert b.revision(layers.fid) == before, "absent-mask clear must not revise caches"
    assert not layers.calls and not b._changed and not b._prepared
    assert layers.layer.mask_calls and not any(layers.layer.mask_calls)
    if pending:
        assert b.is_valid(background.id), "read-only pending background stays live"


@pytest.mark.parametrize("index", [0, 2])
def test_real_auto_background_clear_still_refuses_before_history(layers, index):
    native = layers.layer if index == 0 else layers.aux
    native.autoLayer = True
    with pytest.raises(UnsupportedCapability, match="auto layer"):
        layers.proxy.layers[index].background = None
    assert native.mask is not None and not layers.calls
    assert not layers.backend._changed and not layers.backend._prepared


def test_auxiliary_catalog_preserves_master_ids_order_and_distinct_names(layers):
    masters = list(layers.font.masters)
    first = layers.proxy.layers[masters[0].id]
    catalog = list(layers.proxy.layers)
    assert [layer.name for layer in catalog] == ["Regular", "Bold", "Aux", "Aux"]
    assert catalog[0] is first and layers.proxy.layers[masters[1].id] is catalog[1]
    assert [layer.isMasterLayer for layer in catalog] == [True, True, False, False]
    assert len({layer.layerId for layer in catalog}) == 4
    assert [layer.layerId for layer in catalog[:2]] == [master.id for master in masters]
    for layer in catalog[2:]:
        assert layer.associatedMasterId == masters[0].id
        assert layer.master is masters[0] and layer.parent is layers.proxy
        assert layers.proxy.layers[layer.layerId] is layer
    assert layers.proxy.layers["missing"] is None
    assert layers.service not in [layers.backend._object(layer.id) for layer in catalog]


@pytest.mark.parametrize("master_only", [False, True])
def test_clear_all_and_master_only_target_each_foregrounds_own_mask(
    layers, master_only
):
    catalog = list(layers.proxy.layers)
    backgrounds = [layer.background for layer in catalog]
    assert len({layer.id for layer in backgrounds + catalog}) == 8
    masks = {layer.id: layer.background.id for layer in catalog}
    for layer in catalog:
        if not master_only or layer.isMasterLayer:
            layer.setBackground_(None)
    for layer in catalog:
        cleared = not master_only or layer.isMasterLayer
        assert (layers.backend._object(layer.id).mask is None) == cleared
        assert layers.backend.is_valid(masks[layer.id]) != cleared
    assert layers.service.mask is not None
    assert layers.proxy.layers[0] is catalog[0]


@pytest.mark.parametrize("invalid", ["closed", "glyph", "layer", "token"])
def test_absent_mask_clear_validates_live_ownership(layers, invalid):
    layers.layer.mask = None
    token = layers.lid
    if invalid == "token":
        token = "missing-token"
    else:
        {"closed": layers.package, "glyph": layers.glyph, "layer": layers.layer}[
            invalid
        ].isValid = False
    with pytest.raises(StaleNativeObject):
        layers.backend.clear_background_layer(token)
    assert not layers.calls and not layers.layer.mask_calls


def test_absent_pending_master_clear_is_noop(layers):
    layers.glyph.layers.remove(layers.bold)
    layer = layers.proxy.layers[1]
    before = layers.backend.revision(layers.fid)
    layer.background = None
    assert layers.backend.revision(layers.fid) == before
    assert not layers.calls and not layers.backend._changed


def test_auxiliary_history_keeps_foreground_and_background_rebinding_separate(layers):
    catalog = list(layers.proxy.layers)
    aux = catalog[2]
    background = aux.background
    old = layers.aux
    replacement = Layer(old.id)
    replacement.name, replacement.isService = old.name, False
    replacement.isMaskLayer = False
    replacement.isMasterLayer = False
    replacement.mask = Layer(old.mask.id)
    replacement.mask.name = old.mask.name
    (
        replacement.mask.isMasterLayer,
        replacement.mask.isMaskLayer,
        replacement.mask.isService,
    ) = False, True, True
    replacement.advanceWidth, replacement.mask.advanceWidth = 743, 321
    layers.glyph.layers[layers.glyph.layers.index(old)] = replacement
    old.isValid, old.mask.isValid = False, False
    layers.marker += 1
    assert aux.width == 743 and background.width == 321
    assert layers.backend._object(aux.id) is replacement
    assert layers.backend.layer_location(aux.id) == (layers.gid, aux.layerId, False)
    assert layers.backend.layer_location(background.id) == (
        layers.gid,
        aux.layerId,
        True,
    )
    assert layers.font._native_layer(aux.id) is aux
    assert layers.font._native_layer(background.id) is background
    assert layers.proxy.layers[0] is catalog[0]


def test_empty_font_layers_do_not_invent_auxiliary_master(layers):
    layers.package.masters = []
    layers.backend._revision += 1
    assert list(layers.proxy.layers) == []


def test_catalog_reads_only_identity_and_master_lookup_does_not_enumerate(
    layers, monkeypatch
):
    first = layers.proxy.layers[0]
    with monkeypatch.context() as scoped:
        scoped.setattr(
            layers.backend,
            "glyph_layers",
            lambda _: pytest.fail("master lookup enumerated auxiliaries"),
        )
        assert layers.proxy.layers[layers.mid] is first
        assert layers.proxy.layers[0] is first
    monkeypatch.setattr(
        layers.backend,
        "_read_layer_contents",
        lambda *args: pytest.fail("catalog read geometry"),
    )
    assert len(layers.proxy.layers) == 4


def test_catalog_excludes_masks_but_keeps_interpolating_foregrounds(layers):
    layers.aux.isMaskLayer = True
    layers.duplicate.isMasterLayer = True
    assert [layer.name for layer in layers.proxy.layers] == ["Regular", "Bold", "Aux"]


@pytest.mark.parametrize("role", ["aux", "master", "mask"])
def test_auxiliary_resolution_uses_measured_boolean_role_properties(layers, role):
    layer = layers.aux
    layer.isMasterLayer = role == "master"
    layer.isMaskLayer = layer.isService = role == "mask"
    b = layers.backend
    token = b._layer_token(
        layers.fid, layer, layers.mid, layers.gid, ("auxiliary", layer.id)
    )
    # Native isMasterLayer is name-derived, broader than declared master slots.
    assert b._auxiliary_layer(layers.gid, token) is (layer if role != "mask" else None)


def test_removed_auxiliary_and_mask_stay_stale_after_restore(layers):
    aux = list(layers.proxy.layers)[2]
    mask = aux.background
    aux_id, mask_id = aux.id, mask.id
    layers.glyph.layers.remove(layers.aux)
    layers.marker += 1
    assert not layers.backend.is_valid(aux_id)
    assert not layers.backend.is_valid(mask_id)
    layers.glyph.layers.insert(0, layers.aux)
    layers.marker += 1
    replacement = list(layers.proxy.layers)[2]
    assert replacement.id != aux_id and replacement.name == "Aux"
    assert not layers.backend.is_valid(aux_id) and not layers.backend.is_valid(mask_id)


def test_auxiliary_rename_reorder_keeps_ids_and_mask_scope(layers):
    catalog = list(layers.proxy.layers)
    aux = catalog[2]
    mask = aux.background
    layers.aux.name = "Renamed"
    layers.glyph.layers.remove(layers.aux)
    layers.glyph.layers.append(layers.aux)
    layers.marker += 1
    assert list(layers.proxy.layers)[-1] is aux
    assert aux.name == "Renamed" and aux.background is mask
    assert layers.proxy.layers[0] is catalog[0]


def test_absent_auxiliary_mask_clear_checks_membership_without_history_change(layers):
    aux = list(layers.proxy.layers)[2]
    token = aux.id
    layers.aux.mask = None
    layers.glyph.layers.remove(layers.aux)
    with pytest.raises(StaleNativeObject):
        layers.backend.clear_background_layer(token)
    assert not layers.calls and not layers.aux.mask_calls


def test_auxiliary_missing_mask_has_own_pending_id_and_is_noop(layers):
    aux = list(layers.proxy.layers)[2]
    layers.aux.mask = None
    layers.aux.autoLayer = True
    pending = aux.background
    assert pending.layerId == aux.layerId and pending.associatedMasterId == layers.mid
    before = layers.backend.revision(layers.fid)
    aux.background = None
    assert pending is aux.background and not layers.calls
    assert layers.backend.revision(layers.fid) == before


@pytest.mark.parametrize("finish", ["retry", "discard"])
def test_auxiliary_clear_failed_notification_preserves_retry_boundary(layers, finish):
    b = layers.backend
    aux = list(layers.proxy.layers)[2]
    first_mask = layers.layer.mask
    original = layers.module.flItems

    def fail(*args):
        raise RuntimeError("notification failed")

    b.begin_undo("Clear owned auxiliary")
    b.clear_background_layer(aux.id)
    assert layers.aux.mask is None and layers.layer.mask is first_mask
    before = list(layers.calls)
    layers.module.flItems = lambda: NS(notifyChangesApplied=fail)
    with pytest.raises(RuntimeError, match="notification failed"):
        b.end_undo()
    assert b._undo_name is not None and b._changed
    layers.module.flItems = original
    if finish == "retry":
        b.end_undo()
        assert layers.calls[-1][1] == [layers.aux, layers.glyph]
    else:
        b.discard_undo()
        assert layers.calls == before
    assert b._undo_name is None and not b._changed


def test_fake_auxiliary_catalog_and_missing_mask_preserve_generation():
    from dataclasses import replace

    from fontlab_glyport.model.backend import LayerInfo
    from fontlab_glyport.model.fake_backend import FakeBackend

    b = FakeBackend()
    b.layers["glyph", "aux"] = LayerInfo(
        "aux-token", "master", 743, layerId="aux", name="Aux"
    )
    b._bump()
    font = Model(b).font
    master, aux = list(font.glyphs[0].layers)
    assert master.isMasterLayer and not aux.isMasterLayer
    assert aux.name == "Aux" and aux.associatedMasterId == master.layerId
    pending = aux.background
    before = b.revision("font")
    aux.background = None
    assert b.revision("font") == before and aux.background is pending
    b.fonts["font"] = replace(b.fonts["font"], masters=())
    b._bump()
    assert list(font.glyphs[0].layers) == []


@pytest.mark.parametrize("name", [None, "", "Aux"])
def test_auxiliary_name_read_preserves_backend_value_without_history(layers, name):
    layers.aux.name = name
    before = layers.backend.revision(layers.fid)
    layer = layers.proxy.layers[2]
    assert layer.name == name, "auxiliary names must not fall back to a master name"
    assert not layer.isMasterLayer and layer.master.name == "Regular"
    assert layers.proxy.layers[layer.layerId] is layer
    assert layers.backend.revision(layers.fid) == before
    assert not layers.calls and not layers.backend._changed
    assert [item.name for item in layers.proxy.layers[:2]] == ["Regular", "Bold"]


@pytest.mark.parametrize("name", [None, "", "Aux"])
def test_fake_auxiliary_name_and_copy_preserve_raw_value(name):
    from fontlab_glyport.model.backend import LayerInfo
    from fontlab_glyport.model.fake_backend import FakeBackend

    backend = FakeBackend()
    backend.layers["glyph", "aux"] = LayerInfo(
        "aux-token", "master", 743, layerId="aux", name=name
    )
    backend._bump()
    master, auxiliary = list(Model(backend).font.glyphs[0].layers)
    assert auxiliary.name == name, "do not replace an auxiliary name by its master"
    assert auxiliary.copy().name == name, "copy must retain the same name value"
    assert master.name == master.master.name and master.isMasterLayer


@pytest.mark.parametrize("name", [None, "", "Aux"])
def test_absent_auxiliary_background_keeps_existing_master_name(layers, name):
    layers.aux.name, layers.aux.mask = name, None
    background = layers.proxy.layers[2].background
    assert background.name == "Regular", "absent-mask naming is outside this repair"
    assert not layers.calls and not layers.backend._changed
