# this_file: tests/test_outline_ops_behaviour.py
"""Backend outline publication, selection and failed-edit recovery outcomes."""

from contextlib import contextmanager

import pytest
from test_detached_geometry_behaviour import (
    outline,
    recording_boolean,  # noqa: F401 -- pytest fixture
    rectangle,
)

from fontlab_glyport.errors import PartialFailure
from fontlab_glyport.model import GSComponent, GSNode, GSPath, Model
from fontlab_glyport.model.backend import GlyphInfo, LayerInfo
from fontlab_glyport.model.fake_backend import FakeBackend
from fontlab_glyport.model.pens import path_info


@pytest.fixture
def live():
    backend = FakeBackend()
    backend.layers["glyph", "master"] = LayerInfo("layer", "master", 500)
    font = Model(backend).font
    return backend, font, font.glyphs[0].layers[0]


def test_path_publication_when_more_paths_than_original_slots_then_stages_and_retains_components(
    live, monkeypatch
):
    backend, font, layer = live
    layer.paths = [rectangle()]
    layer.components.append(GSComponent("A", (10, 20)))
    before = backend.outline_layer(layer.id)
    opened = GSPath([GSNode((90, 10)), GSNode((120, 30))], closed=False)
    replacements = (path_info(rectangle()), path_info(opened))
    stages, groups = [], []

    @contextmanager
    def stage(layer_id, field, infos):
        assert layer_id == layer.id and field == "paths"
        assert backend.outline_layer(layer.id) == before, (
            "Staging must precede any write"
        )
        assert infos == replacements
        stages.append("enter")
        yield
        stages.append("exit")

    def regroup(layer_id, counts):
        assert layer_id == layer.id and len(layer.paths) == 2
        groups.append(counts)

    monkeypatch.setattr(backend, "stage_collection", stage, raising=False)
    monkeypatch.setattr(backend, "path_grouping", lambda layer_id: (1,), raising=False)
    monkeypatch.setattr(backend, "restore_path_grouping", regroup, raising=False)
    backend.undo_events.clear()
    backend._replace_outline_paths(
        layer.id, replacements, undo_group=lambda: font.undo_group("Replace outlines")
    )
    assert [outline(path) for path in layer.paths] == [
        outline(rectangle()),
        outline(opened),
    ]
    assert layer.components[0].position == (10, 20)
    assert list(layer.shapes) == [layer.paths[0], layer.components[0], layer.paths[1]]
    assert stages == ["enter", "exit"] and groups == [(1,)]
    assert backend.undo_events == [("begin", "Replace outlines"), ("end", None)]


def test_path_publication_when_edit_and_recovery_both_fail_then_exposes_both_errors(
    live, monkeypatch
):
    backend, _, layer = live
    layer.paths = [rectangle()]
    original = backend.outline_layer(layer.id)
    write_error, recovery_error = (
        RuntimeError("insert failed"),
        RuntimeError("restore failed"),
    )

    def fail_write(*args):
        raise write_error

    def fail_recovery(*args):
        raise recovery_error

    monkeypatch.setattr(backend, "insert_path", fail_write)
    monkeypatch.setattr(backend, "restore_collection", fail_recovery)
    backend.undo_events.clear()
    with pytest.raises(PartialFailure, match="restore failed") as caught:
        backend._replace_outline_paths(
            layer.id,
            (path_info(GSPath([GSNode((10, 20))])),),
            undo_group=lambda: layer._font.undo_group("Replace outlines"),
        )
    assert caught.value.capability == "GSLayer.outlines.rollback"
    assert caught.value.errors == (write_error, recovery_error)
    assert caught.value.__cause__ is recovery_error
    assert original.paths and not layer.paths, (
        "Failed recovery must not pretend the original survived"
    )
    assert backend.undo_events == [("begin", "Replace outlines"), ("end", None)]


def test_decompose_when_second_component_fails_then_restores_first_component_and_paths(
    live, monkeypatch
):
    backend, font, base = live
    base.paths = [rectangle()]
    backend.glyph_lists["font"] += (GlyphInfo("destination", "B", ()),)
    backend.layers["destination", "master"] = LayerInfo("other-layer", "master", 500)
    layer = font.glyphs["B"].layers[0]
    layer.components = [GSComponent("A", (10, 20)), GSComponent("A", (100, 200))]
    original = backend.outline_layer(layer.id)
    decompose, changed = backend.decompose_component, []

    def fail_second(layer_id, component_id, *, on_detach):
        if changed:
            assert len(layer.paths) == 1 and len(layer.components) == 1
            assert layer.paths[0].bounds == ((10, 20), (40, 20))
            raise RuntimeError("second component failed")
        decompose(layer_id, component_id, on_detach=on_detach)
        changed.append(component_id)

    monkeypatch.setattr(backend, "decompose_component", fail_second)
    backend.undo_events.clear()
    with pytest.raises(RuntimeError, match="second component failed"):
        layer.decomposeComponents()
    assert backend.outline_layer(layer.id) == original
    assert not layer.paths and [c.position for c in layer.components] == [
        (10, 20),
        (100, 200),
    ]
    assert backend.undo_events == [("begin", "Change layer"), ("end", None)]


def test_overlap_when_selection_empty_then_no_dependency_or_history_needed(live):
    backend, _, layer = live
    layer.paths = [rectangle()]
    before, revision = backend.outline_layer(layer.id), backend.revision("font")
    backend.undo_events.clear()
    layer.removeOverlap(checkSelection=True)
    assert backend.outline_layer(layer.id) == before
    assert backend.revision("font") == revision and backend.undo_events == []


@pytest.mark.usefixtures("recording_boolean")
def test_overlap_when_selected_contour_unchanged_then_all_tokens_and_history_survive(
    live,
):
    backend, _, layer = live
    selected = rectangle()
    selected.nodes[0].selected = True
    layer.paths = [
        selected,
        GSPath([GSNode((90, 10)), GSNode((120, 30))], closed=False),
    ]
    before, revision = backend.outline_layer(layer.id), backend.revision("font")
    backend.undo_events.clear()
    layer.removeOverlap(checkSelection=True)
    assert backend.outline_layer(layer.id) == before
    assert layer.paths[0].nodes[0].selected
    assert not layer.paths[1].closed
    assert backend.revision("font") == revision and backend.undo_events == []
