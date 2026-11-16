# this_file: tests/test_issue106_round10.py
"""Owned-shape checkpoints and peer reads inside a single enclosing Undo group."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import configure_model
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model import GSNode, GSPath, Model
from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def peer_font(native, monkeypatch):
    backend = FontLabBackend(packages=[native.package])
    monkeypatch.setattr(backend, "_native", lambda: native.module)
    backend._register((777, "font", 777), NS(id=777, isValid=True))
    fid = backend._font_id(native.package)
    mid = backend._register((fid, "master", "Regular"), native.package, fid)
    backend._master_names[mid] = "Regular"
    gid = backend._register((fid, "glyph", 200), native.glyph, fid)
    state = NS(fid=fid, mid=mid, gid=gid, glyph=native.glyph, layer=native.layer)
    configure_model(backend, state, monkeypatch)
    return Model(backend)._font(fid)


@pytest.mark.parametrize("field", ["paths", "shapes"])
@pytest.mark.parametrize("with_peer", [False, True])
def test_owned_shape_bulk_failure_restores_every_contour_after_prior_edit(
    native, monkeypatch, field, with_peer
):
    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]
    observer = peer_font(native, monkeypatch) if with_peer else font
    observed_layer = observer.glyphs[0].layers[0]
    retained = observed_layer.paths[1].nodes[0]

    def fail(*args):
        raise RuntimeError("append failed")

    monkeypatch.setattr(backend, "append_path", fail)
    with font.undo_group("Earlier edit and failed replacement"):
        layer.paths[0].nodes[0].position = (33, 44)
        before = [path.nodes[0].position for path in layer.paths]
        assert before == [(33, 44), (20, 2)]
        protected_shape = native.layer.shapes[0]
        assert protected_shape.id in backend._owned_shapes
        with pytest.raises(RuntimeError, match="append failed"):
            setattr(layer, field, [GSPath([GSNode((99, 99))])])
        assert [path.nodes[0].position for path in layer.paths] == before
        assert [path.nodes[0].position for path in observed_layer.paths] == before
        assert native.layer.shapes == [protected_shape]
        retained.position = (55, 66)
        assert retained.position == (55, 66)
        assert len(layer.paths) == 2


def test_peer_reads_second_edit_to_already_owned_shape_before_publication(
    native, monkeypatch
):
    font = native.font
    observer = peer_font(native, monkeypatch)
    node = font.glyphs[0].layers[0].paths[0].nodes[0]
    peer = observer.glyphs[0].layers[0].paths[0].nodes[0]
    with font.undo_group("Two edits"):
        node.position = (80, 90)
        assert peer.position == (80, 90)
        revision = observer._revision()
        notifications = list(native.calls)
        owned_shape = native.layer.shapes[0]
        node.position = (100, 110)
        assert native.layer.shapes == [owned_shape], "second edit remains in place"
        assert node.position == (100, 110)
        assert peer.position == (100, 110)
        assert observer._revision() != revision
        assert native.calls == notifications, "peer invalidation does not publish Undo"


def test_checkpoint_clone_failure_restores_owned_geometry_and_bindings(
    native, monkeypatch
):
    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]
    with font.undo_group("Owned checkpoint failure"):
        layer.paths[0].nodes[0].position = (33, 44)
        protected = native.layer.shapes[0]
        retained = layer.paths[0].nodes[0]
        key = backend._object_keys[retained.id]

        def fail():
            raise RuntimeError("checkpoint clone failed")

        monkeypatch.setattr(protected, "clone", fail)
        with pytest.raises(RuntimeError, match="checkpoint clone failed"):
            layer.paths = []
        assert [path.nodes[0].position for path in layer.paths] == [(33, 44), (20, 2)]
        assert native.layer.shapes == [protected]
        assert backend._object_keys[retained.id] == key
        retained.position = (45, 67)
        assert retained.position == (45, 67)


def test_peer_reads_owned_shape_smoothness_mutation(native, monkeypatch):
    font = native.font
    observer = peer_font(native, monkeypatch)
    node = font.glyphs[0].layers[0].paths[0].nodes[0]
    peer = observer.glyphs[0].layers[0].paths[0].nodes[0]
    with font.undo_group("Geometry then connection"):
        node.position = (80, 90)
        assert peer.smooth is False
        shape = native.layer.shapes[0]
        node.smooth = True
        assert native.layer.shapes == [shape]
        assert peer.smooth is True


def test_nested_clear_failure_restores_owned_geometry_at_outer_checkpoint(
    native, monkeypatch
):
    from fontlab_glyport.model.backend import HintInfo

    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]
    monkeypatch.setattr(backend, "hints", lambda lid: (HintInfo(True, 0, 10),))

    def fail(*args):
        raise RuntimeError("hint removal failed")

    monkeypatch.setattr(backend, "remove_hint", fail)
    with font.undo_group("Earlier edit and nested clear"):
        layer.paths[0].nodes[0].position = (33, 44)
        retained = layer.paths[1].nodes[0]
        with pytest.raises(RuntimeError, match="hint removal failed"):
            layer.clear()
        assert [path.nodes[0].position for path in layer.paths] == [(33, 44), (20, 2)]
        retained.position = (55, 66)
        assert retained.position == (55, 66)


def test_checkpoint_recovery_failure_reports_both_errors(native, monkeypatch):
    from fontlab_glyport.errors import PartialFailure

    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]

    def fail_insert(*args):
        raise RuntimeError("checkpoint insert failed")

    def fail_restore(*args):
        raise RuntimeError("checkpoint restore failed")

    with font.undo_group("Failed checkpoint recovery"):
        layer.paths[0].nodes[0].position = (33, 44)
        # Detached constructors now all run before mutation. Fail attachment
        # after removal instead, so recovery is genuinely necessary.
        monkeypatch.setattr(native.layer, "insertShape", fail_insert)
        monkeypatch.setattr(backend, "restore_collection", fail_restore)
        with pytest.raises(PartialFailure) as error:
            layer.paths = []
        assert error.value.capability == "GSLayer.paths"
        assert [str(e) for e in error.value.errors] == [
            "checkpoint insert failed",
            "checkpoint restore failed",
        ]
