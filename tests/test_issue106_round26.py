# this_file: tests/test_issue106_round26.py
"""Detached clone staging must precede all history and working-shape edits."""

from contextlib import nullcontext

import pytest
from test_issue106_round9 import native as native_fixture
from test_issue106_round24 import native_write_state

from fontlab_glyport.errors import UnsupportedCapability


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("failure_index", [0, 1])
@pytest.mark.parametrize("owned", [False, True])
def test_collection_clone_refusal_has_no_history_revision_or_working_changes(
    native, monkeypatch, public, failure_index, owned
):
    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]
    native.layer.shapes.append(type(native.layer.shapes[0])())
    scope = font.undo_group("Earlier edit") if owned else nullcontext()
    with scope:
        if owned:
            layer.paths[0].nodes[0].position = (33, 44)
        values = [path.copy() for path in layer.paths]
        shapes = tuple(native.layer.shapes)
        before = native_write_state(native)

        def refuse():
            raise UnsupportedCapability("injected shape clone constructor")

        monkeypatch.setattr(shapes[failure_index], "clone", refuse)
        with pytest.raises(UnsupportedCapability, match="injected"):
            if public:
                layer.paths = values
            else:
                backend.prepare_collection(layer.id, "paths")
        assert tuple(native.layer.shapes) == shapes
        assert native_write_state(native) == before


@pytest.mark.parametrize("field", ["paths", "shapes", "anchors", "guides"])
@pytest.mark.parametrize("failure_index", [0, 1])
def test_bulk_input_constructors_are_all_staged_before_checkpoint(
    native, monkeypatch, field, failure_index
):
    from types import SimpleNamespace as NS

    from test_issue106_round23 import install_path_constructors

    from fontlab_glyport.model import GSAnchor, GSGuide, GSNode, GSPath

    install_path_constructors(native)
    native.layer.appendGuidelines = lambda values: native.layer.guidelines.extend(
        values
    )
    layer = native.font.glyphs[0].layers[0]
    calls = []

    def constructor(*args, **kw):
        index = len(calls)
        calls.append(index)
        if index == failure_index:
            raise UnsupportedCapability("injected input constructor")
        point = args[0] if field == "anchors" else NS(x=lambda: 0, y=lambda: 0)
        return NS(
            id=50000 + index,
            isValid=True,
            point=point,
            centerPoint=point,
            angle=0,
            name=f"guide{index}",
            isHint=False,
        )

    if field in ("paths", "shapes"):
        original = native.module.flNode

        def node(*args, **kw):
            constructor(*args, **kw)
            return original(*args, **kw)

        node.NodeKind = original.NodeKind
        native.module.flNode = node
        values = [GSPath([GSNode((10, 20))]), GSPath([GSNode((30, 40))])]
    elif field == "anchors":
        native.module.flPinPoint = constructor
        values = [GSAnchor("top", (1, 2)), GSAnchor("bottom", (3, 4))]
    else:
        monkeypatch.setattr(native.backend, "_new_guide", constructor)
        values = [GSGuide((1, 2)), GSGuide((3, 4))]
    before = native_write_state(native)
    with pytest.raises(UnsupportedCapability, match="injected"):
        setattr(layer, field, values)
    assert native_write_state(native) == before


_CLONE_OPERATIONS = [
    "set_node_name",
    "set_node_position",
    "set_node_smooth",
    "set_node_connection",
    "transform_layer",
    "make_node_first",
    "remove_path",
    "set_path_nodes",
    "prepare_collection",
    "update_layer_metrics",
    "snapshot_collection",
]


@pytest.mark.parametrize("operation", _CLONE_OPERATIONS)
@pytest.mark.parametrize("error_name", ["UnsupportedCapability", "HostUnavailable"])
def test_last_clone_constructor_refusal_is_before_history_on_each_cow_path(
    native, monkeypatch, operation, error_name
):
    from types import SimpleNamespace as NS

    from test_issue106_round24 import write_arguments

    from fontlab_glyport import errors

    args = write_arguments(native)[operation]
    native.glyph.activeLayer = native.layer
    native.layer.metricsLeft = "=A"
    if operation == "snapshot_collection":
        native.backend._owned_shapes.add(native.layer.shapes[0].id)
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._import_qtgui",
        lambda: NS(QTransform=lambda *a: object()),
    )
    before = native_write_state(native)
    error = getattr(errors, error_name)

    def refuse():
        raise error("injected last clone constructor")

    monkeypatch.setattr(native.layer.shapes[0], "clone", refuse)
    with pytest.raises(error, match="injected"):
        getattr(native.backend, operation)(*args)
    assert native_write_state(native) == before
    assert native.glyph.activeLayer is native.layer


