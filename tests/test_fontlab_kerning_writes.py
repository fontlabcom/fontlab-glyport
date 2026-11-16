# this_file: tests/test_fontlab_kerning_writes.py
"""Real FontLabBackend tool schemas, class cache updates and native failure edges."""

from collections import Counter
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest
from test_kerning_group_cache import native  # noqa: F401

from fontlab_glyport.errors import (
    NativeOperationError,
    StaleNativeObject,
    UnsupportedCapability,
)
from fontlab_glyport.model.fontlab_kerning import SHARED_CLASSES


@pytest.fixture
def tools(native, monkeypatch):  # noqa: F811
    writes, reads, pairs = [], Counter(), {}
    fault = NS(name=None, remaining=0)

    class ToolError(Exception):
        pass

    for package in native.packages:
        package.packageLib = {}
        package.fgPackage.groups = {}
        for master in package.masters:
            first, second, _ = native.data[package.fgId, master]
            pairs[package.fgId, master] = {
                ("@" + first["name"], "@" + second["name"]): -45,
                ("g0", "g1"): -10,
            }

    def key(font_id, master_name=None):
        package = next(p for p in native.packages if p.fgId == font_id)
        return font_id, master_name or package.active

    def list_classes(font_id, master_name=None):
        index = key(font_id, master_name)
        reads["classes", *index] += 1
        # MCP exposes marks but not the underlying native mainGlyphName.
        return {
            "classes": [
                {
                    k: deepcopy(v)
                    for k, v in group.items()
                    if not k.startswith("__native_")
                }
                for group in native.data[index]
            ]
        }

    def list_pairs(font_id, master_name, offset, limit):
        index = key(font_id, master_name)
        reads["pairs", *index] += 1
        rows = [
            {"left": left, "right": right, "value": value}
            for (left, right), value in pairs[index].items()
        ]
        return {"pairs": rows[offset : offset + limit], "total_pairs": len(rows)}

    def write(name, font_id, master_name, **arguments):
        if fault.name == name and fault.remaining == 0:
            raise ToolError("injected native failure")
        if fault.name == name:
            fault.remaining -= 1
        writes.append((name, font_id, master_name, arguments))
        package = next(p for p in native.packages if p.fgId == font_id)
        index = key(font_id, master_name)
        if name == "set_kerning_class":
            groups = native.data[index]
            group = next(
                (g for g in groups if g["name"] == arguments["class_name"]), None
            )
            if group is None:
                group = {
                    "name": arguments["class_name"],
                    "left": arguments["left"],
                    "right": arguments["right"],
                    "mark": 29,
                }
                groups.append(group)
            group["glyph_names"] = arguments["glyph_names"]
        elif name == "delete_kerning_class":
            assert not any(
                "@" + arguments["class_name"] in pair for pair in pairs[index]
            ), "deletion must not flatten referenced pairs"
            native.data[index] = [
                g for g in native.data[index] if g["name"] != arguments["class_name"]
            ]
        elif name == "delete_all_kerning_pairs":
            pairs[index] = {}
        elif name == "set_kerning_pair":
            pairs[index][arguments["left"], arguments["right"]] = arguments["value"]
        elif name == "delete_kerning_pair":
            del pairs[index][arguments["left"], arguments["right"]]
        if name.endswith("kerning_class") and package.packageLib.get(SHARED_CLASSES):
            for master in package.masters:
                native.data[font_id, master] = deepcopy(native.data[index])
        package.history += 1
        return {"status": "ok"}

    api = NS(
        Error=ToolError,
        list_kerning_classes=list_classes,
        list_kerning_pairs=list_pairs,
    )
    for name in (
        "set_kerning_class",
        "delete_kerning_class",
        "delete_all_kerning_pairs",
        "set_kerning_pair",
        "delete_kerning_pair",
    ):
        setattr(api, name, lambda _name=name, **arguments: write(_name, **arguments))
    monkeypatch.setattr(native.backend, "_fontpr", lambda: api)
    return NS(
        **vars(native), api=api, writes=writes, reads=reads, pairs=pairs, fault=fault
    )


