# this_file: tests/test_issue106_round25.py
"""Authoritative native lookups and last-boundary refusal regressions."""

from types import SimpleNamespace as NS

import pytest
from test_issue106_round9 import native as native_fixture

from fontlab_glyport.model.fontlab_backend import FontLabBackend


@pytest.fixture
def native(monkeypatch):
    return native_fixture.__wrapped__(monkeypatch)


def native_catalog(native, monkeypatch, size=2):
    counts = {"name": 0, "unicode": 0, "history": 0, "listings": 0}
    rows, objects, names, codes = [], {}, {}, {}
    markers = {}

    class Catalog:
        @property
        def glyphs(self):
            counts["listings"] += 1
            return tuple(rows)

        def __getitem__(self, name):
            return next(row for row in rows if row.name == name)

    for index in range(size):
        identity, name, code = 80000 + index, f"item{index}", 0x41 + index
        row = NS(id=identity, name=name, unicodes=[code])
        rows.append(row)
        markers[identity] = 0

        def history(identity=identity):
            counts["history"] += 1
            return markers[identity]

        glyph = NS(
            id=identity + 10000,
            fgGlyphId=identity,
            name=name,
            isValid=True,
            currentHistoryState=history,
        )
        objects[identity] = glyph
        names[name], codes[code] = glyph, glyph

    def find_name(name):
        counts["name"] += 1
        return names.get(name)

    def find_unicode(code):
        counts["unicode"] += 1
        return codes.get(code)

    native.package.fgPackage = Catalog()
    native.package.findName = find_name
    native.package.findUnicode = find_unicode
    native.package.findFgId = objects.get
    native.package.glyphsCount = size
    monkeypatch.setattr(
        native.backend, "glyphs", FontLabBackend.glyphs.__get__(native.backend)
    )
    return NS(
        rows=rows,
        objects=objects,
        names=names,
        codes=codes,
        markers=markers,
        counts=counts,
    )


@pytest.mark.parametrize("key", ["B", "0042"])
def test_other_glyph_native_rename_overrides_cached_alias(native, monkeypatch, key):
    catalog = native_catalog(native, monkeypatch)
    font = native.font
    original = font.glyphs[key]
    assert original.unicode == "0042"
    alpha = catalog.objects[80000]
    del catalog.names[alpha.name]
    alpha.name = catalog.rows[0].name = key
    catalog.names[key] = alpha
    catalog.markers[80000] += 1  # the cached Beta candidate did not change
    assert font.glyphs[key].unicode == "0041"
    assert font.glyphs[key].name == key
    assert font.glyphForUnicode_("0042") is original


@pytest.mark.parametrize("operation", ["set_glyph_tags", "set_mark"])
def test_metadata_host_refusal_leaves_values_revision_and_history_unchanged(
    native, monkeypatch, operation
):
    from fontlab_glyport.errors import HostUnavailable

    backend = native.backend
    native.glyph.tags = ["original"]
    native.glyph.mark = 7
    before = (
        list(native.glyph.tags),
        native.glyph.mark,
        backend._revision,
        list(native.calls),
        dict(backend._changed),
    )

    def unavailable():
        raise HostUnavailable("injected final host dependency")

    monkeypatch.setattr(backend, "_native", unavailable)
    with pytest.raises(HostUnavailable, match="injected"):
        if operation == "set_glyph_tags":
            backend.set_glyph_tags(native.gid, ("new",))
        else:
            backend.set_mark(native.gid, 32)
    assert (
        native.glyph.tags,
        native.glyph.mark,
        backend._revision,
        native.calls,
        backend._changed,
    ) == before


@pytest.mark.parametrize("owner", ["font", "glyph", "layer", "master"])
def test_existing_lib_conversion_refuses_before_history(native, owner):
    from fontlab_glyport.errors import UnsupportedCapability

    backend = native.backend
    native.package.master = "Regular"
    token, target, attribute = {
        "font": (native.fid, native.package, "packageLib"),
        "glyph": (native.gid, native.glyph, "lib"),
        "layer": (native.lid, native.layer, "lib"),
        "master": (native.mid, native.package, "masterLib"),
    }[owner]
    original = {"opaque": object()}
    setattr(target, attribute, original)
    before = (list(native.calls), backend._revision, dict(backend._prepared))
    with pytest.raises(UnsupportedCapability):
        backend.set_lib(token, {"replacement": True})
    assert getattr(target, attribute) is original
    assert (native.calls, backend._revision, backend._prepared) == before