def component_template(native, monkeypatch, clone):
    from types import SimpleNamespace as NS

    names = {"A": native.glyph}
    native.layer.name = "Regular"
    native.package.findName = names.get
    native.package.findNewName = lambda name: "_scratch"
    native.package.deleteGlyph = lambda glyph: names.pop(glyph.name)

    def create(**kw):
        names["_scratch"] = NS(
            name="_scratch", findLayer=lambda name: NS(shapes=[NS(clone=clone)])
        )

    monkeypatch.setattr(
        native.backend, "_fontpr", lambda: NS(Error=RuntimeError, set_glyph=create)
    )
    return names


@pytest.mark.parametrize("public", [False, True])
def test_component_template_clone_refusal_precedes_target_checkpoint(
    native, monkeypatch, public
):
    from fontlab_glyport.model import GSComponent
    from fontlab_glyport.model.backend import ComponentInfo

    def refuse():
        raise UnsupportedCapability("injected component clone")

    names = component_template(native, monkeypatch, refuse)
    layer = native.font.glyphs[0].layers[0]
    before = native_write_state(native)
    with pytest.raises(UnsupportedCapability, match="injected"):
        if public:
            layer.components = [GSComponent("A")]
        else:
            native.backend.append_component(
                layer.id, ComponentInfo("", "A", (1, 0, 0, 1, 0, 0))
            )
    assert native_write_state(native) == before
    assert list(names) == ["A"]


def test_success_stages_clones_before_history_but_attaches_after_baseline(
    native, monkeypatch
):
    events = []
    shape_type = type(native.layer.shapes[0])
    clone = shape_type.clone
    original = native.layer.shapes[0]

    def stage(shape):
        events.append("clone")
        return clone(shape)

    monkeypatch.setattr(shape_type, "clone", stage)
    native.package.checkInitHistoryState = lambda index: events.append("init")
    factory = native.module.flItems

    def items():
        item = factory()
        notify = item.notifyChangesApplied

        def publish(*args):
            events.append("notify")
            notify(*args)

        item.notifyChangesApplied = publish
        return item

    native.module.flItems = items
    insert = native.layer.insertShape

    def attach(index, shape):
        events.append("attach")
        return insert(index, shape)

    native.layer.insertShape = attach
    layer = native.font.glyphs[0].layers[0]
    layer.paths = [path.copy() for path in layer.paths]
    assert events[:4] == ["clone", "init", "notify", "attach"]
    assert events.count("clone") == 1, "snapshot and preparation share staged clones"
    assert [c.nodes()[0].x for c in original.contours] == [10, 20]


def test_unchanged_snapshot_recovery_neither_resolves_host_nor_publishes(
    native, monkeypatch
):
    from fontlab_glyport.errors import HostUnavailable

    state = native.backend.snapshot_collection(native.lid, stage=True)
    before = native_write_state(native)

    def unavailable():
        raise HostUnavailable("recovery must not touch the host")

    monkeypatch.setattr(native.backend, "_native", unavailable)
    native.backend.restore_collection(native.lid, state)
    assert native_write_state(native) == before


@pytest.mark.parametrize("operation", ["rename_glyph", "remove_glyph", "remove_guide"])
def test_remaining_wrapper_and_value_conversions_refuse_before_history(
    native, monkeypatch, operation
):
    from types import SimpleNamespace as NS

    backend = native.backend

    class RefusingName:
        def __str__(self):
            raise UnsupportedCapability("injected name conversion")

    class Glyph:
        id, isValid, name = native.glyph.id, True, "A"

        @property
        def fgGlyph(self):
            raise UnsupportedCapability("injected fontgate wrapper conversion")

    class RefusingGuides:
        def __iter__(self):
            raise UnsupportedCapability("injected guideline list conversion")

    if operation == "rename_glyph":
        native.package.renameGlyph = lambda *a, **kw: True
        backend._objects[native.gid] = Glyph()
        args = (native.fid, native.gid, "renamed")
    elif operation == "remove_glyph":
        native.glyph.name = RefusingName()
        args = (native.fid, native.gid)
    else:
        guide = NS(id=999, isValid=True)
        token = backend._register((native.fid, "guide", guide.id), guide, native.lid)
        native.layer.guidelines = RefusingGuides()
        args = (native.lid, token)
    before = (list(native.calls), backend._revision, dict(backend._prepared))
    with pytest.raises(UnsupportedCapability, match="injected"):
        getattr(backend, operation)(*args)
    assert (native.calls, backend._revision, backend._prepared) == before