def test_live_group_changes_every_master_preserve_pairs_refs_and_other_font(tools):
    font, glyph = tools.fonts[0], tools.glyphs[0][1]
    pairs_before = deepcopy(tools.pairs)
    other_before = deepcopy({k: v for k, v in tools.data.items() if k[0] == 120})
    assert glyph.leftKerningGroup == "10_Regular_second"
    glyph.leftKerningGroup = "replacement"
    for master in font.masters:
        tools.backend.set_current_master(font.id, master.id)
        assert glyph.leftKerningGroup == "replacement"
        assert glyph.rightKerningGroup == "10_" + master.name + "_first"
        groups = tools.data[110, master.name]
        old = next(g for g in groups if g["name"].endswith("_second"))
        assert old["glyph_names"] == [f"g{i}" for i in range(47) if i != 1]
    assert tools.pairs == pairs_before
    assert {k: v for k, v in tools.data.items() if k[0] == 120} == other_before
    assert tools.notifications == [], (
        "native tools own history without extra notifications"
    )


def test_many_group_resets_reuse_snapshot_no_glyph_scan_and_keep_pair_keys(tools):
    # Remove the fixture-only ambiguous two-sided overlap before testing a reset.
    for index in tools.data:
        tools.data[index] = tools.data[index][:2]
    before_pairs = deepcopy(tools.pairs)
    font = tools.fonts[0]
    for glyph in tools.glyphs[0]:
        glyph.leftKerningGroup = None
        glyph.rightKerningGroup = None
    assert tools.reads == {
        ("classes", 110, "Regular"): 1,
        ("classes", 110, "Bold"): 1,
        ("pairs", 110, "Regular"): 1,
        ("pairs", 110, "Bold"): 1,
    }
    assert tools.pairs == before_pairs
    for master in font.masters:
        assert all(not g["glyph_names"] for g in tools.data[110, master.name])
        font.kerning[master.id] = {}
        assert tools.data[110, master.name] == []
        assert tools.pairs[110, master.name] == {}
    count = len(tools.writes)
    for glyph in tools.glyphs[0]:
        glyph.leftKerningGroup = None
        glyph.rightKerningGroup = None
    for master in font.masters:
        font.kerning[master.id] = {}
    assert len(tools.writes) == count, "repeating an empty reset performs no writes"


@pytest.mark.parametrize("missing", ["set_kerning_class", "delete_kerning_class"])
def test_missing_group_tool_refuses_before_first_mutation(tools, missing):
    for index in tools.data:
        tools.data[index] = [
            {"name": "single", "glyph_names": ["g1"], "left": True, "right": False}
        ]
    delattr(tools.api, missing)
    before = deepcopy(tools.data)
    with pytest.raises(UnsupportedCapability):
        tools.glyphs[0][1].rightKerningGroup = "new"
    assert tools.writes == [] and tools.data == before


def test_later_master_conflict_refuses_every_master_before_mutation(tools):
    tools.data[110, "Bold"] = [
        {"name": "new", "glyph_names": ["g2"], "left": True, "right": False}
    ]
    with pytest.raises(UnsupportedCapability):
        tools.glyphs[0][1].leftKerningGroup = "new"
    assert tools.writes == []


def test_native_error_keeps_partial_native_history_invalidates_cache_then_retry(tools):
    glyph = tools.glyphs[0][1]
    tools.fault.name, tools.fault.remaining = "set_kerning_class", 1
    with pytest.raises(NativeOperationError, match="injected"):
        glyph.leftKerningGroup = None
    assert len(tools.writes) == 1
    assert tools.fonts[0].id not in tools.backend._kerning_snapshots
    tools.fault.name = None
    glyph.leftKerningGroup = None
    assert all(
        "g1" not in g["glyph_names"]
        for master in ("Regular", "Bold")
        for g in tools.data[110, master]
        if g["right"]
    )
    assert tools.reads["classes", 110, "Regular"] == 2


