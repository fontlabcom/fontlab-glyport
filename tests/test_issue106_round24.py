# this_file: tests/test_issue106_round24.py
"""Constant-cost alias hits and mutation-free native eligibility failures."""

import pytest

from fontlab_glyport.model.backend import GlyphInfo
from fontlab_glyport.model.indexes import IndexedSequence


@pytest.mark.parametrize("size", [100, 2000])
@pytest.mark.parametrize("key", ["0041", "A"])
def test_unchanged_alias_hits_check_only_one_native_marker(size, key):
    calls = []
    records = [GlyphInfo(str(i), f"g{i}", (f"{65 + i:04X}",)) for i in range(size)]
    sequence = IndexedSequence(
        lambda: 0,
        lambda: records,
        lambda token: token,
        keys=lambda row: (
            row.name,
            *row.unicodes,
            *(chr(int(code, 16)) for code in row.unicodes),
        ),
    )

    def marker(token):
        calls.append(token)
        return 0

    sequence._validator = (marker, lambda token: records[int(token)])
    assert sequence.token_for_key(key) == "0"
    calls.clear()
    for _ in range(10):
        assert sequence.token_for_key(key) == "0"
    assert len(calls) == 10


@pytest.fixture
def native(monkeypatch):
    from test_issue106_round9 import native as native_fixture

    return native_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize("operation", ["add_hint", "set_hint", "remove_hint"])
def test_missing_hint_tools_refuse_before_creating_layer_or_history(
    native, monkeypatch, operation
):
    from fontlab_glyport.errors import HostUnavailable
    from fontlab_glyport.model.backend import HintInfo
    from fontlab_glyport.model.fontlab_backend import _PendingLayer

    backend = native.backend
    pending = _PendingLayer("Regular")
    backend._objects[native.lid] = pending
    events = []

    def create(name):
        events.append("created layer")
        return native.layer

    def unavailable():
        raise HostUnavailable("injected fontpr unavailable")

    native.glyph.findLayerCreate = create
    monkeypatch.setattr(backend, "_fontpr", unavailable)
    before = list(native.calls)
    arguments = {
        "add_hint": (HintInfo(True, 10, 20),),
        "set_hint": (0, {"position": 10}),
        "remove_hint": (0,),
    }
    with pytest.raises(HostUnavailable, match="injected"):
        getattr(backend, operation)(native.lid, *arguments[operation])
    assert events == []
    assert native.calls == before
    assert backend._objects[native.lid] is pending


@pytest.mark.parametrize("operation", ["remove_path", "set_path_nodes", "bulk_paths"])
def test_guideline_conversion_refusal_precedes_any_history_or_clone(
    native, monkeypatch, operation
):
    from fontlab_glyport.errors import UnsupportedCapability

    backend = native.backend
    layer = native.font.glyphs[0].layers[0]
    path = layer.paths[0]
    info = path._data()
    original = native.layer.shapes[0]
    native.layer.guidelines = [object()]

    def refuse(raw):
        raise UnsupportedCapability("injected guideline conversion")

    monkeypatch.setattr(backend, "_guide_line", refuse)
    before = list(native.calls)
    with pytest.raises(UnsupportedCapability, match="injected"):
        if operation == "remove_path":
            backend.remove_path(layer.id, path.id)
        elif operation == "set_path_nodes":
            backend.set_path_nodes(path.id, (), False)
        else:
            layer.paths = []
    assert native.calls == before
    assert native.layer.shapes == [original]
    assert [n.x for contour in original.contours for n in contour.nodes()] == [10, 20]
    assert backend._prepared == {}
    assert path._data() == info