_LAST_GATES = {
    "set_kerning": "_fontpr",
    "redraw_edit_view": "_native",
    "set_edit_cursor": "_text_slots",
    "open_edit_view": "QtGui",
    "set_edit_glyphs": "flSymbolList",
    "set_font_selection": "FL.fl",
    "add_hint": "_fontpr",
    "set_hint": "_fontpr",
    "remove_hint": "_fontpr",
    "clear_background_layer": "_native",
    "restore_path_grouping": "_native",
    "prepare_collection": "_native",
    "snapshot_collection": "shape.clone",
    "restore_collection": "_native",
    "set_layer_metrics_key": "to_native",
    "set_guide": "QtGui",
    "append_master_guide": None,
    "update_layer_metrics": "_node_hint_survivors",
    "set_master_zone": None,
    "set_glyph_selected": None,
    "set_path_attributes": None,
    "set_anchor_selected": None,
    "remove_component": "_native",
    "remove_guide": "_native",
    "set_lib": "_plain(existing)",
    "set_feature": "_native",
    "set_feature_prefix": "_native",
    "add_axis": "flAxis",
    "remove_axis": "_native",
    "set_axis": "_native",
    "set_master_axes": "_location",
    "add_instance": "flInstance",
    "set_instance": "_native",
    "remove_instance": "_native",
    "set_class": "_fontgate",
    "rename_class": "_native",
    "set_layer_width": "_native",
    "set_node_name": "_native",
    "set_node_position": "QPointF",
    "set_node_smooth": "_native",
    "set_node_connection": "_native",
    "transform_layer": "QtGui",
    "set_anchor_position": "QPointF",
    "set_master_italic_angle": "_native",
    "set_glyph_unicodes": "_native",
    "set_current_master": "font_info",
    "make_node_first": "_shape_of",
    "remove_glyph": "_native",
    "rename_glyph": "_native",
    "set_node_selected": "_object(final)",
    "append_path": "flShape",
    "insert_path": "flShape",
    "append_glyph": "_fontpr",
    "append_component": "_fontpr",
    "remove_path": "_node_hint_survivors",
    "add_anchor": "flPinPoint",
    "set_glyph_tags": "_native",
    "set_mark": "_native",
    "remove_anchor": "_native",
    "set_path_nodes": "_node_hint_survivors",
    "append_guide": "_new_guide",
    "begin_undo": "_native",
    "end_undo": "_native",
}


