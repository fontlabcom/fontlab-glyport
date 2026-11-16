# this_file: tests/test_foreground_layer_identity.py
"""Native-name roles must not collapse distinct stored foreground identities."""

import pytest
from test_background_auxiliary import layers  # noqa: F401 - shared owned fixture
from test_issue106_round7_native import Layer

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability


@pytest.fixture
def owned(layers):  # noqa: F811 - pytest injects the imported layers fixture by parameter name
    """C++ findLayer selects the last equal name; native master flags are name-based."""
    layers.aux.name, layers.duplicate.name = "Regular", "Bold"
    layers.aux.isMasterLayer = layers.duplicate.isMasterLayer = True
    layers.aux.advanceWidth = 701.25
    layers.bold.advanceWidth = 802.5
    layers.duplicate.advanceWidth = 903.75
    layers.glyph.findLayer = lambda name: next(
        (layer for layer in reversed(layers.glyph.layers) if layer.name == name), None
    )
    return layers


def native_ids(scene, catalog):
    return [scene.backend._object(layer.id).id for layer in catalog]


@pytest.mark.parametrize("native_master_flag", [False, True])
def test_same_names_when_enumerated_then_preserve_native_winners_and_other_identities(
    owned, native_master_flag
):
    owned.aux.isMasterLayer = owned.bold.isMasterLayer = native_master_flag
    before = tuple(owned.glyph.layers)
    revision = owned.backend.revision(owned.fid)
    catalog = list(owned.proxy.layers)
    assert native_ids(owned, catalog) == [30, 60, 50, 40]
    assert [layer.name for layer in catalog] == ["Regular", "Bold", "Regular", "Bold"]
    assert [layer.width for layer in catalog] == [500, 903.75, 701.25, 802.5]
    assert [layer.isMasterLayer for layer in catalog] == [True, True, False, False]
    assert len({layer.layerId for layer in catalog}) == 4
    assert list(owned.proxy.layers) == catalog
    for layer in catalog:
        assert owned.proxy.layers[layer.layerId] is layer
    assert owned.proxy.layers["Regular"] is None, "Display names are not identity keys"
    assert (
        tuple(owned.glyph.layers) == before
        and owned.backend.revision(owned.fid) == revision
    )
    assert (
        not owned.calls and not owned.backend._prepared and not owned.backend._changed
    )


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_width_write_when_names_repeat_then_changes_only_the_exact_target(owned, index):
    catalog = list(owned.proxy.layers)
    assert len(catalog) == 4, "Every stored foreground identity must be addressable"
    targets = [owned.layer, owned.duplicate, owned.aux, owned.bold]
    before = {layer.id: layer.advanceWidth for layer in owned.glyph.layers}
    catalog[index].width = 1111.125
    for layer in owned.glyph.layers:
        assert layer.advanceWidth == (
            1111.125 if layer is targets[index] else before[layer.id]
        )
    assert owned.calls[-1][1] == [targets[index], owned.glyph]


def test_nondeclared_interpolating_layer_when_enumerated_then_keeps_stored_identity(
    owned,
):
    owned.aux.name = "Intermediate [500]"
    assert owned.aux.isMasterLayer is True
    catalog = list(owned.proxy.layers)
    assert native_ids(owned, catalog) == [30, 60, 50, 40]
    assert catalog[2].name == "Intermediate [500]" and not catalog[2].isMasterLayer
    assert catalog[2].associatedMasterId == owned.font.masters[0].id


@pytest.mark.parametrize("role", ["mask", "service"])
def test_protected_stored_layer_when_name_matches_master_then_is_not_an_auxiliary(
    owned, role
):
    owned.aux.isMaskLayer = role == "mask"
    owned.aux.isService = role == "service"
    assert native_ids(owned, list(owned.proxy.layers)) == [30, 60, 40]
    assert not owned.calls


def test_absent_master_when_other_names_repeat_then_remains_no_create_pending_slot(
    owned,
):
    owned.glyph.layers.remove(owned.bold)
    owned.glyph.layers.remove(owned.duplicate)
    before = tuple(owned.glyph.layers)
    catalog = list(owned.proxy.layers)
    assert len(catalog) == 3 and catalog[1].width == 0
    assert catalog[1].layerId == owned.font.masters[1].id
    assert catalog[2].width == 701.25
    assert tuple(owned.glyph.layers) == before and not owned.calls


def test_same_name_auxiliary_when_history_replaces_wrapper_then_rebinds_exact_id(owned):
    catalog = list(owned.proxy.layers)
    assert len(catalog) == 4
    auxiliary = catalog[2]
    old = owned.aux
    replacement = Layer(old.id)
    replacement.name = "Regular"
    replacement.isMasterLayer, replacement.isMaskLayer, replacement.isService = (
        True,
        False,
        False,
    )
    replacement.mask, replacement.advanceWidth = old.mask, 888.25
    owned.glyph.layers[owned.glyph.layers.index(old)] = replacement
    old.isValid = False
    owned.marker += 1
    assert auxiliary.width == 888.25
    assert owned.backend._object(auxiliary.id) is replacement
    assert owned.proxy.layers[auxiliary.layerId] is auxiliary
    assert catalog[0].width == 500


def test_auxiliary_when_it_becomes_native_master_winner_then_old_handle_is_stale(owned):
    catalog = list(owned.proxy.layers)
    assert len(catalog) == 4
    auxiliary, token = catalog[2], catalog[2].id
    owned.glyph.layers.remove(owned.aux)
    owned.glyph.layers.append(owned.aux)
    owned.marker += 1
    with pytest.raises(StaleNativeObject):
        _ = auxiliary.width
    assert not owned.backend.is_valid(token)
    current = list(owned.proxy.layers)
    assert native_ids(owned, current) == [50, 60, 40, 30]
    assert current[0].width == 701.25 and current[-1].width == 500


def test_automatic_same_name_auxiliary_when_written_then_refuses_before_history(owned):
    catalog = list(owned.proxy.layers)
    assert len(catalog) == 4
    owned.aux.autoLayer = True
    with pytest.raises(UnsupportedCapability, match="auto layer"):
        catalog[2].width = 1000
    assert owned.aux.advanceWidth == 701.25 and not owned.calls


def test_documented_helpers_when_run_then_keep_all_same_name_matches_without_edits(
    owned,
):
    import re
    from pathlib import Path

    document = Path(__file__).parents[1] / "src_docs/md/guides/LAYER_IDENTITIES.md"
    scope = {}
    blocks = re.findall(r"```python\n(.*?)```", document.read_text(), re.DOTALL)
    assert len(blocks) == 4
    for body in blocks:
        exec(compile(body, str(document), "exec"), scope)  # noqa: S102 - execute the owned source fixture in an isolated test namespace
    rows = scope["layer_rows"](owned.proxy)
    assert [row["name"] for row in rows] == ["Regular", "Bold", "Regular", "Bold"]
    assert [row["width"] for row in rows] == [500, 903.75, 701.25, 802.5]
    assert len({row["id"] for row in rows}) == 4
    assert len(scope["master_layers"](owned.proxy)) == 2
    matches = scope["named_layers"](owned.proxy, "Regular")
    assert native_ids(owned, matches) == [30, 50]
    assert scope["layer_by_id"](owned.proxy, matches[1].layerId) is matches[1]
    assert (
        not owned.calls and not owned.backend._prepared and not owned.backend._changed
    )