def test_native_history_change_refreshes_writer_snapshot(tools):
    glyph = tools.glyphs[0][1]
    glyph.leftKerningGroup = None
    tools.data[110, "Bold"][1]["glyph_names"].append("g1")
    tools.packages[0].history += 1
    glyph.leftKerningGroup = None
    assert "g1" not in tools.data[110, "Bold"][1]["glyph_names"]
    assert tools.reads["classes", 110, "Bold"] == 2


@pytest.mark.parametrize("matching", [False, True])
def test_shared_class_writes_refuse_without_complete_native_metadata(tools, matching):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    package.packageLib[SHARED_CLASSES] = True
    if matching:
        tools.data[110, "Bold"] = deepcopy(tools.data[110, "Regular"])
    before = deepcopy(tools.data)
    revision = tools.backend._revision
    with pytest.raises(UnsupportedCapability, match="metadata"):
        glyph.leftKerningGroup = None
    assert tools.writes == [] and tools.data == before
    assert tools.backend._revision == revision


def test_foreign_stale_glyph_master_and_unregistered_font_refuse_before_tools(tools):
    backend, font, foreign = tools.backend, tools.fonts[0], tools.glyphs[1][1]
    with pytest.raises(ValueError):
        backend.set_kerning_group(font.id, foreign.id, "left", None)
    with pytest.raises(ValueError):
        font.kerning[tools.fonts[1].masters[0].id] = {}
    glyph = tools.glyphs[0][1]
    backend._objects[glyph.id].isValid = False
    with pytest.raises(StaleNativeObject):
        glyph.leftKerningGroup = None
    backend._owned_fonts[tools.packages[0].id] = tools.packages[0].fgPackage
    with pytest.raises(UnsupportedCapability):
        font.kerning[font.masters[0].id] = {}
    assert tools.writes == []


def test_nonempty_master_replacement_writes_resolved_names_and_native_class_keys(
    tools, monkeypatch
):
    backend, font = tools.backend, tools.fonts[0]
    glyphs = tuple(backend.glyph_info(g.id) for g in tools.glyphs[0])
    monkeypatch.setattr(backend, "glyphs", lambda font_id: glyphs)
    mapping = font.kerning
    master = font.masters[0].id
    other = deepcopy(tools.pairs[110, "Bold"])
    mapping[master] = {
        glyphs[0].id: {glyphs[1].id: -24},
        "@MMK_L_10_Regular_first": {"@MMK_R_10_Regular_second": -92},
    }
    assert tools.pairs[110, "Regular"] == {
        ("g0", "g1"): -24,
        ("@10_Regular_first", "@10_Regular_second"): -92,
    }
    assert tools.pairs[110, "Bold"] == other
    assert mapping[master][glyphs[0].id][glyphs[1].id] == -24
    count = len(tools.writes)
    mapping[master] = mapping[master]
    assert len(tools.writes) == count


def test_replacement_resolves_cleanup_tool_before_deleting_pairs(tools):
    font = tools.fonts[0]
    for index in tools.data:
        tools.data[index] = [
            {"name": "empty", "glyph_names": [], "left": True, "right": False}
        ]
    del tools.api.delete_kerning_class
    before = deepcopy(tools.pairs)
    with pytest.raises(UnsupportedCapability):
        font.kerning[font.masters[0].id] = {}
    assert tools.writes == [] and tools.pairs == before


def test_native_pair_failure_before_mutation_invalidates_snapshot_for_retry(tools):
    font = tools.fonts[0]
    tools.fault.name = "delete_all_kerning_pairs"
    before = deepcopy(tools.pairs)
    with pytest.raises(NativeOperationError):
        font.kerning[font.masters[0].id] = {}
    assert tools.writes == [] and tools.pairs == before
    assert font.id not in tools.backend._kerning_snapshots
    tools.fault.name = None
    font.kerning[font.masters[0].id] = {}
    assert tools.pairs[110, "Regular"] == {}
    assert tools.pairs[110, "Bold"] == before[110, "Bold"]