def configure_last_boundary(native, monkeypatch, operation, refuse):
    """Provide supported predecessors; refuse only the final dependency."""
    import sys
    from copy import deepcopy
    from types import ModuleType

    from test_issue106_round23 import install_path_constructors
    from test_issue106_round24 import write_arguments

    from fontlab_glyport.model import fontlab_backend, metrics_keys

    backend = native.backend
    args = write_arguments(native)[operation]
    kwargs = {}
    package, glyph, layer = native.package, native.glyph, native.layer
    package.master = layer.name = "Regular"
    package.masterLib = {}
    glyph.tags, glyph.mark, layer.mark = ["original"], 7, 3
    layer.activeShape = None
    glyph.activeLayer = layer
    package.axes = [NS(name="Width", tag="wdth", shortName="wd", hidden=False)]
    package.location = lambda name: {}

    class InstanceCopies:
        def __iter__(self):
            return iter(
                deepcopy(
                    [NS(name="Regular", tsn="Regular", exportable=True, location={})]
                )
            )

    package.instances = InstanceCopies()

    class Catalog(dict):
        pass

    package.fgPackage = Catalog(package.fgPackage)
    package.fgPackage.features = NS()
    package.fgPackage.groups = NS(has_key=lambda name: False, asDict=dict)
    package.fgPackage["A"].index = 0
    install_path_constructors(native)
    native.module.flLocation = lambda value: value
    if operation == "add_instance":
        package.axes = []  # the new instance has no axis coordinates
    if operation == "set_guide":
        guide = backend._objects[args[0]]
        guide.centerPoint = NS(x=lambda: 1, y=lambda: 2)
        kwargs = {"x": 40}
    if operation == "clear_background_layer":
        layer.mask = NS(id=50, isValid=True)
    if operation == "snapshot_collection":
        backend._owned_shapes.add(layer.shapes[0].id)
    if operation == "update_layer_metrics":
        layer.metricsLeft = "=A"
    if operation == "set_node_selected":
        backend.node_selected(args[0])  # seed the existing editor observation
    if operation == "end_undo":
        backend._undo_name = "Existing group"
        backend._changed[("glyph", glyph.id)] = glyph

    gate = _LAST_GATES[operation]
    if gate == "QtGui":
        monkeypatch.setattr(fontlab_backend, "_import_qtgui", refuse)
    elif gate == "QPointF":
        monkeypatch.setattr(fontlab_backend, "_qpoint", refuse)
    elif gate == "flSymbolList":
        monkeypatch.setattr(backend, "_text_block", lambda *a: NS())
        native.module.fgSymbol = lambda value: value
        native.module.fgSymbolList = refuse
    elif gate in ("flShape", "flAxis", "flInstance", "flPinPoint"):
        monkeypatch.setattr(native.module, gate, refuse, raising=False)
    elif gate == "_text_slots":
        monkeypatch.setattr(backend, "_text_block", lambda *a: NS())
        monkeypatch.setattr(backend, gate, refuse)
    elif gate == "FL.fl":
        module = ModuleType("FL")

        def missing(name):
            if name == "fl":
                return refuse()
            raise AttributeError(name)

        module.__getattr__ = missing
        monkeypatch.setitem(sys.modules, "FL", module)
        monkeypatch.setattr(backend, "_tool", lambda *a, **kw: {"id": package.fgId})
        native.module.flWorkspace.instance = lambda: NS(
            activeFontPanel=object(), packages=lambda: [package]
        )
    elif gate == "shape.clone":
        monkeypatch.setattr(layer.shapes[0], "clone", refuse)
    elif gate == "to_native":
        monkeypatch.setattr(metrics_keys, "to_native", refuse)
    elif gate == "_plain(existing)":
        original = fontlab_backend._plain

        def convert(value, *args):
            if value is layer.lib:
                return refuse()
            return original(value, *args)

        monkeypatch.setattr(fontlab_backend, "_plain", convert)
    elif gate == "_object(final)":
        original = backend._object
        calls = []

        def final(token):
            calls.append(token)
            return refuse() if len(calls) == 2 else original(token)

        monkeypatch.setattr(backend, "_object", final)
    elif gate:
        monkeypatch.setattr(backend, gate, refuse)
    return args, kwargs


def last_boundary_state(native):
    from test_issue106_round24 import native_write_state

    return (
        native_write_state(native),
        tuple(native.glyph.tags),
        native.glyph.mark,
        native.layer.mark,
        native.glyph.activeLayer,
        native.package.master,
        tuple((a.name, a.tag, a.hidden) for a in native.package.axes),
        tuple((i.name, i.tsn, i.exportable) for i in native.package.instances),
        tuple(getattr(native, "writes", ())),
    )


@pytest.mark.parametrize("operation", _LAST_GATES)
@pytest.mark.parametrize("error_name", ["UnsupportedCapability", "HostUnavailable"])
def test_last_eligibility_refusal_never_writes_native_state_or_history(
    native, monkeypatch, operation, error_name
):
    from fontlab_glyport import errors

    gate = _LAST_GATES[operation]
    error = getattr(errors, error_name) if gate else errors.UnsupportedCapability

    def refuse(*args, **kw):
        raise error("injected LAST eligibility boundary")

    # Independent native doubles reuse package ids; only this test owns its host.
    from weakref import WeakSet

    monkeypatch.setattr(
        "fontlab_glyport.model.fontlab_backend._LIVE_BACKENDS",
        WeakSet([native.backend]),
    )
    args, kwargs = configure_last_boundary(native, monkeypatch, operation, refuse)
    native.writes = []
    for owner in (native.layer, native.glyph, native.package):
        for name in (
            "removeShape",
            "insertShape",
            "removeAllShapes",
            "addShapes",
            "clearAnchors",
            "addAnchor",
            "checkInitHistoryState",
            "changed",
            "update",
        ):
            original = getattr(owner, name, None)
            if original is not None:

                def observe(*a, original=original, name=name, **kw):
                    native.writes.append(name)
                    return original(*a, **kw)

                monkeypatch.setattr(owner, name, observe)
    before = last_boundary_state(native)
    with pytest.raises(error):
        getattr(native.backend, operation)(*args, **kwargs)
    assert last_boundary_state(native) == before, operation


