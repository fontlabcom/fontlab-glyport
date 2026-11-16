# this_file: tests/test_kerning_group_cache.py
"""Font-wide kerning snapshots through real backend readers and native doubles."""

from collections import Counter
from functools import partial
from types import SimpleNamespace as NS

import pytest
from history_scene import install_font_window

from fontlab_glyport.errors import StaleNativeObject
from fontlab_glyport.model import GSGlyph, Model
from fontlab_glyport.model.fontlab_backend import FontLabBackend


class NativeFont(dict):
    info = NS(familyName="Cache fixture")

    @property
    def glyphs(self):
        raise AssertionError("master/cache reads must not scan font glyphs")


class KerningHistory:
    isValid = True

    def __init__(self, number):
        self.id, self.history, self.fail = number, 0, False

    def currentHistoryState(self):
        if self.fail:
            raise RuntimeError("kerning history read failed")
        return self.history


class Package:
    isValid, upm, axes = True, 1000, ()
    masters = ("Regular", "Bold")

    def __init__(self, number):
        self.id, self.fgId = number, number + 100
        self.history, self.master_reads = 0, 0
        self.active, self.fail_master = "Regular", False
        self.fgPackage, self.glyphsCount = NativeFont(), 48
        self.kerning_histories = {
            name: KerningHistory(number * 1000 + i)
            for i, name in enumerate(self.masters)
        }

    def kerningContainer(self):
        return self.kerning_histories[self.active]

    @property
    def master(self):
        self.master_reads += 1
        if self.fail_master:
            raise RuntimeError("master read failed")
        return self.active

    def setMaster(self, name):
        self.active = name  # native master switches do not advance history

    def currentHistoryState(self):
        return self.history


def classes(prefix):
    members = [f"g{i}" for i in range(47)]
    return [
        {
            "name": prefix + "_first",
            "glyph_names": members,
            "left": True,
            "right": False,
        },
        {
            "name": prefix + "_second",
            "glyph_names": members,
            "left": False,
            "right": True,
        },
        {"name": "later", "glyph_names": ["g0"], "left": True, "right": True},
    ]


@pytest.fixture
def native(monkeypatch):
    packages, calls, notifications = [Package(10), Package(20)], Counter(), []
    backend = FontLabBackend(packages=packages)
    model, fonts, glyphs, data = Model(backend), [], [], {}
    for package in packages:
        fid = backend._font_id(package)
        font = model._font(fid)
        handles = []
        for i in range(package.glyphsCount):
            glyph = NS(id=1000 * package.id + i, name=f"g{i}", isValid=True)
            package.fgPackage[glyph.name] = NS(unicodes=[])
            gid = backend._register((fid, "glyph", glyph.id), glyph, fid)
            handles.append(font._proxy(GSGlyph, gid, partial(backend.glyph_info, gid)))
        fonts.append(font)
        glyphs.append(handles)
        for master in package.masters:
            data[package.fgId, master] = classes(f"{package.id}_{master}")

    def list_classes(font_id):
        package = next(p for p in packages if p.fgId == font_id)
        key = font_id, package.active
        calls[key] += 1
        return {"classes": data[key]}

    def notify(name, items, deep):
        notifications.append((name, items, deep))
        for package in items:
            package.history += 1

    monkeypatch.setattr(
        backend, "_fontpr", lambda: NS(list_kerning_classes=list_classes)
    )
    module = NS(flItems=lambda: NS(notifyChangesApplied=notify), flWorkspace=None)
    install_font_window(monkeypatch, module, packages[0])
    monkeypatch.setattr(backend, "_native", lambda: module)
    return NS(
        backend=backend,
        packages=packages,
        fonts=fonts,
        glyphs=glyphs,
        data=data,
        calls=calls,
        notifications=notifications,
    )


def test_many_glyphs_share_one_fetch_per_font_master_revision_and_side(native):
    for index, (font, package) in enumerate(
        zip(native.fonts, native.packages, strict=True)
    ):
        for master in font.masters:
            native.backend.set_current_master(font.id, master.id)
            package.master_reads = 0
            for _ in range(2):
                for i, glyph in enumerate(native.glyphs[index]):
                    prefix = f"{package.id}_{master.name}"
                    assert glyph.rightKerningGroup == (
                        prefix + "_first" if i < 47 else None
                    )
                    assert glyph.leftKerningGroup == (
                        prefix + "_second" if i < 47 else None
                    )
            assert native.calls[package.fgId, master.name] == 2, (
                "one full class fetch per side, not per glyph"
            )
            assert package.master_reads == 4 * package.glyphsCount, (
                "each lookup checks the actual master without glyph enumeration"
            )


def test_master_switch_without_revision_and_mutation_before_return(native):
    b, font, package = native.backend, native.fonts[0], native.packages[0]
    glyph = native.glyphs[0][0]
    assert glyph.rightKerningGroup == "10_Regular_first"
    revision = b.revision(font.id)
    b.set_current_master(font.id, font.masters[1].id)
    assert b.revision(font.id) == revision, "native master switch has no history change"
    assert glyph.rightKerningGroup == "10_Bold_first"
    native.data[package.fgId, "Regular"] = classes("changed")
    package.history += 1
    b.set_current_master(font.id, font.masters[0].id)
    assert glyph.rightKerningGroup == "changed_first"
    assert native.calls == {(110, "Regular"): 2, (110, "Bold"): 1}


