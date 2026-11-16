# this_file: tests/test_issue106_round16.py
"""History ownership and observable Glyphs contracts from round sixteen."""

from types import SimpleNamespace as NS

import pytest
from test_drawing import _scope
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.drawing import context as gc
from fontlab_glyport.model import Model
from fontlab_glyport.model.fake_backend import FakeBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def test_bulk_checkpoint_owns_every_shape_after_history_before_removal(native):
    backend = native.backend
    layer = native.font.glyphs[0].layers[0]
    original = native.layer.shapes[0]
    events = []
    native.package.checkInitHistoryState = lambda index: events.append("init")
    native.module.flItems = lambda: NS(
        notifyChangesApplied=lambda *args: events.append("notify")
    )
    state = backend.snapshot_collection(layer._id)
    # Taking a rollback snapshot alone must never change the working layer.
    assert native.layer.shapes == [original]
    with native.font.undo_group("Apply"):
        backend.prepare_collection(layer._id, "paths")
        assert events[:2] == ["init", "notify"]
        assert native.layer.shapes[0] is not original
        assert len(original.contours) == 2
        backend.remove_path(layer._id, layer.paths[0]._id)
        assert len(original.contours) == 2
        backend.restore_collection(layer._id, state)


@pytest.mark.parametrize("origin", [(5, 80), (55, 180)])
def test_view_coordinates_ignore_glyph_translation_and_expose_origin(origin):
    from fontlab_glyport.model.proxies import _GraphicView

    painter, scope = _scope(base=(2, 0, 0, -2, *origin))
    painter.device = lambda: NS(width=lambda: 400, height=lambda: 300)
    with scope, gc.reporter_view_scope(2):
        context = gc.current()
        assert context.base == (1, 0, 0, -1, 0, 300)
        assert _GraphicView(context).activePosition() == (origin[0], 300 - origin[1])


def test_keyed_anchor_failure_restores_argument_name(monkeypatch):
    from fontlab_glyport.model import GSAnchor

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    anchor = GSAnchor("source", (1, 2))
    backend = layer._font._model._backend

    def fail(*args):
        assert anchor.name == "target", "rename the argument before adding"
        raise RuntimeError("injected")

    monkeypatch.setattr(backend, "add_anchor", fail)
    with pytest.raises(RuntimeError, match="injected"):
        layer.anchors["target"] = anchor
    assert anchor.name == "source"


def test_instance_profile_constants_and_metadata(native):
    from test_glyphsapp import _make

    from fontlab_glyport.model.backend import AxisInfo

    axis = NS(shortName="wt", name="Weight", tag="wght")
    native.package.axes = [axis]
    native.package.instances = [
        NS(name=name, location={"wt": weight}, exportable=active,
           weight="Regular", weightValue=weight, width="Normal")
        for name, weight, active in [("Light", 100, True), ("Regular", 400, False), ("Bold", 700, True)]
    ]
    # Unregistered packages also have a safe native instance list; do not
    # silently replace that list with an empty tuple.
    native.backend._owned_fonts[native.package.id] = NS()
    infos = native.backend.instances(native.fid)
    assert [i.name for i in infos] == ["Light", "Regular", "Bold"]
    assert [i.axes for i in infos] == [(100,), (400,), (700,)]
    backend = FakeBackend()
    from dataclasses import replace

    backend.fonts["font"] = replace(backend.fonts["font"], axes=(AxisInfo("weight", "Weight", "wght"),))
    backend.instance_data["font"] = infos
    module, _, _ = _make(backend)
    namespace = {}
    exec("from GlyphsApp import *", {"__builtins__": {"__import__": lambda *args: module}}, namespace)  # noqa: S102 - test the public star-import contract
    assert namespace["INSTANCETYPESINGLE"] == 0
    instance = module.Glyphs.font.instances[1]
    assert (instance.name, instance.active, instance.type) == ("Regular", False, 0)
    assert instance.axes == [400] and instance.weightValue == 400
    assert instance.weight == "Regular"
    instance.active = True
    assert instance.exports is True


def test_instance_interpolation_and_filename_refuse_precisely_when_unavailable():
    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model import GSInstance

    instance = GSInstance()
    for capability, operation in [
        ("GSInstance.interpolatedFont", lambda: instance.interpolatedFont),
        ("GSInstance.fileName", instance.fileName),
    ]:
        with pytest.raises(UnsupportedCapability) as error:
            operation()
        assert error.value.capability == capability


def test_bulk_path_setter_clones_all_history_shapes_before_deleting_contours(native, monkeypatch):
    from copy import deepcopy

    layer = native.font.glyphs[0].layers[0]
    original = native.layer.shapes[0]
    second = type(original)()
    native.layer.shapes.append(second)
    before = deepcopy(native.layer.shapes)
    events, snapshots = [], []
    native.package.checkInitHistoryState = lambda index: events.append("init")

    def notify(name, objects, recursive=False):
        assert objects == [native.layer, native.glyph]
        snapshots.append(tuple(native.layer.shapes))
        events.append("notify")

    native.module.flItems = lambda: NS(notifyChangesApplied=notify)
    original_remove = type(original).removeContour

    def remove_contour(shape, contour):
        assert shape is not original and shape is not second
        assert events.count("insert clone") == 2, "own the entire layer first"
        original_remove(shape, contour)

    monkeypatch.setattr(type(original), "removeContour", remove_contour)

    def insert(index, shape):
        assert shape is not original and shape is not second
        events.append("insert clone")
        native.layer.shapes.insert(index, shape)

    native.layer.insertShape = insert
    with native.font.undo_group("Filter Apply"):
        layer.paths = []
    assert events[:4] == ["init", "notify", "insert clone", "insert clone"]
    assert snapshots[0] == (original, second)
    assert native.layer.shapes == []
    assert [[(n.x, n.y) for c in s.contours for n in c.nodes()] for s in snapshots[0]] == [
        [(n.x, n.y) for c in s.contours for n in c.nodes()] for s in before
    ]


def test_copy_decomposed_layer_preserves_path_protocol_and_is_detached():
    from fontlab_glyport.model import GSNode, GSPath

    layer = Model(FakeBackend()).font.glyphs[0].layers[0]
    layer.components = []
    layer.paths = [GSPath([GSNode((0, 0)), GSNode((10, 0)), GSNode((10, 10))], closed=True)]
    copied = layer.copyDecomposedLayer()
    assert copied.paths[0].closed is True
    assert copied.bezierPath.bounds().size.width == 10
    copied.paths[0].nodes[0].position = (100, 100)
    assert layer.paths[0].nodes[0].position == (0, 0)