@pytest.mark.parametrize("size", [100, 2000])
@pytest.mark.parametrize("route", ["name", "character", "hex", "unicode"])
def test_authoritative_native_hits_make_constant_hash_and_history_calls(
    native, monkeypatch, size, route
):
    catalog = native_catalog(native, monkeypatch, size)
    font = native.font
    lookup = {
        "name": lambda: font.glyphs["item1"],
        "character": lambda: font.glyphs["B"],
        "hex": lambda: font.glyphs["0042"],
        "unicode": lambda: font.glyphForUnicode_("0042"),
    }[route]
    glyph = lookup()
    catalog.counts.update(dict.fromkeys(catalog.counts, 0))
    for _ in range(10):
        assert lookup() is glyph
    assert catalog.counts == {
        "name": 0 if route == "unicode" else 10,
        "unicode": 0 if route == "name" else 10,
        "history": 20 if route == "unicode" else 10,
        "listings": 0,
    }


def test_authoritative_name_precedes_unicode_alias(native, monkeypatch):
    catalog = native_catalog(native, monkeypatch)
    alpha = catalog.objects[80000]
    del catalog.names[alpha.name]
    alpha.name = catalog.rows[0].name = "0042"
    catalog.names["0042"] = alpha
    assert native.font.glyphs["0042"].unicode == "0041"
    assert native.font.glyphForUnicode_("0042").unicode == "0042"
    assert native.font.glyphs["B"].unicode == "0042"


def test_authoritative_unicode_map_detects_change_to_other_glyph(native, monkeypatch):
    catalog = native_catalog(native, monkeypatch)
    previous = native.font.glyphForUnicode_("0042")
    catalog.rows[0].unicodes = [0x42]
    catalog.codes[0x42] = catalog.objects[80000]
    catalog.markers[80000] += 1
    assert native.font.glyphForUnicode_("0042") is not previous
    assert native.font.glyphs["B"].name == "item0"


def test_new_native_identity_repairs_catalog_once(native, monkeypatch):
    from fontlab_glyport.errors import StaleNativeObject

    catalog = native_catalog(native, monkeypatch)
    previous = native.font.glyphs["item0"]
    catalog.objects[80000].isValid = False
    added = NS(
        id=99000,
        fgGlyphId=90000,
        name="item0",
        isValid=True,
        currentHistoryState=lambda: 1,
    )
    catalog.objects[90000] = catalog.names["item0"] = catalog.codes[0x41] = added
    catalog.rows[0] = NS(id=90000, name="item0", unicodes=[0x41])
    assert native.font.glyphs["item0"].unicode == "0041"
    assert catalog.counts["listings"] == 2
    with pytest.raises(StaleNativeObject):
        _ = previous.name


def test_checkpoint_still_recovers_after_a_prior_clone_changed_the_layer(
    native, monkeypatch
):
    font, backend = native.font, native.backend
    layer = font.glyphs[0].layers[0]
    with font.undo_group("Partial checkpoint"):
        retained = layer.paths[0].nodes[0]
        retained.position = (33, 44)
        first = native.layer.shapes[0]
        second = type(first)()
        native.layer.shapes.append(second)
        backend._owned_shapes.add(second.id)
        before = tuple(native.layer.shapes)

        def refuse():
            raise RuntimeError("second clone failed")

        monkeypatch.setattr(second, "clone", refuse)
        with pytest.raises(RuntimeError, match="second clone failed"):
            backend.snapshot_collection(layer.id)
        assert tuple(native.layer.shapes) == before
        assert retained.position == (33, 44)
        retained.position = (55, 66)
        assert first.contours[0].nodes()[0].x == 55