def test_opentype_name_collision_is_refused_before_native_tools(tools):
    tools.packages[0].fgPackage.groups = {"new": NS(isFeaGroup=lambda: True)}
    # Native fgGroup is iterable; the backend reads only the matching name here.
    tools.packages[0].fgPackage.groups["new"] = type(
        "Class", (list,), {"isFeaGroup": lambda self: True}
    )(["g2"])
    with pytest.raises(UnsupportedCapability):
        tools.glyphs[0][1].leftKerningGroup = "new"
    assert tools.writes == []


def test_pair_api_write_invalidates_replacement_cache_even_without_package_history(
    tools, monkeypatch
):
    backend, font = tools.backend, tools.fonts[0]
    monkeypatch.setattr(tools.packages[0], "currentHistoryState", lambda: 0)
    glyphs = tuple(backend.glyph_info(g.id) for g in tools.glyphs[0])
    monkeypatch.setattr(backend, "glyphs", lambda font_id: glyphs)
    tools.glyphs[0][1].leftKerningGroup = None  # warm the writer cache
    master = font.masters[0].id
    original = font.kerning[master]
    font.setKerningForPair(master, "g0", "g1", -77)
    font.kerning[master] = original
    assert tools.pairs[110, "Regular"]["g0", "g1"] == -10


def test_shared_pair_clear_keeps_referenced_classes_then_refuses_class_cleanup(tools):
    package, font = tools.packages[0], tools.fonts[0]
    package.packageLib[SHARED_CLASSES] = True
    empty = [{"name": "empty", "glyph_names": [], "left": True, "right": False}]
    for master in package.masters:
        tools.data[110, master] = deepcopy(empty)
        tools.pairs[110, master] = {("@empty", "g1"): -30}
    regular, bold = font.masters
    font.kerning[regular.id] = {}
    assert tools.data[110, "Regular"] == tools.data[110, "Bold"] == empty
    assert tools.pairs[110, "Bold"] == {("@empty", "g1"): -30}
    before, pairs = deepcopy(tools.data), deepcopy(tools.pairs)
    tools.writes.clear()
    with pytest.raises(UnsupportedCapability, match="metadata"):
        font.kerning[bold.id] = {}
    assert tools.writes == [] and tools.data == before and tools.pairs == pairs


