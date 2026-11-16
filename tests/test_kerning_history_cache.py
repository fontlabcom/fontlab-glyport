# this_file: tests/test_kerning_history_cache.py
"""Kerning-container Undo markers differ from package/geometry history."""

from copy import deepcopy
from functools import partial

import pytest

from fontlab_glyport.errors import StaleNativeObject, UnsupportedCapability
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fontlab_backend import FontLabBackend

pytest_plugins = ("test_kerning_group_cache", "test_fontlab_kerning_writes")


def peer_glyph(state, monkeypatch):
    backend = FontLabBackend(packages=state.packages)
    monkeypatch.setattr(backend, "_fontpr", state.backend._fontpr)
    package, original = state.packages[0], state.glyphs[0][1]
    font_id = backend._font_id(package)
    font = Model(backend)._font(font_id)
    native = state.backend._object(original.id)
    token = backend._register((font_id, "glyph", native.id), native, font_id)
    return font._proxy(GSGlyph, token, partial(backend.glyph_info, token))


@pytest.mark.parametrize("attribute", ["leftKerningGroup", "rightKerningGroup"])
def test_retained_and_peer_group_reads_follow_native_undo_redo_with_package_fixed(
    tools, monkeypatch, attribute
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    peer = peer_glyph(tools, monkeypatch)
    original = deepcopy(tools.data)
    before = getattr(glyph, attribute)
    assert getattr(peer, attribute) == before
    setattr(glyph, attribute, None)
    edited = deepcopy(tools.data)
    package.kerningContainer().history = 2
    assert getattr(glyph, attribute) is None and getattr(peer, attribute) is None
    geometry = tools.backend.revision(tools.fonts[0].id)
    tools.data.update(deepcopy(original))
    package.kerningContainer().history = 0
    assert getattr(glyph, attribute) == getattr(peer, attribute) == before
    tools.data.update(edited)
    package.kerningContainer().history = 2
    assert getattr(glyph, attribute) is None and getattr(peer, attribute) is None
    assert tools.backend.revision(tools.fonts[0].id) == geometry, (
        "kerning history must not widen geometry revision"
    )


def test_later_group_write_after_undo_rereads_restored_memberships(tools, monkeypatch):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    original = deepcopy(tools.data)
    glyph.leftKerningGroup = None
    package.kerningContainer().history = 2
    tools.glyphs[0][-1].leftKerningGroup = None  # cache the actual post marker
    tools.data.update(deepcopy(original))
    package.kerningContainer().history = 0
    glyph.leftKerningGroup = None
    for master in package.masters:
        assert "g1" not in tools.data[110, master][1]["glyph_names"], (
            "writer cannot treat restored membership as already removed"
        )
        assert tools.data[110, master][0] == original[110, master][0]


def test_pair_replacement_after_undo_and_redo_rereads_actual_values(tools, monkeypatch):
    backend, package, font = tools.backend, tools.packages[0], tools.fonts[0]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    glyphs = tuple(backend.glyph_info(g.id) for g in tools.glyphs[0])
    monkeypatch.setattr(backend, "glyphs", lambda font_id: glyphs)
    master = font.masters[0].id
    requested = {glyphs[0].id: {glyphs[1].id: -27}}
    font.kerning[master] = requested
    package.kerningContainer().history = 2
    font.kerning[master] = requested  # cache post state
    other = deepcopy(tools.pairs[110, "Bold"])
    for marker, actual, expected in ((0, -10, -27), (2, -27, -10)):
        tools.pairs[110, "Regular"] = {("g0", "g1"): actual}
        package.kerningContainer().history = marker
        font.kerning[master] = {glyphs[0].id: {glyphs[1].id: expected}}
        assert tools.pairs[110, "Regular"] == {("g0", "g1"): expected}
    assert tools.pairs[110, "Bold"] == other


def test_marker_changes_do_not_invalidate_other_font_or_scan_glyphs(tools):
    glyph, other = tools.glyphs[0][1], tools.glyphs[1][1]
    assert glyph.rightKerningGroup == "10_Regular_first"
    assert other.rightKerningGroup == "20_Regular_first"
    reads = tools.reads.copy()
    tools.data[110, "Regular"][0]["glyph_names"] = ["g2"]
    tools.packages[0].kerningContainer().history = 2
    assert glyph.rightKerningGroup is None
    assert other.rightKerningGroup == "20_Regular_first"
    assert tools.reads["classes", 120, "Regular"] == reads["classes", 120, "Regular"]
    assert (
        tools.reads["classes", 110, "Regular"] == reads["classes", 110, "Regular"] + 1
    )


def test_master_switch_and_history_undo_refresh_current_membership(tools):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    for master in ("Regular", "Bold"):
        package.active = master
        assert glyph.rightKerningGroup == f"10_{master}_first"
        tools.data[110, master][0]["glyph_names"] = ["g2"]
        package.kerningContainer().history = 2
        assert glyph.rightKerningGroup is None
    package.active = "Regular"
    tools.data[110, "Regular"][0]["glyph_names"] = ["g1", "g2"]
    package.kerningContainer().history = 0
    assert glyph.rightKerningGroup == "10_Regular_first"
    assert tools.packages[0].history == 0


@pytest.mark.parametrize("warm", [False, True])
def test_failed_history_read_cannot_publish_or_reuse_membership_cache(tools, warm):
    glyph, package = tools.glyphs[0][1], tools.packages[0]
    if warm:
        assert glyph.rightKerningGroup
    history = package.kerningContainer()
    history.history, history.fail = 2, True
    tools.data[110, "Regular"][0]["glyph_names"] = ["g2"]
    with pytest.raises(RuntimeError, match="kerning history read failed"):
        _ = glyph.rightKerningGroup
    history.fail = False
    assert glyph.rightKerningGroup is None


def test_failed_history_read_refuses_writer_before_edits_then_retries(tools):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    glyph.leftKerningGroup = None
    original = deepcopy(tools.data)
    history = package.kerningContainer()
    history.fail = True
    tools.writes.clear()
    with pytest.raises(RuntimeError, match="kerning history read failed"):
        glyph.rightKerningGroup = None
    assert tools.writes == [] and tools.data == original
    history.fail = False
    glyph.rightKerningGroup = None
    assert "g1" not in tools.data[110, "Regular"][0]["glyph_names"]


def test_stale_font_refuses_history_access_and_owned_package_skips_native_getter(
    tools, monkeypatch
):
    backend, package, font = tools.backend, tools.packages[0], tools.fonts[0]
    backend._owned_fonts[package.id] = package.fgPackage
    monkeypatch.setattr(
        type(package),
        "kerningContainer",
        lambda self: (_ for _ in ()).throw(
            AssertionError("unsafe owned history access")
        ),
    )
    backend.kerning_revision(font.id)
    package.isValid = False
    with pytest.raises(StaleNativeObject):
        backend.kerning_revision(font.id)


@pytest.mark.parametrize("missing", ["container", "history"])
def test_missing_class_level_history_api_refuses_warm_cache_and_writes(
    tools, monkeypatch, missing
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    assert glyph.rightKerningGroup
    if missing == "container":
        # An instance-only callable must not stand in for a verified binding.
        getter = package.kerningContainer
        monkeypatch.delattr(type(package), "kerningContainer")
        monkeypatch.setattr(package, "kerningContainer", getter, raising=False)
    else:
        monkeypatch.setattr(
            type(package.kerningContainer()), "currentHistoryState", None
        )
    tools.writes.clear()
    with pytest.raises(UnsupportedCapability, match="Native kerning history"):
        _ = glyph.rightKerningGroup
    with pytest.raises(UnsupportedCapability, match="Native kerning history"):
        glyph.rightKerningGroup = None
    assert tools.writes == []


def test_stale_container_refuses_warm_cache_then_replacement_identity_refreshes(tools):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    assert glyph.rightKerningGroup
    old = package.kerningContainer()
    old.isValid = False
    with pytest.raises(StaleNativeObject, match="kerning history container"):
        _ = glyph.rightKerningGroup
    tools.data[110, "Regular"][0]["glyph_names"] = ["g2"]
    package.kerning_histories["Regular"] = type(old)(old.id + 1)
    assert glyph.rightKerningGroup is None, (
        "replacement at the same history index must refresh"
    )


def test_noncurrent_master_undo_then_switch_back_refreshes_all_master_group_plan(
    tools, monkeypatch
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    original = deepcopy(tools.data)
    glyph.leftKerningGroup = None
    for history in package.kerning_histories.values():
        history.history = 2
    glyph.leftKerningGroup = None  # warm the all-master snapshot in Regular
    package.setMaster("Bold")
    tools.data[110, "Bold"] = deepcopy(original[110, "Bold"])
    package.kerningContainer().history = 0
    package.setMaster("Regular")  # no Glyport access while Bold is selected
    tools.writes.clear()
    glyph.leftKerningGroup = None
    assert "g1" not in tools.data[110, "Bold"][1]["glyph_names"], (
        "restored noncurrent membership must be removed"
    )
    assert tools.writes, "retry must edit the restored Bold group"
    assert package.active == "Regular", (
        "history validation must restore selected master"
    )
    assert tools.data[110, "Regular"][0] == original[110, "Regular"][0]


def test_noncurrent_master_pair_undo_then_switch_back_refreshes_pair_plan(
    tools, monkeypatch
):
    backend, package, font = tools.backend, tools.packages[0], tools.fonts[0]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    glyphs = tuple(backend.glyph_info(g.id) for g in tools.glyphs[0])
    monkeypatch.setattr(backend, "glyphs", lambda font_id: glyphs)
    master = font.masters[1].id
    wanted = {glyphs[0].id: {glyphs[1].id: -27}}
    font.kerning[master] = wanted
    for history in package.kerning_histories.values():
        history.history = 2
    font.kerning[master] = wanted  # current Regular marker remains 2 throughout
    regular = deepcopy(tools.pairs[110, "Regular"])
    package.setMaster("Bold")
    tools.pairs[110, "Bold"] = {("g0", "g1"): -10}
    package.kerningContainer().history = 0
    package.setMaster("Regular")
    tools.writes.clear()
    font.kerning[master] = wanted
    assert tools.pairs[110, "Bold"] == {("g0", "g1"): -27}, (
        "noncurrent pair Undo must invalidate write planning"
    )
    assert tools.writes and tools.pairs[110, "Regular"] == regular
    assert package.active == "Regular"


def test_warm_writer_checks_retained_histories_without_master_switches(
    tools, monkeypatch
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    glyph.leftKerningGroup = None
    reads = tools.reads.copy()
    monkeypatch.setattr(
        package,
        "setMaster",
        lambda name: (_ for _ in ()).throw(
            AssertionError("warm history validation must not switch masters")
        ),
    )
    for other in tools.glyphs[0][2:]:
        other.leftKerningGroup = None
    assert tools.reads == reads, "warm writes must not enumerate classes/pairs again"


@pytest.mark.parametrize("warm", [False, True])
@pytest.mark.parametrize("failure", ["stale", "read"])
def test_noncurrent_history_failure_refuses_writer_and_retry_recaptures(
    tools, warm, failure
):
    backend, package, glyph = tools.backend, tools.packages[0], tools.glyphs[0][1]
    if warm:
        glyph.leftKerningGroup = None
    before = deepcopy(tools.data)
    bold = package.kerning_histories["Bold"]
    if failure == "stale":
        bold.isValid = False
        error = StaleNativeObject
    else:
        bold.fail = True
        error = RuntimeError
    tools.writes.clear()
    with pytest.raises(error):
        glyph.rightKerningGroup = None
    assert tools.data == before and tools.writes == []
    assert package.active == "Regular"
    assert tools.fonts[0].id not in backend._kerning_snapshots
    package.kerning_histories["Bold"] = type(bold)(bold.id + 1)
    glyph.rightKerningGroup = None
    assert "g1" not in tools.data[110, "Bold"][0]["glyph_names"]
    assert package.active == "Regular"


def test_failed_noncurrent_container_capture_restores_master_then_retries(
    tools, monkeypatch
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    getter = type(package).kerningContainer

    def fail_bold(self):
        if self.active == "Bold":
            raise RuntimeError("container setup failed")
        return getter(self)

    monkeypatch.setattr(type(package), "kerningContainer", fail_bold)
    with pytest.raises(RuntimeError, match="container setup failed"):
        glyph.leftKerningGroup = None
    assert package.active == "Regular" and tools.writes == []
    monkeypatch.setattr(type(package), "kerningContainer", getter)
    glyph.leftKerningGroup = None
    assert "g1" not in tools.data[110, "Bold"][1]["glyph_names"]
    assert package.active == "Regular"


def test_writer_rechecks_live_current_identity_before_reusing_retained_handles(
    tools, monkeypatch
):
    package, glyph = tools.packages[0], tools.glyphs[0][1]
    monkeypatch.setattr(package, "currentHistoryState", lambda: 0)
    original = deepcopy(tools.data[110, "Regular"])
    glyph.leftKerningGroup = None
    old = package.kerningContainer()
    package.kerning_histories["Regular"] = type(old)(old.id + 1)
    tools.data[110, "Regular"] = original
    glyph.leftKerningGroup = None
    assert old.isValid, "old live wrapper alone cannot establish current identity"
    assert "g1" not in tools.data[110, "Regular"][1]["glyph_names"]
    assert package.active == "Regular"