@pytest.mark.parametrize(
    "operation",
    [
        "append_glyph",
        "set_glyph_unicodes",
        "set_class",
        "set_guide",
        "set_anchor_position",
        "open_edit_view",
    ],
)
def test_late_dependency_refusal_keeps_native_state_and_history_unchanged(
    native, monkeypatch, operation
):
    from types import SimpleNamespace as NS

    from fontlab_glyport.errors import HostUnavailable

    backend = native.backend
    events = []

    def refuse(*args, **kw):
        raise HostUnavailable("injected eligibility refusal")

    def called(*args, **kw):
        events.append((args, kw))

    if operation == "append_glyph":
        monkeypatch.setattr(backend, "_fontpr", refuse)
        invoke = lambda: backend.append_glyph(native.fid, "newGlyph")
    elif operation == "set_glyph_unicodes":
        monkeypatch.setattr(backend, "_fontgate_font", refuse)
        invoke = lambda: backend.set_glyph_unicodes(native.gid, ("0042",))
    elif operation == "set_class":
        monkeypatch.setattr(
            backend, "_ot_groups", lambda *a: (native.package, NS(asDict=dict))
        )
        monkeypatch.setattr(backend, "_fontgate", refuse)
        invoke = lambda: backend.set_class(native.fid, "Letters", ["A"])
    elif operation == "set_guide":
        guide = NS(
            id=555,
            isValid=True,
            centerPoint=NS(x=lambda: 1, y=lambda: 2),
            applyTransform=called,
        )
        token = backend._register((native.fid, "guide", 555), guide, native.lid)
        monkeypatch.setattr(
            "fontlab_glyport.model.fontlab_backend._import_qtgui", refuse
        )
        invoke = lambda: backend.set_guide(token, x=4)
    elif operation == "set_anchor_position":
        anchor = NS(id=555, isValid=True, point="original")
        token = backend._register((native.fid, "anchor", 555), anchor, native.lid)
        monkeypatch.setattr("fontlab_glyport.model.fontlab_backend._qpoint", refuse)
        invoke = lambda: backend.set_anchor_position(token, 4, 5)
    else:
        monkeypatch.setattr(backend, "_tool", called)
        monkeypatch.setattr(
            "fontlab_glyport.model.fontlab_backend._import_qtgui", refuse
        )
        invoke = lambda: backend.open_edit_view(native.fid)
    before = list(native.calls)
    original = native.layer.shapes[0]
    with pytest.raises(HostUnavailable, match="injected"):
        invoke()
    assert events == []
    assert native.calls == before
    assert native.layer.shapes == [original]
    assert backend._prepared == {}


# Explicit public write-entry inventory. Delegating entry points are included:
# each must refuse before native/history changes, even when its leaf is shared.
_WRITE_GATES = {
    "set_kerning": "_tool_font",
    "redraw_edit_view": "_native",
    "set_edit_cursor": "_text_block",
    "open_edit_view": "_tool_font",
    "set_edit_glyphs": "_text_block",
    "set_font_selection": "_tool_font",
    "add_hint": "_resolve_tool",
    "set_hint": "_resolve_tool",
    "remove_hint": "_resolve_tool",
    "clear_background_layer": "_object",
    "restore_path_grouping": "_object",
    "prepare_collection": "_native",
    "snapshot_collection": "_object",
    "restore_collection": "_native",
    "set_layer_metrics_key": "_object",
    "set_guide": "_guide_line",
    "append_master_guide": "_object",
    "update_layer_metrics": "_object",
    "set_master_zone": None,
    "set_glyph_selected": None,
    "set_path_attributes": None,
    "set_anchor_selected": "_object",
    "remove_component": "_object",
    "remove_guide": "_object",
    "set_lib": "_object",
    "set_feature": "_font_write",
    "set_feature_prefix": "_font_write",
    "add_axis": "_font_write",
    "remove_axis": "_font_write",
    "set_axis": "_font_write",
    "set_master_axes": "_font_write",
    "add_instance": "_font_write",
    "set_instance": "_font_write",
    "remove_instance": "_font_write",
    "set_class": "_ot_groups",
    "rename_class": "_ot_groups",
    "set_layer_width": "_object",
    "set_node_name": "_object",
    "set_node_position": "_object",
    "set_node_smooth": "_object",
    "set_node_connection": "_check_connection",
    "transform_layer": "_object",
    "set_anchor_position": "_object",
    "set_master_italic_angle": "_object",
    "set_glyph_unicodes": "_fontgate_font",
    "set_current_master": "_object",
    "make_node_first": "_object",
    "remove_glyph": "_object",
    "rename_glyph": "_object",
    "set_node_selected": "_object",
    "append_path": "_native",
    "insert_path": "_native",
    "append_glyph": "_resolve_tool",
    "append_component": "_fontpr",
    "remove_path": "_node_hint_survivors",
    "add_anchor": "_object",
    "set_glyph_tags": "_object",
    "set_mark": "_object",
    "remove_anchor": "_object",
    "set_path_nodes": "_node_hint_survivors",
    "append_guide": "_new_guide",
    "begin_undo": "_native",
    "end_undo": "_native",
}