@pytest.mark.parametrize("grouped", [False, True])
def test_notified_edits_and_undo_refresh_shared_snapshot(native, grouped):
    b, package = native.backend, native.packages[0]
    glyph, peer = native.glyphs[0][:2]
    original = native.data[110, "Regular"]
    assert glyph.leftKerningGroup == "10_Regular_second"
    if grouped:
        b.begin_undo("Kerning fixture")
    for number, prefix in enumerate(("edited", "edited_again"), start=2):
        native.data[110, "Regular"] = classes(prefix)
        b._touch(("font", package))
        assert peer.leftKerningGroup == prefix + "_second"
        assert glyph.leftKerningGroup == prefix + "_second"
        assert native.calls[110, "Regular"] == number, (
            "notified edits invalidate once across glyphs"
        )
    if grouped:
        assert not native.notifications, "reads inside a group must not publish Undo"
        b.end_undo()
        assert peer.leftKerningGroup == "edited_again_second"
    previous_calls = sum(native.calls.values())
    native.data[110, "Regular"] = original
    package.history = 0  # native Undo restores an earlier history state
    assert glyph.leftKerningGroup == "10_Regular_second"
    assert peer.leftKerningGroup == "10_Regular_second"
    assert sum(native.calls.values()) == previous_calls + 1, (
        "Undo invalidates once across glyphs"
    )
    assert len(native.notifications) == (1 if grouped else 2)


def test_renamed_and_removed_glyphs_cannot_poison_membership(native):
    b, package = native.backend, native.packages[0]
    glyph, peer = native.glyphs[0][:2]
    assert glyph.rightKerningGroup == "10_Regular_first"
    item = b._object(glyph.id)
    item.name = "renamed"
    package.fgPackage[item.name] = package.fgPackage.pop("g0")
    package.history += 1
    assert glyph.rightKerningGroup is None
    assert peer.rightKerningGroup == "10_Regular_first"
    item.isValid = False
    package.glyphsCount -= 1
    with pytest.raises(StaleNativeObject):
        _ = glyph.rightKerningGroup
    assert peer.rightKerningGroup == "10_Regular_first"
    assert native.calls[110, "Regular"] == 3


@pytest.mark.parametrize("warm", [False, True])
def test_failed_full_class_read_is_retried_without_partial_or_stale_cache(native, warm):
    package, glyph = native.packages[0], native.glyphs[0][0]
    if warm:
        assert glyph.rightKerningGroup == "10_Regular_first"
        package.history += 1
    native.data[110, "Regular"] = classes("partial") + [{"name": "broken"}]
    with pytest.raises(KeyError):
        _ = glyph.rightKerningGroup
    native.data[110, "Regular"] = classes("recovered")
    assert glyph.rightKerningGroup == "recovered_first"
    assert native.glyphs[0][1].rightKerningGroup == "recovered_first"
    assert native.calls[110, "Regular"] == 2 + warm


def test_failed_master_read_preserves_cache_and_retries_actual_master(native):
    package, glyph = native.packages[0], native.glyphs[0][0]
    assert glyph.rightKerningGroup == "10_Regular_first"
    package.active, package.fail_master = "Bold", True
    with pytest.raises(RuntimeError, match="master read failed"):
        _ = glyph.rightKerningGroup
    package.fail_master = False
    assert glyph.rightKerningGroup == "10_Bold_first"
    assert native.calls == {(110, "Regular"): 1, (110, "Bold"): 1}


@pytest.mark.parametrize("both_sides", [False, True])
def test_empty_and_two_sided_classes_keep_shared_none_and_side_semantics(
    native, both_sides
):
    native.data[110, "Regular"] = (
        [{"name": "both", "glyph_names": ["g0", "g1"], "left": True, "right": True}]
        if both_sides
        else []
    )
    expected = "both" if both_sides else None
    for glyph in native.glyphs[0][:2]:
        assert (glyph.rightKerningGroup, glyph.leftKerningGroup) == (expected, expected)
    assert native.calls[110, "Regular"] == 2, (
        "empty maps are cached and the two sides remain separate"
    )


def test_failed_glyph_name_read_does_not_publish_a_class_snapshot(native):
    package, glyph = native.packages[0], native.glyphs[0][0]
    record = package.fgPackage.pop("g0")
    with pytest.raises(KeyError):
        _ = glyph.leftKerningGroup
    assert not native.calls, "resolve the live glyph name before reading membership"
    native.data[110, "Regular"] = classes("recovered")
    package.fgPackage["g0"] = record
    assert glyph.leftKerningGroup == "recovered_second"
    assert native.glyphs[0][1].leftKerningGroup == "recovered_second"
    assert native.calls[110, "Regular"] == 1