def test_removed_master_without_history_change_is_not_reused_by_group_writer(
    tools, monkeypatch
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    glyph.leftKerningGroup = None
    tools.writes.clear()
    package.masters = ("Regular",)
    glyph.rightKerningGroup = None
    assert [master for _, _, master, _ in tools.writes] == ["Regular"]


@pytest.mark.parametrize("field", ["mark", "__native_mainGlyphName"])
@pytest.mark.parametrize("group_index", [0, 1])
def test_shared_metadata_differences_preserved_or_refused_before_any_write(
    tools, field, group_index
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    package.packageLib[SHARED_CLASSES] = True
    for group in tools.data[110, "Regular"]:
        group.update(mark=10, __native_mainGlyphName="g0")
    tools.data[110, "Bold"] = deepcopy(tools.data[110, "Regular"])
    tools.data[110, "Bold"][group_index][field] = 20 if field == "mark" else "g2"
    before = deepcopy(tools.data)
    try:
        glyph.leftKerningGroup = None
    except UnsupportedCapability:
        assert tools.writes == [] and tools.data == before
        return
    for master in package.masters:
        expected = deepcopy(before[110, master])
        expected[1]["glyph_names"] = [
            n for n in expected[1]["glyph_names"] if n != "g1"
        ]
        assert tools.data[110, master] == expected, (
            "a single membership edit must preserve every master's native metadata"
        )


def test_matching_shared_rich_metadata_refuses_without_claiming_full_equality(tools):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    package.packageLib[SHARED_CLASSES] = True
    for group in tools.data[110, "Regular"]:
        group.update(mark=17, __native_mainGlyphName="g0")
    tools.data[110, "Bold"] = deepcopy(tools.data[110, "Regular"])
    before = deepcopy(tools.data)
    with pytest.raises(UnsupportedCapability, match="metadata"):
        glyph.leftKerningGroup = None
    assert tools.writes == [] and tools.data == before


def test_independent_master_writes_preserve_distinct_marks_and_raw_references(tools):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    for index, master in enumerate(package.masters):
        for group in tools.data[110, master]:
            group.update(mark=10 + index, __native_mainGlyphName="g" + str(index))
    before = deepcopy(tools.data)
    glyph.leftKerningGroup = None
    for master in package.masters:
        expected = deepcopy(before[110, master])
        expected[1]["glyph_names"] = [
            n for n in expected[1]["glyph_names"] if n != "g1"
        ]
        assert tools.data[110, master] == expected
    assert {k: v for k, v in tools.data.items() if k[0] == 120} == {
        k: v for k, v in before.items() if k[0] == 120
    }


def test_shared_pair_clear_cleanup_preserves_or_preflights_unrelated_metadata(tools):
    package, font = tools.packages[0], tools.fonts[0]
    package.packageLib[SHARED_CLASSES] = True
    tools.data[110, "Regular"].append(
        {
            "name": "empty",
            "glyph_names": [],
            "left": True,
            "right": False,
            "mark": 31,
            "__native_mainGlyphName": "",
        }
    )
    for group in tools.data[110, "Regular"]:
        group.setdefault("mark", 10)
        group.setdefault("__native_mainGlyphName", "g0")
    tools.data[110, "Bold"] = deepcopy(tools.data[110, "Regular"])
    tools.data[110, "Bold"][0]["mark"] = 20
    before, pairs = deepcopy(tools.data), deepcopy(tools.pairs)
    try:
        font.kerning[font.masters[0].id] = {}
    except UnsupportedCapability:
        assert tools.writes == [] and tools.data == before and tools.pairs == pairs
        return
    for master in package.masters:
        assert tools.data[110, master] == [
            g for g in before[110, master] if g["name"] != "empty"
        ]
    assert tools.pairs[110, "Regular"] == {}
    assert tools.pairs[110, "Bold"] == pairs[110, "Bold"]


def test_shared_pair_only_replacement_preserves_divergent_metadata_and_class_cache(
    tools, monkeypatch
):
    backend, font, package = tools.backend, tools.fonts[0], tools.packages[0]
    package.packageLib[SHARED_CLASSES] = True
    glyphs = tuple(backend.glyph_info(g.id) for g in tools.glyphs[0])
    monkeypatch.setattr(backend, "glyphs", lambda font_id: glyphs)
    for i, master in enumerate(package.masters):
        for group in tools.data[110, master]:
            group.update(mark=10 + i, __native_mainGlyphName="g" + str(i))
    classes, other_pairs = deepcopy(tools.data), deepcopy(tools.pairs[110, "Bold"])
    del tools.api.set_kerning_class
    del tools.api.delete_kerning_class
    master, bold = font.masters
    font.kerning[master.id] = {glyphs[0].id: {glyphs[1].id: -27}}
    assert tools.pairs[110, "Regular"] == {("g0", "g1"): -27}
    font.kerning[master.id] = {}
    assert tools.pairs[110, "Regular"] == {}
    assert tools.pairs[110, "Bold"] == other_pairs
    assert tools.data == classes
    cached = backend._kerning_snapshots[font.id][1]["classes"][bold.id]
    assert [g.name for g in cached] == [g["name"] for g in classes[110, "Bold"]]
    assert all(not name.endswith("kerning_class") for name, *_ in tools.writes)


def test_shared_class_capability_checks_live_flag_even_without_history_marker(tools):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    glyph.leftKerningGroup = None
    package.packageLib[SHARED_CLASSES] = True
    tools.writes.clear()
    before = deepcopy(tools.data)
    with pytest.raises(UnsupportedCapability, match="metadata"):
        glyph.rightKerningGroup = None
    assert tools.writes == [] and tools.data == before


def test_shared_noop_membership_checks_all_masters_without_mutation(tools):
    tools.packages[0].packageLib[SHARED_CLASSES] = True
    glyph = tools.glyphs[0][-1]
    glyph.leftKerningGroup = None
    glyph.rightKerningGroup = None
    assert tools.writes == []