def write_arguments(native):
    from types import SimpleNamespace as NS

    from fontlab_glyport.model.backend import (
        AnchorInfo,
        AxisInfo,
        ComponentInfo,
        GuideInfo,
        HintInfo,
        InstanceInfo,
        PathInfo,
    )

    b = native.backend
    path = native.font.glyphs[0].layers[0].paths[0]
    node = path.nodes[0]
    guide = b._register(
        (native.fid, "guide", 999), NS(id=999, isValid=True), native.lid
    )
    anchor = b._register(
        (native.fid, "anchor", 998), NS(id=998, isValid=True), native.lid
    )
    component = b._register(
        (native.fid, "component", 997), NS(id=997, isValid=True), native.lid
    )
    f, m, g, l, p, n = native.fid, native.mid, native.gid, native.lid, path.id, node.id
    axis = AxisInfo("", "Weight", "wght")
    hint = HintInfo(True, 10, 20)
    return {
        "set_kerning": (f, m, "A", "A", 10),
        "redraw_edit_view": (f,),
        "set_edit_cursor": (f, 0),
        "open_edit_view": (f,),
        "set_edit_glyphs": (f, (("A",),)),
        "set_font_selection": (f, (g,)),
        "add_hint": (l, hint),
        "set_hint": (l, 0, {"position": 10}),
        "remove_hint": (l, 0),
        "clear_background_layer": (l,),
        "restore_path_grouping": (l, (2,)),
        "prepare_collection": (l, "paths"),
        "snapshot_collection": (l,),
        "restore_collection": (
            l,
            (native.layer, tuple(native.layer.shapes), (), (), {}),
        ),
        "set_layer_metrics_key": (l, "left", "=A"),
        "set_guide": (guide,),
        "append_master_guide": (m, GuideInfo("", 0, 0)),
        "update_layer_metrics": (l,),
        "set_master_zone": (m, 0, 0, 10),
        "set_glyph_selected": (f, g, True),
        "set_path_attributes": (p, {}),
        "set_anchor_selected": (anchor, True),
        "remove_component": (l, component),
        "remove_guide": (l, guide),
        "set_lib": (l, {"hello": "world"}),
        "set_feature": (f, "liga", "sub A A by A;"),
        "set_feature_prefix": (f, "# prefix"),
        "add_axis": (f, axis),
        "remove_axis": (f, 0),
        "set_axis": (f, 0, axis),
        "set_master_axes": (m, (100,)),
        "add_instance": (f, InstanceInfo("", "Regular")),
        "set_instance": (f, 0, {"name": "Bold"}),
        "remove_instance": (f, 0),
        "set_class": (f, "Letters", ["A"]),
        "rename_class": (f, "Letters", "Uppercase"),
        "set_layer_width": (l, 600),
        "set_node_name": (n, "corner"),
        "set_node_position": (n, 10, 20),
        "set_node_smooth": (n, True),
        "set_node_connection": (n, 100),
        "transform_layer": (l, (1, 0, 0, 1, 0, 0)),
        "set_anchor_position": (anchor, 10, 20),
        "set_master_italic_angle": (m, 12),
        "set_glyph_unicodes": (g, ("0042",)),
        "set_current_master": (f, m),
        "make_node_first": (n,),
        "remove_glyph": (f, g),
        "rename_glyph": (f, g, "newName"),
        "set_node_selected": (n, True),
        "append_path": (l, PathInfo("", ())),
        "insert_path": (l, 0, PathInfo("", ())),
        "append_glyph": (f, "newName"),
        "append_component": (l, ComponentInfo("", "A", (1, 0, 0, 1, 0, 0))),
        "remove_path": (l, p),
        "add_anchor": (l, AnchorInfo("", "top", 0, 0)),
        "set_glyph_tags": (g, ("tag",)),
        "set_mark": (l, 20),
        "remove_anchor": (l, anchor),
        "set_path_nodes": (p, (), False),
        "append_guide": (l, GuideInfo("", 0, 0)),
        "begin_undo": ("Edit",),
        "end_undo": (),
    }


def native_write_state(native):
    b = native.backend
    return (
        tuple(
            (
                s.id,
                tuple(
                    (
                        c.id,
                        tuple(
                            (
                                n.id,
                                n.x,
                                n.y,
                                n.smooth,
                                n.selected,
                                getattr(n, "name", None),
                            )
                            for n in c.nodes()
                        ),
                    )
                    for c in s.contours
                ),
            )
            for s in native.layer.shapes
        ),
        tuple(native.layer.anchors),
        tuple(native.layer.guidelines),
        native.layer.advanceWidth,
        dict(native.layer.lib),
        native.glyph.name,
        tuple(native.glyph.fgGlyph.unicodes),
        tuple(native.calls),
        dict(b._changed),
        dict(b._prepared),
        b._undo_name,
        dict(b._objects),
        dict(b._object_keys),
        dict(b._parents),
        b._revision,
        tuple(getattr(native, "mutation_events", ())),
        dict(b._keys),
        dict(b._selection_flags),
        set(b._owned_shapes),
        dict(b._history_aliases),
    )


