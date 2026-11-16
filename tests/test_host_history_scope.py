# this_file: tests/test_host_history_scope.py
"""Prospective native history boundaries, using the real shared App predicates.

The native-shaped scene extends existing backend fixtures; it is offline evidence.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from functools import partial
from types import SimpleNamespace as NS

import pytest
from test_issue106_round7_native import native as native_fixture

from fontlab_glyport.model.backend import ComponentInfo
from fontlab_glyport.model.fontlab_backend import _PendingLayer


@pytest.fixture
def scene(monkeypatch):
    s = native_fixture.__wrapped__(monkeypatch)
    return canvas_scene(s, monkeypatch)


def canvas_scene(s, monkeypatch):
    """Add readable native UI surfaces to an existing realistic backend fixture."""
    s.events = []
    s.package.isNull = s.glyph.isNull = False
    s.glyph.package = s.package
    s.glyph.tags, s.glyph.mark = [], 0
    s.package.master = "Regular"
    s.package.setMaster = lambda name: s.events.append(("master", name))
    s.package.checkInitHistoryState = lambda _: s.events.append("init")
    s.package.packageLib = {}
    s.package.masterLib = {}
    s.glyph.fgGlyph = s.glyph
    if not hasattr(s.package, "findName"):
        s.package.findName = lambda name: s.glyph if name == s.glyph.name else None
    s.layer.changed = lambda: s.events.append("changed")
    s.layer.update = lambda: s.events.append("update")
    s.layer.clearAnchors = lambda: s.layer.anchors.clear()
    s.layer.removeAllShapes = lambda: s.layer.shapes.clear()
    s.layer.addShapes = lambda shapes: s.layer.shapes.extend(shapes)
    frame = NS(inherits=lambda name: name == "YFrameWindow")
    panel = NS(inherits=lambda name: name == "FontWindow", parentWidget=lambda: frame)
    s.canvas = NS(isNull=False, textBlocks=list)
    s.workspace = NS(
        packages=lambda: [s.package],
        currentPackage=s.package,
        activeFontPanel=panel,
        getActiveCanvas=lambda: s.canvas,
    )
    s.module.flWorkspace.instance = lambda: s.workspace
    s.module.CurrentGlyph = lambda: s.glyph
    s.module.flGlyph = NS(updatedFgGlyphs=lambda: (17, 23))
    monkeypatch.setitem(sys.modules, "fontlab", s.module)

    def show(*glyphs):
        s.canvas.textBlocks = lambda: [
            NS(
                glyphsCount=lambda: len(glyphs),
                getGlyphAt=lambda i: NS(glyph=glyphs[i]),
            )
        ]
        s.workspace.getActiveCanvas = lambda: s.canvas
        s.workspace.activeFontPanel = None

    def font_window():
        s.workspace.getActiveCanvas = lambda: None
        s.workspace.activeFontPanel = panel

    s.show, s.font_window = show, font_window
    s.show(NS(name="other", package=s.package, isNull=False))
    return s


def snapshot(s):
    b = s.backend
    return (
        dict(b._changed),
        dict(b._prepared),
        set(b._pending_layer_updates),
        set(b._owned_shapes),
        dict(b._objects),
        b._undo_name,
        s.layer.advanceWidth,
        list(s.calls),
        list(s.events),
    )


def test_off_canvas_width_refuses_before_any_native_effect(scene):
    s = scene
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.set_layer_width(s.lid, 650)
    assert snapshot(s) == before, (
        "A rejected write crossed a history/cache/write boundary"
    )


@pytest.mark.parametrize("window", ["shown", "font", "unreadable"])
def test_existing_owner_allowed_with_real_app_policy(scene, window):
    s = scene
    if window == "font":
        s.font_window()
    elif window == "shown":
        alias = copy(s.glyph)
        alias.id = 999  # canvas slot ids differ from CurrentGlyph ids on 9790
        s.show(alias, s.glyph)
    else:

        def unreadable():
            raise RuntimeError("unreadable canvas")

        s.workspace.getActiveCanvas = unreadable
    s.backend.set_layer_width(s.lid, 650)
    assert s.layer.advanceWidth == 650 and len(s.calls) == 2


def test_prepared_shortcut_revalidates_after_focus_change(scene):
    s = scene
    s.show(s.glyph)
    s.backend.begin_undo("Retained")
    s.backend.set_layer_width(s.lid, 600)
    s.show(NS(name="other", package=s.package, isNull=False))
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.set_layer_width(s.lid, 700)
    assert snapshot(s) == before, "Already prepared must not cache permission"
    s.font_window()
    s.backend.end_undo()
    assert s.layer.advanceWidth == 600 and s.backend._undo_name is None


@pytest.mark.parametrize("unreadable", [False, True])
def test_retained_owner_and_pending_update_join_prospective_owner(scene, unreadable):
    s = scene
    s.show(s.glyph)
    b = s.backend
    b.begin_undo("C then D")
    b.set_layer_width(s.lid, 600)
    b._pending_layer_updates.add(s.lid)
    other = NS(
        id=21,
        name="D",
        isValid=True,
        isNull=False,
        package=s.package,
        changed=lambda: s.events.append("D.changed"),
        update=lambda: None,
    )
    gid = b._register((s.fid, "glyph", 201), other, s.fid)
    layer = type(s.layer)(31)
    lid = b._read_layer(s.fid, layer, s.mid, gid).id
    s.show(other)
    if unreadable:
        s.module.CurrentGlyph = lambda: other
        s.workspace.getActiveCanvas = lambda: (_ for _ in ()).throw(
            RuntimeError("canvas")
        )
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        b.set_layer_width(lid, 750)
    assert snapshot(s) == before and layer.advanceWidth == 500


@pytest.mark.parametrize("background", [False, True])
def test_pending_materialization_is_guarded_before_creation(scene, background):
    s = scene
    s.glyph.findLayerCreate = lambda name: s.events.append("findLayerCreate")
    s.backend._objects[s.lid] = _PendingLayer("Regular")
    lid = s.backend.background_layer(s.lid).id if background else s.lid
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.set_layer_width(lid, 650)
    assert snapshot(s) == before, "Pending foreground/mask was materialized"


def test_existing_foreground_missing_mask_refuses_before_get_mask_create(scene):
    s = scene
    background = s.backend.background_layer(s.lid).id
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.set_layer_width(background, 650)
    assert snapshot(s) == before and s.layer.mask is None
    assert not any(s.layer.mask_calls), "A rejected background created a mask"


def test_anchor_edit_refuses_before_point_assignment_or_history(scene, monkeypatch):
    s = scene
    anchor = NS(id=90, isValid=True, point=(12, 34))
    token = s.backend._register((s.fid, "anchor", 90), anchor, s.lid)
    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._qpoint", lambda x, y: (x, y)
    )
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.set_anchor_position(token, 50, 60)
    assert snapshot(s) == before and anchor.point == (12, 34)


def test_collection_preflight_precedes_history_initialization(scene):
    s = scene
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.prepare_collection(s.lid, "paths")
    assert not s.events and not s.calls, "Collection initialized history before refusal"


@pytest.mark.parametrize("operation", ["tags", "mark", "grouping"])
def test_direct_writers_refuse_before_assignment(scene, operation):
    s = scene
    effects = []
    shape = NS(
        isComponent=False, contours=[1], addContour=lambda *a: effects.append("add")
    )
    second = NS(isComponent=False, contours=[2])
    s.layer.shapes = [shape, second]
    with pytest.raises(ValueError, match="Glyph window"):
        if operation == "tags":
            s.backend.set_glyph_tags(s.gid, ("new",))
        elif operation == "mark":
            s.backend.set_mark(s.gid, 50)
        else:
            s.backend.restore_path_grouping(s.lid, (2,))
    assert s.glyph.tags == [] and s.glyph.mark == 0
    assert s.layer.shapes == [shape, second] and not effects and not s.calls


@pytest.mark.parametrize("operation", ["lib", "delete", "rename", "master"])
def test_package_history_requires_matching_font_window(scene, operation):
    s = scene
    s.show(s.glyph)  # even the current single glyph cannot own package history
    s.package.deleteGlyph = lambda _: s.events.append("delete")
    s.package.renameGlyph = lambda *a: s.events.append("rename") or True
    if operation == "master":
        s.package.masters.append("Bold")
        mid = s.backend._register((s.fid, "master", "Bold"), s.package, s.fid)
        s.backend._master_names[mid] = "Bold"
        action = partial(s.backend.set_lib, mid, {"new": 1})
    elif operation == "rename":
        # The getter is itself a measured cache hazard, so refusal must precede it.
        action = partial(s.backend.rename_glyph, s.fid, s.gid, "new")
    elif operation == "delete":
        action = partial(s.backend.remove_glyph, s.fid, s.gid)
    else:
        action = partial(s.backend.set_lib, s.fid, {"new": 1})
    with pytest.raises(ValueError, match="Font window"):
        action()
    assert not s.events and not s.calls and s.package.packageLib == {}


@pytest.mark.parametrize("kind", ["glyph", "component"])
@pytest.mark.parametrize("unreadable", [False, True])
def test_registered_creation_refuses_before_builder_and_capture(
    scene, monkeypatch, kind, unreadable
):
    from fontlab_glyport.model import creation

    s = scene
    s.show(s.glyph)
    if unreadable:
        s.workspace.getActiveCanvas = lambda: (_ for _ in ()).throw(
            RuntimeError("canvas")
        )
    s.backend._tool_font = lambda *a: s.package.fgId

    def builder(**kwargs):
        s.events.append("builder")
        raise RuntimeError("builder side effect spy")

    s.backend._resolve_tool = lambda *a: builder
    monkeypatch.setattr(
        creation, "capture", lambda *a: (s.events.append("capture") or [], None)
    )
    s.package.findNewName = lambda _: "_scratch"
    with pytest.raises(ValueError, match="Glyph window"):
        if kind == "glyph":
            s.backend.append_glyph(s.fid, "new")
        else:
            with s.backend.stage_collection(
                s.lid, "components", (ComponentInfo("", "A", (1, 0, 0, 1, 0, 0)),)
            ):
                pass
    assert not s.events and not s.calls, (
        "Registered scratch builder escaped staging guard"
    )


def test_same_name_other_package_and_off_thread_refuse(scene):
    s = scene
    s.show(NS(name=s.glyph.name, package=NS(id=999), isNull=False))
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.set_layer_width(s.lid, 700)
    s.font_window()
    with ThreadPoolExecutor(max_workers=1) as pool, pytest.raises(ValueError, match="Glyph window"):
        pool.submit(s.backend.set_layer_width, s.lid, 700).result()
    assert not s.events and not s.calls and s.layer.advanceWidth == 500


def test_publication_rechecks_before_pending_cache_refresh_and_can_retry(scene):
    s = scene
    s.show(s.glyph)
    b = s.backend
    b.begin_undo("Focus switch")
    b.set_layer_width(s.lid, 600)
    b._pending_layer_updates.add(s.lid)
    s.show(NS(name="other", package=s.package, isNull=False))
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        b.end_undo()
    assert snapshot(s) == before, (
        "Publication refreshed caches or discarded retry state"
    )
    s.font_window()
    b.end_undo()
    assert not b._changed and not b._prepared and b._undo_name is None


def test_recovery_restores_live_geometry_even_after_focus_changes(scene):
    s = scene
    s.show(s.glyph)
    b = s.backend
    b.begin_undo("Recovery")
    state = b.snapshot_collection(s.lid)
    b.set_layer_width(s.lid, 600)
    s.layer.shapes.append(NS(id=99))
    s.show(NS(name="other", package=s.package, isNull=False))
    with pytest.raises(ValueError, match="Glyph window"):
        b.restore_collection(s.lid, state)
    assert s.layer.shapes == [], "Scope refusal must not prevent required recovery"
    assert s.lid in b._pending_layer_updates and b._changed, (
        "Recovery publication must remain retryable"
    )
    s.font_window()
    b.end_undo()


def test_pending_queue_is_disclosed_without_blocking_or_clearing(scene, capsys):
    s = scene
    reads = []
    s.module.flGlyph.updatedFgGlyphs = lambda: reads.append("read") or (17, 23)
    s.show(s.glyph)
    s.backend.set_layer_width(s.lid, 600)
    assert s.layer.advanceWidth == 600
    assert reads == ["read"], "Read the queue once at the forward batch boundary"
    assert "queued updates" in capsys.readouterr().out and len(s.calls) == 2


@pytest.fixture
def geometry(monkeypatch):
    from test_geometry_cache_updates import cached

    return canvas_scene(cached.__wrapped__(monkeypatch), monkeypatch)


def test_owned_shape_and_node_shortcut_rechecks_without_clone_or_rebind(geometry):
    s = geometry
    s.show(s.glyph)
    b = s.backend
    node = s.font.glyphs[0].layers[0].paths[0].nodes[0]
    b.begin_undo("Owned clone")
    b.set_node_position(node.id, 100, 200)
    original = b._object(node.id)
    assert b._owned_shapes, "Control did not reach owned shortcut"
    s.show(NS(name="other", package=s.package, isNull=False))
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        b.set_node_position(node.id, 300, 400)
    assert snapshot(s) == before and b._object(node.id) is original
    assert (original.x, original.y) == (100, 200)


@pytest.mark.parametrize("method", ["endChanges", "endUndo", "finish"])
def test_nested_proxy_publication_keeps_pending_state_then_retries(geometry, method):
    s = geometry
    s.show(s.glyph)
    font = s.font
    glyph = font.glyphs[0]
    layer = font._native_layer(s.lid)
    if method == "endChanges":
        layer.beginChanges()
        layer.beginChanges()
    else:
        glyph.beginUndo()
        glyph.beginUndo()
    layer.width = 600
    if method == "endChanges":
        layer.endChanges()
    else:
        glyph.endUndo()
    s.show(NS(name="other", package=s.package, isNull=False))
    before = snapshot(s)
    if method == "finish":
        diagnostics = []
        with pytest.raises(ValueError, match="Glyph window"):
            font._finish_undo(diagnostics.append)
        assert diagnostics[-1].code == "UNDO_CLOSE_FAILED"
    else:
        with pytest.raises(ValueError, match="Glyph window"):
            layer.endChanges() if method == "endChanges" else glyph.endUndo()
    assert snapshot(s) == before and font._undo_pending
    if method == "endChanges":
        assert len(layer._change_scopes) == 1
    s.font_window()
    layer.endChanges() if method == "endChanges" else font._end_undo()
    assert not font._undo_pending and not s.backend._changed


def test_unreadable_canvas_noncurrent_and_unreadable_current_fail_closed(scene):
    s = scene
    s.workspace.getActiveCanvas = lambda: (_ for _ in ()).throw(RuntimeError("canvas"))
    for current in [NS(name="other"), None]:
        s.module.CurrentGlyph = lambda current=current: current
        with pytest.raises(ValueError, match="Glyph window"):
            s.backend.set_layer_width(s.lid, 800)
    assert not s.events and not s.calls and s.layer.advanceWidth == 500


def test_unknown_retained_owner_refuses_before_prospective_write(scene):
    from fontlab_glyport.errors import StaleNativeObject

    s = scene
    s.font_window()
    s.backend._prepared["glyph", 999] = NS(id=999)
    before = snapshot(s)
    with pytest.raises(StaleNativeObject):
        s.backend.set_layer_width(s.lid, 800)
    assert snapshot(s) == before


def test_font_global_write_works_only_for_matching_current_font(scene):
    s = scene
    s.font_window()
    s.workspace.currentPackage = NS(id=999, isNull=False)
    with pytest.raises(ValueError, match="matching Font window"):
        s.backend.set_lib(s.fid, {"value": 1})
    assert not s.calls and s.package.packageLib == {}
    s.workspace.currentPackage = s.package
    s.backend.set_lib(s.fid, {"value": 1})
    assert s.package.packageLib == {"value": 1} and len(s.calls) == 2


def test_pure_staging_refusal_needs_no_recovery_or_history(scene):
    s = scene
    state = s.backend.snapshot_collection(s.lid)
    before = snapshot(s)
    with pytest.raises(ValueError, match="Glyph window"):
        s.backend.prepare_collection(s.lid, "paths", state=state)
    s.backend.restore_collection(s.lid, state)
    assert snapshot(s) == before, "No-change recovery created history or cache writes"


def test_creation_recovery_preserves_original_error_after_focus_switch(
    scene, monkeypatch
):
    from fontlab_glyport.model import creation

    s = scene
    s.font_window()
    effects = []
    original = RuntimeError("original builder failure")
    monkeypatch.setattr(creation, "capture", lambda *a: ([], None))
    monkeypatch.setattr(creation, "restore", lambda *a: effects.append("restore"))
    s.package.findName = lambda name: NS(id=200) if name == "new" else None
    s.package.deleteGlyph = lambda glyph: effects.append("delete") or True

    def builder(**kwargs):
        s.show(s.glyph)
        effects.append("builder")
        raise original

    with pytest.raises(RuntimeError) as error:
        creation.create_preserving(s.backend, s.package, "new", builder)
    assert error.value is original and effects == ["builder", "delete", "restore"]


def test_bulk_recovery_keeps_original_and_publication_error_after_focus_switch(
    geometry, monkeypatch
):
    from fontlab_glyport.errors import PartialFailure
    from fontlab_glyport.model import GSNode, GSPath

    s = geometry
    s.show(s.glyph)
    layer = s.font.glyphs[0].layers[0]
    before = tuple(s.layer.shapes)
    original = RuntimeError("append after prior removal")

    def append(*args):
        s.show(NS(name="other", package=s.package, isNull=False))
        raise original

    monkeypatch.setattr(s.backend, "append_path", append)
    with pytest.raises(PartialFailure) as error:
        layer.paths = [GSPath([GSNode((1, 2)), GSNode((3, 4))])]
    assert error.value.errors[0] is original
    assert isinstance(error.value.errors[1], ValueError)
    assert tuple(s.layer.shapes) == before, "Necessary restoration was blocked by focus"
    assert s.font._undo_pending and s.backend._changed
    s.font_window()
    s.font._end_undo()


def test_creation_validation_precedence_is_unchanged(scene):
    s = scene
    with pytest.raises(ValueError, match="Duplicate or empty"):
        s.backend.append_glyph(s.fid, "")
    with pytest.raises(ValueError, match="Duplicate or empty"):
        s.backend.append_glyph(s.fid, s.glyph.name)
    assert not s.events and not s.calls


def test_cache_callback_focus_switch_refuses_final_sink_without_losing_batch(scene):
    s = scene
    s.show(s.glyph)
    b = s.backend
    b.begin_undo("Cache callback")
    b.set_layer_width(s.lid, 600)
    b._pending_layer_updates.add(s.lid)

    def switch():
        s.show(NS(name="other", package=s.package, isNull=False))

    s.glyph.update = switch
    with pytest.raises(ValueError, match="Glyph window"):
        b.end_undo()
    assert len(s.calls) == 1 and b._changed and b._prepared
    s.font_window()
    b.end_undo()
    assert len(s.calls) == 2 and not b._changed


def test_component_originals_survive_focus_refusal_and_publication_retry(monkeypatch):
    from test_component_history import assert_originals_before_owners, history

    s = canvas_scene(history.__wrapped__(monkeypatch), monkeypatch)
    s.show(s.glyph)
    b = s.backend
    b.begin_undo("Retained component")
    component = s.public.components[0]
    component.name = "C"
    before = snapshot(s)
    assert any(key[0] == "component_history" for key in b._prepared)
    s.show(NS(name="other", package=s.package, isNull=False))
    with pytest.raises(ValueError, match="Glyph window"):
        component.name = "B"
    assert snapshot(s) == before and component.name == "C"
    s.font_window()
    s.publish_failure = True
    with pytest.raises(RuntimeError, match="history publication"):
        b.end_undo()
    assert b._prepared and b._changed
    s.publish_failure = False
    b.end_undo()
    assert_originals_before_owners(s)
    s.undo()
    assert s.layer.shapes[1].isComponent
    assert s.layer.shapes[1].shapeData.componentGlyph == "B"


def switch_focus_on_preparation(s):
    """Inject a synchronous preparation callback; keep the real App guards."""
    notify = s.module.flItems().notifyChangesApplied

    def callback(name, items, deep):
        notify(name, items, deep)
        s.show(NS(name="other", package=s.package, isNull=False))

    s.module.flItems = lambda: NS(notifyChangesApplied=callback)
    return notify


def test_preparation_callback_refuses_scalar_before_write_and_preserves_checkpoint(
    scene,
):
    s = scene
    s.show(s.glyph)
    b = s.backend
    b.begin_undo("Callback before scalar")
    notify = switch_focus_on_preparation(s)
    with pytest.raises(ValueError, match="Glyph window"):
        b.set_layer_width(s.lid, 800)
    assert s.layer.advanceWidth == 500, (
        "Preparation callback refusal came after width mutation"
    )
    assert len(s.calls) == 1 and b._prepared, "Legitimate preparation receipt was lost"
    assert not b._changed and not b._pending_layer_updates and not s.events
    s.module.flItems = lambda: NS(notifyChangesApplied=notify)
    s.font_window()
    b.set_layer_width(s.lid, 800)
    b.end_undo()
    assert s.layer.advanceWidth == 800 and len(s.calls) == 2
    assert not b._prepared and not b._changed


def test_preparation_callback_refuses_cow_before_attachment_or_rebind(geometry):
    s = geometry
    s.show(s.glyph)
    b = s.backend
    node = s.font.glyphs[0].layers[0].paths[0].nodes[0]
    original = b._object(node.id)
    shapes, bindings = tuple(s.layer.shapes), dict(b._objects)
    before = original.x, original.y
    b.begin_undo("Callback before COW")
    notify = switch_focus_on_preparation(s)
    with pytest.raises(ValueError, match="Glyph window"):
        b.set_node_position(node.id, 800, 900)
    assert tuple(s.layer.shapes) == shapes and b._objects == bindings
    assert (original.x, original.y) == before and not b._owned_shapes
    assert len(s.calls) == 1 and b._prepared and not b._changed
    assert not b._pending_layer_updates and s.events == [
        ("notify", "Callback before COW", (s.layer.id, s.glyph.id), True)
    ], "Only the legitimate preparation notification may have occurred"
    s.module.flItems = lambda: NS(notifyChangesApplied=notify)
    s.font_window()
    b.set_node_position(node.id, 800, 900)
    b.end_undo()
    assert (b._object(node.id).x, b._object(node.id).y) == (800, 900)
    assert len(s.calls) == 2 and not b._prepared and not b._changed


@pytest.mark.parametrize("target", ["master", "mask", "recursive_mask"])
def test_preparation_callback_refuses_materialization_before_creation(scene, target):
    s = scene
    s.show(s.glyph)
    b = s.backend
    creations = []
    if target != "mask":
        b._objects[s.lid] = _PendingLayer("Regular")
        s.glyph.layers = []

        def create(name):
            creations.append(name)
            s.glyph.layers.append(s.layer)
            return s.layer

        s.glyph.findLayerCreate = create
    lid = s.lid if target == "master" else b.background_layer(s.lid).id
    pending = b._object(lid)
    b.begin_undo("Callback before materialization")
    notify = switch_focus_on_preparation(s)
    with pytest.raises(ValueError, match="Glyph window"):
        b.set_layer_width(lid, 800)
    assert b._object(lid) is pending, "A rejected write published a native layer handle"
    assert not creations and s.layer.mask is None and not any(s.layer.mask_calls)
    assert len(s.calls) == 1 and b._prepared and not b._changed
    assert not b._pending_layer_updates and not s.events
    s.module.flItems = lambda: NS(notifyChangesApplied=notify)
    s.font_window()
    b.set_layer_width(lid, 800)
    b.end_undo()
    assert b._object(lid).advanceWidth == 800 and not b._changed