@pytest.mark.parametrize("operation", _WRITE_GATES)
@pytest.mark.parametrize("error_name", ["UnsupportedCapability", "HostUnavailable"])
def test_backend_write_eligibility_refusal_is_mutation_and_history_free(
    native, monkeypatch, operation, error_name
):
    from fontlab_glyport import errors
    from fontlab_glyport.model import fontlab_backend

    arguments = write_arguments(native)[operation]
    native.mutation_events = []
    for owner in (native.layer, native.glyph, native.package):
        for method in (
            "removeShape",
            "insertShape",
            "removeAllShapes",
            "addShapes",
            "clearAnchors",
            "addAnchor",
            "findLayerCreate",
            "removeLayer",
            "deleteGlyph",
            "renameGlyph",
            "setMaster",
            "checkInitHistoryState",
            "changed",
            "update",
        ):
            original = getattr(owner, method, None)
            if original is None:
                continue

            def observe(*args, original=original, method=method, **kw):
                native.mutation_events.append(method)
                return original(*args, **kw)

            monkeypatch.setattr(owner, method, observe)
    backend = native.backend
    if operation == "end_undo":
        backend._undo_name = "Existing group"
        backend._changed[("glyph", native.glyph.id)] = native.glyph
    # A native transform double isolates eligibility from unavailable PythonQt.
    monkeypatch.setattr(
        fontlab_backend,
        "_import_qtgui",
        lambda: type("Qt", (), {"QTransform": lambda *a: object()}),
    )
    gate = _WRITE_GATES[operation]
    error = getattr(errors, error_name) if gate else errors.UnsupportedCapability

    def refuse(*args, **kw):
        raise error("injected eligibility")

    if gate:
        monkeypatch.setattr(backend, gate, refuse)
    before = native_write_state(native)
    with pytest.raises(error):
        getattr(backend, operation)(*arguments)
    assert native_write_state(native) == before, operation


@pytest.mark.parametrize("operation", ["set_mark", "set_master_italic_angle"])
def test_scalar_coercion_refuses_before_history_or_layer_materialization(
    native, operation
):
    from fontlab_glyport.errors import HostUnavailable
    from fontlab_glyport.model.fontlab_backend import _PendingLayer

    class UnavailableValue:
        def __int__(self):
            raise HostUnavailable("injected conversion")

        __float__ = __int__

    native.package.master = "Regular"
    pending = _PendingLayer("Regular")
    created = []
    native.glyph.findLayerCreate = lambda name: created.append(name) or native.layer
    if operation == "set_mark":
        native.backend._objects[native.lid] = pending
        token = native.lid
    else:
        token = native.mid
    before = list(native.calls)
    with pytest.raises(HostUnavailable, match="injected"):
        getattr(native.backend, operation)(token, UnavailableValue())
    assert native.calls == before
    assert created == []


@pytest.mark.parametrize("operation", ["add_hint", "append_glyph", "append_component"])
def test_missing_tool_member_refuses_before_pending_layer_or_history(
    native, monkeypatch, operation
):
    from types import SimpleNamespace as NS

    from fontlab_glyport.errors import UnsupportedCapability
    from fontlab_glyport.model.backend import ComponentInfo, HintInfo
    from fontlab_glyport.model.fontlab_backend import _PendingLayer

    backend = native.backend
    pending = _PendingLayer("Regular")
    backend._objects[native.lid] = pending
    events = []
    native.glyph.findLayerCreate = lambda name: events.append("create") or native.layer
    native.package.findNewName = lambda name: name
    native.layer.name = "Regular"
    monkeypatch.setattr(backend, "_fontpr", lambda: NS(Error=RuntimeError))
    before = list(native.calls)
    arguments = {
        "add_hint": (native.lid, HintInfo(True, 10, 20)),
        "append_glyph": (native.fid, "newGlyph"),
        "append_component": (native.lid, ComponentInfo("", "A", (1, 0, 0, 1, 0, 0))),
    }
    with pytest.raises(UnsupportedCapability, match="unavailable"):
        getattr(backend, operation)(*arguments[operation])
    assert events == []
    assert native.calls == before
    assert backend._objects[native.lid] is pending


@pytest.mark.parametrize("size", [100, 2000])
@pytest.mark.parametrize("character", [False, True])
def test_native_alias_hits_keep_history_and_listing_cost_constant(
    native, monkeypatch, size, character
):
    from types import SimpleNamespace as NS

    counts = {"history": 0, "listings": 0}

    def history():
        counts["history"] += 1
        return 4

    records = []
    for index in range(size):
        code = 0x400 + index
        glyph = NS(
            id=70000 + index,
            name=f"item{index}",
            isValid=True,
            currentHistoryState=history,
        )
        token = native.backend._register(
            (native.fid, "glyph", glyph.id), glyph, native.fid
        )
        native.package.fgPackage[glyph.name] = NS(unicodes=[code])
        records.append(GlyphInfo(token, glyph.name, (f"{code:04X}",)))

    def listing(font_id):
        counts["listings"] += 1
        return tuple(records)

    monkeypatch.setattr(native.backend, "glyphs", listing)
    key = chr(0x400) if character else "0400"
    glyph = native.font.glyphs[key]
    counts["history"] = 0
    for _ in range(10):
        assert native.font.glyphs[key] is glyph
    assert counts == {"history": 10, "listings": 1}
